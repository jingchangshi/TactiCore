"""V3.4 阶段 2 前置底座：东财 40 季免费 PIT 财报拉取、9 年 PIT ERP/B/P/EDI 重建与交叉核验。

严格边界：
1. 仅使用免费公开接口（东财 datacenter-web、中债国债收益率曲线）及本地只读快照/RQAlpha bundle；
   严禁依赖 Tushare，严禁写入线上 `/data/ashare.sqlite` 或 `/private/portfolio.sqlite`，
   严禁修改 `~/.rqalpha/bundle_202611_root/`。
2. 所有基本面指标均严格遵守 `ann_date <= T` 零前视原则，按除权送转股本因子（非含现金分红的复权因子）
   将每股指标从报告期末调整至交易日 `T`，滚动分位严格因果（截断至 T 不改变 <= T 的任何历史值）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
import requests
from scipy import stats

CACHE_DIR = Path.home() / ".local/share/ashare-private/v34_pit_cache"
RAW_QUARTER_DIR = CACHE_DIR / "raw_quarters"
FINA_SQLITE_PATH = CACHE_DIR / "fina_40q_pit.sqlite"
MACRO_YIELD_CSV_PATH = CACHE_DIR / "macro_yield_curve_2018_2026.csv"
NOV_YIELD_CACHE_PATH = CACHE_DIR / "chinabond_yields_202611.csv"
NOV_SHAREBONUS_CACHE_PATH = CACHE_DIR / "sharebonus_202611.csv"
DAILY_FUNDAMENTAL_CSV_PATH = CACHE_DIR / "market_fundamental_daily_2018_2026.csv"
VALIDATION_REPORT_PATH = CACHE_DIR / "pit_validation_report.json"

BUNDLE_PATH = Path.home() / ".rqalpha/bundle_202611_root/bundle"
SNAPSHOT_DIR = Path.home() / ".local/share/finance-mcp-ashare/exports/v3_snapshot_20261126"
AUX_DIR = Path.home() / ".local/share/finance-mcp-ashare/exports/v3_aux_20261126"

WARMUP_START_YMD = "20170502"
TURNOVER_WARMUP_YMD = "20170315"
EXP_START_YMD = "20180102"
EXP_END_YMD = "20261126"
BUNDLE_CUTOFF_YMD = "20261030"
VAL_START_YMD = "20240102"
VAL_END_YMD = "20261126"

QUARTERS_40: tuple[str, ...] = tuple(
    f"{y}-{m}"
    for y in range(2016, 2027)
    for m in ("03-31", "06-30", "09-30", "12-31")
    if "2016-12-31" <= f"{y}-{m}" <= "2026-09-30"
)

EASTMONEY_DATA_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
CHINABOND_YIELD_URL = "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery"
HEADERS = {"User-Agent": "Mozilla/5.0"}
A_SHARE_CODE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")


def _normalize_ymd(raw: Any) -> str | None:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("none", "nan", "nat"):
        return None
    digits = re.sub(r"[^0-9]", "", s[:10])
    if len(digits) == 8:
        return digits
    return None


def _float_or_nan(val: Any) -> float:
    if val is None:
        return float("nan")
    try:
        f = float(val)
        return f if np.isfinite(f) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _request_json_with_retry(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    *,
    retries: int = 4,
    timeout: float = 15.0,
) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, params=params, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
            raise ValueError(f"Unexpected non-dict JSON response: {type(payload)}")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < retries:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"HTTP request failed after {retries + 1} attempts: {last_err}")


def _fetch_datacenter_report(
    session: requests.Session,
    report_name: str,
    date_field: str,
    iso_period: str,
    columns: str,
    *,
    page_workers: int = 4,
) -> list[dict[str, Any]]:
    filter_expr = f"({date_field}='{iso_period}')"
    base_params = {
        "reportName": report_name,
        "columns": columns,
        "pageSize": 500,
        "filter": filter_expr,
    }
    first = _request_json_with_retry(session, EASTMONEY_DATA_URL, {**base_params, "pageNumber": 1})
    res = first.get("result") or {}
    data = res.get("data")
    if not isinstance(data, list):
        return []
    total_pages = max(1, int(res.get("pages") or 1))
    all_rows: list[dict[str, Any]] = list(data)
    if total_pages == 1:
        return all_rows

    def _fetch_page(pn: int) -> list[dict[str, Any]]:
        j = _request_json_with_retry(session, EASTMONEY_DATA_URL, {**base_params, "pageNumber": pn})
        rows = (j.get("result") or {}).get("data")
        return rows if isinstance(rows, list) else []

    with ThreadPoolExecutor(max_workers=page_workers) as pool:
        futures = {pool.submit(_fetch_page, pn): pn for pn in range(2, total_pages + 1)}
        page_results: dict[int, list[dict[str, Any]]] = {}
        for fut in as_completed(futures):
            pn = futures[fut]
            page_results[pn] = fut.result()
    for pn in range(2, total_pages + 1):
        all_rows.extend(page_results[pn])
    return all_rows


def _fetch_single_quarter(iso_period: str, *, force_refresh: bool = False) -> pd.DataFrame:
    RAW_QUARTER_DIR.mkdir(parents=True, exist_ok=True)
    q_ymd = iso_period.replace("-", "")
    cache_file = RAW_QUARTER_DIR / f"quarter_{q_ymd}.csv.gz"
    if cache_file.is_file() and not force_refresh and cache_file.stat().st_size > 100:
        return pd.read_csv(
            cache_file,
            dtype={"ts_code": str, "end_date": str, "ann_date": str, "update_date": str},
        )

    session = requests.Session()
    try:
        cpd_rows = _fetch_datacenter_report(
            session,
            "RPT_LICO_FN_CPD",
            "REPORTDATE",
            iso_period,
            "SECUCODE,NOTICE_DATE,UPDATE_DATE,REPORTDATE,BASIC_EPS,DEDUCT_BASIC_EPS,"
            "BPS,WEIGHTAVG_ROE,YSTZ,SJLTZ,MGJYXJJE,XSMLL,PARENT_NETPROFIT,"
            "TOTAL_OPERATE_INCOME,ISNEW",
        )
        bal_rows = _fetch_datacenter_report(
            session,
            "RPT_DMSK_FN_BALANCE",
            "REPORT_DATE",
            iso_period,
            "SECUCODE,DEBT_ASSET_RATIO,TOTAL_EQUITY",
        )
        cf_rows = _fetch_datacenter_report(
            session,
            "RPT_DMSK_FN_CASHFLOW",
            "REPORT_DATE",
            iso_period,
            "SECUCODE,NETCASH_OPERATE",
        )
    finally:
        session.close()

    debt_map: dict[str, tuple[float, float]] = {}
    for r in bal_rows:
        code = str(r.get("SECUCODE") or "").strip().upper()
        if not A_SHARE_CODE_RE.match(code):
            continue
        debt_map[code] = (
            _float_or_nan(r.get("DEBT_ASSET_RATIO")),
            _float_or_nan(r.get("TOTAL_EQUITY")),
        )

    ocf_map: dict[str, float] = {}
    for r in cf_rows:
        code = str(r.get("SECUCODE") or "").strip().upper()
        if not A_SHARE_CODE_RE.match(code):
            continue
        ocf_map[code] = _float_or_nan(r.get("NETCASH_OPERATE"))

    records: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    # 排序保证同代码重复时优先取 ISNEW='1' 且较早有效公告日
    cpd_rows.sort(
        key=lambda x: (
            str(x.get("SECUCODE") or ""),
            0 if str(x.get("ISNEW") or "") == "1" else 1,
            _normalize_ymd(x.get("NOTICE_DATE")) or "99999999",
        )
    )
    for r in cpd_rows:
        code = str(r.get("SECUCODE") or "").strip().upper()
        if not A_SHARE_CODE_RE.match(code) or code in seen_codes:
            continue
        ann_date = _normalize_ymd(r.get("NOTICE_DATE"))
        if not ann_date:
            continue
        end_date = _normalize_ymd(r.get("REPORTDATE")) or q_ymd
        upd_date = _normalize_ymd(r.get("UPDATE_DATE")) or ""
        seen_codes.add(code)
        debt_ratio, tot_eq = debt_map.get(code, (float("nan"), float("nan")))
        ocf = ocf_map.get(code, float("nan"))
        roe = _float_or_nan(r.get("WEIGHTAVG_ROE"))
        np_yoy = _float_or_nan(r.get("SJLTZ"))
        parent_np = _float_or_nan(r.get("PARENT_NETPROFIT"))
        ocf_to_profit = float("nan")
        if np.isfinite(ocf) and np.isfinite(parent_np) and abs(parent_np) > 1e-6:
            if parent_np > 0:
                ocf_to_profit = round((ocf / parent_np) * 100.0, 4)
            else:
                ocf_to_profit = round(-abs(ocf / parent_np) * 100.0, 4) if ocf < 0 else 0.0

        records.append(
            {
                "ts_code": code,
                "end_date": end_date,
                "ann_date": ann_date,
                "update_date": upd_date,
                "basic_eps": _float_or_nan(r.get("BASIC_EPS")),
                "deduct_basic_eps": _float_or_nan(r.get("DEDUCT_BASIC_EPS")),
                "bps": _float_or_nan(r.get("BPS")),
                "roe": roe,
                "roe_dt": roe,
                "netprofit_yoy": np_yoy,
                "dt_netprofit_yoy": np_yoy,
                "or_yoy": _float_or_nan(r.get("YSTZ")),
                "grossprofit_margin": _float_or_nan(r.get("XSMLL")),
                "debt_to_assets": debt_ratio,
                "ocf": ocf,
                "ocfps": _float_or_nan(r.get("MGJYXJJE")),
                "ocf_to_profit": ocf_to_profit,
                "parent_netprofit": parent_np,
                "total_operate_income": _float_or_nan(r.get("TOTAL_OPERATE_INCOME")),
                "total_equity": tot_eq,
            }
        )

    df = pd.DataFrame(records)
    tmp_path = RAW_QUARTER_DIR / f".tmp_quarter_{q_ymd}.csv.gz"
    df.to_csv(tmp_path, index=False, compression="gzip")
    os.replace(tmp_path, cache_file)
    return df


def fetch_eastmoney_40q(
    quarters: tuple[str, ...] = QUARTERS_40,
    *,
    force_refresh: bool = False,
    quarter_workers: int = 3,
) -> pd.DataFrame:
    """断点续传拉取 40 季全市场 A 股 PIT 财报指标并写入独立 SQLite 缓存。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RAW_QUARTER_DIR.mkdir(parents=True, exist_ok=True)

    dfs: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=quarter_workers) as pool:
        futures = {
            pool.submit(_fetch_single_quarter, q, force_refresh=force_refresh): q for q in quarters
        }
        q_map: dict[str, pd.DataFrame] = {}
        for fut in as_completed(futures):
            q = futures[fut]
            q_map[q] = fut.result()
    for q in quarters:
        if not q_map[q].empty:
            dfs.append(q_map[q])

    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.sort_values(["ts_code", "end_date", "ann_date"]).drop_duplicates(
        subset=["ts_code", "end_date"], keep="first"
    )

    tmp_db = CACHE_DIR / ".tmp_fina_40q_pit.sqlite"
    if tmp_db.exists():
        tmp_db.unlink()
    conn = sqlite3.connect(tmp_db)
    try:
        combined.to_sql("fina_pit", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX idx_fina_code_ann_end ON fina_pit (ts_code, ann_date, end_date)")
        conn.execute("CREATE INDEX idx_fina_end_date ON fina_pit (end_date)")
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp_db, FINA_SQLITE_PATH)
    return combined


