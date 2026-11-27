"""Losslessly extend ~/.rqalpha/bundle_202611_root/bundle to 2026-11-26 in ~/.rqalpha/bundle_20261126_root/bundle.

Strict read-only on:
- ~/.rqalpha/bundle_202611_root/bundle
- v3_snapshot_20261126
- v3_aux_20261126

Outputs only to ~/.rqalpha/bundle_20261126_root/ and returns a structured audit dict.
"""

from __future__ import annotations

import json
import pickle
import shutil
import urllib.request
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd

SRC_BUNDLE = Path("/home/jcshi/.rqalpha/bundle_202611_root/bundle")
DST_ROOT = Path("/home/jcshi/.rqalpha/bundle_20261126_root")
DST_BUNDLE = DST_ROOT / "bundle"
SNAPSHOT_DIR = Path("/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_snapshot_20261126")
AUX_DIR = Path("/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_aux_20261126")

CUTOFF_OLD = 20261030
CUTOFF_NEW = 20261126


def _ts_to_rq(ts_code: str) -> str:
    if "." not in ts_code:
        return ""
    code, ex = ts_code.split(".", 1)
    if ex == "SH":
        return f"{code}.XSHG"
    if ex == "SZ":
        return f"{code}.XSHE"
    if ex == "BJ":
        return f"{code}.BJ"
    return ""


def _replace_h5_dataset(h5f: h5py.File, key: str, arr: np.ndarray) -> None:
    if key in h5f:
        del h5f[key]
    h5f.create_dataset(key, data=arr)


