"""V3 Phase 2 共享数据加载、跨源拼接与双锚市场状态计算模块。

数据权威边界（Strict PIT Provenance）：
1. 核心研究行情、复权因子、财务公告日与交易日历来自只读快照 `v3_snapshot_20261113`
   （经 `load_snapshot_manifest(..., verify_content=True)` 全量 SHA-256 校验）。
2. 指数日线（`000300.SH` / `000905.SH` / `399006.SZ` / `000001.SH` / `000852.SH`）来自关联附属导出
   `v3_aux_20261113/index_daily.csv`（校验 `aux_manifest.json` 哈希与 `linked_snapshot_id`）。
3. 历史扩展窗口（`2017-01-03 .. 2026-08-31`）与原生 RQAlpha 撮合来自只读 `~/.rqalpha/bundle`，
   并在重叠窗（`2026-06-01 .. 2026-08-31`）与快照核对后通过除权日收益 `close / pre_close`
   向右串联至 `2026-11-13`。
4. 严格执行 `NaN != 0` 与上市前/退市后 `tradability_mask`（`tacticore.data.tradability`）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rqalpha.utils.datetime_func import convert_int_to_date

from research.ashare.data.contract import SnapshotManifest, load_snapshot_manifest, sha256_file
from research.ashare.engines.bundle_source import (
    _normalize_delisted,
    bundle_calendar,
    open_bundle_source,
)
from tacticore.data.tradability import AssetLifetime, build_tradability_mask

SNAPSHOT_DIR = Path("/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_snapshot_20261113")
AUX_DIR = Path("/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_aux_20261113")
BUNDLE_PATH = Path("/home/jcshi/.rqalpha/bundle")
WHITELIST_PATH = Path(
    "/home/jcshi/workspace/AShareInvestor/docs/v3-offensive-system/fee-profiles/"
    "super_etf_whitelist_20261115.json"
)
REGIME_CACHE_PATH = AUX_DIR / "v3_regime_daily.csv"

BUNDLE_CUTOFF = pd.Timestamp("2026-08-31")
WARMUP_START = pd.Timestamp("2017-01-03")
EXP_START = pd.Timestamp("2018-01-02")
IS_END = pd.Timestamp("2023-12-29")
OOS_START = pd.Timestamp("2024-01-02")
EXP_END = pd.Timestamp("2026-11-13")

INDEX_CODES: tuple[str, ...] = (
    "000300.SH",
    "000905.SH",
    "399006.SZ",
    "000001.SH",
    "000852.SH",
)
FALLBACK_ETFS: tuple[str, ...] = (
    "510300.SH",
    "510500.SH",
    "159915.SZ",
    "512890.SH",
    "511010.SH",
    "512480.SH",
    "515790.SH",
    "512170.SH",
    "159558.SZ",
)
REGIME_CACHE_VERSION = "v3_regime_breadth_v1"


@dataclass(frozen=True)
class SnapshotProvenance:
    """已校验的 V3 实验输入溯源记录。"""

    snapshot_id: str
    as_of_trade_date: str
    manifest: SnapshotManifest
    dataset_hashes: dict[str, str]
    aux_hashes: dict[str, str]
    whitelist_sha256: str
    super_etf_codes: tuple[str, ...]
    super_etf_names: dict[str, str]
    super_etf_categories: dict[str, str]


@dataclass(frozen=True)
class V3StitchedPanels:
    """V3 实验共享价格面板、生命周期与拼接审计结果。"""

    calendar: pd.DatetimeIndex
    index_close: pd.DataFrame
    etf_adj_close: pd.DataFrame
    etf_raw_close: pd.DataFrame
    etf_lifetimes: dict[str, AssetLifetime]
    etf_tradability_mask: pd.DataFrame
    overlap_audit: dict[str, Any]
    missing_fund_adj_factor_codes: tuple[str, ...]
    adjustment_disclosure: str


def ts_to_rq(ts_code: str) -> str:
    """把 Tushare `xxxxxx.SH/.SZ` 转为 RQAlpha `xxxxxx.XSHG/.XSHE`。"""
    code, ex = ts_code.split(".")
    if ex == "SH":
        return f"{code}.XSHG"
    if ex == "SZ":
        return f"{code}.XSHE"
    raise ValueError(f"不支持的交易所后缀: {ts_code}")


def rq_to_ts(order_book_id: str) -> str:
    """把 RQAlpha `xxxxxx.XSHG/.XSHE` 转为 Tushare `xxxxxx.SH/.SZ`。"""
    code, ex = order_book_id.split(".")
    if ex == "XSHG":
        return f"{code}.SH"
    if ex == "XSHE":
        return f"{code}.SZ"
    raise ValueError(f"不支持的 RQAlpha 后缀: {order_book_id}")


def verify_v3_provenance(verify_content: bool = True) -> SnapshotProvenance:
    """校验 PIT 主快照、关联指数附属导出及东财超级 ETF 白名单哈希。"""
    manifest = load_snapshot_manifest(SNAPSHOT_DIR, verify_content=verify_content)
    aux_manifest_path = AUX_DIR / "aux_manifest.json"
    if not aux_manifest_path.is_file():
        raise FileNotFoundError(f"缺少附属导出 manifest: {aux_manifest_path}")
    aux_raw = json.loads(aux_manifest_path.read_text(encoding="utf-8"))
    if aux_raw.get("linked_snapshot_id") != manifest.snapshot_id:
        raise ValueError(
            "aux_manifest.json linked_snapshot_id 与主快照不一致: "
            f"{aux_raw.get('linked_snapshot_id')} != {manifest.snapshot_id}"
        )
    aux_hashes: dict[str, str] = {}
    for filename, meta in dict(aux_raw.get("files", {})).items():
        fpath = AUX_DIR / filename
        expected_sha = str(meta["sha256"])
        if verify_content:
            actual_sha = sha256_file(fpath)
            if actual_sha != expected_sha:
                raise ValueError(f"附属文件哈希校验失败 {filename}: {actual_sha} != {expected_sha}")
        aux_hashes[filename] = expected_sha

    wl_raw = json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))
    wl_sha = sha256_file(WHITELIST_PATH)
    entries = list(wl_raw["entries"])
    codes = tuple(str(item["ts_code"]) for item in entries)
    names = {str(item["ts_code"]): str(item["name"]) for item in entries}
    cats = {str(item["ts_code"]): str(item["category"]) for item in entries}

    return SnapshotProvenance(
        snapshot_id=manifest.snapshot_id,
        as_of_trade_date=manifest.as_of_trade_date,
        manifest=manifest,
        dataset_hashes=dict(manifest.content_hashes),
        aux_hashes=aux_hashes,
        whitelist_sha256=wl_sha,
        super_etf_codes=codes,
        super_etf_names=names,
        super_etf_categories=cats,
    )


def build_unified_calendar(
    source: Any,
    *,
    start: pd.Timestamp = WARMUP_START,
    end: pd.Timestamp = EXP_END,
) -> pd.DatetimeIndex:
    """拼接 RQAlpha 历史交易日历（截至 2026-08-31）与快照交易日历（至 2026-11-13）。"""
    cal_hist = bundle_calendar(source, start, min(end, BUNDLE_CUTOFF))
    if end <= BUNDLE_CUTOFF:
        return cal_hist
    tc_df = pd.read_csv(SNAPSHOT_DIR / "trade_calendar.csv", dtype=str)
    open_df = tc_df[tc_df["is_open"] == "1"].copy()
    open_dates = pd.DatetimeIndex(sorted(pd.to_datetime(open_df["cal_date"]).unique()))
    tail = open_dates[(open_dates > BUNDLE_CUTOFF) & (open_dates <= end)]
    combined = pd.DatetimeIndex(sorted(set(cal_hist).union(set(tail))))
    return combined


def _read_bundle_index_series(
    source: Any,
    order_book_id: str,
    end: pd.Timestamp,
) -> pd.Series:
    inst = list(source.get_instruments([order_book_id]))[-1]
    bars = source.history_bars(
        inst,
        None,
        "1d",
        None,
        pd.Timestamp(end).to_pydatetime(),
        skip_suspended=True,
        include_now=True,
        adjust_type="none",
    )
    dates = pd.DatetimeIndex(
        [pd.Timestamp(convert_int_to_date(int(val))).normalize() for val in bars["datetime"]]
    )
    series = pd.Series(bars["close"].astype(float), index=dates)
    return series[~series.index.duplicated(keep="last")]


def _read_bundle_etf_series(
    source: Any,
    order_book_id: str,
    end: pd.Timestamp,
) -> tuple[pd.Series, pd.Series, pd.Timestamp, pd.Timestamp | None]:
    candidates = list(source.get_instruments([order_book_id]))
    if not candidates:
        raise KeyError(order_book_id)
    inst = candidates[-1]
    listed = pd.Timestamp(inst.listed_date).normalize()
    delisted = _normalize_delisted(getattr(inst, "de_listed_date", None))
    eff_end = min(end, delisted) if delisted is not None else end
    bars_raw = source.history_bars(
        inst,
        None,
        "1d",
        None,
        eff_end.to_pydatetime(),
        skip_suspended=True,
        include_now=True,
        adjust_type="none",
    )
    bars_post = source.history_bars(
        inst,
        None,
        "1d",
        None,
        eff_end.to_pydatetime(),
        skip_suspended=True,
        include_now=True,
        adjust_type="post",
        adjust_orig=eff_end.to_pydatetime(),
    )
    dt_raw = pd.DatetimeIndex(
        [pd.Timestamp(convert_int_to_date(int(val))).normalize() for val in bars_raw["datetime"]]
    )
    raw = pd.Series(bars_raw["close"].astype(float), index=dt_raw)
    raw = raw[~raw.index.duplicated(keep="last")]
    dt_post = pd.DatetimeIndex(
        [pd.Timestamp(convert_int_to_date(int(val))).normalize() for val in bars_post["datetime"]]
    )
    post = pd.Series(bars_post["close"].astype(float), index=dt_post)
    post = post[~post.index.duplicated(keep="last")]
    return raw, post, listed, delisted


def load_stitched_panels(
    provenance: SnapshotProvenance,
    *,
    start: pd.Timestamp = WARMUP_START,
    end: pd.Timestamp = EXP_END,
) -> V3StitchedPanels:
    """加载 2017–2026 指数与 ETF 全收益面板并执行重叠窗审计。"""
    source = open_bundle_source(BUNDLE_PATH)
    calendar = build_unified_calendar(source, start=start, end=end)

    # 1. 指数日线：RQAlpha (<= 2026-08-31) + index_daily.csv (> 2026-08-31)
    idx_df = pd.read_csv(
        AUX_DIR / "index_daily.csv",
        dtype={"ts_code": str, "trade_date": str},
    )
    idx_df["dt"] = pd.to_datetime(idx_df["trade_date"])
    idx_cols: dict[str, pd.Series] = {}
    idx_overlap: dict[str, dict[str, float]] = {}
    ov_start = pd.Timestamp("2026-06-01")
    for code in INDEX_CODES:
        s_bundle = _read_bundle_index_series(source, ts_to_rq(code), min(end, BUNDLE_CUTOFF))
        sub = idx_df[idx_df["ts_code"] == code].set_index("dt")["close"].astype(float).sort_index()
        common = s_bundle.index.intersection(sub.index)
        common_ov = common[(common >= ov_start) & (common <= BUNDLE_CUTOFF)]
        if len(common_ov) > 0:
            max_close_diff = float((s_bundle.loc[common_ov] - sub.loc[common_ov]).abs().max())
            ret_b = s_bundle.pct_change().reindex(common_ov)
            ret_s = sub.pct_change().reindex(common_ov)
            max_ret_diff = float((ret_b - ret_s).abs().max())
            idx_overlap[code] = {
                "common_days": float(len(common_ov)),
                "max_abs_close_diff": round(max_close_diff, 8),
                "max_abs_ret_diff": round(max_ret_diff, 10),
            }
        tail = sub.loc[sub.index > BUNDLE_CUTOFF]
        stitched = pd.concat([s_bundle, tail]).sort_index()
        idx_cols[code] = stitched.reindex(calendar)
    index_close = pd.DataFrame(idx_cols, index=calendar)

    # 2. ETF 面板：33 只超级 ETF + 基线/回退 ETF
    all_etfs = sorted(set(provenance.super_etf_codes) | set(FALLBACK_ETFS))
    fb_df = pd.read_csv(
        SNAPSHOT_DIR / "fund_daily_bars.csv",
        dtype={"ts_code": str, "trade_date": str},
    )
    fb_df["dt"] = pd.to_datetime(fb_df["trade_date"])
    fa_df = pd.read_csv(
        SNAPSHOT_DIR / "fund_adj_factor.csv",
        dtype={"ts_code": str, "trade_date": str},
    )
    fbasic_df = pd.read_csv(
        SNAPSHOT_DIR / "fund_basic.csv",
        dtype={"ts_code": str, "list_date": str, "delist_date": str},
    ).set_index("ts_code")

    fa_codes_complete = set(
        fa_df.groupby("ts_code")["trade_date"].count().loc[lambda s: s >= 190].index
    )
    missing_adj = tuple(sorted(c for c in all_etfs if c not in fa_codes_complete))

    adj_cols: dict[str, pd.Series] = {}
    raw_cols: dict[str, pd.Series] = {}
    lifetimes: dict[str, AssetLifetime] = {}
    etf_overlap: dict[str, dict[str, float]] = {}

    for code in all_etfs:
        sub_fb = (
            fb_df[fb_df["ts_code"] == code].sort_values("dt").drop_duplicates("dt").set_index("dt")
        )
        rq_id = ts_to_rq(code)
        try:
            b_raw, b_post, listed, delisted = _read_bundle_etf_series(
                source, rq_id, min(end, BUNDLE_CUTOFF)
            )
            in_bundle = True
        except KeyError:
            in_bundle = False
            meta = fbasic_df.loc[code]
            listed_str = str(meta["list_date"])
            delist_val = meta["delist_date"]
            listed = pd.to_datetime(listed_str).normalize()
            delisted = (
                pd.to_datetime(str(delist_val)).normalize()
                if pd.notna(delist_val) and str(delist_val).strip() not in ("", "nan", "None")
                else None
            )

        if in_bundle:
            common = b_raw.index.intersection(sub_fb.index)
            common_ov = common[(common >= ov_start) & (common <= BUNDLE_CUTOFF)]
            if len(common_ov) > 1:
                ov_close = sub_fb.loc[common_ov, "close"]
                max_raw_diff = float((b_raw.loc[common_ov] - ov_close).abs().max())
                ret_post = b_post.pct_change().reindex(common_ov)
                raw_ratio = sub_fb["close"].astype(float) / sub_fb["pre_close"].astype(float) - 1.0
                ret_preclose = raw_ratio.reindex(common_ov)
                max_ret_diff = float((ret_post - ret_preclose).abs().max())
                etf_overlap[code] = {
                    "common_days": float(len(common_ov)),
                    "max_abs_raw_close_diff": round(max_raw_diff, 8),
                    "max_abs_adj_ret_diff": round(max_ret_diff, 10),
                }

            tail_fb = sub_fb[sub_fb.index > BUNDLE_CUTOFF]
            if not tail_fb.empty and not b_post.empty:
                last_post = float(b_post.iloc[-1])
                daily_mult = (
                    tail_fb["close"].astype(float) / tail_fb["pre_close"].astype(float)
                ).replace([np.inf, -np.inf], np.nan)
                tail_post = last_post * daily_mult.cumprod()
                stitched_adj = pd.concat([b_post, tail_post]).sort_index()
                stitched_raw = pd.concat([b_raw, tail_fb["close"].astype(float)]).sort_index()
            else:
                stitched_adj = b_post
                stitched_raw = b_raw
        else:
            # Snapshot-only newly listed ETF (e.g., 158049.SZ listed 2026-09-22)
            if sub_fb.empty:
                stitched_adj = pd.Series(dtype=float)
                stitched_raw = pd.Series(dtype=float)
            else:
                daily_mult = (
                    sub_fb["close"].astype(float) / sub_fb["pre_close"].astype(float)
                ).fillna(1.0)
                first_close = float(sub_fb["close"].iloc[0])
                # Day 0 ratio uses close/pre_close from issue close; normalize day 0 to close.
                rel = daily_mult / float(daily_mult.iloc[0])
                stitched_adj = first_close * rel.cumprod()
                stitched_raw = sub_fb["close"].astype(float)

        # Clip strictly outside AssetLifetime so NaN != 0 is preserved
        mask_life = (calendar >= listed) & (calendar <= delisted if delisted is not None else True)
        adj_s = stitched_adj.reindex(calendar)
        raw_s = stitched_raw.reindex(calendar)
        adj_s[~mask_life] = np.nan
        raw_s[~mask_life] = np.nan
        adj_cols[code] = adj_s
        raw_cols[code] = raw_s
        lifetimes[code] = AssetLifetime(symbol=code, listed_date=listed, delisted_date=delisted)

    etf_adj_close = pd.DataFrame(adj_cols, index=calendar)
    etf_raw_close = pd.DataFrame(raw_cols, index=calendar)
    tradability_mask = build_tradability_mask(calendar, all_etfs, lifetimes, etf_adj_close)

    max_etf_ret_diff = max((v["max_abs_adj_ret_diff"] for v in etf_overlap.values()), default=0.0)
    max_idx_ret_diff = max((v["max_abs_ret_diff"] for v in idx_overlap.values()), default=0.0)
    disclosure = (
        f"raw_close_no_adj_factor_for={len(missing_adj)}/{len(all_etfs)} ETFs in snapshot "
        f"(mitigated via ex-right daily total return close/pre_close chaining onto RQAlpha "
        f"post-adjusted history; max 2026-06..08 overlap adj_ret diff={max_etf_ret_diff:.2e})"
    )

    return V3StitchedPanels(
        calendar=calendar,
        index_close=index_close,
        etf_adj_close=etf_adj_close,
        etf_raw_close=etf_raw_close,
        etf_lifetimes=lifetimes,
        etf_tradability_mask=tradability_mask,
        overlap_audit={
            "window": "2026-06-01..2026-08-31",
            "max_index_ret_diff": max_idx_ret_diff,
            "max_etf_adj_ret_diff": max_etf_ret_diff,
            "indices": idx_overlap,
            "etfs_audited": len(etf_overlap),
        },
        missing_fund_adj_factor_codes=missing_adj,
        adjustment_disclosure=disclosure,
    )


def _compute_bundle_breadth(
    cal_hist: pd.DatetimeIndex,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """从 RQAlpha bundle 读取历史全部非北交 CS 股票（含已退市）日宽度指标。"""
    source = open_bundle_source(BUNDLE_PATH)
    all_cs = [
        inst
        for inst in source.get_instruments(types=["CS"])
        if not inst.order_book_id.endswith(".BJ")
    ]
    cal_ints = np.array([int(d.strftime("%Y%m%d")) for d in cal_hist], dtype=np.int64)
    n_days = len(cal_ints)
    above_num = np.zeros(n_days, dtype=np.int32)
    above_den = np.zeros(n_days, dtype=np.int32)
    mkt_amt_yuan = np.zeros(n_days, dtype=np.float64)
    limit_dn = np.zeros(n_days, dtype=np.int32)

    end_dt = cutoff.to_pydatetime()
    start_int = int(cal_hist[0].strftime("%Y%m%d"))

    for inst in all_cs:
        listed = pd.Timestamp(inst.listed_date)
        delisted = pd.Timestamp(inst.de_listed_date)
        if listed > cutoff or delisted < cal_hist[0]:
            continue
        eff_end = min(end_dt, delisted.to_pydatetime()) if delisted.year < 2999 else end_dt
        bars_raw = source.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="none",
        )
        if bars_raw is None or len(bars_raw) == 0:
            continue
        bars_adj = source.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="pre",
            adjust_orig=eff_end,
        )
        if bars_adj is None or len(bars_adj) != len(bars_raw):
            bars_adj = bars_raw

        dts = (bars_adj["datetime"] // 1000000).astype(np.int64)
        mask = dts >= start_int
        if not mask.any():
            continue

        c_adj = bars_adj["close"].astype(np.float64)
        ma60 = pd.Series(c_adj).rolling(60, min_periods=60).mean().to_numpy()

        dts_w = dts[mask]
        idxs = np.searchsorted(cal_ints, dts_w)
        in_cal = (idxs < n_days) & (cal_ints[np.minimum(idxs, n_days - 1)] == dts_w)
        if not in_cal.any():
            continue
        idxs = idxs[in_cal]

        c_w = c_adj[mask][in_cal]
        ma_w = ma60[mask][in_cal]
        amt_w = bars_raw["total_turnover"][mask][in_cal].astype(np.float64)
        c_raw_w = bars_raw["close"][mask][in_cal].astype(np.float64)
        ld_w = bars_raw["limit_down"][mask][in_cal].astype(np.float64)

        valid_ma = ~np.isnan(ma_w)
        if valid_ma.any():
            np.add.at(above_den, idxs[valid_ma], 1)
            np.add.at(above_num, idxs[valid_ma], (c_w[valid_ma] > ma_w[valid_ma]).astype(np.int32))
        np.add.at(mkt_amt_yuan, idxs, np.nan_to_num(amt_w, 0.0))
        is_ld = np.isfinite(ld_w) & (ld_w > 0) & (c_raw_w <= ld_w + 1e-4)
        np.add.at(limit_dn, idxs, is_ld.astype(np.int32))

    pct_above = np.where(above_den > 0, above_num / above_den, np.nan)
    return pd.DataFrame(
        {
            "pct_above_ma60": pct_above,
            "amount_yi": mkt_amt_yuan / 1e8,
            "limit_down": limit_dn,
        },
        index=cal_hist,
    )


def _compute_snapshot_breadth() -> pd.DataFrame:
    """从 v3_snapshot_20261113 计算 2024-01-02..2026-11-13 全市场宽度指标。"""
    sb = pd.read_csv(SNAPSHOT_DIR / "stock_basic.csv", usecols=["ts_code"], dtype=str)
    valid_codes = set(sb[~sb["ts_code"].str.endswith(".BJ")]["ts_code"])

    daily = pd.read_csv(
        SNAPSHOT_DIR / "daily_bars.csv",
        usecols=["ts_code", "trade_date", "close", "amount"],
        dtype={"ts_code": str, "trade_date": str, "close": float, "amount": float},
    )
    daily = daily[daily["ts_code"].isin(valid_codes)].copy()

    adj = pd.read_csv(
        SNAPSHOT_DIR / "adj_factor.csv",
        usecols=["ts_code", "trade_date", "adj_factor"],
        dtype={"ts_code": str, "trade_date": str, "adj_factor": float},
    )
    pl = pd.read_csv(
        SNAPSHOT_DIR / "price_limit.csv",
        usecols=["ts_code", "trade_date", "down_limit"],
        dtype={"ts_code": str, "trade_date": str, "down_limit": float},
    )

    merged = daily.merge(adj, on=["ts_code", "trade_date"], how="left")
    merged = merged.merge(pl, on=["ts_code", "trade_date"], how="left")
    merged = merged.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    merged["adj_close"] = merged["close"] * merged["adj_factor"]
    merged["ma60"] = (
        merged.groupby("ts_code", sort=False)["adj_close"]
        .rolling(60, min_periods=60)
        .mean()
        .reset_index(level=0, drop=True)
    )
    merged["valid_ma"] = merged["ma60"].notna().astype(np.int32)
    merged["above_ma"] = (merged["ma60"].notna() & (merged["adj_close"] > merged["ma60"])).astype(
        np.int32
    )
    merged["is_ld"] = (
        merged["down_limit"].notna()
        & (merged["down_limit"] > 0)
        & (merged["close"] <= merged["down_limit"] + 1e-4)
    ).astype(np.int32)

    agg = merged.groupby("trade_date", sort=True).agg(
        above_num=("above_ma", "sum"),
        above_den=("valid_ma", "sum"),
        amount_k=("amount", "sum"),
        limit_down=("is_ld", "sum"),
    )
    agg.index = pd.to_datetime(agg.index)
    pct_above = np.where(agg["above_den"] > 0, agg["above_num"] / agg["above_den"], np.nan)
    return pd.DataFrame(
        {
            "pct_above_ma60": pct_above,
            "amount_yi": agg["amount_k"] / 1e5,
            "limit_down": agg["limit_down"].astype(int),
        },
        index=agg.index.sort_values(),
    )


def _anchor_states(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    s = series.astype(float)
    ma20 = s.rolling(20, min_periods=20).mean()
    ma20_prev5 = ma20.shift(5)
    ma60 = s.rolling(60, min_periods=60).mean()
    pct_chg = s.pct_change() * 100.0
    ret20_pct = s.pct_change(20) * 100.0

    states: list[str] = []
    for c, m20, m20p, m60 in zip(s, ma20, ma20_prev5, ma60, strict=True):
        if np.isnan(c) or np.isnan(m20) or np.isnan(m20p) or np.isnan(m60):
            states.append("RANGE")
        elif c > m60 and m20 > m60 and m20 > m20p:
            states.append("BULL")
        elif c < m60 and m20 <= m20p:
            states.append("BEAR")
        else:
            states.append("RANGE")
    return pd.Series(states, index=s.index), pct_chg, ret20_pct


def compute_v3_market_regime_series(
    provenance: SnapshotProvenance,
    index_close: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    *,
    pct_above_ma60_off: float = 0.45,
    style_spread_threshold: float = 0.03,
    use_cache: bool = True,
) -> pd.DataFrame:
    """严格对齐 `FinanceMCP/src/ashare/marketRegime.ts` 规则计算逐日三档环境与风格状态。"""
    breadth: pd.DataFrame | None = None
    if use_cache and REGIME_CACHE_PATH.is_file():
        cached = pd.read_csv(REGIME_CACHE_PATH, dtype={"trade_date": str, "snapshot_id": str})
        if (
            not cached.empty
            and str(cached["snapshot_id"].iloc[0]) == provenance.snapshot_id
            and str(cached.get("cache_version", pd.Series([""])).iloc[0]) == REGIME_CACHE_VERSION
        ):
            cached["dt"] = pd.to_datetime(cached["trade_date"])
            cached = cached.set_index("dt")[["pct_above_ma60", "amount_yi", "limit_down"]]
            if set(calendar).issubset(set(cached.index)):
                breadth = cached.reindex(calendar)

    if breadth is None:
        stitch_split = pd.Timestamp("2024-06-30")
        cal_hist = calendar[calendar <= pd.Timestamp("2026-08-31")]
        b_hist = _compute_bundle_breadth(cal_hist, BUNDLE_CUTOFF)
        b_snap = _compute_snapshot_breadth()

        # Seam diagnostics in 2024-07 .. 2026-08
        ov = b_hist.index.intersection(b_snap.index)
        ov = ov[ov > stitch_split]
        if len(ov) > 0:
            pct_diff = b_hist.loc[ov, "pct_above_ma60"] - b_snap.loc[ov, "pct_above_ma60"]
            max_pct_diff = float(pct_diff.abs().max())
            amt_ratio = float((b_snap.loc[ov, "amount_yi"] / b_hist.loc[ov, "amount_yi"]).median())
        else:
            max_pct_diff = 0.0
            amt_ratio = 1.0

        # Use bundle up to 2024-06-30 (warmup clean) and snapshot >= 2024-07-01 for continuous MA60.
        part_hist = b_hist.loc[b_hist.index <= stitch_split]
        part_snap = b_snap.loc[b_snap.index > stitch_split]
        breadth = pd.concat([part_hist, part_snap]).sort_index().reindex(calendar)

        if use_cache:
            out_cache = breadth.copy()
            out_cache.insert(0, "trade_date", out_cache.index.strftime("%Y%m%d"))
            out_cache["snapshot_id"] = provenance.snapshot_id
            out_cache["cache_version"] = REGIME_CACHE_VERSION
            out_cache["seam_max_pct_diff"] = round(max_pct_diff, 6)
            out_cache["seam_amt_ratio"] = round(amt_ratio, 6)
            out_cache.to_csv(REGIME_CACHE_PATH, index=False)

    amount_ma20 = breadth["amount_yi"].rolling(20, min_periods=20).mean()
    amount_vs_ma20 = (breadth["amount_yi"] / amount_ma20).round(3)

    val_state, val_pct_chg, val_ret20 = _anchor_states(index_close["000300.SH"])
    csi500_state, csi500_pct_chg, csi500_ret20 = _anchor_states(index_close["000905.SH"])
    chinext_state, chinext_pct_chg, chinext_ret20 = _anchor_states(index_close["399006.SZ"])

    rows: list[dict[str, Any]] = []
    confirmed = "STRUCTURAL"
    prev_raw = "STRUCTURAL"
    target_bps_map = {"OFFENSIVE": 8500, "STRUCTURAL": 6000, "DEFENSIVE": 1500}
    thresh_pct = style_spread_threshold * 100.0

    for i, _dt in enumerate(calendar):
        vs = str(val_state.iloc[i])
        g1 = str(csi500_state.iloc[i])
        g2 = str(chinext_state.iloc[i])
        if g1 == "BEAR" and g2 == "BEAR":
            gs = "BEAR"
        elif (g1 == "BULL" or g2 == "BULL") and g1 != "BEAR" and g2 != "BEAR":
            gs = "BULL"
        else:
            gs = "RANGE"

        pct_ab = breadth["pct_above_ma60"].iloc[i]
        amt_ratio = amount_vs_ma20.iloc[i]
        ld = int(breadth["limit_down"].iloc[i]) if pd.notna(breadth["limit_down"].iloc[i]) else 0

        off_breadth = pd.notna(pct_ab) and float(pct_ab) >= pct_above_ma60_off
        off_vol = pd.notna(amt_ratio) and float(amt_ratio) >= 0.85
        def_breadth = pd.notna(pct_ab) and float(pct_ab) < 0.30

        is_bull_pair = (vs == "BULL" or gs == "BULL") and vs != "BEAR" and gs != "BEAR"
        if is_bull_pair and off_breadth and off_vol:
            raw = "OFFENSIVE"
        elif (vs == "BEAR" and gs == "BEAR") or ((vs == "BEAR" or gs == "BEAR") and def_breadth):
            raw = "DEFENSIVE"
        else:
            raw = "STRUCTURAL"

        v_chg = val_pct_chg.iloc[i]
        g_chgs = [x for x in (csi500_pct_chg.iloc[i], chinext_pct_chg.iloc[i]) if pd.notna(x)]
        g_chg = float(np.mean(g_chgs)) if g_chgs else np.nan
        crash = (
            pd.notna(v_chg)
            and float(v_chg) < -3.5
            and pd.notna(g_chg)
            and float(g_chg) < -3.5
            and ld > 80
        )

        if i == 0:
            confirmed = "DEFENSIVE" if crash else raw
        elif crash:
            confirmed = "DEFENSIVE"
        elif raw == prev_raw:
            confirmed = raw
        prev_raw = raw

        v_r20 = val_ret20.iloc[i]
        g_r20s = [x for x in (csi500_ret20.iloc[i], chinext_ret20.iloc[i]) if pd.notna(x)]
        g_r20 = float(np.mean(g_r20s)) if g_r20s else np.nan
        spread = float(g_r20 - v_r20) if pd.notna(v_r20) and pd.notna(g_r20) else 0.0
        if spread > thresh_pct:
            style = "GROWTH_LEADING"
        elif spread < -thresh_pct:
            style = "VALUE_LEADING"
        else:
            style = "BALANCED"

        rows.append(
            {
                "value_state": vs,
                "growth_state": gs,
                "pct_above_ma60": float(pct_ab) if pd.notna(pct_ab) else np.nan,
                "amount_yi": float(breadth["amount_yi"].iloc[i]),
                "amount_vs_ma20": float(amt_ratio) if pd.notna(amt_ratio) else np.nan,
                "limit_down": ld,
                "crash_override": bool(crash),
                "raw_regime": raw,
                "confirmed_regime": confirmed,
                "target_equity_bps": target_bps_map[confirmed],
                "style": style,
                "style_spread_pct": spread,
            }
        )

    return pd.DataFrame(rows, index=calendar)