def fetch_nov2026_yields(*, force_refresh: bool = False) -> pd.DataFrame:
    """拉取 2026-10-28..2026-11-26 中债国债收益率曲线（含 1Y / 10Y）。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if NOV_YIELD_CACHE_PATH.is_file() and not force_refresh:
        cached = pd.read_csv(NOV_YIELD_CACHE_PATH, dtype={"trade_date": str})
        if not cached.empty and str(cached["trade_date"].max()) >= EXP_END_YMD:
            return cached

    resp = requests.get(
        CHINABOND_YIELD_URL,
        params={
            "startDate": "2026-10-28",
            "endDate": "2026-11-26",
            "gjqx": "0",
            "qxId": "ycqx",
            "locale": "cn_ZH",
        },
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    if len(tables) < 2:
        raise RuntimeError("Unexpected ChinaBond HTML table structure")
    df_raw = tables[1].copy()
    df_raw.columns = df_raw.iloc[0]
    df_raw = df_raw.iloc[1:].copy()
    gz = df_raw[df_raw["曲线名称"] == "中债国债收益率曲线"].copy()
    gz["trade_date"] = gz["日期"].astype(str).str.replace("-", "", regex=False)
    gz["cgb_1y_pct"] = pd.to_numeric(gz["1年"], errors="coerce")
    gz["cgb_10y_pct"] = pd.to_numeric(gz["10年"], errors="coerce")
    out = (
        gz[["trade_date", "cgb_1y_pct", "cgb_10y_pct"]]
        .dropna(subset=["trade_date", "cgb_1y_pct", "cgb_10y_pct"])
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    tmp = CACHE_DIR / ".tmp_chinabond_yields.csv"
    out.to_csv(tmp, index=False)
    os.replace(tmp, NOV_YIELD_CACHE_PATH)
    return out


def build_macro_yield_curve(*, force_refresh: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    """拼接 RQAlpha yield_curve.h5 (2018..2026-10-30) 与中债 2026-11 尾部，输出 CSV。"""
    with h5py.File(BUNDLE_PATH / "yield_curve.h5", "r") as f:
        arr = f["data"][:]
    yc = pd.DataFrame(
        {
            "trade_date": pd.Series(arr["date"]).astype(str),
            "cgb_1y_pct": arr["1Y"].astype(np.float64) * 100.0,
            "cgb_10y_pct": arr["10Y"].astype(np.float64) * 100.0,
        }
    )
    yc = yc[(yc["trade_date"] >= TURNOVER_WARMUP_YMD) & (yc["trade_date"] <= BUNDLE_CUTOFF_YMD)]
    yc["source"] = "rqalpha_yield_curve_h5"

    nov = fetch_nov2026_yields(force_refresh=force_refresh)
    nov["source"] = "chinabond_free"

    # 重叠窗核验 (2026-10-28..2026-10-30)
    ov = yc.merge(nov, on="trade_date", suffixes=("_h5", "_cb"))
    overlap_audit = {
        "overlap_days": int(len(ov)),
        "max_abs_1y_diff_bps": float(
            ((ov["cgb_1y_pct_h5"] - ov["cgb_1y_pct_cb"]).abs() * 100.0).max()
        )
        if len(ov)
        else float("nan"),
        "max_abs_10y_diff_bps": float(
            ((ov["cgb_10y_pct_h5"] - ov["cgb_10y_pct_cb"]).abs() * 100.0).max()
        )
        if len(ov)
        else float("nan"),
    }

    tail = nov[nov["trade_date"] > BUNDLE_CUTOFF_YMD].copy()
    stitched = pd.concat([yc, tail], ignore_index=True).sort_values("trade_date")

    cal = _load_unified_calendar(start_ymd=EXP_START_YMD, end_ymd=EXP_END_YMD)
    stitched_2018 = (
        stitched.set_index("trade_date")
        .reindex(cal)
        .ffill()
        .reset_index()
        .rename(columns={"index": "trade_date"})
    )
    stitched_2018["cgb_1y_bps"] = (stitched_2018["cgb_1y_pct"] * 100.0).round(4)
    stitched_2018["cgb_10y_bps"] = (stitched_2018["cgb_10y_pct"] * 100.0).round(4)
    stitched_2018["term_spread_10y_1y_bps"] = (
        stitched_2018["cgb_10y_bps"] - stitched_2018["cgb_1y_bps"]
    ).round(4)

    tmp = CACHE_DIR / ".tmp_macro_yield.csv"
    stitched_2018.to_csv(tmp, index=False)
    os.replace(tmp, MACRO_YIELD_CSV_PATH)
    return stitched_2018, overlap_audit


def fetch_nov2026_sharebonus(*, force_refresh: bool = False) -> pd.DataFrame:
    """拉取 2026-10-31..2026-11-26 分红送转明细，无缝扩展 dividends/split_factor 至 11-26。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if NOV_SHAREBONUS_CACHE_PATH.is_file() and not force_refresh:
        return pd.read_csv(NOV_SHAREBONUS_CACHE_PATH, dtype={"ts_code": str, "ex_date": str})
    session = requests.Session()
    try:
        j = _request_json_with_retry(
            session,
            EASTMONEY_DATA_URL,
            {
                "reportName": "RPT_SHAREBONUS_DET",
                "columns": "SECUCODE,EX_DIVIDEND_DATE,BONUS_IT_RATIO,BONUS_RATIO,IT_RATIO,"
                "PRETAX_BONUS_RMB",
                "pageSize": 500,
                "pageNumber": 1,
                "filter": "(EX_DIVIDEND_DATE>='2026-10-31')(EX_DIVIDEND_DATE<='2026-11-26')",
            },
        )
    finally:
        session.close()
    rows = (j.get("result") or {}).get("data") or []
    recs: list[dict[str, Any]] = []
    for r in rows:
        code = str(r.get("SECUCODE") or "").strip().upper()
        ex_date = _normalize_ymd(r.get("EX_DIVIDEND_DATE"))
        if not A_SHARE_CODE_RE.match(code) or not ex_date:
            continue
        bonus_it = _float_or_nan(r.get("BONUS_IT_RATIO"))
        cash_per10 = _float_or_nan(r.get("PRETAX_BONUS_RMB"))
        split_ratio = 1.0 + (bonus_it / 10.0 if np.isfinite(bonus_it) and bonus_it > 0 else 0.0)
        cash_per_share = cash_per10 / 10.0 if np.isfinite(cash_per10) and cash_per10 > 0 else 0.0
        recs.append(
            {
                "ts_code": code,
                "ex_date": ex_date,
                "split_factor": split_ratio,
                "cash_per_share": cash_per_share,
            }
        )
    df = pd.DataFrame(recs)
    tmp = CACHE_DIR / ".tmp_sharebonus_202611.csv"
    df.to_csv(tmp, index=False)
    os.replace(tmp, NOV_SHAREBONUS_CACHE_PATH)
    return df


