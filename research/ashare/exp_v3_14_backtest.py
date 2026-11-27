"""EXP-V3-14: 40-quarter PIT ERP+B/P Dual Envelope (B1), Implied Expectation Tilt (B2),
QualityCore v2 100k Stock Guard (B3), and 5%-Gold Diagnostic (B1_G5_DIAG) on bundle_20261126.

Dual-engine (VectorBT + native RQAlpha 6.3.0 69k/100k chassis & 6 unified accounts)
plus all 7 anti-overfitting and Occam's Razor hard gates, including dual-scope CSCV PBO
(PBO_distinct vs PBO_with_perturb) and cumulative multiple-testing DSR.
"""

from __future__ import annotations

import json
import math
import sqlite3
import subprocess
import sys
from importlib.metadata import version
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from research.ashare import v3_data_202611 as data
from research.ashare.exp_v3_13_backtest import (
    END_DATE,
    GOLD_TS,
    GROWTH_CHAIN_TS,
    LOW_VOL_CHAIN_RQ,
    LOW_VOL_CHAIN_TS,
    PIT_CSV,
    VALUE_CHAIN_TS,
    _compute_loyo_metrics,
    _compute_walk_forward,
    _patch_bundle_paths,
    _pick_upward_sticky,
    replay_core40_account,
)
from research.ashare.v3_data import rq_to_ts, ts_to_rq
from research.batches.exp_v3_06_defensive_rotation.run import (
    LOW_TICKET_BONDS,
    select_bond_reserve,
)
from research.batches.exp_v3_08_icepoint_recovery.run import compute_recovery_overlay_series
from research.batches.exp_v3_09_drawdown_control.run import DrawdownController
from research.batches.exp_v3_11_v330_integration.analytics import (
    compute_calendar_stats,
    compute_roundtrip_stats,
)
from research.batches.exp_v3_11_v330_integration.run import (
    BOND_SET_TS,
    CASH,
    LOW_TICKET_BONDS_RQ,
    OOS_CASH_START,
    OOS_CONC_START,
    START,
    STRESS_START,
    apply_drawdown_overlay_202611,
    build_v3_base_chassis_weights,
    load_sector_pioneer_pool,
    make_group_fn,
)
from research.batches.v3_account_replay_v2 import stock_signals
from research.batches.v3_account_replay_v2.policy import FOCUS, GOLD, indicators
from research.batches.v3_complexity_hurdle_v2.native import NORMAL, SUPER, replay
from research.batches.v3_complexity_hurdle_v2.run import utc
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
REPORTS_DIR = ROOT / "research/ashare/reports"
EXP13_SUMMARY_PATH = REPORTS_DIR / "exp_v3_13_summary.json"
PIT_CACHE_DIR = Path.home() / ".local/share/ashare-private/v34_pit_cache"
PIT_DAILY_CSV = PIT_CACHE_DIR / "market_fundamental_daily_2018_2026.csv"
PIT_YIELD_CSV = PIT_CACHE_DIR / "macro_yield_curve_2018_2026.csv"
PIT_FINA_SQLITE = PIT_CACHE_DIR / "fina_40q_pit.sqlite"
GOLD_CRASH_START = pd.Timestamp("2026-01-29")

UNIFIED_CELLS = (
    "OOS_CASH_69000",
    "OOS_CASH_100000",
    "CORE25_69000",
    "CORE25_100000",
    "LEGACY70_69000",
    "LEGACY70_100000",
)


