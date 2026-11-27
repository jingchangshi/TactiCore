"""9-year strictly causal PIT Dividend Spread (DV_TTM_PIT_median - y_10Y) builder & validator.

Reads ONLY from ~/.rqalpha/bundle_20261126_root/bundle and validates against
v3_aux_20261126/daily_basic_pit.csv over 2024-01-02..2026-11-17.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

BUNDLE_20261126 = Path("/home/jcshi/.rqalpha/bundle_20261126_root/bundle")
AUX_DIR = Path("/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_aux_20261126")
REPORTS_DIR = Path("/home/jcshi/workspace/TactiCore/research/ashare/reports")


def _load_bundle_trading_dates(bundle_path: Path, start_int: int, end_int: int) -> np.ndarray:
    td = np.load(bundle_path / "trading_dates.npy")
    td = td[(td >= start_int) & (td <= end_int)]
    return np.sort(td.astype(np.int64))


def _load_yield_10y(bundle_path: Path) -> pd.Series:
    with h5py.File(bundle_path / "yield_curve.h5", "r") as f:
        arr = f["data"][:]
    s = pd.Series(arr["10Y"].astype(np.float64), index=pd.Index(arr["date"].astype(np.int64), name="date_int"))
    return s.sort_index().ffill()


def compute_pit_dividend_spread_series(
    bundle_path: Path = BUNDLE_20261126,
    *,
    warmup_start_int: int = 20131001,
    end_int: int = 20261126,
    top_n_liquid: int = 800,
    rolling_window: int = 756,
    high_enter: float = 0.80,
    high_exit: float = 0.75,
    low_enter: float = 0.15,
    low_exit: float = 0.20,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compute strictly causal 2014..2026-11-26 PIT dividend yield median, spread, and 756d percentile."""
    cal_ints = _load_bundle_trading_dates(bundle_path, warmup_start_int, end_int)
    cal_ts = pd.to_datetime([str(int(d)) for d in cal_ints])
    cal_days_epoch = (cal_ts.asi8 // 86_400_000_000_000).astype(np.int64)
    n_days = len(cal_ints)
    cal_map = {int(d): idx for idx, d in enumerate(cal_ints)}

    with open(bundle_path / "instruments.pk", "rb") as f:
        insts = pickle.load(f)
    cs_lifetimes: dict[str, tuple[int, int]] = {}
    for inst in insts:
        if inst.get("type") != "CS":
            continue
        ob = str(inst["order_book_id"])
        if ob.endswith(".BJ"):
            continue
        ld_raw = str(inst.get("listed_date", "1990-01-01")).replace("-", "")[:8]
        ld = int(ld_raw) if ld_raw.isdigit() and int(ld_raw) > 0 else 19900101
        dd_raw = str(inst.get("de_listed_date", "2999-12-31")).replace("-", "")[:8]
        dd = int(dd_raw) if dd_raw.isdigit() and int(dd_raw) > 0 else 29991231
        cs_lifetimes[ob] = (ld, dd)

    # Pre-allocate dense matrices [n_days, n_stocks] for fast vectorized top-800 cross-section
    h5_stocks = h5py.File(bundle_path / "stocks.h5", "r")
    h5_divs = h5py.File(bundle_path / "dividends.h5", "r")
    h5_splits = h5py.File(bundle_path / "split_factor.h5", "r")
    h5_susp = h5py.File(bundle_path / "suspended_days.h5", "r")

    eligible_obs = sorted(ob for ob in cs_lifetimes if ob in h5_stocks)
    n_stk = len(eligible_obs)
    dv_mat = np.full((n_days, n_stk), np.nan, dtype=np.float32)
    amt_ma20_mat = np.full((n_days, n_stk), np.nan, dtype=np.float32)

    try:
        for col_idx, ob in enumerate(eligible_obs):
            ld, dd = cs_lifetimes[ob]
            if ld > end_int or dd < warmup_start_int:
                continue
            bars = h5_stocks[ob][:]
            if len(bars) == 0:
                continue
            b_dts = (bars["datetime"] // 1000000).astype(np.int64)
            mask = (b_dts >= warmup_start_int) & (b_dts <= end_int) & (b_dts >= ld) & (b_dts <= dd)
            if not mask.any():
                continue
            b_dts = b_dts[mask]
            closes = bars["close"][mask].astype(np.float64)
            turnovers = bars["total_turnover"][mask].astype(np.float64)

            # Suspended days mask
            if ob in h5_susp and len(h5_susp[ob]) > 0:
                susp_set = set(int(x) for x in h5_susp[ob][:])
                not_susp = np.array([int(d) not in susp_set for d in b_dts], dtype=bool)
            else:
                not_susp = np.ones(len(b_dts), dtype=bool)

            # Trailing 20d turnover average (computed strictly on active bars)
            amt_s = pd.Series(np.where(not_susp & (turnovers > 0), turnovers, np.nan))
            amt_ma20 = amt_s.rolling(20, min_periods=10).mean().to_numpy()

            # Load dividend events (per 1 share before split adjustment)
            if ob in h5_divs and len(h5_divs[ob]) > 0:
                d_arr = h5_divs[ob][:]
                valid_d = (
                    (d_arr["ex_dividend_date"] > 0)
                    & (d_arr["ex_dividend_date"] <= end_int)
                    & (d_arr["dividend_cash_before_tax"] > 0)
                    & (d_arr["round_lot"] > 0)
                )
                d_arr = d_arr[valid_d]
            else:
                d_arr = np.empty(0)

            if len(d_arr) > 0:
                ex_ints = d_arr["ex_dividend_date"].astype(np.int64)
                # Convert YYYYMMDD to days since epoch cleanly
                ex_ts = pd.to_datetime([str(int(x)) for x in ex_ints], errors="coerce")
                ok_ts = np.asarray(ex_ts.notna(), dtype=bool)
                ex_ints = ex_ints[ok_ts]
                ex_days = (np.asarray(ex_ts[ok_ts].asi8, dtype=np.int64) // 86_400_000_000_000).astype(np.int64)
                cash_raw = (
                    d_arr["dividend_cash_before_tax"][ok_ts].astype(np.float64)
                    / d_arr["round_lot"][ok_ts].astype(np.float64)
                )
                # Load splits to express past cash dividend in T-day per-share terms
                if ob in h5_splits and len(h5_splits[ob]) > 0:
                    sp_arr = h5_splits[ob][:]
                    sp_dts = (sp_arr["ex_date"] // 1000000).astype(np.int64)
                    sp_fac = sp_arr["split_factor"].astype(np.float64)
                    sp_ok = (sp_dts > 0) & np.isfinite(sp_fac) & (sp_fac > 0)
                    sp_dts = sp_dts[sp_ok]
                    sp_fac = sp_fac[sp_ok]
                    order_sp = np.argsort(sp_dts)
                    sp_dts = sp_dts[order_sp]
                    sp_fac = sp_fac[order_sp]
                else:
                    sp_dts = np.empty(0, dtype=np.int64)
                    sp_fac = np.empty(0, dtype=np.float64)

                # For each bar date d_t, sum cash_raw[k] / split_between(ex_date[k], d_t)
                # where ex_date[k] <= d_t and d_t_days - ex_days[k] < 365
                bar_days = np.array([cal_days_epoch[cal_map[int(d)]] for d in b_dts if int(d) in cal_map], dtype=np.int64)
                bar_valid_idx = np.array([int(d) in cal_map for d in b_dts], dtype=bool)
                b_dts_v = b_dts[bar_valid_idx]
                c_v = closes[bar_valid_idx]
                ns_v = not_susp[bar_valid_idx]
                am_v = amt_ma20[bar_valid_idx]

                # Precompute cumulative split factor at each split date
                if len(sp_dts) > 0:
                    sp_cum = np.cumprod(sp_fac)
                    # Cumulative split strictly BEFORE ex_ints[k] (so ex_date >= ex_ints[k] IS included!)
                    idx_before_div = np.searchsorted(sp_dts, ex_ints, side="left") - 1
                    div_base_cum = np.where(idx_before_div >= 0, sp_cum[np.maximum(idx_before_div, 0)], 1.0)
                    idx_at_bar = np.searchsorted(sp_dts, b_dts_v, side="right") - 1
                    bar_cum = np.where(idx_at_bar >= 0, sp_cum[np.maximum(idx_at_bar, 0)], 1.0)
                else:
                    div_base_cum = np.ones(len(ex_ints), dtype=np.float64)
                    bar_cum = np.ones(len(b_dts_v), dtype=np.float64)

                # Cash dividend adjusted to cumulative split base 1.0 at epoch start:
                # value at bar T = (cash_raw * div_base_cum) / bar_cum[T]
                cash_base = cash_raw * div_base_cum
                order_dv = np.argsort(ex_ints)
                ex_ints_s = ex_ints[order_dv]
                ex_days_s = ex_days[order_dv]
                cash_base_s = cash_base[order_dv]
                prefix_cash = np.concatenate([[0.0], np.cumsum(cash_base_s)])

                # Strict causal window: ex_ints <= T and (T_days - ex_days) < 365
                hi = np.searchsorted(ex_ints_s, b_dts_v, side="right")
                lo = np.searchsorted(ex_days_s, bar_days - 365, side="right")
                lo = np.minimum(lo, hi)
                ttm_cash = (prefix_cash[hi] - prefix_cash[lo]) / bar_cum
                dv_vals = np.where(ns_v & (c_v > 0), ttm_cash / c_v, np.nan)
            else:
                bar_valid_idx = np.array([int(d) in cal_map for d in b_dts], dtype=bool)
                b_dts_v = b_dts[bar_valid_idx]
                c_v = closes[bar_valid_idx]
                ns_v = not_susp[bar_valid_idx]
                am_v = amt_ma20[bar_valid_idx]
                dv_vals = np.where(ns_v & (c_v > 0), 0.0, np.nan)

            row_idxs = np.array([cal_map[int(d)] for d in b_dts_v], dtype=np.int64)
            dv_mat[row_idxs, col_idx] = dv_vals.astype(np.float32)
            amt_ma20_mat[row_idxs, col_idx] = am_v.astype(np.float32)
    finally:
        h5_stocks.close()
        h5_divs.close()
        h5_splits.close()
        h5_susp.close()

    # Daily cross-sectional Top-800 liquidity median & all-active median
    y10 = _load_yield_10y(bundle_path)
    records: list[dict[str, Any]] = []
    for i, dt_int in enumerate(cal_ints):
        dv_row = dv_mat[i]
        amt_row = amt_ma20_mat[i]
        valid = np.isfinite(dv_row) & np.isfinite(amt_row) & (amt_row > 0)
        n_active = int(valid.sum())
        if n_active == 0:
            records.append(
                {
                    "date_int": int(dt_int),
                    "n_active": 0,
                    "n_top": 0,
                    "dv_ttm_pit_top800_median": np.nan,
                    "dv_ttm_pit_all_median": np.nan,
                    "dv_ttm_pit_top800_pos_median": np.nan,
                    "y_10y": float(y10.get(int(dt_int), np.nan)),
                }
            )
            continue
        dv_act = dv_row[valid]
        amt_act = amt_row[valid]
        k = min(top_n_liquid, n_active)
        if k < n_active:
            top_idx = np.argpartition(amt_act, -k)[-k:]
            dv_top = dv_act[top_idx]
        else:
            dv_top = dv_act
        dv_pos = dv_top[dv_top > 0]
        records.append(
            {
                "date_int": int(dt_int),
                "n_active": n_active,
                "n_top": int(k),
                "dv_ttm_pit_top800_median": float(np.median(dv_top)),
                "dv_ttm_pit_all_median": float(np.median(dv_act)),
                "dv_ttm_pit_top800_pos_median": float(np.median(dv_pos)) if len(dv_pos) > 0 else 0.0,
                "y_10y": float(y10.get(int(dt_int), np.nan)),
            }
        )

    df = pd.DataFrame(records)
    df["dt"] = pd.to_datetime(df["date_int"].astype(str))
    df = df.set_index("dt")
    df["y_10y"] = df["y_10y"].ffill()
    df["div_spread"] = df["dv_ttm_pit_top800_median"] - df["y_10y"]

    # Strict causal 756d rolling percentile (uses ONLY [i - 755 : i + 1])
    spread_arr = df["div_spread"].to_numpy(dtype=np.float64)
    pct_756 = np.full(len(df), np.nan, dtype=np.float64)
    for i in range(rolling_window - 1, len(df)):
        win = spread_arr[i - rolling_window + 1 : i + 1]
        win_v = win[np.isfinite(win)]
        if len(win_v) >= int(rolling_window * 0.9) and np.isfinite(spread_arr[i]):
            pct_756[i] = float(np.mean(win_v <= spread_arr[i]))
    df["pct_756"] = pct_756

    # Causal 5% hysteresis state machine
    states: list[str] = []
    cur_state = "NEUTRAL"
    for p in pct_756:
        if not np.isfinite(p):
            states.append("NEUTRAL")
            continue
        if cur_state == "HIGH_SPREAD":
            if p <= low_enter:
                cur_state = "LOW_SPREAD"
            elif p < high_exit:
                cur_state = "NEUTRAL"
        elif cur_state == "LOW_SPREAD":
            if p >= high_enter:
                cur_state = "HIGH_SPREAD"
            elif p > low_exit:
                cur_state = "NEUTRAL"
        else:
            if p >= high_enter:
                cur_state = "HIGH_SPREAD"
            elif p <= low_enter:
                cur_state = "LOW_SPREAD"
        states.append(cur_state)
    df["spread_regime"] = states

    # Validate against daily_basic_pit.csv over 2024-01-02..2026-11-17
    val = _validate_against_daily_basic(df, eligible_obs, dv_mat, amt_ma20_mat, cal_map)
    return df, val


def _validate_against_daily_basic(
    pit_df: pd.DataFrame,
    eligible_obs: list[str],
    dv_mat: np.ndarray,
    amt_ma20_mat: np.ndarray,
    cal_map: dict[int, int],
) -> dict[str, Any]:
    db = pd.read_csv(
        AUX_DIR / "daily_basic_pit.csv",
        usecols=["ts_code", "trade_date", "dv_ttm"],
        dtype={"ts_code": str, "trade_date": str, "dv_ttm": float},
    )
    db = db[(db["trade_date"] >= "20240102") & (db["trade_date"] <= "20261117")].copy()
    db = db[~db["ts_code"].str.endswith(".BJ")].copy()
    db["rq_id"] = db["ts_code"].str.replace(".SH", ".XSHG", regex=False).str.replace(".SZ", ".XSHE", regex=False)
    ob_to_col = {ob: j for j, ob in enumerate(eligible_obs)}

    # Build daily_basic Top-800 median using exact same liquidity mask (amt_ma20 top 800)
    db_by_dt = {dt: grp.set_index("rq_id")["dv_ttm"] for dt, grp in db.groupby("trade_date")}
    rows_cmp: list[dict[str, Any]] = []
    for dt_str, s_db in sorted(db_by_dt.items()):
        dt_int = int(dt_str)
        if dt_int not in cal_map:
            continue
        i = cal_map[dt_int]
        dv_row = dv_mat[i]
        amt_row = amt_ma20_mat[i]
        valid = np.isfinite(dv_row) & np.isfinite(amt_row) & (amt_row > 0)
        if valid.sum() == 0:
            continue
        act_cols = np.where(valid)[0]
        k = min(800, len(act_cols))
        top_local = np.argpartition(amt_row[act_cols], -k)[-k:]
        top_cols = act_cols[top_local]
        top_obs = [eligible_obs[c] for c in top_cols]

        ref_vals = s_db.reindex(top_obs).fillna(0.0).to_numpy(dtype=np.float64) / 100.0
        ref_pos_vals = s_db.reindex(top_obs).dropna().to_numpy(dtype=np.float64) / 100.0
        pit_vals = dv_row[top_cols].astype(np.float64)
        rows_cmp.append(
            {
                "trade_date": dt_str,
                "pit_med": float(np.median(pit_vals)),
                "ref_med_zero_fill": float(np.median(ref_vals)),
                "ref_med_nonnull": float(np.median(ref_pos_vals)) if len(ref_pos_vals) else np.nan,
                "pit_pos_med": float(np.median(pit_vals[pit_vals > 0])) if (pit_vals > 0).any() else 0.0,
            }
        )

    cmp_df = pd.DataFrame(rows_cmp)
    r_zero, _ = pearsonr(cmp_df["pit_med"], cmp_df["ref_med_zero_fill"])
    rho_zero, _ = spearmanr(cmp_df["pit_med"], cmp_df["ref_med_zero_fill"])
    mae_bps_zero = float(np.mean(np.abs(cmp_df["pit_med"] - cmp_df["ref_med_zero_fill"])) * 10000.0)

    # Stock-level spot check on 20240628, 20250630, 20261117
    sample_dates = ["20240628", "20250630", "20261117"]
    stk_pit, stk_ref = [], []
    for ds in sample_dates:
        if ds not in db_by_dt or int(ds) not in cal_map:
            continue
        i = cal_map[int(ds)]
        s_db = db_by_dt[ds].dropna()
        for ob, ref_v in s_db.items():
            if ob in ob_to_col:
                pv = float(dv_mat[i, ob_to_col[ob]])
                if np.isfinite(pv):
                    stk_pit.append(pv * 100.0)
                    stk_ref.append(float(ref_v))
    stk_r, _ = pearsonr(stk_pit, stk_ref)
    stk_mae_pct = float(np.mean(np.abs(np.array(stk_pit) - np.array(stk_ref))))

    exp_slice = pit_df.loc["2018-01-02":"2026-11-26"]
    return {
        "window": "2024-01-02..2026-11-17",
        "overlap_days": int(len(cmp_df)),
        "ts_top800_pearson_r": round(float(r_zero), 6),
        "ts_top800_spearman_rho": round(float(rho_zero), 6),
        "ts_top800_mae_bps": round(mae_bps_zero, 2),
        "pit_median_mean_pct": round(float(cmp_df["pit_med"].mean() * 100.0), 4),
        "ref_median_mean_pct": round(float(cmp_df["ref_med_zero_fill"].mean() * 100.0), 4),
        "stock_sample_n": int(len(stk_pit)),
        "stock_sample_pearson_r": round(float(stk_r), 6),
        "stock_sample_mae_pct": round(stk_mae_pct, 4),
        "full_2018_2026_pct756_missing": int(exp_slice["pct_756"].isna().sum()),
        "spread_regime_counts_2018_2026": exp_slice["spread_regime"].value_counts().to_dict(),
        "div_spread_summary_pct": {
            "min": round(float(exp_slice["div_spread"].min() * 100.0), 4),
            "median": round(float(exp_slice["div_spread"].median() * 100.0), 4),
            "max": round(float(exp_slice["div_spread"].max() * 100.0), 4),
            "latest_20261126": round(float(exp_slice["div_spread"].iloc[-1] * 100.0), 4),
            "latest_pct_756": round(float(exp_slice["pct_756"].iloc[-1]), 4),
            "latest_regime": str(exp_slice["spread_regime"].iloc[-1]),
        },
    }


if __name__ == "__main__":
    df, val = compute_pit_dividend_spread_series()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = REPORTS_DIR / "exp_v3_13_pit_div_spread_2014_2026.csv"
    df.to_csv(out_csv)
    print(json.dumps({"csv": str(out_csv), "validation": val}, ensure_ascii=False, indent=2))