def _load_unified_calendar(*, start_ymd: str, end_ymd: str) -> list[str]:
    td = np.load(BUNDLE_PATH / "trading_dates.npy")
    hist = [str(int(d)) for d in td if start_ymd <= str(int(d)) <= BUNDLE_CUTOFF_YMD]
    if end_ymd <= BUNDLE_CUTOFF_YMD:
        return [d for d in hist if d <= end_ymd]
    tc = pd.read_csv(SNAPSHOT_DIR / "trade_calendar.csv", dtype=str)
    tail = sorted(
        tc.loc[
            (tc["is_open"] == "1")
            & (tc["cal_date"] > BUNDLE_CUTOFF_YMD)
            & (tc["cal_date"] <= end_ymd),
            "cal_date",
        ].unique()
    )
    return sorted(set(hist) | set(tail))


def _rq_to_ts(rq_code: str) -> str:
    code, exch = rq_code.split(".")
    return f"{code}.{'SZ' if exch == 'XSHE' else 'SH'}"


def _ts_to_rq(ts_code: str) -> str:
    code, exch = ts_code.split(".")
    return f"{code}.{'XSHE' if exch == 'SZ' else 'XSHG'}"


def compute_pit_ttm_eps(
    reports: list[dict[str, Any]],
    *,
    use_netprofit_shares: bool = False,
    split_events: list[tuple[int, float]] | None = None,
    trade_date_int: int = 99999999,
) -> tuple[float, float]:
    """根据已公告财报列表（调用方已保证 ann_date <= T）计算 PIT TTM EPS 与最新 BPS（已含送转调整）。

    Returns:
        (eps_ttm_adj, bps_adj) —— 若缺失则返回 nan。
    """
    if not reports:
        return float("nan"), float("nan")

    # 按报告期降序、同报告期按公告日降序取最新一期
    by_end: dict[str, dict[str, Any]] = {}
    for r in reports:
        ed = str(r["end_date"])
        prev = by_end.get(ed)
        if prev is None or str(r["ann_date"]) > str(prev["ann_date"]):
            by_end[ed] = r

    sorted_ends = sorted(by_end.keys(), reverse=True)
    latest = by_end[sorted_ends[0]]
    latest_ed = str(latest["end_date"])
    latest_ed_int = int(latest_ed)
    year = int(latest_ed[:4])
    mmdd = latest_ed[4:]

    # 1) BPS 调整至 T：RPT_LICO_FN_CPD 的 BPS 保持在报告期末股本口径，
    # 只需按 (end_date, T] 的送转拆分调整
    bps_raw = _float_or_nan(latest.get("bps"))
    split_mult_to_t = _cum_split_ratio(split_events or [], latest_ed_int, trade_date_int)
    bps_adj = (
        bps_raw / split_mult_to_t if np.isfinite(bps_raw) and split_mult_to_t > 0 else float("nan")
    )

    # 2) EPS_TTM 计算
    def _ttm_value(field: str) -> float:
        curr_val = _float_or_nan(latest.get(field))
        if not np.isfinite(curr_val):
            return float("nan")
        if mmdd == "1231":
            return curr_val
        prev_ann_ed = f"{year - 1}1231"
        prev_same_ed = f"{year - 1}{mmdd}"
        prev_ann = by_end.get(prev_ann_ed)
        prev_same = by_end.get(prev_same_ed)
        if prev_ann is not None and prev_same is not None:
            pa = _float_or_nan(prev_ann.get(field))
            ps = _float_or_nan(prev_same.get(field))
            if np.isfinite(pa) and np.isfinite(ps):
                return curr_val + pa - ps
        # 安全回退：缺上期同季时退回上年年报；仍缺则按季度年化
        if prev_ann is not None:
            pa = _float_or_nan(prev_ann.get(field))
            if np.isfinite(pa):
                return pa
        q_idx = {"0331": 1, "0630": 2, "0930": 3}.get(mmdd, 4)
        return curr_val * (4.0 / q_idx)

    if use_netprofit_shares:
        np_ttm = _ttm_value("parent_netprofit")
        latest_np = _float_or_nan(latest.get("parent_netprofit"))
        latest_eps = _float_or_nan(latest.get("basic_eps"))
        if (
            np.isfinite(np_ttm)
            and np.isfinite(latest_np)
            and np.isfinite(latest_eps)
            and abs(latest_eps) > 1e-8
        ):
            implied_shares = latest_np / latest_eps
            if implied_shares > 0:
                eps_ttm_adj = (np_ttm / implied_shares) / split_mult_to_t
                return eps_ttm_adj, bps_adj

    eps_ttm_raw = _ttm_value("basic_eps")
    eps_ttm_adj = (
        eps_ttm_raw / split_mult_to_t
        if np.isfinite(eps_ttm_raw) and split_mult_to_t > 0
        else float("nan")
    )
    return eps_ttm_adj, bps_adj