def load_v34_pit_signals(calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Load strictly causal 40-quarter PIT daily fundamentals and yield curve aligned to calendar."""
    fund = pd.read_csv(PIT_DAILY_CSV)
    yc = pd.read_csv(PIT_YIELD_CSV, usecols=["trade_date", "term_spread_10y_1y_bps"])
    merged = fund.merge(yc, on="trade_date", how="left")
    merged["dt"] = pd.to_datetime(merged["trade_date"].astype(str))
    merged = merged.sort_values("dt").set_index("dt").reindex(calendar)
    merged["d_edi_60"] = merged["edi_bps"].diff(60).fillna(0.0)
    merged["d_ts_60"] = merged["term_spread_10y_1y_bps"].diff(60).fillna(0.0)
    return merged


def compute_b_arm_regimes(
    panels: Any,
    regime_df: pd.DataFrame,
    pit_df: pd.DataFrame,
    *,
    use_b1_envelope: bool = True,
    use_b2_tilt: bool = False,
    ice10_th: float = 0.10,
    ice10_days: int = 15,
    ice10_floor_w: float = 0.35,
    high_ice10_w: float = 0.425,
    high_rec_w: float = 0.50,
    high_str_w: float = 0.65,
    low_off_w: float = 0.70,
    low_str_w: float = 0.50,
    erp_high_enter: float = 0.80,
    erp_high_exit: float = 0.75,
    bp_high_enter: float = 0.70,
    bp_high_exit: float = 0.65,
    low_enter: float = 0.15,
    low_exit: float = 0.20,
    rec_tilt_step: float = 0.05,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Compute strictly causal (eff_regime, eq_budget, b1_state, tilt_tag) over panels.calendar."""
    cal = panels.calendar
    eff_m2, _, _ = compute_recovery_overlay_series(
        panels, regime_df, mode="m2_thrust", ice_th=0.15, recovery_weight=0.40
    )

    erp_s = pit_df["erp_pct_756"].reindex(cal)
    bp_s = pit_df["bp_pct_756"].reindex(cal)
    b1_states: list[str] = []
    cur_st = "NEUTRAL"
    for e_val, b_val in zip(erp_s, bp_s, strict=True):
        if not (np.isfinite(e_val) and np.isfinite(b_val)):
            b1_states.append("NEUTRAL")
            continue
        if cur_st == "EXTREME_UNDERVAL":
            if e_val <= low_enter and b_val <= low_enter:
                cur_st = "EXTREME_BUBBLE"
            elif e_val < erp_high_exit or b_val < bp_high_exit:
                cur_st = "NEUTRAL"
        elif cur_st == "EXTREME_BUBBLE":
            if e_val >= erp_high_enter and b_val >= bp_high_enter:
                cur_st = "EXTREME_UNDERVAL"
            elif e_val > low_exit or b_val > low_exit:
                cur_st = "NEUTRAL"
        else:
            if e_val >= erp_high_enter and b_val >= bp_high_enter:
                cur_st = "EXTREME_UNDERVAL"
            elif e_val <= low_enter and b_val <= low_enter:
                cur_st = "EXTREME_BUBBLE"
        b1_states.append(cur_st)
    b1_series = pd.Series(b1_states, index=cal)

    pct60 = regime_df["pct_above_ma60"].reindex(cal)
    d_edi_s = pit_df["d_edi_60"].reindex(cal).fillna(0.0)
    d_ts_s = pit_df["d_ts_60"].reindex(cal).fillna(0.0)

    eff_regs: list[str] = []
    eff_budgets: list[float] = []
    tilt_tags: list[str] = []
    ice10_until = -1000

    for pos, dt in enumerate(cal):
        base_r = str(eff_m2.at[dt])
        p60 = float(pct60.at[dt]) if pd.notna(pct60.at[dt]) else 1.0
        if p60 < ice10_th:
            ice10_until = pos + ice10_days
        reg_out = "ICE_10" if (base_r == "DEFENSIVE" and pos <= ice10_until) else base_r

        b1_st = str(b1_series.at[dt]) if use_b1_envelope else "NEUTRAL"
        if b1_st == "EXTREME_UNDERVAL":
            b_map = {
                "OFFENSIVE": 0.85,
                "STRUCTURAL": high_str_w,
                "RECOVERY": high_rec_w,
                "ICE_10": high_ice10_w,
                "DEFENSIVE": 0.25,
            }
        elif b1_st == "EXTREME_BUBBLE":
            b_map = {
                "OFFENSIVE": low_off_w,
                "STRUCTURAL": low_str_w,
                "RECOVERY": 0.40,
                "ICE_10": ice10_floor_w,
                "DEFENSIVE": 0.25,
            }
        else:
            b_map = {
                "OFFENSIVE": 0.85,
                "STRUCTURAL": 0.60,
                "RECOVERY": 0.40,
                "ICE_10": ice10_floor_w,
                "DEFENSIVE": 0.25,
            }
        budget = float(b_map[reg_out])

        tilt_tag = "NONE"
        if use_b2_tilt:
            d_edi = float(d_edi_s.at[dt])
            d_ts = float(d_ts_s.at[dt])
            if d_edi > 0.0 and d_ts > 0.0:
                tilt_tag = "IMPROVING_STEEP"
                if reg_out == "RECOVERY":
                    budget = min(0.85, budget + rec_tilt_step)
            elif d_edi < 0.0 and d_ts < 0.0:
                tilt_tag = "DETERIORATING_FLAT"
                if reg_out == "RECOVERY":
                    budget = max(0.35, budget - rec_tilt_step)

        eff_regs.append(reg_out)
        eff_budgets.append(budget)
        tilt_tags.append(tilt_tag)

    return (
        pd.Series(eff_regs, index=cal),
        pd.Series(eff_budgets, index=cal, dtype=float),
        b1_series,
        pd.Series(tilt_tags, index=cal),
    )


def build_b_chassis_weights(
    panels: Any,
    regime_df: pd.DataFrame,
    pit_df: pd.DataFrame,
    *,
    use_b1_envelope: bool = True,
    use_b2_tilt: bool = False,
    end: pd.Timestamp = END_DATE,
    lowvol_w: float = 0.15,
    gold_w: float = 0.10,
    gold_band: float = 0.04,
    bond_band: float = 0.10,
    sat_drift_band: float = 0.10,
    **kwargs: Any,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build strictly causal T+1 sparse target weights for B0/B1/B2/B1_G5_DIAG."""
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    adj = panels.etf_adj_close
    mask = panels.etf_tradability_mask
    cols = list(adj.columns)
    rets = adj.loc[cal].ffill().pct_change(fill_method=None).fillna(0.0)

    eff_reg, eff_budget, b1_series, tilt_series = compute_b_arm_regimes(
        panels, regime_df, pit_df, use_b1_envelope=use_b1_envelope, use_b2_tilt=use_b2_tilt, **kwargs
    )
    ctrl = DrawdownController(init_nav=1.0, mode="c3_gradual", floor_dd=0.15, cppi_m=5.0)
    out_w = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)

    nav = 1.0
    cur_w = pd.Series(0.0, index=cols, dtype=float)
    prev_state_key: tuple[str, float, bool, str] | None = None
    prev_locked = False
    max_true_dd = 0.0
    breach_days = 0
    rebal_count = 0

    for pos in range(len(cal) - 1):
        sig_dt = cal[pos]
        exec_dt = cal[pos + 1]
        if pos > 0:
            r_day = rets.loc[sig_dt]
            nav *= 1.0 + float((cur_w * r_day).sum())
            cur_w = cur_w * (1.0 + r_day)
            s_sum = float(cur_w.sum())
            if s_sum > 1e-12:
                cur_w = cur_w / s_sum

        reg_s = str(eff_reg.at[sig_dt])
        style = str(regime_df.at[sig_dt, "style"])
        base_eq_budget = float(eff_budget.at[sig_dt])
        tilt_tag = str(tilt_series.at[sig_dt])

        st = ctrl.step(pos, nav, concentrated=False, base_eq_budget=base_eq_budget)
        max_true_dd = max(max_true_dd, float(st["true_dd"]))
        if st["breach"] > 0:
            breach_days += 1

        locked = bool(st["locked"])
        if reg_s == "ICE_10" and locked:
            base_eq_budget = 0.25
            reg_eff = "DEFENSIVE"
        else:
            reg_eff = reg_s

        cap = float(st["buy_cap"])
        target_eq = min(base_eq_budget, cap)

        held_codes = {c for c in cols if float(cur_w[c]) > 1e-4}
        desired = pd.Series(0.0, index=cols, dtype=float)

        lv_w = lowvol_w
        if use_b2_tilt and style == "BALANCED" and tilt_tag == "DETERIORATING_FLAT":
            lv_w = min(lowvol_w + 0.05, max(lowvol_w, target_eq - gold_w))
        core_risk_target = lv_w + gold_w
        if target_eq >= core_risk_target - 1e-9:
            lv_target = lv_w
            g_target = gold_w
            sat_target = target_eq - core_risk_target
        else:
            scale_core = target_eq / max(core_risk_target, 1e-9)
            lv_target = lv_w * scale_core
            g_target = gold_w * scale_core
            sat_target = 0.0

        lv_picks = _pick_upward_sticky(LOW_VOL_CHAIN_TS, exec_dt, mask, adj, held_codes, count=2)
        if lv_picks and lv_target > 0:
            for c in lv_picks:
                desired[c] += lv_target / len(lv_picks)

        if g_target > 0 and bool(mask.at[exec_dt, GOLD_TS]):
            cur_g = float(cur_w[GOLD_TS])
            if cur_g > 1e-4 and abs(cur_g - g_target) < gold_band and st["ctrl_cap"] is None:
                desired[GOLD_TS] = cur_g
                sat_target = max(0.0, target_eq - lv_target - cur_g)
            else:
                desired[GOLD_TS] = g_target

        if sat_target > 0.01:
            if style == "GROWTH_LEADING":
                gro_share, val_share = 0.65, 0.35
            elif style == "VALUE_LEADING":
                gro_share, val_share = 0.35, 0.65
            elif use_b2_tilt and tilt_tag == "IMPROVING_STEEP":
                gro_share, val_share = 0.60, 0.40
            elif use_b2_tilt and tilt_tag == "DETERIORATING_FLAT":
                gro_share, val_share = 0.40, 0.60
            else:
                gro_share, val_share = 0.50, 0.50

            val_p = _pick_upward_sticky(VALUE_CHAIN_TS, exec_dt, mask, adj, held_codes, count=1)
            gro_p = _pick_upward_sticky(GROWTH_CHAIN_TS, exec_dt, mask, adj, held_codes, count=1)
            if val_p and gro_p:
                desired[val_p[0]] += sat_target * val_share
                desired[gro_p[0]] += sat_target * gro_share
            elif val_p:
                desired[val_p[0]] += sat_target
            elif gro_p:
                desired[gro_p[0]] += sat_target

        res_code = select_bond_reserve(exec_dt, mask, adj, LOW_TICKET_BONDS)
        rem = max(0.0, 1.0 - float(desired.sum()))
        if res_code is not None and rem > 1e-6:
            desired[res_code] = rem

        eff_tilt = tilt_tag if (use_b2_tilt and style == "BALANCED" and sat_target > 0.01) else "NONE"
        state_key = (reg_eff, round(float(target_eq), 4), locked, eff_tilt)
        state_changed = prev_state_key is None or state_key != prev_state_key
        unlocked_today = prev_locked and not locked

        cur_g = float(cur_w[GOLD_TS])
        gold_breach = (
            bool(mask.at[exec_dt, GOLD_TS])
            and g_target > 0
            and (cur_g < 1e-4 or abs(cur_g - g_target) >= gold_band)
        )
        cur_bond = float(cur_w[list(BOND_SET_TS)].sum()) if any(c in cur_w.index for c in BOND_SET_TS) else 0.0
        tgt_bond = float(desired[list(BOND_SET_TS)].sum()) if any(c in desired.index for c in BOND_SET_TS) else 0.0
        bond_breach = abs(tgt_bond - cur_bond) >= bond_band

        eq_drift = float(
            (
                desired.drop(labels=list(BOND_SET_TS), errors="ignore")
                - cur_w.drop(labels=list(BOND_SET_TS), errors="ignore")
            )
            .abs()
            .sum()
        )
        extreme_drift = eq_drift >= sat_drift_band or gold_breach or bond_breach

        if pos == 0 or state_changed or unlocked_today or bool(st["trigger"]) or extreme_drift:
            if not state_changed and not bool(st["trigger"]) and st["ctrl_cap"] is None and not gold_breach and cur_g > 1e-4:
                desired[GOLD_TS] = cur_g
                tot_now = float(desired.sum())
                if res_code is not None and abs(tot_now - 1.0) > 1e-6:
                    desired[res_code] = max(0.0, desired[res_code] + (1.0 - tot_now))

            cand_row = pd.Series(np.nan, index=cols, dtype=float)
            for sym in cols:
                if desired[sym] > 1e-6:
                    cand_row[sym] = float(desired[sym])
                elif cur_w[sym] > 1e-6:
                    cand_row[sym] = 0.0
            out_w.loc[exec_dt] = cand_row
            cur_w = desired.copy()
            rebal_count += 1

        prev_state_key = state_key
        prev_locked = locked

    return out_w, {
        "locks": ctrl.locks,
        "relock_loops": ctrl.relock_loops,
        "breach_days": breach_days,
        "proxy_max_true_dd": round(max_true_dd, 4),
        "rebal_events": rebal_count,
        "ice10_days": int((eff_reg == "ICE_10").sum()),
        "underval_days": int((b1_series == "EXTREME_UNDERVAL").sum()) if use_b1_envelope else 0,
        "bubble_days": int((b1_series == "EXTREME_BUBBLE").sum()) if use_b1_envelope else 0,
        "improving_steep_days": int((tilt_series == "IMPROVING_STEEP").sum()) if use_b2_tilt else 0,
        "deteriorating_flat_days": int((tilt_series == "DETERIORATING_FLAT").sum()) if use_b2_tilt else 0,
    }


def _load_quality_core_v2_table() -> dict[str, dict[str, np.ndarray]]:
    """Load 40-quarter Eastmoney PIT QualityCore v2 table (strict ann_date <= T)."""
    conn = sqlite3.connect(PIT_FINA_SQLITE)
    try:
        fi = pd.read_sql_query(
            "SELECT ts_code, end_date, ann_date, basic_eps, roe_dt, ocf_to_profit, bps FROM fina_pit",
            conn,
        )
    finally:
        conn.close()
    fi = fi[fi["ann_date"].notna() & fi["ann_date"].str.match(r"^\d{8}$", na=False)].copy()
    fi = fi.sort_values(["ts_code", "ann_date", "end_date"]).reset_index(drop=True)
    mmdd = fi["end_date"].str.slice(4, 8)
    mult = mmdd.map({"0331": 4.0, "0630": 2.0, "0930": 4.0 / 3.0, "1231": 1.0}).fillna(1.0)
    ann_roe_dt = fi["roe_dt"].astype(float) * mult
    fi["qc_ok"] = (
        (ann_roe_dt > 6.0)
        & (fi["basic_eps"].astype(float) > 0.0)
        & (fi["ocf_to_profit"].astype(float) >= 50.0)
        & (fi["bps"].astype(float) > 0.0)
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


def build_bp1_candidates_quality_v2(
    *, oos_start: pd.Timestamp = OOS_CASH_START, bundle_end: pd.Timestamp = END_DATE
) -> tuple[dict[str, list[Any]], dict[str, Any]]:
    """Build causal BP1 candidates filtered by 40-quarter PIT QualityCore v2."""
    tbl_v2 = _load_quality_core_v2_table()
    orig_loader = stock_signals._load_pit_financial_table_202611
    stock_signals._load_pit_financial_table_202611 = lambda: tbl_v2  # type: ignore[assignment]
    try:
        return stock_signals.build_causal_bp1_candidates_202611(
            oos_start=oos_start, bundle_end=bundle_end
        )
    finally:
        stock_signals._load_pit_financial_table_202611 = orig_loader


def _cscv_pbo(eq_dict: dict[str, pd.Series], ref_index: pd.DatetimeIndex, n_blocks: int = 16) -> float:
    """Compute CSCV PBO (S=16 blocks -> C(16,8)=12,870 splits) across given equity series."""
    mat_rets = np.column_stack(
        [eq_dict[k].reindex(ref_index).pct_change(fill_method=None).fillna(0.0).to_numpy() for k in eq_dict]
    )
    block_size = len(mat_rets) // n_blocks
    mat_rets = mat_rets[: block_size * n_blocks]
    blocks = [mat_rets[b * block_size : (b + 1) * block_size] for b in range(n_blocks)]

    logits: list[float] = []
    half = n_blocks // 2
    for is_idx in combinations(range(n_blocks), half):
        oos_idx = [i for i in range(n_blocks) if i not in is_idx]
        is_m = np.vstack([blocks[i] for i in is_idx])
        oos_m = np.vstack([blocks[i] for i in oos_idx])
        is_sr = np.mean(is_m, axis=0) / np.maximum(np.std(is_m, axis=0, ddof=1), 1e-12)
        oos_sr = np.mean(oos_m, axis=0) / np.maximum(np.std(oos_m, axis=0, ddof=1), 1e-12)
        best_is = int(np.argmax(is_sr))
        rank_oos = int(np.sum(oos_sr <= oos_sr[best_is]))
        w_bar = min(max(rank_oos / (len(oos_sr) + 1.0), 1e-4), 1.0 - 1e-4)
        logits.append(math.log(w_bar / (1.0 - w_bar)))
    return float(np.mean(np.array(logits) < 0.0))


def compute_dual_multiple_testing(
    distinct_eqs: dict[str, pd.Series],
    all_with_perturb_eqs: dict[str, pd.Series],
    candidate_key: str,
    *,
    n_trials_exp14: int,
    n_trials_cumulative: int,
) -> dict[str, Any]:
    """Compute DSR (both Exp14 and cumulative N) and dual-scope PBO (distinct vs with_perturb)."""
    eq = distinct_eqs[candidate_key]
    ret = eq.pct_change(fill_method=None).dropna().to_numpy(dtype=np.float64)
    t_obs = len(ret)
    sr_daily = float(np.mean(ret) / np.std(ret, ddof=1))
    sr_ann = sr_daily * np.sqrt(252.0)
    skew = float(pd.Series(ret).skew())
    kurt = float(pd.Series(ret).kurtosis() + 3.0)

    all_srs = []
    for s in all_with_perturb_eqs.values():
        r = s.pct_change(fill_method=None).dropna().to_numpy(dtype=np.float64)
        all_srs.append(float(np.mean(r) / np.std(r, ddof=1) * np.sqrt(252.0)))
    sr_std = max(float(np.sqrt(np.var(all_srs, ddof=1))) if len(all_srs) > 1 else 0.05, 0.05)

    def _dsr_for_n(n_tr: int) -> tuple[float, float, float]:
        euler_gamma = 0.5772156649
        if n_tr > 1:
            e_max_z = (1.0 - euler_gamma) * norm.ppf(1.0 - 1.0 / n_tr) + euler_gamma * norm.ppf(
                1.0 - 1.0 / (n_tr * math.e)
            )
        else:
            e_max_z = 0.0
        sr0_ann = sr_std * e_max_z
        sr0_daily = sr0_ann / np.sqrt(252.0)
        denom = math.sqrt(max(1e-9, 1.0 - skew * sr_daily + ((kurt - 1.0) / 4.0) * (sr_daily**2)))
        z_val = ((sr_daily - sr0_daily) * math.sqrt(t_obs - 1.0)) / denom
        return float(sr0_ann), float(z_val), float(norm.cdf(z_val))

    sr0_14, z_14, p_14 = _dsr_for_n(n_trials_exp14)
    sr0_cum, z_cum, p_cum = _dsr_for_n(n_trials_cumulative)
    pbo_dist = _cscv_pbo(distinct_eqs, eq.index, n_blocks=16)
    pbo_pert = _cscv_pbo(all_with_perturb_eqs, eq.index, n_blocks=16)

    return {
        "candidate": candidate_key,
        "candidate_sharpe_ann": round(sr_ann, 4),
        "n_trials_exp14": int(n_trials_exp14),
        "n_trials_cumulative": int(n_trials_cumulative),
        "n_cscv_distinct": int(len(distinct_eqs)),
        "n_cscv_with_perturb": int(len(all_with_perturb_eqs)),
        "expected_max_null_sr_exp14": round(sr0_14, 4),
        "dsr_z_exp14": round(z_14, 4),
        "dsr_prob_exp14": round(p_14, 4),
        "expected_max_null_sr_cum": round(sr0_cum, 4),
        "dsr_z_cum": round(z_cum, 4),
        "dsr_prob_cum": round(p_cum, 4),
        "pbo_distinct": round(pbo_dist, 4),
        "pbo_with_perturb": round(pbo_pert, 4),
    }


def _eval_vbt(p: Any, prov: Any, ow: pd.DataFrame) -> pd.Series:
    prices, mask, targets_df = (f.loc[:END_DATE] for f in (p.etf_adj_close, p.etf_tradability_mask, ow))
    validate_execution_targets(targets_df, prices, mask, p.etf_lifetimes)
    rates = np.array([SUPER if c in prov.super_etf_codes else NORMAL for c in ow.columns])[None, :]
    return run_target_weights(
        prices,
        targets_df,
        fees=rates,
        slippage=0.0002,
        initial_cash=100000.0,
        metric_start=START,
        tradability_mask=mask,
        lifetimes=p.etf_lifetimes,
    ).equity.loc[START:END_DATE]


def _record_vbt(report_vbt: dict[str, Any], label: str, eq: pd.Series, meta: dict[str, Any]) -> None:
    report_vbt[label] = {
        "ctrl": meta,
        "full_2018_20261126": compute_calendar_stats(eq),
        "is_2018_2023": compute_calendar_stats(eq.loc[: data.IS_END]),
        "oos_2024_20261126": compute_calendar_stats(eq.loc[data.IS_END :]),
        "stress_2026h2": compute_calendar_stats(eq.loc[STRESS_START:]),
        "stress_gold_peak_to_trough": compute_calendar_stats(eq.loc[GOLD_CRASH_START:]),
    }


def _run_chassis_pair(
    label: str,
    ow: pd.DataFrame,
    prov: Any,
    group_fn: Any,
    report_chassis: dict[str, Any],
    rqa_chassis_eq: dict[str, pd.Series],
    *,
    gold_w: float = 0.10,
) -> None:
    for cash in CASH:
        key = f"{label}_{cash}"
        sys.stdout.write(f"{utc()} chassis {key}\n")
        sys.stdout.flush()
        eq, run = replay(ow, cash, prov.super_etf_codes, True, start=START, end=END_DATE)
        rqa_chassis_eq[key] = eq
        fees = sum(float(f["commission"]) for f in run["fills"])
        report_chassis[key] = {
            "gold_w": gold_w,
            "full": compute_calendar_stats(eq),
            "is": compute_calendar_stats(eq.loc[: data.IS_END]),
            "oos": compute_calendar_stats(eq.loc[data.IS_END :]),
            "stress_2026h2": compute_calendar_stats(eq.loc[STRESS_START:]),
            "stress_gold_peak_to_trough": compute_calendar_stats(eq.loc[GOLD_CRASH_START:]),
            "roundtrips": compute_roundtrip_stats(run["fills"], group_fn),
            "trade_count": len(run["fills"]),
            "commission_yuan": round(fees, 2),
            "dates_pass": run["dates_pass"],
            "fill_capture_pass": run["fill_capture_pass"],
            "fees_pass": run["commission_audit"]["fees_pass"],
            "illegal_non_lot_fills": len(run["commission_audit"]["illegal_non_lot_fills"]),
        }


def _replay_b_account_with_gold_or_tilt(
    *,
    days: list[str],
    market_map: dict[str, tuple[str, str, float]],
    features: dict[str, dict[str, Any]],
    stock_candidates: dict[str, list[Any]],
    white: set[str],
    capital: float,
    seed: float,
    group_fn: Any,
    gold_w: float = 0.10,
    tilt_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run replay_core40_account with optional B2 BALANCED tilt or G5 5%-Gold core target."""
    import research.ashare.exp_v3_13_backtest as r13_mod

    orig_selector = r13_mod.select_core40_account_targets
    if gold_w == 0.10 and tilt_map is None:
        return replay_core40_account(
            days=days,
            market_map=market_map,
            features=features,
            stock_candidates=stock_candidates,
            white=white,
            capital=capital,
            seed=seed,
            group_fn=group_fn,
        )

    # Inject clean wrapper preserving exact replay_core40_account mechanics
    day_cursor = {"idx": 0}
    sorted_days = list(days)

    def _custom_selector(
        *,
        regime: str,
        style: str,
        budget_total: float,
        occupied_weight: float,
        features: dict[str, Any],
        held_mv: dict[str, float],
        nav: float,
        p0_ctrl_cap: float | None,
    ) -> dict[str, float]:
        cur_d = sorted_days[min(day_cursor["idx"], len(sorted_days) - 1)]
        tilt_tag = tilt_map.get(cur_d, "NONE") if tilt_map else "NONE"

        def valid(c: str) -> bool:
            return c in features and pd.notna(features[c].ma20) and features[c].raw > 0

        def holdable(c: str) -> bool:
            return bool(held_mv.get(c, 0.0) > 0 and c in features and pd.notna(features[c].raw) and features[c].raw > 0)

        def eligible(c: str) -> bool:
            return holdable(c) or valid(c)

        eff_total = max(0.0, budget_total)
        lv_base = 0.15
        if tilt_map is not None and style == "BALANCED" and tilt_tag == "DETERIORATING_FLAT":
            lv_base = 0.20
        core_risk = lv_base + gold_w
        if eff_total >= core_risk - 1e-9:
            lv_w = lv_base
            g_w = gold_w
        else:
            sc = eff_total / max(core_risk, 1e-9)
            lv_w = lv_base * sc
            g_w = gold_w * sc

        out: dict[str, float] = {}
        lv_picks = [c for c in LOW_VOL_CHAIN_RQ if eligible(c)][:2]
        if lv_picks and lv_w > 0.005:
            for c in lv_picks:
                out[c] = lv_w / len(lv_picks)

        if g_w > 0.005 and eligible(GOLD):
            cur_gold_w = held_mv.get(GOLD, 0.0) / max(nav, 1.0)
            if p0_ctrl_cap is None and cur_gold_w > 0.005:
                if abs(cur_gold_w - g_w) < 0.04 or abs(cur_gold_w - g_w) * nav < 5000.0:
                    out[GOLD] = cur_gold_w
                else:
                    out[GOLD] = g_w
            else:
                out[GOLD] = g_w

        core_used = sum(out.values())
        sat_room = max(0.0, eff_total - core_used - occupied_weight)
        if sat_room > 0.01:
            val_chain = tuple(ts_to_rq(c) for c in VALUE_CHAIN_TS)
            gro_chain = tuple(ts_to_rq(c) for c in GROWTH_CHAIN_TS)
            val_c = next((c for c in val_chain if eligible(c)), None)
            gro_c = next((c for c in gro_chain if eligible(c)), None)
            if style == "GROWTH_LEADING":
                gro_share, val_share = 0.65, 0.35
            elif style == "VALUE_LEADING":
                gro_share, val_share = 0.35, 0.65
            elif tilt_map is not None and tilt_tag == "IMPROVING_STEEP":
                gro_share, val_share = 0.60, 0.40
            elif tilt_map is not None and tilt_tag == "DETERIORATING_FLAT":
                gro_share, val_share = 0.40, 0.60
            else:
                gro_share, val_share = 0.50, 0.50

            if val_c and gro_c:
                out[val_c] = sat_room * val_share
                out[gro_c] = sat_room * gro_share
            elif val_c:
                out[val_c] = sat_room
            elif gro_c:
                out[gro_c] = sat_room
        return {c: w for c, w in out.items() if w > 0.01}

    # replay_core40_account calls select_core40_account_targets twice per day (provisional_t, raw_t)
    call_cnt = {"n": 0}

    def _counting_selector(**kw: Any) -> dict[str, float]:
        res = _custom_selector(**kw)
        call_cnt["n"] += 1
        # Wait: when locked, raw_t is skipped! Better to track cur_d via features[d] match or date cursor
        return res

    # Map id(features[d]) -> date string so cursor is exact even when locked skips raw_t
    feat_to_date = {id(v): d for d, v in features.items()}

    def _exact_selector(**kw: Any) -> dict[str, float]:
        d_match = feat_to_date.get(id(kw["features"]))
        if d_match is not None:
            day_cursor["idx"] = sorted_days.index(d_match) if d_match in sorted_days else day_cursor["idx"]
        return _custom_selector(**kw)

    r13_mod.select_core40_account_targets = _exact_selector  # type: ignore[assignment]
    try:
        return replay_core40_account(
            days=days,
            market_map=market_map,
            features=features,
            stock_candidates=stock_candidates,
            white=white,
            capital=capital,
            seed=seed,
            group_fn=group_fn,
        )
    finally:
        r13_mod.select_core40_account_targets = orig_selector  # type: ignore[assignment]


def main() -> int:
    _patch_bundle_paths()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    exp13 = json.loads(EXP13_SUMMARY_PATH.read_text(encoding="utf-8"))

    report: dict[str, Any] = {
        "started": utc(),
        "bundle_path": str(data.BUNDLE_PATH_202611),
        "runner_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "versions": {k: version(k) for k in ("rqalpha", "vectorbt")},
        "vbt": {},
        "chassis_rqa": {},
        "account_replay": {},
        "loyo": {},
        "walk_forward": {},
        "plateau": {},
        "multiple_testing": {},
        "gates": {},
    }

    prov = data.verify_v3_202611_provenance(verify_content=True)
    report["snapshot_id"] = prov.snapshot_id
    p = data.load_stitched_panels_202611(prov, end=END_DATE)
    reg = data.compute_v3_regime_series_202611(prov, p.index_close, p.calendar, use_cache=True)
    pit_df = load_v34_pit_signals(p.calendar)
    spread_df = pd.read_csv(PIT_CSV, parse_dates=["dt"]).set_index("dt")
    sector_pool_ts = load_sector_pioneer_pool()
    group_fn = make_group_fn(sector_pool_ts)

    # 1) Build target weights & VBT equity for reference (A0, A1, A3) + pre-registered B arms
    vbt_eq: dict[str, pd.Series] = {}
    arm_weights: dict[str, pd.DataFrame] = {}

    a0_base, a0_eff_reg, a0_rec = build_v3_base_chassis_weights(
        p, reg, sector_pool_ts=sector_pool_ts, use_recovery=True,
        use_lowvol_core=True, use_low_ticket_bond=True, use_sector_pioneer=False, end=END_DATE,
    )
    a0_ow, a0_ctrl = apply_drawdown_overlay_202611(
        p, a0_base, a0_eff_reg, ctrl_mode="c3_gradual", use_low_ticket_bond=True, end=END_DATE
    )
    vbt_eq["A0_V331"] = _eval_vbt(p, prov, a0_ow)
    _record_vbt(report["vbt"], "A0_V331", vbt_eq["A0_V331"], {**a0_rec, **a0_ctrl})

    # Include A1 and A3 VBT for clean distinct-arm CSCV PBO
    from research.ashare.exp_v3_13_backtest import build_core40_chassis_weights

    a1_ow, a1_meta = build_core40_chassis_weights(p, reg, spread_df, arm="A1", end=END_DATE)
    vbt_eq["A1_CORE40_G10_REGIME_ONLY"] = _eval_vbt(p, prov, a1_ow)
    _record_vbt(report["vbt"], "A1_CORE40_G10_REGIME_ONLY", vbt_eq["A1_CORE40_G10_REGIME_ONLY"], a1_meta)

    a3_ow, a3_meta = build_core40_chassis_weights(p, reg, spread_df, arm="A3", end=END_DATE)
    vbt_eq["A3_A2_PLUS_DIV_SPREAD_GUARD"] = _eval_vbt(p, prov, a3_ow)
    _record_vbt(report["vbt"], "A3_A2_PLUS_DIV_SPREAD_GUARD", vbt_eq["A3_A2_PLUS_DIV_SPREAD_GUARD"], a3_meta)

    b_specs = (
        ("B0_A2_BASE", dict(use_b1_envelope=False, use_b2_tilt=False, gold_w=0.10)),
        ("B1_PIT_ERP_BP_ENVELOPE", dict(use_b1_envelope=True, use_b2_tilt=False, gold_w=0.10)),
        ("B2_IMPLIED_EXPECTATION_TILT", dict(use_b1_envelope=True, use_b2_tilt=True, gold_w=0.10)),
        ("B1_G5_DIAG", dict(use_b1_envelope=True, use_b2_tilt=False, gold_w=0.05)),
    )
    for label, kw in b_specs:
        ow, meta = build_b_chassis_weights(p, reg, pit_df, end=END_DATE, **kw)
        arm_weights[label] = ow
        eq = _eval_vbt(p, prov, ow)
        vbt_eq[label] = eq
        _record_vbt(report["vbt"], label, eq, meta)

    # 2) Import verified A0_V331 and A3 RQA metrics from EXP-V3-13 (same bundle & dates),
    #    and run full native RQAlpha 6.3.0 chassis on B0, B1, B2, B1_G5_DIAG
    rqa_chassis_eq: dict[str, pd.Series] = {}
    for ref_arm in ("A0_V331", "A3_A2_PLUS_DIV_SPREAD_GUARD"):
        for cash in CASH:
            report["chassis_rqa"][f"{ref_arm}_{cash}"] = exp13["chassis_rqa"][f"{ref_arm}_{cash}"]
        report["loyo"][f"RQA_{ref_arm}_69000"] = exp13["loyo"][f"RQA_{ref_arm}_69000"]
        report["loyo"][f"RQA_{ref_arm}_100000"] = exp13["loyo"][f"RQA_{ref_arm}_100000"]
        report["walk_forward"][f"RQA_{ref_arm}_69000"] = exp13["walk_forward"][f"RQA_{ref_arm}_69000"]
        report["walk_forward"][f"RQA_{ref_arm}_100000"] = exp13["walk_forward"][f"RQA_{ref_arm}_100000"]
        for sc in UNIFIED_CELLS:
            report["account_replay"][f"{sc}_{ref_arm}"] = exp13["account_replay"][f"{sc}_{ref_arm}"]

    for label, kw in b_specs:
        _run_chassis_pair(label, arm_weights[label], prov, group_fn, report["chassis_rqa"], rqa_chassis_eq, gold_w=float(kw["gold_w"]))

    # 3) Native RQAlpha 6.3.0 Unified Account Replays
    all_codes_rq = sorted(
        {
            FOCUS,
            GOLD,
            *(ts_to_rq(c) for c in VALUE_CHAIN_TS),
            *(ts_to_rq(c) for c in GROWTH_CHAIN_TS),
            *LOW_VOL_CHAIN_RQ,
            *LOW_TICKET_BONDS_RQ,
            *(ts_to_rq(c) for c in sector_pool_ts),
        }
    )
    feat_dfs = {}
    for rq in all_codes_rq:
        ts = rq_to_ts(rq)
        if ts in p.etf_adj_close.columns and ts in p.etf_raw_close.columns:
            df_i = indicators(p.etf_adj_close[ts], p.etf_raw_close[ts])
            df_i["ret60"] = df_i["c"] / df_i["c"].shift(60) - 1.0
            feat_dfs[rq] = df_i.where(p.etf_tradability_mask[ts], np.nan)
    features: dict[str, dict[str, Any]] = {}
    for dt in p.calendar:
        d_s = str(dt.date())
        features[d_s] = {
            rq: row
            for rq, df_i in feat_dfs.items()
            for row in [df_i.loc[dt]]
            if pd.notna(row["c"]) and pd.notna(row["raw"]) and float(row["raw"]) > 0
        }
    white_rq = {ts_to_rq(c) for c in prov.super_etf_codes}

    sys.stdout.write(f"{utc()} building BP1 v1 & QualityCore v2 candidates\n")
    sys.stdout.flush()
    cands_v1, bp1_stats_v1 = stock_signals.build_causal_bp1_candidates_202611(
        oos_start=OOS_CASH_START, bundle_end=END_DATE
    )
    cands_v2, bp1_stats_v2 = build_bp1_candidates_quality_v2(
        oos_start=OOS_CASH_START, bundle_end=END_DATE
    )
    report["bp1_candidate_stats"] = {"quality_v1": bp1_stats_v1, "quality_v2": bp1_stats_v2}

    cal_full = p.calendar[p.calendar <= END_DATE]
    days_cash = [str(d.date()) for d in cal_full[cal_full >= OOS_CASH_START]]
    days_conc = [str(d.date()) for d in cal_full[cal_full >= OOS_CONC_START]]

    mkt_maps: dict[str, dict[str, tuple[str, str, float]]] = {}
    tilt_maps: dict[str, dict[str, str] | None] = {}
    for label, kw in b_specs:
        er, eb, _, ts_s = compute_b_arm_regimes(
            p, reg, pit_df, use_b1_envelope=bool(kw["use_b1_envelope"]), use_b2_tilt=bool(kw["use_b2_tilt"])
        )
        mkt_maps[label] = {
            str(dt.date()): (str(er.at[dt]), str(reg.at[dt, "style"]), float(eb.at[dt])) for dt in p.calendar
        }
        tilt_maps[label] = {str(dt.date()): str(ts_s.at[dt]) for dt in p.calendar} if kw["use_b2_tilt"] else None

    for scenario, s_days, seed in (("OOS_CASH", days_cash, 0.0), ("CORE25", days_conc, 0.25), ("LEGACY70", days_conc, 0.70)):
        for cash in CASH:
            for label, kw in b_specs:
                cell = f"{scenario}_{cash}_{label}"
                sys.stdout.write(f"{utc()} acct {cell}\n")
                sys.stdout.flush()
                report["account_replay"][cell] = _replay_b_account_with_gold_or_tilt(
                    days=s_days,
                    market_map=mkt_maps[label],
                    features=features,
                    stock_candidates=cands_v1,
                    white=white_rq,
                    capital=float(cash),
                    seed=seed,
                    group_fn=group_fn,
                    gold_w=float(kw["gold_w"]),
                    tilt_map=tilt_maps[label],
                )

    # B3_BP1_QUALITY_V2_100K: on winning ETF arm (check B1 vs B2 on RQA 69k; B1 is primary)
    b1_r69_cal = report["chassis_rqa"]["B1_PIT_ERP_BP_ENVELOPE_69000"]["full"]["calmar"]
    b2_r69_cal = report["chassis_rqa"]["B2_IMPLIED_EXPECTATION_TILT_69000"]["full"]["calmar"]
    b3_etf_base = "B1_PIT_ERP_BP_ENVELOPE" if b1_r69_cal >= b2_r69_cal else "B2_IMPLIED_EXPECTATION_TILT"
    report["b3_etf_base"] = b3_etf_base
    # B3 shares ETF-only chassis & 69k unified accounts with b3_etf_base (69k never triggers >=100k BP1)
    vbt_eq["B3_BP1_QUALITY_V2_100K"] = vbt_eq[b3_etf_base]
    report["vbt"]["B3_BP1_QUALITY_V2_100K"] = report["vbt"][b3_etf_base]
    for cash in CASH:
        report["chassis_rqa"][f"B3_BP1_QUALITY_V2_100K_{cash}"] = report["chassis_rqa"][f"{b3_etf_base}_{cash}"]
        rqa_chassis_eq[f"B3_BP1_QUALITY_V2_100K_{cash}"] = rqa_chassis_eq[f"{b3_etf_base}_{cash}"]

    for scenario, s_days, seed in (("OOS_CASH", days_cash, 0.0), ("CORE25", days_conc, 0.25), ("LEGACY70", days_conc, 0.70)):
        # 69k shared with b3_etf_base (verify 0 BP1 fills)
        report["account_replay"][f"{scenario}_69000_B3_BP1_QUALITY_V2_100K"] = report["account_replay"][f"{scenario}_69000_{b3_etf_base}"]
        cell_100 = f"{scenario}_100000_B3_BP1_QUALITY_V2_100K"
        sys.stdout.write(f"{utc()} acct {cell_100}\n")
        sys.stdout.flush()
        report["account_replay"][cell_100] = _replay_b_account_with_gold_or_tilt(
            days=s_days,
            market_map=mkt_maps[b3_etf_base],
            features=features,
            stock_candidates=cands_v2,
            white=white_rq,
            capital=100000.0,
            seed=seed,
            group_fn=group_fn,
            gold_w=0.10,
            tilt_map=tilt_maps[b3_etf_base],
        )

    # 4) LOYO & Walk-Forward on VBT + RQA 69k/100k
    for label, eq in vbt_eq.items():
        if label != "B3_BP1_QUALITY_V2_100K":
            report["loyo"][f"VBT_{label}"] = _compute_loyo_metrics(eq)
            report["walk_forward"][f"VBT_{label}"] = _compute_walk_forward(eq)
    report["loyo"]["VBT_B3_BP1_QUALITY_V2_100K"] = report["loyo"][f"VBT_{b3_etf_base}"]
    report["walk_forward"]["VBT_B3_BP1_QUALITY_V2_100K"] = report["walk_forward"][f"VBT_{b3_etf_base}"]

    for key, eq in rqa_chassis_eq.items():
        report["loyo"][f"RQA_{key}"] = _compute_loyo_metrics(eq)
        report["walk_forward"][f"RQA_{key}"] = _compute_walk_forward(eq)

    # 5) ±5% Parameter Plateau around B1 (18 perturbations in VBT)
    plateau_specs = [
        ("gold_w_95bp", {"gold_w": 0.095}),
        ("gold_w_105bp", {"gold_w": 0.105}),
        ("lowvol_1425bp", {"lowvol_w": 0.1425}),
        ("lowvol_1575bp", {"lowvol_w": 0.1575}),
        ("gold_band_380bp", {"gold_band": 0.038}),
        ("gold_band_420bp", {"gold_band": 0.042}),
        ("ice10_th_095", {"ice10_th": 0.095}),
        ("ice10_th_105", {"ice10_th": 0.105}),
        ("ice10_days_14", {"ice10_days": 14}),
        ("ice10_days_16", {"ice10_days": 16}),
        ("ice10_floor_3325", {"ice10_floor_w": 0.3325}),
        ("ice10_floor_3675", {"ice10_floor_w": 0.3675}),
        ("high_ice10_400", {"high_ice10_w": 0.40}),
        ("high_ice10_450", {"high_ice10_w": 0.45}),
        ("erp_high_76_71", {"erp_high_enter": 0.76, "erp_high_exit": 0.71}),
        ("erp_high_84_79", {"erp_high_enter": 0.84, "erp_high_exit": 0.79}),
        ("bp_high_665_6175", {"bp_high_enter": 0.665, "bp_high_exit": 0.6175}),
        ("bp_high_735_6825", {"bp_high_enter": 0.735, "bp_high_exit": 0.6825}),
    ]
    distinct_vbt_eqs = {k: v for k, v in vbt_eq.items() if k != "B3_BP1_QUALITY_V2_100K"}
    all_vbt_eqs = dict(distinct_vbt_eqs)
    a0_cal = report["vbt"]["A0_V331"]["full_2018_20261126"]["calmar"]
    b1_cal = report["vbt"]["B1_PIT_ERP_BP_ENVELOPE"]["full_2018_20261126"]["calmar"]
    peak_gain = max(1e-6, b1_cal - a0_cal)
    plateau_rows: list[dict[str, Any]] = []
    for p_name, p_kw in plateau_specs:
        ow_p, _ = build_b_chassis_weights(p, reg, pit_df, use_b1_envelope=True, use_b2_tilt=False, end=END_DATE, **p_kw)
        eq_p = _eval_vbt(p, prov, ow_p)
        all_vbt_eqs[p_name] = eq_p
        st_p = compute_calendar_stats(eq_p)
        ret_gain = (st_p["calmar"] - a0_cal) / peak_gain
        plateau_rows.append(
            {
                "variant": p_name,
                "cagr": round(st_p["cagr"], 6),
                "max_dd": round(st_p["max_drawdown"], 6),
                "calmar": round(st_p["calmar"], 4),
                "gain_retention": round(ret_gain, 4),
            }
        )
    min_retention = min(r["gain_retention"] for r in plateau_rows)
    report["plateau"] = {
        "a0_calmar": a0_cal,
        "b1_calmar": b1_cal,
        "min_gain_retention": round(min_retention, 4),
        "median_gain_retention": round(float(np.median([r["gain_retention"] for r in plateau_rows])), 4),
        "variants": plateau_rows,
    }

    # 6) Dual-scope CSCV PBO & cumulative DSR
    # Exp14 distinct VBT arms = 4 (B0, B1, B2, B1_G5_DIAG) + 18 plateau + 1 (B3 stock overlay) = 23
    # Cumulative across Exp13 (22) + new Exp14 distinct (3) + Exp14 plateau (18) + B3 (1) = 44
    n_exp14 = 4 + len(plateau_specs) + 1
    n_cum = 22 + 3 + len(plateau_specs) + 1
    for arm_key in ("B0_A2_BASE", "B1_PIT_ERP_BP_ENVELOPE", "B2_IMPLIED_EXPECTATION_TILT", "B1_G5_DIAG", "B3_BP1_QUALITY_V2_100K"):
        cscv_key = b3_etf_base if arm_key == "B3_BP1_QUALITY_V2_100K" else arm_key
        mt = compute_dual_multiple_testing(
            distinct_vbt_eqs,
            all_vbt_eqs,
            cscv_key,
            n_trials_exp14=n_exp14,
            n_trials_cumulative=n_cum,
        )
        mt["candidate"] = arm_key
        report["multiple_testing"][arm_key] = mt

    # 7) Evaluate 7 Hard Gates for all B arms vs A0_V331
    new_rqa_keys = [k for k in report["chassis_rqa"] if not k.startswith(("A0_", "A3_"))]
    new_acct_keys = [k for k in report["account_replay"] if not k.endswith(("A0_V331", "A3_A2_PLUS_DIV_SPREAD_GUARD"))]
    integrity_ok = (
        all(
            report["chassis_rqa"][k]["dates_pass"]
            and report["chassis_rqa"][k]["fill_capture_pass"]
            and report["chassis_rqa"][k]["fees_pass"]
            and report["chassis_rqa"][k]["illegal_non_lot_fills"] == 0
            for k in new_rqa_keys
        )
        and all(report["account_replay"][k]["violation_count"] == 0 for k in new_acct_keys)
    )
    report["integrity_ok"] = integrity_ok

    gate_eval: dict[str, Any] = {}
    eval_arms = (
        "B0_A2_BASE",
        "B1_PIT_ERP_BP_ENVELOPE",
        "B2_IMPLIED_EXPECTATION_TILT",
        "B3_BP1_QUALITY_V2_100K",
        "B1_G5_DIAG",
    )
    v_0 = report["vbt"]["A0_V331"]
    r69_0 = report["chassis_rqa"]["A0_V331_69000"]
    for arm_label in eval_arms:
        v_a = report["vbt"][arm_label]
        r69_a = report["chassis_rqa"][f"{arm_label}_69000"]
        r100_a = report["chassis_rqa"][f"{arm_label}_100000"]

        g1_vbt = (
            v_a["is_2018_2023"]["cagr"] > v_0["is_2018_2023"]["cagr"]
            and v_a["is_2018_2023"]["calmar"] > v_0["is_2018_2023"]["calmar"]
            and v_a["oos_2024_20261126"]["cagr"] > v_0["oos_2024_20261126"]["cagr"]
            and v_a["oos_2024_20261126"]["calmar"] > v_0["oos_2024_20261126"]["calmar"]
            and v_a["full_2018_20261126"]["calmar"] >= v_0["full_2018_20261126"]["calmar"] * 1.35
        )
        g1_r69 = (
            r69_a["is"]["cagr"] > r69_0["is"]["cagr"]
            and r69_a["is"]["calmar"] > r69_0["is"]["calmar"]
            and r69_a["oos"]["cagr"] > r69_0["oos"]["cagr"]
            and r69_a["oos"]["calmar"] > r69_0["oos"]["calmar"]
            and r69_a["full"]["calmar"] >= r69_0["full"]["calmar"] * 1.35
        )
        g1_pass = bool(g1_vbt and g1_r69)

        accts_a = {sc: report["account_replay"][f"{sc}_{arm_label}"] for sc in UNIFIED_CELLS}
        full_dds = [v_a["full_2018_20261126"]["max_drawdown"], r69_a["full"]["max_drawdown"], r100_a["full"]["max_drawdown"]]
        acct_true_dds = {k: -accts_a[k]["true_max_dd"] for k in accts_a}
        acct_69_dds = [acct_true_dds[k] for k in ("OOS_CASH_69000", "CORE25_69000", "LEGACY70_69000")]
        breaches = sum(accts_a[k]["breach_days"] for k in accts_a)
        g2_pass = bool(
            all(d >= -0.12 for d in full_dds)
            and all(d >= -0.12 for d in acct_true_dds.values())
            and all(d >= -0.10 for d in acct_69_dds)
            and breaches == 0
        )

        st_vbt = v_a["stress_2026h2"]
        st_r69 = r69_a["stress_2026h2"]
        g3_pass = bool(
            st_vbt["total_return"] >= -0.015
            and st_vbt["max_drawdown"] >= -0.06
            and st_r69["total_return"] >= -0.015
            and st_r69["max_drawdown"] >= -0.06
        )

        ex25_vbt = report["loyo"][f"VBT_{arm_label}"]["ex_2025"]["calmar"]
        ex25_vbt_0 = report["loyo"]["VBT_A0_V331"]["ex_2025"]["calmar"]
        ex25_r69 = report["loyo"][f"RQA_{arm_label}_69000"]["ex_2025"]["calmar"]
        ex25_r69_0 = report["loyo"]["RQA_A0_V331_69000"]["ex_2025"]["calmar"]
        g4_pass = bool(ex25_vbt > ex25_vbt_0 and ex25_r69 > ex25_r69_0)

        wf_a = report["walk_forward"][f"RQA_{arm_label}_69000"]
        wf_0 = report["walk_forward"]["RQA_A0_V331_69000"]
        wf_wins = sum(1 for a_w, z_w in zip(wf_a, wf_0, strict=True) if a_w["oos_calmar"] >= z_w["oos_calmar"])
        g5_plateau = min_retention >= 0.85 if arm_label in ("B1_PIT_ERP_BP_ENVELOPE", "B3_BP1_QUALITY_V2_100K") else True
        g5_pass = bool(wf_wins >= 4 and g5_plateau)

        mt = report["multiple_testing"][arm_label]
        g6_pass = bool(mt["dsr_prob_cum"] >= 0.50 and mt["pbo_distinct"] <= 0.50)

        gate_eval[arm_label] = {
            "G1_IS_OOS_and_Calmar_35pct": {
                "pass": g1_pass,
                "vbt_is_cagr": round(v_a["is_2018_2023"]["cagr"], 6),
                "r69_is_cagr": round(r69_a["is"]["cagr"], 6),
                "r69_a0_is_cagr": round(r69_0["is"]["cagr"], 6),
                "vbt_calmar_lift_pct": round((v_a["full_2018_20261126"]["calmar"] / v_0["full_2018_20261126"]["calmar"] - 1.0) * 100.0, 2),
                "r69_calmar_lift_pct": round((r69_a["full"]["calmar"] / r69_0["full"]["calmar"] - 1.0) * 100.0, 2),
            },
            "G2_True_Peak_DD": {
                "pass": g2_pass,
                "worst_full_dd": round(min(full_dds), 4),
                "worst_acct_true_dd": round(min(acct_true_dds.values()), 4),
                "worst_69k_acct_true_dd": round(min(acct_69_dds), 4),
                "acct_true_dds": {k: round(v, 4) for k, v in acct_true_dds.items()},
                "breach_days": breaches,
            },
            "G3_2026H2_Stress": {
                "pass": g3_pass,
                "vbt_2026h2_ret": round(st_vbt["total_return"], 4),
                "vbt_2026h2_dd": round(st_vbt["max_drawdown"], 4),
                "r69_2026h2_ret": round(st_r69["total_return"], 4),
                "r69_2026h2_dd": round(st_r69["max_drawdown"], 4),
            },
            "G4_LOYO_Ex2025": {
                "pass": g4_pass,
                "vbt_ex2025_calmar": ex25_vbt,
                "vbt_a0_ex2025_calmar": ex25_vbt_0,
                "r69_ex2025_calmar": ex25_r69,
                "r69_a0_ex2025_calmar": ex25_r69_0,
            },
            "G5_WalkForward_and_Plateau": {
                "pass": g5_pass,
                "r69_wf_calmar_wins_of_6": wf_wins,
                "min_plateau_retention": report["plateau"]["min_gain_retention"] if arm_label in ("B1_PIT_ERP_BP_ENVELOPE", "B3_BP1_QUALITY_V2_100K") else None,
            },
            "G6_Multiple_Testing": {
                "pass": g6_pass,
                **mt,
            },
        }

    def _occam_step(prev_arm: str, next_arm: str) -> dict[str, Any]:
        p69 = report["chassis_rqa"][f"{prev_arm}_69000"]
        n69 = report["chassis_rqa"][f"{next_arm}_69000"]
        d_cal = round(n69["full"]["calmar"] - p69["full"]["calmar"], 4)
        d_dd_pp = round((abs(p69["full"]["max_drawdown"]) - abs(n69["full"]["max_drawdown"])) * 100.0, 3)
        d_cagr_pp = round((n69["full"]["cagr"] - p69["full"]["cagr"]) * 100.0, 3)
        d_is_cagr_pp = round((n69["is"]["cagr"] - p69["is"]["cagr"]) * 100.0, 3)
        d_oos_cagr_pp = round((n69["oos"]["cagr"] - p69["oos"]["cagr"]) * 100.0, 3)

        acct_69_p = [report["account_replay"][f"{s}_69000_{prev_arm}"]["metrics"]["calmar"] for s in ("OOS_CASH", "CORE25", "LEGACY70")]
        acct_69_n = [report["account_replay"][f"{s}_69000_{next_arm}"]["metrics"]["calmar"] for s in ("OOS_CASH", "CORE25", "LEGACY70")]
        acct_100_p = [report["account_replay"][f"{s}_100000_{prev_arm}"]["metrics"]["calmar"] for s in ("OOS_CASH", "CORE25", "LEGACY70")]
        acct_100_n = [report["account_replay"][f"{s}_100000_{next_arm}"]["metrics"]["calmar"] for s in ("OOS_CASH", "CORE25", "LEGACY70")]

        hurdle_ok = (d_cal >= 0.03) or (d_dd_pp >= 0.8 and d_cagr_pp >= -0.05)
        no_deg = (d_is_cagr_pp >= -0.15) and (d_oos_cagr_pp >= -0.15)
        return {
            "pass": bool(hurdle_ok and no_deg),
            "r69_full_calmar_delta": d_cal,
            "r69_full_dd_reduction_pp": d_dd_pp,
            "r69_full_cagr_delta_pp": d_cagr_pp,
            "r69_is_cagr_delta_pp": d_is_cagr_pp,
            "r69_oos_cagr_delta_pp": d_oos_cagr_pp,
            "r69_acct_mean_calmar_delta": round(float(np.mean(acct_69_n) - np.mean(acct_69_p)), 4),
            "r100_acct_mean_calmar_delta": round(float(np.mean(acct_100_n) - np.mean(acct_100_p)), 4),
        }

    report["gates"] = {
        "integrity_ok": integrity_ok,
        "by_arm": gate_eval,
        "G7_Occam": {
            "B0_to_B1": _occam_step("B0_A2_BASE", "B1_PIT_ERP_BP_ENVELOPE"),
            "B1_to_B2": _occam_step("B1_PIT_ERP_BP_ENVELOPE", "B2_IMPLIED_EXPECTATION_TILT"),
            "B1_to_B1_G5_DIAG": _occam_step("B1_PIT_ERP_BP_ENVELOPE", "B1_G5_DIAG"),
            "B1_to_B3_100K": _occam_step(b3_etf_base, "B3_BP1_QUALITY_V2_100K"),
        },
    }

    report["finished"] = utc()
    (REPORTS_DIR / "exp_v3_14_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown_report(report)
    return 0


def _write_markdown_report(report: dict[str, Any]) -> None:
    lines: list[str] = [
        "# EXP-V3-14：40季 PIT ERP+B/P 双极值包络 + 隐含预期倾斜 + QualityCore v2 防雷回测报告",
        "",
        f"- **Bundle**：`{report['bundle_path']}`（`2018-01-02..2026-11-26`）",
        f"- **完整性硬门禁**：`{report['integrity_ok']}`",
        f"- **B3 100k 底座 ETF 臂**：`{report['b3_etf_base']}`",
        "",
        "## 1. 全窗 VectorBT（2018-01-02..2026-11-26）",
        "",
        "| Arm | Full CAGR / DD / Calmar | IS(18-23) CAGR / Calmar | OOS(24-26) CAGR / DD / Calmar | 2026H2(Ret/DD) | 调仓 / 极值日(低估/泡沫) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm, blk in report["vbt"].items():
        if arm == "B3_BP1_QUALITY_V2_100K":
            continue
        f, is_, oos, st = (
            blk["full_2018_20261126"],
            blk["is_2018_2023"],
            blk["oos_2024_20261126"],
            blk["stress_2026h2"],
        )
        ctrl = blk["ctrl"]
        ext = f"{ctrl.get('rebal_events', '—')} ({ctrl.get('underval_days', 0)}/{ctrl.get('bubble_days', 0)})"
        lines.append(
            f"| {arm} | {f['cagr']:.2%} / {f['max_drawdown']:.2%} / {f['calmar']:.3f} "
            f"| {is_['cagr']:.2%} / {is_['calmar']:.3f} "
            f"| {oos['cagr']:.2%} / {oos['max_drawdown']:.2%} / {oos['calmar']:.3f} "
            f"| {st['total_return']:.2%} / {st['max_drawdown']:.2%} | {ext} |"
        )

    lines += [
        "",
        "## 2. 全窗原生 RQAlpha 6.3.0 底盘（2018-01-02..2026-11-26 @ ¥69k & ¥100k）",
        "",
        "| 回放 | Full CAGR | IS CAGR | OOS CAGR | MaxDD | Sharpe | Calmar | 2026H2(Ret/DD) | 笔数 | 佣金(元) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k, r in report["chassis_rqa"].items():
        if k.startswith("B3_"):
            continue
        f, is_, oos, st = r["full"], r["is"], r["oos"], r["stress_2026h2"]
        lines.append(
            f"| {k} | {f['cagr']:.2%} | {is_['cagr']:.2%} | {oos['cagr']:.2%} | {f['max_drawdown']:.2%} "
            f"| {f['sharpe']:.3f} | {f['calmar']:.3f} | {st['total_return']:.2%} / {st['max_drawdown']:.2%} "
            f"| {r['trade_count']} | {r['commission_yuan']:.2f} |"
        )

    lines += [
        "",
        "## 3. 统一账户原生 RQAlpha 6.3.0 全 6 组明细（2024-02/07..2026-11-26）",
        "",
        "| 场景 | CAGR(净) | MaxDD(净) | 真实Peak DD | 穿-15%天 | Calmar | Sharpe | 摩擦(元) | BP1笔数/盈亏 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell, r in report["account_replay"].items():
        m = r["metrics"]
        bp1 = r.get("bp1_summary", {"closed_trades": 0, "pnl_yuan": 0.0})
        lines.append(
            f"| {cell} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {-r['true_max_dd']:.2%} "
            f"| {r['breach_days']} | {m['calmar']:.3f} | {m['sharpe']:.3f} | {r['total_friction_yuan']:.2f} "
            f"| {bp1['closed_trades']} / {bp1['pnl_yuan']:.2f} |"
        )

    lines += [
        "",
        "## 4. 7 条硬门禁与双口径 PBO / 累积 DSR 汇总",
        "",
        "| 臂 | G1 IS/OOS+35% | G2 TrueDD(全/69k/100k) | G3 2026H2 | G4 LOYO去2025 | G5 WF+高原 | G6 DSR(累积) / PBO(去重/含微扰) |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm, g in report["gates"]["by_arm"].items():
        g1, g2, g3, g4, g5, g6 = (
            g["G1_IS_OOS_and_Calmar_35pct"],
            g["G2_True_Peak_DD"],
            g["G3_2026H2_Stress"],
            g["G4_LOYO_Ex2025"],
            g["G5_WalkForward_and_Plateau"],
            g["G6_Multiple_Testing"],
        )
        def _p_str(x: dict[str, Any]) -> str:
            return "PASS" if x["pass"] else "FAIL"

        lines.append(
            f"| {arm} | {_p_str(g1)} (R69k +{g1['r69_calmar_lift_pct']:.1f}%, IS {g1['r69_is_cagr']:.2%}) "
            f"| {_p_str(g2)} ({g2['worst_full_dd']:.2%}/{g2['worst_69k_acct_true_dd']:.2%}/{g2['worst_acct_true_dd']:.2%}) "
            f"| {_p_str(g3)} ({g3['r69_2026h2_ret']:.2%}) "
            f"| {_p_str(g4)} (R69k {g4['r69_ex2025_calmar']:.3f}) "
            f"| {_p_str(g5)} ({g5['r69_wf_calmar_wins_of_6']}/6, {g5['min_plateau_retention']}) "
            f"| {_p_str(g6)} (DSR={g6['dsr_prob_cum']:.3f} N={g6['n_trials_cumulative']}, PBO={g6['pbo_distinct']:.3f}/{g6['pbo_with_perturb']:.3f}) |"
        )

    lines += ["", "## 5. G7 奥卡姆逐层边际增量（69k 原生 RQA / 统一账户）", ""]
    lines += [
        "| 跃迁 | PASS | R69k ΔCalmar | R69k ΔMaxDD(pp) | ΔIS CAGR(pp) | ΔOOS CAGR(pp) | 69k账户均值ΔCalmar | 100k账户均值ΔCalmar |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for step_name, st in report["gates"]["G7_Occam"].items():
        lines.append(
            f"| {step_name} | {'PASS' if st['pass'] else 'FAIL'} | {st['r69_full_calmar_delta']:+.4f} "
            f"| {st['r69_full_dd_reduction_pp']:+.3f} | {st['r69_is_cagr_delta_pp']:+.3f} "
            f"| {st['r69_oos_cagr_delta_pp']:+.3f} | {st['r69_acct_mean_calmar_delta']:+.4f} "
            f"| {st['r100_acct_mean_calmar_delta']:+.4f} |"
        )

    (REPORTS_DIR / "exp_v3_14_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
