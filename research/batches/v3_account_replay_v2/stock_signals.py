"""Strict causal OOS BP1_PULLBACK stock signals using PIT circ_mv (>=50亿) and QualityCore."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from research.ashare.engines.bundle_source import bundle_calendar, open_bundle_source
from research.ashare.v3_data import rq_to_ts
from research.ashare.v3_data_202611 import (
    AUX_DIR_202611,
    BUNDLE_CUTOFF_202611,
    BUNDLE_PATH_202611,
    SNAPSHOT_DIR_202611,
)

MAIN_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")
# daily_basic.circ_mv is stored in 万元 (10k CNY); 500,000 万元 = 50 亿元
MIN_CIRC_MV_WAN = 500_000.0
DEFAULT_WARMUP_START = pd.Timestamp("2022-07-01")
DEFAULT_OOS_START = pd.Timestamp("2024-02-01")


@dataclass(frozen=True)
class SwingCandidateV2:
    order_book_id: str
    ts_code: str
    bp_type: str
    score: float
    rps60: float
    rps120: float
    ref_close_raw: float
    hard_stop_raw: float
    circ_mv_wan: float
    quality_core_ok: bool


def _is_mainboard(order_book_id: str) -> bool:
    code = order_book_id.split(".", 1)[0]
    return not order_book_id.endswith(".BJ") and code.startswith(MAIN_PREFIXES)


def _wilder_rsi14(close: pd.Series) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - (100.0 / (1.0 + rs))).fillna(100.0)


def _load_pit_financial_table_202611() -> dict[str, dict[str, np.ndarray]]:
    fi = pd.read_csv(
        SNAPSHOT_DIR_202611 / "financial_indicator.csv",
        usecols=["ts_code", "end_date", "ann_date", "roe", "ocf_to_profit", "eps"],
        dtype={"ts_code": str, "end_date": str, "ann_date": str},
    )
    fi = fi[fi["ann_date"].notna() & fi["ann_date"].str.match(r"^\d{8}$", na=False)].copy()
    fi = fi.sort_values(["ts_code", "ann_date", "end_date"]).reset_index(drop=True)
    mmdd = fi["end_date"].str.slice(4, 8)
    mult = mmdd.map({"0331": 4.0, "0630": 2.0, "0930": 4.0 / 3.0, "1231": 1.0}).fillna(1.0)
    ann_roe = fi["roe"].astype(float) * mult
    fi["qc_ok"] = (
        (ann_roe > 5.0)
        & (fi["eps"].astype(float) > 0.0)
        & (fi["ocf_to_profit"].astype(float) > 50.0)
    ).astype(bool)
    fi["ann_int"] = fi["ann_date"].astype(np.int64)
    fi["end_dt_ns"] = pd.to_datetime(fi["end_date"]).astype("int64")

    table: dict[str, dict[str, np.ndarray]] = {}
    for code, grp in fi.groupby("ts_code", sort=False):
        table[str(code)] = {
            "ann_int": grp["ann_int"].to_numpy(dtype=np.int64),
            "end_ns": grp["end_dt_ns"].to_numpy(dtype=np.int64),
            "qc_ok": grp["qc_ok"].to_numpy(dtype=bool),
        }
    return table


def _lookup_quality_core(
    fin_table: dict[str, dict[str, np.ndarray]],
    ts_code: str,
    trade_date_int: int,
    trade_dt_ns: int,
) -> bool:
    rec = fin_table.get(ts_code)
    if rec is None:
        return False
    idx = int(np.searchsorted(rec["ann_int"], trade_date_int, side="right")) - 1
    if idx < 0:
        return False
    age_days = (trade_dt_ns - int(rec["end_ns"][idx])) / 86_400_000_000_000.0
    if age_days > 550.0 or age_days < 0.0:
        return False
    return bool(rec["qc_ok"][idx])


def load_pit_circ_mv_table() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Load exact-date PIT circ_mv (万元) arrays per ts_code from v3_aux_20261126."""
    db = pd.read_csv(
        AUX_DIR_202611 / "daily_basic_pit.csv",
        usecols=["ts_code", "trade_date", "circ_mv"],
        dtype={"ts_code": str, "trade_date": str, "circ_mv": float},
    )
    db = db[db["trade_date"].notna() & db["circ_mv"].notna()].copy()
    db["dt_int"] = db["trade_date"].astype(np.int64)
    db = db.sort_values(["ts_code", "dt_int"])
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for code, grp in db.groupby("ts_code", sort=False):
        out[str(code)] = (
            grp["dt_int"].to_numpy(dtype=np.int64),
            grp["circ_mv"].to_numpy(dtype=np.float64),
        )
    return out


def lookup_exact_circ_mv(
    circ_table: dict[str, tuple[np.ndarray, np.ndarray]], ts_code: str, trade_date_int: int
) -> float | None:
    """Exact-date lookup without forward-fill."""
    rec = circ_table.get(ts_code)
    if rec is None:
        return None
    dts, vals = rec
    idx = int(np.searchsorted(dts, trade_date_int))
    if idx < len(dts) and int(dts[idx]) == trade_date_int:
        v = float(vals[idx])
        return v if np.isfinite(v) else None
    return None