def _cum_split_ratio(
    split_events: list[tuple[int, float]],
    from_date_exclusive: int,
    to_date_inclusive: int,
) -> float:
    """计算区间 (from_date_exclusive, to_date_inclusive] 的纯送转拆股累计倍数。"""
    ratio = 1.0
    for ex_d, fac in split_events:
        if from_date_exclusive < ex_d <= to_date_inclusive and fac > 0:
            ratio *= fac
    return ratio


def causal_rolling_percentile(
    series: np.ndarray, window: int = 756, min_periods: int = 60
) -> np.ndarray:
    """严格因果滚动经验分位 [0, 1]：t 时刻只使用 <= t 的窗口观测，截断未来不改变历史值。"""
    n = len(series)
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        val = series[i]
        if not np.isfinite(val):
            continue
        lo = max(0, i - window + 1)
        win = series[lo : i + 1]
        valid = win[np.isfinite(win)]
        if len(valid) < min_periods:
            continue
        out[i] = float(np.mean(valid <= val))
    return out


def _load_split_and_dividend_events(
    nov_sb: pd.DataFrame,
) -> tuple[dict[str, list[tuple[int, float]]], dict[str, list[tuple[int, float]]]]:
    """读取 RQAlpha split_factor.h5 与 dividends.h5 并无缝追加 2026-11 送转/派现事件。"""
    splits: dict[str, list[tuple[int, float]]] = {}
    with h5py.File(BUNDLE_PATH / "split_factor.h5", "r") as f:
        for rq_code in f.keys():
            if rq_code.endswith(".BJ"):
                continue
            ts_code = _rq_to_ts(rq_code)
            arr = f[rq_code][:]
            ev = [
                (int(r["ex_date"] // 1000000), float(r["split_factor"]))
                for r in arr
                if float(r["split_factor"]) > 0
            ]
            if ev:
                splits[ts_code] = ev

    divs: dict[str, list[tuple[int, float]]] = {}
    with h5py.File(BUNDLE_PATH / "dividends.h5", "r") as f:
        for rq_code in f.keys():
            if rq_code.endswith(".BJ"):
                continue
            ts_code = _rq_to_ts(rq_code)
            arr = f[rq_code][:]
            ev = []
            for r in arr:
                ex_d = int(r["ex_dividend_date"])
                cash = float(r["dividend_cash_before_tax"])
                lot = float(r["round_lot"]) if float(r["round_lot"]) > 0 else 10.0
                if ex_d > 0 and cash > 0:
                    ev.append((ex_d, cash / lot))
            if ev:
                divs[ts_code] = ev

    if not nov_sb.empty:
        for row in nov_sb.itertuples(index=False):
            ts_code = str(row.ts_code)
            if ts_code.endswith(".BJ"):
                continue
            ex_d = int(row.ex_date)
            if float(row.split_factor) > 1.0 + 1e-6:
                splits.setdefault(ts_code, []).append((ex_d, float(row.split_factor)))
            if float(row.cash_per_share) > 0:
                divs.setdefault(ts_code, []).append((ex_d, float(row.cash_per_share)))

    for k in splits:
        splits[k].sort(key=lambda x: x[0])
    for k in divs:
        divs[k].sort(key=lambda x: x[0])
    return splits, divs


def _compute_stock_daily_matrices(
    cal: list[str],
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray]:
    """构建 2017-03-15..2026-11-26 非北交 A 股致密矩阵: close, amount_yuan, active_mask。"""
    cal_ints = np.array([int(d) for d in cal], dtype=np.int64)
    n_days = len(cal_ints)
    start_int = int(cal_ints[0])
    cutoff_int = int(BUNDLE_CUTOFF_YMD)

    # 读取 2026-11 快照尾部与股票全集
    sb = pd.read_csv(SNAPSHOT_DIR / "stock_basic.csv", usecols=["ts_code"], dtype=str)
    snap_codes = set(sb.loc[~sb["ts_code"].str.endswith(".BJ"), "ts_code"])

    with h5py.File(BUNDLE_PATH / "stocks.h5", "r") as f:
        h5_keys = [k for k in f.keys() if not k.endswith(".BJ")]
    h5_ts = {_rq_to_ts(k) for k in h5_keys}
    all_codes = sorted(h5_ts | snap_codes)
    code_to_idx = {c: i for i, c in enumerate(all_codes)}
    n_stocks = len(all_codes)

    close_mat = np.full((n_days, n_stocks), np.nan, dtype=np.float64)
    amt_mat = np.full((n_days, n_stocks), np.nan, dtype=np.float64)
    active_mat = np.zeros((n_days, n_stocks), dtype=bool)

    # 1. RQAlpha stocks.h5 (<= 2026-10-30) & suspended_days.h5
    susp_map: dict[str, set[int]] = {}
    with h5py.File(BUNDLE_PATH / "suspended_days.h5", "r") as fsusp:
        for k in fsusp.keys():
            susp_map[k] = set(int(x) for x in fsusp[k][:])

    with h5py.File(BUNDLE_PATH / "stocks.h5", "r") as f:
        for rq_code in h5_keys:
            ts_code = _rq_to_ts(rq_code)
            s_idx = code_to_idx[ts_code]
            arr = f[rq_code][:]
            dts = (arr["datetime"] // 1000000).astype(np.int64)
            mask = (dts >= start_int) & (dts <= cutoff_int)
            if not mask.any():
                continue
            dts_m = dts[mask]
            pos = np.searchsorted(cal_ints, dts_m)
            valid_p = (pos < n_days) & (cal_ints[np.minimum(pos, n_days - 1)] == dts_m)
            if not valid_p.any():
                continue
            pos = pos[valid_p]
            cls_v = arr["close"][mask][valid_p].astype(np.float64)
            vol_v = arr["volume"][mask][valid_p].astype(np.float64)
            amt_v = arr["total_turnover"][mask][valid_p].astype(np.float64)
            susp_set = susp_map.get(rq_code, set())
            is_act = (
                np.isfinite(cls_v)
                & (cls_v > 0)
                & np.isfinite(vol_v)
                & (vol_v > 0)
                & np.isfinite(amt_v)
                & (amt_v > 0)
            )
            if susp_set:
                for k_i, d_val in enumerate(dts_m[valid_p]):
                    if int(d_val) in susp_set:
                        is_act[k_i] = False
            close_mat[pos, s_idx] = cls_v
            amt_mat[pos, s_idx] = amt_v
            active_mat[pos, s_idx] = is_act

    # 2. 2026-11 快照尾部 (> 2026-10-30)
    bars = pd.read_csv(
        SNAPSHOT_DIR / "daily_bars.csv",
        usecols=["ts_code", "trade_date", "close", "vol", "amount"],
        dtype={"ts_code": str, "trade_date": str, "close": float, "vol": float, "amount": float},
    )
    bars = bars[(bars["trade_date"] > BUNDLE_CUTOFF_YMD) & (~bars["ts_code"].str.endswith(".BJ"))]
    susp_df = pd.read_csv(SNAPSHOT_DIR / "suspend.csv", dtype=str)
    susp_pairs = set(zip(susp_df["ts_code"], susp_df["trade_date"], strict=False))
    date_to_pos = {d: i for i, d in enumerate(cal)}
    for row in bars.itertuples(index=False):
        s_idx = code_to_idx.get(row.ts_code)
        d_idx = date_to_pos.get(row.trade_date)
        if s_idx is None or d_idx is None:
            continue
        cls_v = float(row.close)
        vol_v = float(row.vol)
        amt_v = float(row.amount) * 1000.0  # 千元 -> 元
        is_susp = (row.ts_code, row.trade_date) in susp_pairs
        close_mat[d_idx, s_idx] = cls_v
        amt_mat[d_idx, s_idx] = amt_v
        active_mat[d_idx, s_idx] = (
            (not is_susp)
            and np.isfinite(cls_v)
            and cls_v > 0
            and np.isfinite(vol_v)
            and vol_v > 0
            and np.isfinite(amt_v)
            and amt_v > 0
        )

    return all_codes, close_mat, amt_mat, active_mat


def _build_cumulative_split_matrix(
    cal_ints: np.ndarray,
    all_codes: list[str],
    splits: dict[str, list[tuple[int, float]]],
) -> np.ndarray:
    """返回每个 (day, stock) 截至 day 的累计送转拆股倍数矩阵（>= 1.0）。"""
    n_days = len(cal_ints)
    n_stocks = len(all_codes)
    mat = np.ones((n_days, n_stocks), dtype=np.float64)
    for s_idx, code in enumerate(all_codes):
        evs = splits.get(code)
        if not evs:
            continue
        cum = 1.0
        for ex_d, fac in evs:
            pos = int(np.searchsorted(cal_ints, ex_d, side="left"))
            if pos < n_days:
                mat[pos:, s_idx] *= fac
            cum *= fac
    return mat


def _build_pit_dividend_matrix(
    cal: list[str],
    cal_ints: np.ndarray,
    all_codes: list[str],
    divs: dict[str, list[tuple[int, float]]],
    splits: dict[str, list[tuple[int, float]]],
    cum_split_mat: np.ndarray,
    close_mat: np.ndarray,
) -> np.ndarray:
    """计算严格 PIT 滚动 365 自然日实发股息率矩阵 (小数, e.g. 0.03 = 3%)。"""
    n_days = len(cal_ints)
    n_stocks = len(all_codes)
    # 先把每个分红事件在发生日 d_pos 转化为 pre-split 等价现金分红 * cum_split_before_ex
    cal_dt = [dt.datetime.strptime(d, "%Y%m%d").date() for d in cal]
    cal_ord = np.array([d.toordinal() for d in cal_dt], dtype=np.int64)
    dv_mat = np.full((n_days, n_stocks), np.nan, dtype=np.float64)

    for s_idx, code in enumerate(all_codes):
        d_evs = divs.get(code)
        if not d_evs:
            continue
        s_evs = splits.get(code, [])
        # 对每次分红计算 (ex_d - 1) 时的累计送转因子，
        # 从而按 cash_per_share * cum_split(ex_d - 1) / cum_split(T) 稀释
        ev_ords: list[int] = []
        ev_scaled_cash: list[float] = []
        for ex_d, cash in d_evs:
            y, m, dd = ex_d // 10000, (ex_d // 100) % 100, ex_d % 100
            try:
                ex_ord = dt.date(y, m, dd).toordinal()
            except ValueError:
                continue
            cum_before = 1.0
            for sp_d, fac in s_evs:
                if sp_d < ex_d and fac > 0:
                    cum_before *= fac
            ev_ords.append(ex_ord)
            ev_scaled_cash.append(cash * cum_before)

        if not ev_ords:
            continue
        ev_ords_arr = np.array(ev_ords, dtype=np.int64)
        ev_cash_arr = np.array(ev_scaled_cash, dtype=np.float64)
        for d_idx in range(n_days):
            t_ord = cal_ord[d_idx]
            lo_ord = t_ord - 365
            # 严格 PIT: ex_date <= T 且 > T - 365d
            in_win = (ev_ords_arr > lo_ord) & (ev_ords_arr <= t_ord)
            if not in_win.any():
                continue
            c_t = close_mat[d_idx, s_idx]
            if not np.isfinite(c_t) or c_t <= 0:
                continue
            total_cash_t = float(ev_cash_arr[in_win].sum()) / cum_split_mat[d_idx, s_idx]
            if total_cash_t > 0:
                dv_mat[d_idx, s_idx] = total_cash_t / c_t
    return dv_mat


def _build_pit_fundamental_matrices(
    fina_df: pd.DataFrame,
    cal: list[str],
    cal_ints: np.ndarray,
    all_codes: list[str],
    splits: dict[str, list[tuple[int, float]]],
    cum_split_mat: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """将 40 季 PIT 财报按 ann_date <= T 严格前向投影到每日矩阵:

    Returns:
        eps_ttm_adj_direct, eps_ttm_adj_np_shares, bps_adj, edi_improved (bool/nan float)
    """
    n_days = len(cal_ints)
    n_stocks = len(all_codes)
    eps_direct_mat = np.full((n_days, n_stocks), np.nan, dtype=np.float64)
    eps_np_mat = np.full((n_days, n_stocks), np.nan, dtype=np.float64)
    bps_mat = np.full((n_days, n_stocks), np.nan, dtype=np.float64)
    edi_mat = np.full((n_days, n_stocks), np.nan, dtype=np.float64)

    code_to_idx = {c: i for i, c in enumerate(all_codes)}
    # 只处理 universe 内股票
    sub = fina_df[fina_df["ts_code"].isin(code_to_idx)].copy()
    sub["ann_int"] = sub["ann_date"].astype(np.int64)
    sub["end_int"] = sub["end_date"].astype(np.int64)
    sub = sub.sort_values(["ts_code", "ann_int", "end_int"])

    for ts_code, grp in sub.groupby("ts_code", sort=False):
        s_idx = code_to_idx[str(ts_code)]
        s_evs = splits.get(str(ts_code), [])
        rows = grp.to_dict("records")
        # 按公告日分事件块推进，只更新发生新公告后的区间 [start_pos, next_pos)
        ann_events: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            ann_events.setdefault(int(r["ann_int"]), []).append(r)

        sorted_anns = sorted(ann_events.keys())
        seen_reports: list[dict[str, Any]] = []
        for idx_a, ann_d in enumerate(sorted_anns):
            seen_reports.extend(ann_events[ann_d])
            start_pos = int(np.searchsorted(cal_ints, ann_d, side="left"))
            if start_pos >= n_days:
                continue
            if idx_a + 1 < len(sorted_anns):
                end_pos = int(np.searchsorted(cal_ints, sorted_anns[idx_a + 1], side="left"))
            else:
                end_pos = n_days
            if end_pos <= start_pos:
                continue

            # 取截至当前 ann_d 的最新报告期字典
            by_end: dict[str, dict[str, Any]] = {}
            for rr in seen_reports:
                ed = str(rr["end_date"])
                prev = by_end.get(ed)
                if prev is None or str(rr["ann_date"]) > str(prev["ann_date"]):
                    by_end[ed] = rr
            sorted_eds = sorted(by_end.keys(), reverse=True)
            latest = by_end[sorted_eds[0]]
            latest_ed = str(latest["end_date"])
            latest_ed_int = int(latest_ed)
            year = int(latest_ed[:4])
            mmdd = latest_ed[4:]

            # 基期（未除权至 T 前）TTM 计算
            def _calc_ttm(
                field: str, _latest=latest, _by_end=by_end, _year=year, _mmdd=mmdd
            ) -> float:
                cv = _float_or_nan(_latest.get(field))
                if not np.isfinite(cv):
                    return float("nan")
                if _mmdd == "1231":
                    return cv
                pa_r = _by_end.get(f"{_year - 1}1231")
                ps_r = _by_end.get(f"{_year - 1}{_mmdd}")
                if pa_r is not None and ps_r is not None:
                    pa = _float_or_nan(pa_r.get(field))
                    ps = _float_or_nan(ps_r.get(field))
                    if np.isfinite(pa) and np.isfinite(ps):
                        return cv + pa - ps
                if pa_r is not None:
                    pa = _float_or_nan(pa_r.get(field))
                    if np.isfinite(pa):
                        return pa
                q_idx = {"0331": 1, "0630": 2, "0930": 3}.get(_mmdd, 4)
                return cv * (4.0 / q_idx)

            bps_raw = _float_or_nan(latest.get("bps"))
            eps_ttm_raw = _calc_ttm("basic_eps")
            np_ttm = _calc_ttm("parent_netprofit")
            latest_np = _float_or_nan(latest.get("parent_netprofit"))
            latest_eps = _float_or_nan(latest.get("basic_eps"))

            # 注意：对于 RPT_LICO_FN_CPD，若 end_date 到 1 年后之间发生送转，
            # 东财可能已把去年同期的 comparative BASIC_EPS 重述。
            # 这里同时记录两种口径供 2024-2026 交叉核验：
            #   (1) direct: 直接以 latest.end_date 作为基准股本点除权至 T
            #   (2) np_share: 以 PARENT_NETPROFIT_TTM / (latest_np / latest_eps)
            #       作为最新单期 EPS 股本口径除权至 T
            cum_at_end = 1.0
            for sp_d, fac in s_evs:
                if sp_d <= latest_ed_int and fac > 0:
                    cum_at_end *= fac

            split_slice = cum_split_mat[start_pos:end_pos, s_idx]
            rel_split = np.where(split_slice > 0, split_slice / cum_at_end, 1.0)

            if np.isfinite(bps_raw):
                bps_mat[start_pos:end_pos, s_idx] = bps_raw / rel_split
            if np.isfinite(eps_ttm_raw):
                eps_direct_mat[start_pos:end_pos, s_idx] = eps_ttm_raw / rel_split
            if (
                np.isfinite(np_ttm)
                and np.isfinite(latest_np)
                and np.isfinite(latest_eps)
                and abs(latest_eps) > 1e-8
                and (latest_np / latest_eps) > 0
            ):
                eps_np_base = np_ttm / (latest_np / latest_eps)
                eps_np_mat[start_pos:end_pos, s_idx] = eps_np_base / rel_split

            # EDI：最近两期已公告季报 dt_netprofit_yoy 或 roe_dt 环比改善
            if len(sorted_eds) >= 2:
                prev_r = by_end[sorted_eds[1]]
                c_yoy = _float_or_nan(latest.get("dt_netprofit_yoy"))
                p_yoy = _float_or_nan(prev_r.get("dt_netprofit_yoy"))
                if np.isfinite(c_yoy) and np.isfinite(p_yoy):
                    edi_mat[start_pos:end_pos, s_idx] = 1.0 if c_yoy > p_yoy else 0.0
                else:
                    c_roe = _float_or_nan(latest.get("roe_dt"))
                    p_roe = _float_or_nan(prev_r.get("roe_dt"))
                    if np.isfinite(c_roe) and np.isfinite(p_roe):
                        edi_mat[start_pos:end_pos, s_idx] = 1.0 if c_roe > p_roe else 0.0

    return eps_direct_mat, eps_np_mat, bps_mat, edi_mat


def _compute_daily_cross_sections(
    cal: list[str],
    all_codes: list[str],
    close_mat: np.ndarray,
    amt_mat: np.ndarray,
    active_mat: np.ndarray,
    eps_direct_mat: np.ndarray,
    eps_np_mat: np.ndarray,
    bps_mat: np.ndarray,
    edi_mat: np.ndarray,
    dv_mat: np.ndarray,
    yield_df: pd.DataFrame,
) -> pd.DataFrame:
    """计算 Top-800 流动性活跃股横截面估值/ERP/EDI/股息率及严格因果 756d 分位。"""
    n_days, n_stocks = close_mat.shape

    # 20日移动平均成交额（严格因果 <= d）
    amt_clean = np.where(active_mat & np.isfinite(amt_mat), amt_mat, 0.0)
    amt_df = pd.DataFrame(amt_clean)
    amt20_mat = amt_df.rolling(20, min_periods=1).mean().to_numpy()

    # 60日对数收益波动率（用于低波红利组）
    cls_df = pd.DataFrame(np.where(close_mat > 0, close_mat, np.nan))
    ret_df = cls_df.pct_change(fill_method=None)
    vol60_mat = ret_df.rolling(60, min_periods=20).std().to_numpy()

    yield_map = yield_df.set_index("trade_date")["cgb_10y_bps"].to_dict()
    yield1y_map = yield_df.set_index("trade_date")["cgb_1y_bps"].to_dict()

    records: list[dict[str, Any]] = []
    for d_idx, td in enumerate(cal):
        if td < WARMUP_START_YMD:
            continue
        act_mask = active_mat[d_idx]
        act_indices = np.flatnonzero(act_mask)
        if len(act_indices) == 0:
            continue
        if len(act_indices) > 800:
            top_local = np.argpartition(amt20_mat[d_idx, act_indices], -800)[-800:]
            top800 = act_indices[top_local]
        else:
            top800 = act_indices

        c_top = close_mat[d_idx, top800]
        ep_dir = (eps_direct_mat[d_idx, top800] / c_top) * 10000.0
        ep_np = (eps_np_mat[d_idx, top800] / c_top) * 10000.0
        bp_top = (bps_mat[d_idx, top800] / c_top) * 10000.0

        ep_dir_fin = ep_dir[np.isfinite(ep_dir)]
        ep_dir_pos = ep_dir[np.isfinite(ep_dir) & (ep_dir > 0)]
        ep_np_fin = ep_np[np.isfinite(ep_np)]
        ep_np_pos = ep_np[np.isfinite(ep_np) & (ep_np > 0)]
        bp_fin = bp_top[np.isfinite(bp_top) & (bp_top > 0)]

        edi_top = edi_mat[d_idx, top800]
        edi_fin = edi_top[np.isfinite(edi_top)]
        edi_all = edi_mat[d_idx, act_indices]
        edi_all_fin = edi_all[np.isfinite(edi_all)]

        dv_top = dv_mat[d_idx, top800] * 10000.0
        dv_pos = dv_top[np.isfinite(dv_top) & (dv_top > 0)]
        dv_all_zero = np.where(np.isfinite(dv_top) & (dv_top > 0), dv_top, 0.0)

        # 低波红利组：Top-800 中有有效股息率且 60d 波动率处于后 30% 低波分位的股票
        vol_top = vol60_mat[d_idx, top800]
        valid_lv = np.isfinite(dv_top) & (dv_top > 0) & np.isfinite(vol_top)
        dv_lowvol_med = float("nan")
        if valid_lv.sum() >= 20:
            v_thresh = np.nanpercentile(vol_top[valid_lv], 30.0)
            lv_mask = valid_lv & (vol_top <= v_thresh)
            if lv_mask.any():
                dv_lowvol_med = float(np.median(dv_top[lv_mask]))

        cgb10_bps = float(yield_map.get(td, float("nan")))
        cgb1_bps = float(yield1y_map.get(td, float("nan")))
        ep_med = float(np.median(ep_np_fin)) if len(ep_np_fin) else float("nan")
        ep_pos_med = float(np.median(ep_np_pos)) if len(ep_np_pos) else float("nan")
        ep_dir_med = float(np.median(ep_dir_fin)) if len(ep_dir_fin) else float("nan")
        ep_dir_pos_med = float(np.median(ep_dir_pos)) if len(ep_dir_pos) else float("nan")
        bp_med = float(np.median(bp_fin)) if len(bp_fin) else float("nan")

        records.append(
            {
                "trade_date": td,
                "active_count": int(len(act_indices)),
                "top800_count": int(len(top800)),
                "ep_valid_count": int(len(ep_np_fin)),
                "ep_pos_count": int(len(ep_np_pos)),
                "bp_valid_count": int(len(bp_fin)),
                "ep_median_bps": ep_med,
                "ep_pos_median_bps": ep_pos_med,
                "ep_direct_median_bps": ep_dir_med,
                "ep_direct_pos_median_bps": ep_dir_pos_med,
                "bp_median_bps": bp_med,
                "cgb_1y_bps": cgb1_bps,
                "cgb_10y_bps": cgb10_bps,
                "erp_bps": ep_med - cgb10_bps
                if np.isfinite(ep_med) and np.isfinite(cgb10_bps)
                else float("nan"),
                "erp_pos_bps": ep_pos_med - cgb10_bps
                if np.isfinite(ep_pos_med) and np.isfinite(cgb10_bps)
                else float("nan"),
                "edi_bps": float(np.mean(edi_fin) * 10000.0) if len(edi_fin) else float("nan"),
                "edi_all_bps": float(np.mean(edi_all_fin) * 10000.0)
                if len(edi_all_fin)
                else float("nan"),
                "dv_ttm_pit_bps": float(np.median(dv_pos)) if len(dv_pos) else float("nan"),
                "dv_ttm_pit_all800_bps": float(np.median(dv_all_zero))
                if len(dv_all_zero)
                else float("nan"),
                "dv_ttm_lowvol_bps": dv_lowvol_med,
            }
        )

    df = pd.DataFrame(records).sort_values("trade_date").reset_index(drop=True)
    # 严格因果 756d 滚动分位（含 2017-05..2017-12 热身，截断未来不影响 <= T）
    df["erp_pct_756"] = causal_rolling_percentile(
        df["erp_bps"].to_numpy(), window=756, min_periods=60
    )
    df["erp_pos_pct_756"] = causal_rolling_percentile(
        df["erp_pos_bps"].to_numpy(), window=756, min_periods=60
    )
    df["bp_pct_756"] = causal_rolling_percentile(
        df["bp_median_bps"].to_numpy(), window=756, min_periods=60
    )
    df["dv_spread_10y_bps"] = df["dv_ttm_pit_bps"] - df["cgb_10y_bps"]
    df["dv_spread_pct_756"] = causal_rolling_percentile(
        df["dv_spread_10y_bps"].to_numpy(), window=756, min_periods=60
    )
    return df


def validate_against_daily_basic(
    pit_df: pd.DataFrame,
    cal: list[str],
    all_codes: list[str],
    amt_mat: np.ndarray,
    active_mat: np.ndarray,
) -> dict[str, Any]:
    """2024-01-02 ~ 2026-11-26 与 daily_basic_pit.csv Top-800 同口径交叉核验。"""
    db = pd.read_csv(
        AUX_DIR / "daily_basic_pit.csv",
        usecols=["ts_code", "trade_date", "pe_ttm", "pb", "dv_ttm"],
        dtype={"ts_code": str, "trade_date": str, "pe_ttm": float, "pb": float, "dv_ttm": float},
    )
    db = db[(db["trade_date"] >= VAL_START_YMD) & (db["trade_date"] <= VAL_END_YMD)]
    db = db[~db["ts_code"].str.endswith(".BJ")].copy()

    # 构建与上面完全一致的 20d 滚动成交额 Top-800 集合
    amt_clean = np.where(active_mat & np.isfinite(amt_mat), amt_mat, 0.0)
    amt20_mat = pd.DataFrame(amt_clean).rolling(20, min_periods=1).mean().to_numpy()
    date_to_idx = {d: i for i, d in enumerate(cal)}
    code_arr = np.array(all_codes)

    top_rows: list[tuple[str, str]] = []
    for d in sorted(db["trade_date"].unique()):
        d_idx = date_to_idx.get(d)
        if d_idx is None:
            continue
        act_indices = np.flatnonzero(active_mat[d_idx])
        if len(act_indices) > 800:
            top_local = np.argpartition(amt20_mat[d_idx, act_indices], -800)[-800:]
            top800 = act_indices[top_local]
        else:
            top800 = act_indices
        for c in code_arr[top800]:
            top_rows.append((d, str(c)))

    top_df = pd.DataFrame(top_rows, columns=["trade_date", "ts_code"])
    db_top = db.merge(top_df, on=["trade_date", "ts_code"], how="inner")
    db_top["ref_ep_bps"] = np.where(
        db_top["pe_ttm"] > 0, (1.0 / db_top["pe_ttm"]) * 10000.0, np.nan
    )
    db_top["ref_bp_bps"] = np.where(db_top["pb"] > 0, (1.0 / db_top["pb"]) * 10000.0, np.nan)
    db_top["ref_dv_bps"] = np.where(db_top["dv_ttm"] > 0, db_top["dv_ttm"] * 100.0, np.nan)

    ref_daily = (
        db_top.groupby("trade_date", sort=True)
        .agg(
            ref_ep_median_bps=("ref_ep_bps", "median"),
            ref_bp_median_bps=("ref_bp_bps", "median"),
            ref_dv_median_bps=("ref_dv_bps", "median"),
            ref_ep_count=("ref_ep_bps", "count"),
            ref_bp_count=("ref_bp_bps", "count"),
        )
        .reset_index()
    )

    merged = pit_df.merge(ref_daily, on="trade_date", how="inner").sort_values("trade_date")

    def _pair_metrics(a: pd.Series, b: pd.Series, dates: pd.Series) -> dict[str, Any]:
        valid = a.notna() & b.notna()
        va = a[valid].to_numpy(dtype=np.float64)
        vb = b[valid].to_numpy(dtype=np.float64)
        vd = dates[valid].to_numpy()
        if len(va) < 5:
            return {
                "n_days": int(len(va)),
                "pearson_r": None,
                "spearman_rho": None,
                "mae_bps": None,
            }
        r_val = float(np.corrcoef(va, vb)[0, 1])
        rho_val = float(stats.spearmanr(va, vb).statistic)
        diff = va - vb
        abs_diff = np.abs(diff)
        max_i = int(np.argmax(abs_diff))
        return {
            "n_days": int(len(va)),
            "pearson_r": round(r_val, 6),
            "spearman_rho": round(rho_val, 6),
            "mae_bps": round(float(np.mean(abs_diff)), 4),
            "bias_bps": round(float(np.mean(diff)), 4),
            "max_abs_diff_bps": round(float(abs_diff[max_i]), 4),
            "max_diff_date": str(vd[max_i]),
            "max_diff_pit_bps": round(float(va[max_i]), 4),
            "max_diff_ref_bps": round(float(vb[max_i]), 4),
        }

    ep_np_pos = _pair_metrics(
        merged["ep_pos_median_bps"], merged["ref_ep_median_bps"], merged["trade_date"]
    )
    ep_dir_pos = _pair_metrics(
        merged["ep_direct_pos_median_bps"], merged["ref_ep_median_bps"], merged["trade_date"]
    )
    ep_all = _pair_metrics(
        merged["ep_median_bps"], merged["ref_ep_median_bps"], merged["trade_date"]
    )
    bp_metrics = _pair_metrics(
        merged["bp_median_bps"], merged["ref_bp_median_bps"], merged["trade_date"]
    )
    dv_metrics = _pair_metrics(
        merged["dv_ttm_pit_bps"], merged["ref_dv_median_bps"], merged["trade_date"]
    )

    # 选择与 daily_basic 口径最匹配的 EP 指标检验门禁（r >= 0.98）
    pass_ep = (ep_np_pos.get("pearson_r") or 0.0) >= 0.98
    pass_bp = (bp_metrics.get("pearson_r") or 0.0) >= 0.98
    return {
        "window": f"{VAL_START_YMD}..{VAL_END_YMD}",
        "gate_passed": bool(pass_ep and pass_bp),
        "ep_pos_np_shares_vs_ref": ep_np_pos,
        "ep_pos_direct_vs_ref": ep_dir_pos,
        "ep_all_vs_ref": ep_all,
        "bp_vs_ref": bp_metrics,
        "dv_vs_ref_2024_20261117": dv_metrics,
    }


def run_pipeline(
    *,
    force_fetch: bool = False,
    skip_fetch: bool = False,
) -> dict[str, Any]:
    """执行完整阶段 2 PIT 拉取、9 年日频重建与 2024-2026 交叉核验流水线。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if skip_fetch and FINA_SQLITE_PATH.is_file():
        conn = sqlite3.connect(FINA_SQLITE_PATH)
        try:
            fina_df = pd.read_sql_query("SELECT * FROM fina_pit", conn)
        finally:
            conn.close()
    else:
        fina_df = fetch_eastmoney_40q(force_refresh=force_fetch)

    yield_df_2018, yield_overlap = build_macro_yield_curve(force_refresh=force_fetch)
    nov_sb = fetch_nov2026_sharebonus(force_refresh=force_fetch)

    # 读取完整 2017-05..2026-11 国债曲线用于 warmup 期间计算 ERP
    with h5py.File(BUNDLE_PATH / "yield_curve.h5", "r") as f:
        arr = f["data"][:]
    yc_full = pd.DataFrame(
        {
            "trade_date": pd.Series(arr["date"]).astype(str),
            "cgb_1y_bps": arr["1Y"].astype(np.float64) * 10000.0,
            "cgb_10y_bps": arr["10Y"].astype(np.float64) * 10000.0,
        }
    )
    nov_y = fetch_nov2026_yields(force_refresh=force_fetch)
    nov_y_bps = pd.DataFrame(
        {
            "trade_date": nov_y["trade_date"].astype(str),
            "cgb_1y_bps": nov_y["cgb_1y_pct"].astype(float) * 100.0,
            "cgb_10y_bps": nov_y["cgb_10y_pct"].astype(float) * 100.0,
        }
    )
    yc_all = pd.concat(
        [
            yc_full[yc_full["trade_date"] <= BUNDLE_CUTOFF_YMD],
            nov_y_bps[nov_y_bps["trade_date"] > BUNDLE_CUTOFF_YMD],
        ],
        ignore_index=True,
    ).sort_values("trade_date")

    cal_full = _load_unified_calendar(start_ymd=TURNOVER_WARMUP_YMD, end_ymd=EXP_END_YMD)
    cal_ints = np.array([int(d) for d in cal_full], dtype=np.int64)
    yc_aligned = (
        yc_all.set_index("trade_date")
        .reindex(cal_full)
        .ffill()
        .reset_index()
        .rename(columns={"index": "trade_date"})
    )

    splits, divs = _load_split_and_dividend_events(nov_sb)
    all_codes, close_mat, amt_mat, active_mat = _compute_stock_daily_matrices(cal_full)
    cum_split_mat = _build_cumulative_split_matrix(cal_ints, all_codes, splits)
    dv_mat = _build_pit_dividend_matrix(
        cal_full, cal_ints, all_codes, divs, splits, cum_split_mat, close_mat
    )
    eps_dir_mat, eps_np_mat, bps_mat, edi_mat = _build_pit_fundamental_matrices(
        fina_df, cal_full, cal_ints, all_codes, splits, cum_split_mat
    )
    daily_full = _compute_daily_cross_sections(
        cal_full,
        all_codes,
        close_mat,
        amt_mat,
        active_mat,
        eps_dir_mat,
        eps_np_mat,
        bps_mat,
        edi_mat,
        dv_mat,
        yc_aligned,
    )

    daily_2018 = daily_full[daily_full["trade_date"] >= EXP_START_YMD].copy().reset_index(drop=True)
    tmp_csv = CACHE_DIR / ".tmp_market_fundamental_daily.csv"
    daily_2018.to_csv(tmp_csv, index=False)
    os.replace(tmp_csv, DAILY_FUNDAMENTAL_CSV_PATH)

    val_report = validate_against_daily_basic(daily_2018, cal_full, all_codes, amt_mat, active_mat)

    q_counts = fina_df.groupby("end_date")["ts_code"].nunique().to_dict()
    report = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fina_40q_rows": int(len(fina_df)),
        "fina_quarters_covered": int(len(q_counts)),
        "fina_unique_stocks": int(fina_df["ts_code"].nunique()),
        "fina_min_end_date": str(fina_df["end_date"].min()),
        "fina_max_end_date": str(fina_df["end_date"].max()),
        "fina_min_ann_date": str(fina_df["ann_date"].min()),
        "fina_max_ann_date": str(fina_df["ann_date"].max()),
        "fina_quarter_stock_counts": {str(k): int(v) for k, v in sorted(q_counts.items())},
        "macro_yield_rows": int(len(yield_df_2018)),
        "macro_yield_overlap_audit": yield_overlap,
        "daily_fundamental_rows": int(len(daily_2018)),
        "daily_date_range": [
            str(daily_2018["trade_date"].min()),
            str(daily_2018["trade_date"].max()),
        ],
        "validation": val_report,
    }
    tmp_json = CACHE_DIR / ".tmp_pit_validation_report.json"
    tmp_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_json, VALIDATION_REPORT_PATH)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="V3.4 Stage 2 PIT Fundamental Builder")
    parser.add_argument("--force-fetch", action="store_true", help="Re-fetch all quarters/yields")
    parser.add_argument(
        "--skip-fetch", action="store_true", help="Rebuild from existing SQLite cache"
    )
    args = parser.parse_args()
    rep = run_pipeline(force_fetch=args.force_fetch, skip_fetch=args.skip_fetch)
    print(json.dumps(rep["validation"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