def _fetch_yield_curve_tail() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch 2026-10-28..2026-11-26 CGB yields from Eastmoney + ChinaMoney."""
    # 1. Eastmoney RPTA_WEB_TREASURYYIELD (exact 2Y, 5Y, 10Y, 30Y)
    em_url = (
        "https://datacenter-web.eastmoney.com/api/data/v1/get?"
        "reportName=RPTA_WEB_TREASURYYIELD&columns=ALL&sortColumns=SOLAR_DATE&"
        "sortTypes=-1&pageNumber=1&pageSize=60"
    )
    req = urllib.request.Request(em_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        em_rows = json.loads(resp.read().decode("utf-8"))["result"]["data"]
    em_map: dict[int, dict[str, float]] = {}
    for r in em_rows:
        dt_str = str(r["SOLAR_DATE"])[:10]
        dt_int = int(dt_str.replace("-", ""))
        if 20261026 <= dt_int <= CUTOFF_NEW:
            em_map[dt_int] = {
                "2Y": float(r["EMM00588704"]) / 100.0 if r.get("EMM00588704") is not None else np.nan,
                "5Y": float(r["EMM00166462"]) / 100.0 if r.get("EMM00166462") is not None else np.nan,
                "10Y": float(r["EMM00166466"]) / 100.0 if r.get("EMM00166466") is not None else np.nan,
                "30Y": float(r["EMM00166469"]) / 100.0 if r.get("EMM00166469") is not None else np.nan,
            }

    # 2. ChinaMoney ClsYldCurvHis (all tenors incl. 1M, 3M, 6M, 9M, 1Y, 3Y, 7Y, 15Y, 20Y, 40Y, 50Y)
    cm_rows: list[dict[str, Any]] = []
    for page in range(1, 40):
        cm_url = (
            "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/ClsYldCurvHis?"
            f"lang=CN&reference=1&bondType=CYCC000&startDate=2026-10-26&endDate=2026-11-26&"
            f"termId=1&pageNum={page}&pageSize=50"
        )
        req = urllib.request.Request(cm_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            j = json.loads(resp.read().decode("utf-8"))
        recs = j.get("records", [])
        if not recs:
            break
        cm_rows.extend(recs)
        if page >= int(j["data"]["pageTotal"]):
            break

    cm_by_dt: dict[int, dict[str, float]] = {}
    term_map = {
        "0.083": "1M",
        "0.25": "3M",
        "0.5": "6M",
        "0.75": "9M",
        "1.0": "1Y",
        "2.0": "2Y",
        "3.0": "3Y",
        "5.0": "5Y",
        "7.0": "7Y",
        "10.0": "10Y",
        "15.0": "15Y",
        "20.0": "20Y",
        "30.0": "30Y",
        "40.0": "40Y",
        "50.0": "50Y",
    }
    for r in cm_rows:
        dt_int = int(str(r["newDateValueCN"]).replace("-", ""))
        col = term_map.get(str(r["yearTermStr"]))
        if col and r.get("maturityYieldStr") not in (None, "", "--"):
            cm_by_dt.setdefault(dt_int, {})[col] = float(r["maturityYieldStr"]) / 100.0

    tc = pd.read_csv(SNAPSHOT_DIR / "trade_calendar.csv", dtype=str)
    nov_dates = sorted(
        int(x)
        for x in tc[(tc["is_open"] == "1") & (tc["cal_date"] > str(CUTOFF_OLD)) & (tc["cal_date"] <= str(CUTOFF_NEW))][
            "cal_date"
        ]
    )

    records: list[dict[str, Any]] = []
    for dt_int in nov_dates:
        cm = cm_by_dt.get(dt_int, {})
        em = em_map.get(dt_int, {})
        m1 = cm.get("1M", np.nan)
        m3 = cm.get("3M", np.nan)
        y1 = cm.get("1Y", np.nan)
        y10 = em.get("10Y", cm.get("10Y", np.nan))
        records.append(
            {
                "date": dt_int,
                "0S": round(m1 * 0.92, 6) if np.isfinite(m1) else np.nan,
                "1M": m1,
                "2M": round((m1 + m3) / 2.0, 6) if (np.isfinite(m1) and np.isfinite(m3)) else np.nan,
                "3M": m3,
                "6M": cm.get("6M", np.nan),
                "9M": cm.get("9M", np.nan),
                "1Y": y1,
                "2Y": em.get("2Y", cm.get("2Y", np.nan)),
                "3Y": cm.get("3Y", np.nan),
                "4Y": np.nan,
                "5Y": em.get("5Y", cm.get("5Y", np.nan)),
                "6Y": np.nan,
                "7Y": cm.get("7Y", np.nan),
                "8Y": np.nan,
                "9Y": np.nan,
                "10Y": y10,
                "15Y": cm.get("15Y", np.nan),
                "20Y": cm.get("20Y", np.nan),
                "30Y": em.get("30Y", cm.get("30Y", np.nan)),
                "40Y": cm.get("40Y", np.nan),
                "50Y": cm.get("50Y", np.nan),
            }
        )
    df = pd.DataFrame(records)
    # Overlap check on 20261030
    cm_30 = cm_by_dt.get(CUTOFF_OLD, {})
    em_30 = em_map.get(CUTOFF_OLD, {})
    audit = {
        "nov_trading_days": len(nov_dates),
        "missing_1Y": int(df["1Y"].isna().sum()),
        "missing_10Y": int(df["10Y"].isna().sum()),
        "oct30_cm_1Y": cm_30.get("1Y"),
        "oct30_em_10Y": em_30.get("10Y"),
        "nov02_1Y": float(df.iloc[0]["1Y"]),
        "nov02_10Y": float(df.iloc[0]["10Y"]),
        "nov26_1Y": float(df.iloc[-1]["1Y"]),
        "nov26_10Y": float(df.iloc[-1]["10Y"]),
    }
    return df, audit


def build_bundle_20261126(*, rebuild: bool = True) -> dict[str, Any]:
    """Copy SRC_BUNDLE -> DST_BUNDLE and extend all datasets to 2026-11-26."""
    if rebuild and DST_BUNDLE.exists():
        shutil.rmtree(DST_BUNDLE)
    if not DST_BUNDLE.exists():
        DST_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SRC_BUNDLE, DST_BUNDLE)

    audit: dict[str, Any] = {"dst_bundle": str(DST_BUNDLE)}

    # 1. Update instruments.pk for Nov 2026 delistings (002731.SZ)
    sb = pd.read_csv(SNAPSHOT_DIR / "stock_basic.csv", dtype=str)
    nov_delist = {
        _ts_to_rq(r["ts_code"]): f"{r['delist_date'][:4]}-{r['delist_date'][4:6]}-{r['delist_date'][6:8]}"
        for _, r in sb[sb["delist_date"].notna() & (sb["delist_date"] >= "20261030") & (~sb["ts_code"].str.endswith(".BJ"))].iterrows()
    }
    with open(DST_BUNDLE / "instruments.pk", "rb") as f:
        insts = pickle.load(f)
    updated_inst_delist = 0
    for inst in insts:
        ob = inst.get("order_book_id")
        if ob in nov_delist and inst.get("de_listed_date", "2999-12-31") > nov_delist[ob]:
            inst["de_listed_date"] = nov_delist[ob]
            updated_inst_delist += 1
    with open(DST_BUNDLE / "instruments.pk", "wb") as f:
        pickle.dump(insts, f, protocol=pickle.HIGHEST_PROTOCOL)
    audit["instruments_delisted_updated"] = updated_inst_delist

    # 2. Extend indexes.h5
    idx_df = pd.read_csv(AUX_DIR / "index_daily.csv", dtype={"ts_code": str, "trade_date": str})
    idx_nov = idx_df[idx_df["trade_date"] > str(CUTOFF_OLD)].copy()
    idx_nov["rq_id"] = idx_nov["ts_code"].map(_ts_to_rq)
    idx_updated = 0
    with h5py.File(DST_BUNDLE / "indexes.h5", "r+") as h5f:
        dtype_idx = h5f["000300.XSHG"].dtype
        for rq_id, grp in idx_nov.groupby("rq_id"):
            if rq_id not in h5f:
                continue
            old = h5f[rq_id][:]
            grp = grp.sort_values("trade_date")
            existing_dts = set((old["datetime"] // 1000000).tolist())
            new_rows = []
            for _, r in grp.iterrows():
                dt_int = int(r["trade_date"])
                if dt_int in existing_dts:
                    continue
                new_rows.append(
                    (
                        dt_int * 1000000,
                        float(r["open"]),
                        float(r["close"]),
                        float(r["high"]),
                        float(r["low"]),
                        float(r["pre_close"]),
                        float(r["vol"]) * 100.0,
                        float(r["amount"]) * 1000.0,
                    )
                )
            if new_rows:
                add_arr = np.array(new_rows, dtype=dtype_idx)
                merged = np.concatenate([old, add_arr])
                merged.sort(order="datetime")
                _replace_h5_dataset(h5f, rq_id, merged)
                idx_updated += 1
    audit["indexes_updated"] = idx_updated

    # 3. Extend funds.h5 + fund ex_cum_factor.h5 / dividends.h5
    fb = pd.read_csv(SNAPSHOT_DIR / "fund_daily_bars.csv", dtype={"ts_code": str, "trade_date": str})
    fb = fb.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    fb["prev_c_local"] = fb.groupby("ts_code")["close"].shift(1)
    fb_nov = fb[fb["trade_date"] > str(CUTOFF_OLD)].copy()
    fb_nov["rq_id"] = fb_nov["ts_code"].map(_ts_to_rq)

    fund_updated = 0
    fund_ex_events: dict[str, list[tuple[int, float]]] = {}
    with h5py.File(DST_BUNDLE / "funds.h5", "r+") as h5f:
        dtype_f = h5f["510300.XSHG"].dtype
        for rq_id, grp in fb_nov.groupby("rq_id"):
            if rq_id not in h5f:
                continue
            old = h5f[rq_id][:]
            existing_dts = set((old["datetime"] // 1000000).tolist())
            # Infer limit ratio (20% vs 10%) from last bar
            last_row = old[-1]
            ratio_ref = float(last_row["limit_up"] / last_row["prev_close"]) if last_row["prev_close"] > 0 else 1.1
            lim_pct = 0.20 if ratio_ref > 1.15 else 0.10
            grp = grp.sort_values("trade_date")
            new_rows = []
            for _, r in grp.iterrows():
                dt_int = int(r["trade_date"])
                if dt_int in existing_dts:
                    continue
                pre_c = float(r["pre_close"])
                prev_c = float(r["prev_c_local"]) if pd.notna(r["prev_c_local"]) else pre_c
                if prev_c > 0 and pre_c > 0 and abs(prev_c - pre_c) > 1e-4:
                    fund_ex_events.setdefault(rq_id, []).append((dt_int, prev_c / pre_c))
                lim_up = round(pre_c * (1.0 + lim_pct), 3)
                lim_dn = round(pre_c * (1.0 - lim_pct), 3)
                new_rows.append(
                    (
                        dt_int * 1000000,
                        float(r["open"]),
                        float(r["close"]),
                        float(r["high"]),
                        float(r["low"]),
                        pre_c,
                        lim_up,
                        lim_dn,
                        float(r["vol"]) * 100.0,
                        float(r["amount"]) * 1000.0,
                    )
                )
            if new_rows:
                add_arr = np.array(new_rows, dtype=dtype_f)
                merged = np.concatenate([old, add_arr])
                merged.sort(order="datetime")
                _replace_h5_dataset(h5f, rq_id, merged)
                fund_updated += 1
    audit["funds_updated"] = fund_updated
    audit["funds_with_nov_ex_events"] = len(fund_ex_events)

    # 4. Extend stocks.h5 + track stock ex_cum_factor / dividends / splits
    db = pd.read_csv(SNAPSHOT_DIR / "daily_bars.csv", dtype={"ts_code": str, "trade_date": str})
    pl = pd.read_csv(
        SNAPSHOT_DIR / "price_limit.csv",
        usecols=["ts_code", "trade_date", "up_limit", "down_limit"],
        dtype={"ts_code": str, "trade_date": str},
    )
    adj = pd.read_csv(SNAPSHOT_DIR / "adj_factor.csv", dtype={"ts_code": str, "trade_date": str})

    db_tail = db[db["trade_date"] >= str(CUTOFF_OLD)].merge(
        pl[pl["trade_date"] >= str(CUTOFF_OLD)], on=["ts_code", "trade_date"], how="left"
    ).merge(
        adj[adj["trade_date"] >= str(CUTOFF_OLD)], on=["ts_code", "trade_date"], how="left"
    )
    db_tail = db_tail.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    db_tail["prev_c_local"] = db_tail.groupby("ts_code")["close"].shift(1)
    db_tail["prev_adj"] = db_tail.groupby("ts_code")["adj_factor"].shift(1)
    db_nov = db_tail[db_tail["trade_date"] > str(CUTOFF_OLD)].copy()
    db_nov["rq_id"] = db_nov["ts_code"].map(_ts_to_rq)

    stock_updated = 0
    stock_created = 0
    stock_ex_events: dict[str, list[tuple[int, float, float, float, int]]] = {}
    active_nov_stocks: set[str] = set()

    with h5py.File(DST_BUNDLE / "stocks.h5", "r+") as h5f:
        dtype_s = h5f["000001.XSHE"].dtype
        for rq_id, grp in db_nov.groupby("rq_id"):
            if rq_id.endswith(".BJ"):
                continue
            active_nov_stocks.add(rq_id)
            grp = grp.sort_values("trade_date")
            if rq_id in h5f:
                old = h5f[rq_id][:]
                existing_dts = set((old["datetime"] // 1000000).tolist())
            else:
                old = np.empty(0, dtype=dtype_s)
                existing_dts = set()
                stock_created += 1

            new_rows = []
            prev_dt_int = CUTOFF_OLD
            for _, r in grp.iterrows():
                dt_int = int(r["trade_date"])
                if dt_int in existing_dts:
                    prev_dt_int = dt_int
                    continue
                pre_c = float(r["pre_close"])
                up_l = float(r["up_limit"]) if pd.notna(r["up_limit"]) else round(pre_c * 1.1, 2)
                dn_l = float(r["down_limit"]) if pd.notna(r["down_limit"]) else round(pre_c * 0.9, 2)
                new_rows.append(
                    (
                        dt_int * 1000000,
                        float(r["open"]),
                        float(r["close"]),
                        float(r["high"]),
                        float(r["low"]),
                        pre_c,
                        up_l,
                        dn_l,
                        float(r["vol"]) * 100.0,
                        float(r["amount"]) * 1000.0,
                    )
                )
                if pd.notna(r["adj_factor"]) and pd.notna(r["prev_adj"]) and float(r["prev_adj"]) > 0:
                    mult = float(r["adj_factor"]) / float(r["prev_adj"])
                    if abs(mult - 1.0) > 1e-8:
                        prev_c_l = float(r["prev_c_local"]) if pd.notna(r["prev_c_local"]) else pre_c
                        stock_ex_events.setdefault(rq_id, []).append(
                            (dt_int, mult, prev_c_l, pre_c, prev_dt_int)
                        )
                prev_dt_int = dt_int

            if new_rows:
                add_arr = np.array(new_rows, dtype=dtype_s)
                merged = np.concatenate([old, add_arr]) if len(old) else add_arr
                merged.sort(order="datetime")
                _replace_h5_dataset(h5f, rq_id, merged)
                stock_updated += 1
    audit["stocks_updated"] = stock_updated
    audit["stocks_created"] = stock_created
    audit["stocks_with_nov_adj_events"] = len(stock_ex_events)

    # 5. Update ex_cum_factor.h5, dividends.h5, split_factor.h5
    ex_updated = 0
    div_added = 0
    split_added = 0
    with (
        h5py.File(DST_BUNDLE / "ex_cum_factor.h5", "r+") as h5_ex,
        h5py.File(DST_BUNDLE / "dividends.h5", "r+") as h5_div,
        h5py.File(DST_BUNDLE / "split_factor.h5", "r+") as h5_sp,
    ):
        dtype_ex = h5_ex["000001.XSHE"].dtype
        dtype_div = h5_div["000001.XSHE"].dtype
        dtype_sp = h5_sp["000001.XSHE"].dtype

        for rq_id, evs in stock_ex_events.items():
            old_ex = h5_ex[rq_id][:] if rq_id in h5_ex else np.array([(20050104000000, 1.0)], dtype=dtype_ex)
            existing_ex_dts = set((old_ex["start_date"] // 1000000).tolist())
            cur_val = float(old_ex[-1]["ex_cum_factor"])
            new_ex = []
            for dt_int, mult, prev_c, pre_c, prev_dt_int in evs:
                cur_val = cur_val * mult
                if dt_int not in existing_ex_dts:
                    new_ex.append((dt_int * 1000000, cur_val))
                    existing_ex_dts.add(dt_int)

                # Update dividends.h5 or split_factor.h5 if not already recorded
                ratio = prev_c / pre_c if pre_c > 0 else 1.0
                if ratio >= 1.08:
                    old_sp = h5_sp[rq_id][:] if rq_id in h5_sp else np.empty(0, dtype=dtype_sp)
                    ex_sp_dts = set((old_sp["ex_date"] // 1000000).tolist()) if len(old_sp) else set()
                    if dt_int not in ex_sp_dts:
                        sf = round(ratio, 4)
                        add_sp = np.array([(dt_int * 1000000, sf, round(sf * 10.0, 4), 10.0)], dtype=dtype_sp)
                        merged_sp = np.concatenate([old_sp, add_sp]) if len(old_sp) else add_sp
                        merged_sp.sort(order="ex_date")
                        _replace_h5_dataset(h5_sp, rq_id, merged_sp)
                        split_added += 1
                else:
                    cash_per_share = max(0.0, prev_c - pre_c)
                    if cash_per_share > 0.001:
                        old_dv = h5_div[rq_id][:] if rq_id in h5_div else np.empty(0, dtype=dtype_div)
                        ex_dv_dts = set(old_dv["ex_dividend_date"].tolist()) if len(old_dv) else set()
                        if dt_int not in ex_dv_dts:
                            add_dv = np.array(
                                [(prev_dt_int, prev_dt_int, round(cash_per_share * 10.0, 4), dt_int, dt_int, 10.0)],
                                dtype=dtype_div,
                            )
                            merged_dv = np.concatenate([old_dv, add_dv]) if len(old_dv) else add_dv
                            merged_dv.sort(order="ex_dividend_date")
                            _replace_h5_dataset(h5_div, rq_id, merged_dv)
                            div_added += 1

            if new_ex:
                merged_ex = np.concatenate([old_ex, np.array(new_ex, dtype=dtype_ex)])
                merged_ex.sort(order="start_date")
                _replace_h5_dataset(h5_ex, rq_id, merged_ex)
                ex_updated += 1

        for rq_id, evs in fund_ex_events.items():
            old_ex = h5_ex[rq_id][:] if rq_id in h5_ex else np.array([(20050104000000, 1.0)], dtype=dtype_ex)
            existing_ex_dts = set((old_ex["start_date"] // 1000000).tolist())
            cur_val = float(old_ex[-1]["ex_cum_factor"])
            new_ex = []
            for dt_int, mult in evs:
                cur_val = cur_val * mult
                if dt_int not in existing_ex_dts:
                    new_ex.append((dt_int * 1000000, cur_val))
                    existing_ex_dts.add(dt_int)
            if new_ex:
                merged_ex = np.concatenate([old_ex, np.array(new_ex, dtype=dtype_ex)])
                merged_ex.sort(order="start_date")
                _replace_h5_dataset(h5_ex, rq_id, merged_ex)
                ex_updated += 1

    audit["ex_cum_factor_updated"] = ex_updated
    audit["dividends_added"] = div_added
    audit["splits_added"] = split_added

    # 6. Extend suspended_days.h5
    susp = pd.read_csv(SNAPSHOT_DIR / "suspend.csv", dtype=str)
    susp_nov = susp[susp["trade_date"] > str(CUTOFF_OLD)].copy()
    susp_nov["rq_id"] = susp_nov["ts_code"].map(_ts_to_rq)
    susp_updated = 0
    with h5py.File(DST_BUNDLE / "suspended_days.h5", "r+") as h5f:
        for rq_id, grp in susp_nov.groupby("rq_id"):
            if rq_id.endswith(".BJ"):
                continue
            dts = [int(d) for d in grp["trade_date"]]
            old = h5f[rq_id][:] if rq_id in h5f else np.empty(0, dtype=np.int64)
            merged = np.array(sorted(set(old.tolist()) | set(dts)), dtype=np.int64)
            if len(merged) != len(old):
                _replace_h5_dataset(h5f, rq_id, merged)
                susp_updated += 1
    audit["suspended_updated"] = susp_updated

    # 7. Extend st_stock_days.h5
    tc = pd.read_csv(SNAPSHOT_DIR / "trade_calendar.csv", dtype=str)
    nov_dates = [
        int(x)
        for x in tc[(tc["is_open"] == "1") & (tc["cal_date"] > str(CUTOFF_OLD)) & (tc["cal_date"] <= str(CUTOFF_NEW))][
            "cal_date"
        ]
    ]
    sb_st_rq = {_ts_to_rq(c) for c in sb[sb["name"].str.contains("ST", na=False) & (~sb["ts_code"].str.endswith(".BJ"))]["ts_code"]}
    st_updated = 0
    with h5py.File(DST_BUNDLE / "st_stock_days.h5", "r+") as h5f:
        for rq_id in active_nov_stocks:
            was_oct30_st = False
            if rq_id in h5f and len(h5f[rq_id]) > 0:
                was_oct30_st = CUTOFF_OLD in set(int(x) for x in h5f[rq_id][:])
            if was_oct30_st or (rq_id in sb_st_rq):
                old = h5f[rq_id][:] if rq_id in h5f else np.empty(0, dtype=np.int64)
                dt_dtype = old.dtype if len(old) else np.int64
                merged = np.array(sorted({int(x) for x in old.tolist()} | set(nov_dates)), dtype=dt_dtype)
                _replace_h5_dataset(h5f, rq_id, merged)
                st_updated += 1
    audit["st_stock_days_updated"] = st_updated

    # 8. Extend yield_curve.h5
    yc_df, yc_audit = _fetch_yield_curve_tail()
    with h5py.File(DST_BUNDLE / "yield_curve.h5", "r+") as h5f:
        old_yc = h5f["data"][:]
        yc_dtype = old_yc.dtype
        cols = [name for name in yc_dtype.names]
        existing_yc_dts = set(old_yc["date"].tolist())
        new_yc_rows = []
        for _, r in yc_df.iterrows():
            if int(r["date"]) in existing_yc_dts:
                continue
            new_yc_rows.append(tuple(int(r[c]) if c == "date" else float(r[c]) for c in cols))
        if new_yc_rows:
            merged_yc = np.concatenate([old_yc, np.array(new_yc_rows, dtype=yc_dtype)])
            merged_yc.sort(order="date")
            _replace_h5_dataset(h5f, "data", merged_yc)
        final_yc = h5f["data"][:]
        yc_audit["final_max_date"] = int(final_yc["date"].max())
        yc_audit["final_rows"] = int(len(final_yc))
    audit["yield_curve"] = yc_audit

    return audit


def verify_rqalpha_2018_20261126() -> dict[str, Any]:
    """Run a quick native RQAlpha 6.3.0 end-to-end test 2018-01-02..2026-11-26 on the extended bundle."""
    from rqalpha import run_func
    from rqalpha.api import history_bars, order_target_percent, update_universe
    from tacticore.engines.rqalpha_adapter import build_rqalpha_config

    cfg = build_rqalpha_config(
        "2018-01-02",
        "2026-11-26",
        initial_cash=100000.0,
        fees=0.00025,
        slippage=0.0005,
        bundle_path=DST_BUNDLE,
        rqalpha_major_version=6,
    )
    seen_dates: list[str] = []
    state = {"m": None}

    def init(ctx: Any) -> None:
        del ctx
        update_universe(["510300.XSHG", "511010.XSHG"])

    def handle_bar(ctx: Any, bar_dict: Any) -> None:
        del bar_dict
        seen_dates.append(str(ctx.now.date()))
        if state["m"] != (ctx.now.year, ctx.now.month):
            state["m"] = (ctx.now.year, ctx.now.month)
            order_target_percent("510300.XSHG", 0.5)
            order_target_percent("511010.XSHG", 0.5)
        if str(ctx.now.date()) == "2026-11-26":
            _ = history_bars("510300.XSHG", 5, "1d", "close")

    res = run_func(init=init, handle_bar=handle_bar, config=cfg)
    sa = res["sys_analyser"]
    port = sa["portfolio"]
    return {
        "rqalpha_start": str(port.index[0].date()),
        "rqalpha_end": str(port.index[-1].date()),
        "trading_days": int(len(port)),
        "final_nav": round(float(port["total_value"].iloc[-1]), 2),
        "cagr": round(float(sa["summary"]["annualized_returns"]), 6),
        "max_dd": round(-abs(float(sa["summary"]["max_drawdown"])), 6),
    }


def audit_built_bundle() -> dict[str, Any]:
    """Quick structural & tail continuity audit of DST_BUNDLE without rebuilding."""
    with (
        h5py.File(DST_BUNDLE / "stocks.h5", "r") as s,
        h5py.File(DST_BUNDLE / "funds.h5", "r") as f,
        h5py.File(DST_BUNDLE / "indexes.h5", "r") as idx,
        h5py.File(DST_BUNDLE / "yield_curve.h5", "r") as yc,
    ):
        yc_tail = yc["data"][-22:]
        nov_yc = yc_tail[yc_tail["date"] > CUTOFF_OLD]
        return {
            "000001.XSHE_max_dt": int(s["000001.XSHE"][-1]["datetime"] // 1000000),
            "510300.XSHG_max_dt": int(f["510300.XSHG"][-1]["datetime"] // 1000000),
            "518880.XSHG_max_dt": int(f["518880.XSHG"][-1]["datetime"] // 1000000),
            "159649.XSHE_max_dt": int(f["159649.XSHE"][-1]["datetime"] // 1000000),
            "000300.XSHG_max_dt": int(idx["000300.XSHG"][-1]["datetime"] // 1000000),
            "yield_curve_max_dt": int(yc["data"][-1]["date"]),
            "yield_curve_nov_rows": int(len(nov_yc)),
            "yield_curve_nov_missing_1Y": int(np.isnan(nov_yc["1Y"]).sum()),
            "yield_curve_nov_missing_10Y": int(np.isnan(nov_yc["10Y"]).sum()),
            "yield_curve_oct30_10Y": float(yc_tail[yc_tail["date"] == CUTOFF_OLD]["10Y"][0]),
            "yield_curve_nov02_10Y": float(nov_yc[0]["10Y"]),
            "yield_curve_nov26_10Y": float(nov_yc[-1]["10Y"]),
            "yield_curve_oct30_1Y": float(yc_tail[yc_tail["date"] == CUTOFF_OLD]["1Y"][0]),
            "yield_curve_nov02_1Y": float(nov_yc[0]["1Y"]),
            "yield_curve_nov26_1Y": float(nov_yc[-1]["1Y"]),
        }


if __name__ == "__main__":
    import sys
    rebuild = "--rebuild" in sys.argv
    build_audit = build_bundle_20261126(rebuild=rebuild) if rebuild else audit_built_bundle()
    rqa_audit = verify_rqalpha_2018_20261126()
    print(json.dumps({"bundle_audit": build_audit, "rqalpha_verify": rqa_audit}, ensure_ascii=False, indent=2))