def build_causal_bp1_candidates_202611(
    *,
    warmup_start: pd.Timestamp = DEFAULT_WARMUP_START,
    oos_start: pd.Timestamp = DEFAULT_OOS_START,
    bundle_end: pd.Timestamp = BUNDLE_CUTOFF_202611,
) -> tuple[dict[str, list[SwingCandidateV2]], dict[str, Any]]:
    """Build strictly causal v3.2.1 BP1_PULLBACK candidates (no industry top-30 gate)."""
    src = open_bundle_source(BUNDLE_PATH_202611)
    cal = bundle_calendar(src, warmup_start, bundle_end)
    cal_ints = np.array([int(d.strftime("%Y%m%d")) for d in cal], dtype=np.int64)
    cal_set = set(cal_ints.tolist())
    n_days = len(cal_ints)
    oos_start_int = int(oos_start.strftime("%Y%m%d"))

    all_cs = [i for i in src.get_instruments(types=["CS"]) if not i.order_book_id.endswith(".BJ")]
    end_dt = bundle_end.to_pydatetime()

    ret60_cols: dict[str, np.ndarray] = {}
    ret120_cols: dict[str, np.ndarray] = {}
    main_insts: list[Any] = []
    bars_post_cache: dict[str, Any] = {}

    for inst in all_cs:
        listed = pd.Timestamp(inst.listed_date)
        delisted = pd.Timestamp(inst.de_listed_date)
        if listed > bundle_end or delisted < cal[0]:
            continue
        eff_end = min(end_dt, delisted.to_pydatetime()) if delisted.year < 2999 else end_dt
        bars_p = src.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="post",
            adjust_orig=eff_end,
        )
        if bars_p is None or len(bars_p) < 125:
            continue
        c_p = pd.Series(bars_p["close"].astype(float))
        r60 = (c_p / c_p.shift(60) - 1.0).to_numpy(dtype=np.float32)
        r120 = (c_p / c_p.shift(120) - 1.0).to_numpy(dtype=np.float32)
        r60[:120] = np.nan
        r120[:120] = np.nan
        dts = (bars_p["datetime"] // 1000000).astype(np.int64)
        mask = np.isin(dts, list(cal_set))
        if not mask.any():
            continue
        idxs = np.searchsorted(cal_ints, dts[mask])
        arr60 = np.full(n_days, np.nan, dtype=np.float32)
        arr120 = np.full(n_days, np.nan, dtype=np.float32)
        arr60[idxs] = r60[mask]
        arr120[idxs] = r120[mask]
        ob = inst.order_book_id
        ret60_cols[ob] = arr60
        ret120_cols[ob] = arr120
        if _is_mainboard(ob):
            main_insts.append(inst)
            bars_post_cache[ob] = bars_p

    rps60_df = pd.DataFrame(ret60_cols, index=cal).rank(axis=1, pct=True) * 100.0
    rps120_df = pd.DataFrame(ret120_cols, index=cal).rank(axis=1, pct=True) * 100.0
    fin_table = _load_pit_financial_table_202611()
    circ_table = load_pit_circ_mv_table()

    candidates_by_date: dict[str, list[SwingCandidateV2]] = {}
    stats = {
        "bp1_tech_raw": 0,
        "st_filtered": 0,
        "qc_filtered": 0,
        "circ_mv_filtered": 0,
        "circ_mv_missing": 0,
        "qualified_bp1": 0,
    }

    for inst in main_insts:
        ob = inst.order_book_id
        ts_c = rq_to_ts(ob)
        bars_p = bars_post_cache[ob]
        listed_dt = pd.Timestamp(inst.listed_date).normalize()
        delisted_dt = pd.Timestamp(inst.de_listed_date).normalize()
        eff_end = min(end_dt, delisted_dt.to_pydatetime()) if delisted_dt.year < 2999 else end_dt
        bars_r = src.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="none",
        )
        if bars_r is None or len(bars_r) != len(bars_p):
            continue

        dts = (bars_p["datetime"] // 1000000).astype(np.int64)
        c_p = pd.Series(bars_p["close"].astype(float))
        h_p = pd.Series(bars_p["high"].astype(float))
        l_p = pd.Series(bars_p["low"].astype(float))
        v_r = pd.Series(bars_r["volume"].astype(float))
        c_r = pd.Series(bars_r["close"].astype(float))
        o_r = pd.Series(bars_r["open"].astype(float))
        h_r = pd.Series(bars_r["high"].astype(float))
        l_r = pd.Series(bars_r["low"].astype(float))
        amt_r = pd.Series(bars_r["total_turnover"].astype(float))

        ma5 = c_p.rolling(5, min_periods=5).mean()
        ma20 = c_p.rolling(20, min_periods=20).mean()
        ma60 = c_p.rolling(60, min_periods=60).mean()
        vol_ma20 = v_r.rolling(20, min_periods=20).mean()
        amt_ma20 = amt_r.rolling(20, min_periods=20).mean()
        rsi14 = _wilder_rsi14(c_p)
        ret5 = c_p / c_p.shift(5) - 1.0

        in_cal = np.isin(dts, list(cal_set))
        if not in_cal.any():
            continue
        idx_c = np.searchsorted(cal_ints, dts[in_cal])
        r60_series = np.full(len(bars_p), np.nan, dtype=float)
        r120_series = np.full(len(bars_p), np.nan, dtype=float)
        r60_series[in_cal] = rps60_df[ob].to_numpy()[idx_c]
        r120_series[in_cal] = rps120_df[ob].to_numpy()[idx_c]
        s_r60 = pd.Series(r60_series)
        s_r120 = pd.Series(r120_series)

        bar_dates_pd = pd.to_datetime([str(int(x)) for x in dts])
        listed_days = pd.Series((bar_dates_pd - listed_dt).days)
        base_ok = (
            (dts >= oos_start_int)
            & (listed_days >= 250)
            & (c_r > 0.0)
            & (c_r <= 90.0)
            & (h_r > l_r)
            & (v_r > 0.0)
            & (amt_ma20 >= 1.5e8)
            & ((s_r60 >= 80.0) | (s_r120 >= 80.0))
            & (c_p > ma20)
            & (ma20 > ma60)
            & (ma20 > ma20.shift(5))
            & (ma60 > ma60.shift(5))
            & (ret5 < 0.12)
            & ((c_p - ma20) / ma20 <= 0.08)
            & (rsi14 < 75.0)
        )

        hh20 = h_p.rolling(20, min_periods=20).max()
        hit_high_3_8 = pd.Series(False, index=c_p.index)
        for k in range(3, 9):
            hit_high_3_8 = hit_high_3_8 | (
                (h_p.shift(k) >= hh20.shift(k) - 1e-9) & (h_p.shift(k) > c_p)
            )
        low_min_5 = l_p.rolling(5, min_periods=5).min()
        touch_ma20 = (low_min_5 >= ma20 * 0.985) & (low_min_5 <= ma20 * 1.025)
        vol_shrink = v_r.shift(1).rolling(3, min_periods=3).min() <= 0.8 * vol_ma20
        bp1 = (
            base_ok
            & hit_high_3_8
            & touch_ma20
            & vol_shrink
            & (c_r > o_r)
            & (c_p > c_p.shift(1))
            & (c_p > ma5)
        )

        any_hit = np.where(bp1.to_numpy())[0]
        if len(any_hit) == 0:
            continue

        cand_ts = [pd.Timestamp(bar_dates_pd[idx]) for idx in any_hit]
        st_flags = src.is_st_stock(ob, cand_ts)
        low_5d_raw = l_r.rolling(5, min_periods=5).min()
        ma20_raw_approx = c_r * (ma20 / c_p)

        for j, st_flag in zip(any_hit, st_flags, strict=True):
            stats["bp1_tech_raw"] += 1
            if st_flag:
                stats["st_filtered"] += 1
                continue
            dt_int = int(dts[j])
            dt_ts = pd.Timestamp(bar_dates_pd[j])
            if not _lookup_quality_core(fin_table, ts_c, dt_int, int(dt_ts.value)):
                stats["qc_filtered"] += 1
                continue
            circ_mv = lookup_exact_circ_mv(circ_table, ts_c, dt_int)
            if circ_mv is None:
                stats["circ_mv_missing"] += 1
                continue
            if circ_mv < MIN_CIRC_MV_WAN:
                stats["circ_mv_filtered"] += 1
                continue

            ref_c = float(c_r.iloc[j])
            l5 = float(low_5d_raw.iloc[j])
            m20r = float(ma20_raw_approx.iloc[j])
            hard_stop = max(round(ref_c * 0.92, 2), round(min(l5, m20r * 0.97), 2))
            if hard_stop >= ref_c * 0.99:
                hard_stop = round(ref_c * 0.96, 2)
            r60_v = float(s_r60.iloc[j])
            r120_v = float(s_r120.iloc[j])
            score = max(r60_v, r120_v) + 0.001 * ((r60_v + r120_v) / 2.0)

            stats["qualified_bp1"] += 1
            candidates_by_date.setdefault(dt_ts.strftime("%Y-%m-%d"), []).append(
                SwingCandidateV2(
                    order_book_id=ob,
                    ts_code=ts_c,
                    bp_type="BP1_PULLBACK",
                    score=score,
                    rps60=r60_v,
                    rps120=r120_v,
                    ref_close_raw=ref_c,
                    hard_stop_raw=hard_stop,
                    circ_mv_wan=circ_mv,
                    quality_core_ok=True,
                )
            )

    for lst in candidates_by_date.values():
        lst.sort(key=lambda x: (-x.score, x.order_book_id))
    return candidates_by_date, stats
