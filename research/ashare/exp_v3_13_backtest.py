"""EXP-V3-13: Orthogonal ladder A0..A3 on extended bundle_20261126 (2018-01-02..2026-11-26).

Dual-engine (VectorBT + native RQAlpha 6.3.0 69k/100k chassis & 6 unified accounts)
plus all 7 anti-overfitting and Occam's Razor hard gates.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from importlib.metadata import version
from itertools import combinations
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rqalpha import run_func
from rqalpha.const import INSTRUMENT_TYPE
from rqalpha.core.events import EVENT
from rqalpha.environment import Environment
from rqalpha.mod.rqalpha_mod_sys_accounts.trade_utils import get_amount_from_value
from rqalpha.mod.utils import round_order_quantity
from scipy.stats import norm

from research.ashare import v3_data_202611 as data
from research.ashare.exp_v3_13_pit_div_spread import BUNDLE_20261126
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
    BOND_SET_RQ,
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
from research.batches.exp_v3_12_v331_architecture.run_r2 import run_with_upward_sticky
from research.batches.v3_account_replay_v2 import native as acct_native
from research.batches.v3_account_replay_v2 import stock_signals
from research.batches.v3_account_replay_v2.native import TieredFees, asset_group, opening_block
from research.batches.v3_account_replay_v2.policy import FOCUS, GOLD, GROWTH, VALUE, indicators
from research.batches.v3_account_replay_v2.stock_signals import build_causal_bp1_candidates_202611
from research.batches.v3_complexity_hurdle_v2 import native as hurdle_native
from research.batches.v3_complexity_hurdle_v2.native import NORMAL, SUPER, replay
from research.batches.v3_complexity_hurdle_v2.run import require, utc
from tacticore.engines.rqalpha_adapter import build_rqalpha_config
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
REPORTS_DIR = ROOT / "research/ashare/reports"
PIT_CSV = REPORTS_DIR / "exp_v3_13_pit_div_spread_2014_2026.csv"
END_DATE = pd.Timestamp("2026-11-26")

# Include 510880.SH as early 2018 low-vol fallback before 512890.SH listed (2019-01-18)
LOW_VOL_CHAIN_TS = ("159549.SZ", "159207.SZ", "512890.SH", "510880.SH")
LOW_VOL_CHAIN_RQ = tuple(ts_to_rq(c) for c in LOW_VOL_CHAIN_TS)
VALUE_CHAIN_TS = ("159330.SZ", "530050.SH", "510140.SH", "510300.SH")
GROWTH_CHAIN_TS = ("159205.SZ", "159337.SZ", "589850.SH", "159290.SZ", "589060.SH", "589330.SH", "510500.SH", "159915.SZ")
GOLD_TS = "518880.SH"


def _patch_bundle_paths() -> None:
    """Point in-memory bundle constants to bundle_20261126_root without modifying frozen modules."""
    data.BUNDLE_PATH_202611 = BUNDLE_20261126
    stock_signals.BUNDLE_PATH_202611 = BUNDLE_20261126
    acct_native.BUNDLE_PATH_202611 = BUNDLE_20261126
    hurdle_native.BUNDLE_PATH_202611 = BUNDLE_20261126


def _pick_upward_sticky(
    chain: tuple[str, ...],
    exec_dt: pd.Timestamp,
    mask: pd.DataFrame,
    adj: pd.DataFrame,
    held_codes: set[str],
    count: int = 1,
    min_bars: int = 20,
) -> list[str]:
    """Upward-only sticky selector: first `count` items that are (held & listed) or (tradable & >=20 bars)."""
    hist = adj.loc[:exec_dt]
    chosen: list[str] = []
    for c in chain:
        if c not in mask.columns:
            continue
        is_tradable = bool(mask.at[exec_dt, c])
        has_bars = int(hist[c].notna().sum()) >= min_bars
        is_held_ok = (c in held_codes) and pd.notna(adj.at[exec_dt, c]) and float(adj.at[exec_dt, c]) > 0
        if is_held_ok or (is_tradable and has_bars):
            chosen.append(c)
            if len(chosen) >= count:
                break
    return chosen


def compute_arm_effective_regimes(
    panels: Any,
    regime_df: pd.DataFrame,
    spread_df: pd.DataFrame,
    *,
    arm: str,
    ice10_th: float = 0.10,
    ice10_days: int = 15,
    ice10_floor_w: float = 0.35,
    high_ice10_w: float = 0.425,
    high_rec_w: float = 0.50,
    high_str_w: float = 0.65,
    low_off_w: float = 0.70,
    low_str_w: float = 0.50,
    high_enter: float = 0.80,
    high_exit: float = 0.75,
    low_enter: float = 0.15,
    low_exit: float = 0.20,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return strictly causal (eff_regime, base_eq_budget, spread_state) series over panels.calendar."""
    cal = panels.calendar
    eff_m2, _, _ = compute_recovery_overlay_series(
        panels, regime_df, mode="m2_thrust", ice_th=0.15, recovery_weight=0.40
    )

    # Recompute causal spread state with given thresholds (allows +/-5% plateau perturbation)
    pct_s = spread_df["pct_756"].reindex(cal)
    sp_states: list[str] = []
    cur_sp = "NEUTRAL"
    for p in pct_s:
        if not np.isfinite(p):
            sp_states.append("NEUTRAL")
            continue
        if cur_sp == "HIGH_SPREAD":
            if p <= low_enter:
                cur_sp = "LOW_SPREAD"
            elif p < high_exit:
                cur_sp = "NEUTRAL"
        elif cur_sp == "LOW_SPREAD":
            if p >= high_enter:
                cur_sp = "HIGH_SPREAD"
            elif p > low_exit:
                cur_sp = "NEUTRAL"
        else:
            if p >= high_enter:
                cur_sp = "HIGH_SPREAD"
            elif p <= low_enter:
                cur_sp = "LOW_SPREAD"
        sp_states.append(cur_sp)
    sp_series = pd.Series(sp_states, index=cal)

    pct60 = regime_df["pct_above_ma60"].reindex(cal)
    eff_regs: list[str] = []
    eff_budgets: list[float] = []
    ice10_until = -1000

    for pos, dt in enumerate(cal):
        base_r = str(eff_m2.at[dt])
        p60 = float(pct60.at[dt]) if pd.notna(pct60.at[dt]) else 1.0
        if arm in ("A2", "A3") and p60 < ice10_th:
            ice10_until = pos + ice10_days
        ice10_active = arm in ("A2", "A3") and (pos <= ice10_until)

        sp = sp_series.at[dt] if arm == "A3" else "NEUTRAL"
        if base_r == "DEFENSIVE" and ice10_active:
            reg_out = "ICE_10"
        else:
            reg_out = base_r

        if arm == "A1":
            b_map = {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "RECOVERY": 0.40, "DEFENSIVE": 0.25}
            budget = b_map[reg_out]
        elif arm == "A2":
            b_map = {
                "OFFENSIVE": 0.85,
                "STRUCTURAL": 0.60,
                "RECOVERY": 0.40,
                "ICE_10": ice10_floor_w,
                "DEFENSIVE": 0.25,
            }
            budget = b_map[reg_out]
        else:  # A3
            if sp == "HIGH_SPREAD":
                b_map = {
                    "OFFENSIVE": 0.85,
                    "STRUCTURAL": high_str_w,
                    "RECOVERY": high_rec_w,
                    "ICE_10": high_ice10_w,
                    "DEFENSIVE": 0.25,  # Always 25% in normal DEFENSIVE!
                }
            elif sp == "LOW_SPREAD":
                b_map = {
                    "OFFENSIVE": low_off_w,
                    "STRUCTURAL": low_str_w,
                    "RECOVERY": 0.40,
                    "ICE_10": ice10_floor_w,  # Do NOT lift ICE_10 in LOW_SPREAD
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
            budget = b_map[reg_out]

        eff_regs.append(reg_out)
        eff_budgets.append(float(budget))

    return (
        pd.Series(eff_regs, index=cal),
        pd.Series(eff_budgets, index=cal, dtype=float),
        sp_series,
    )


def build_core40_chassis_weights(
    panels: Any,
    regime_df: pd.DataFrame,
    spread_df: pd.DataFrame,
    *,
    arm: str,
    end: pd.Timestamp = END_DATE,
    lowvol_w: float = 0.15,
    gold_w: float = 0.10,
    gold_band: float = 0.04,
    bond_band: float = 0.10,
    sat_drift_band: float = 0.10,
    **kwargs: Any,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build strictly causal T+1 sparse target weights for A1/A2/A3 with CORE40 + REGIME_ONLY + P0 overlay."""
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    adj = panels.etf_adj_close
    mask = panels.etf_tradability_mask
    cols = list(adj.columns)
    rets = adj.loc[cal].ffill().pct_change(fill_method=None).fillna(0.0)

    eff_reg, eff_budget, sp_series = compute_arm_effective_regimes(
        panels, regime_df, spread_df, arm=arm, **kwargs
    )
    ctrl = DrawdownController(init_nav=1.0, mode="c3_gradual", floor_dd=0.15, cppi_m=5.0)
    out_w = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)

    nav = 1.0
    cur_w = pd.Series(0.0, index=cols, dtype=float)  # drifted portfolio weights at sig_dt
    prev_state_key: tuple[str, float, bool] | None = None
    prev_locked = False
    max_true_dd = 0.0
    breach_days = 0
    rebal_count = 0

    for pos in range(len(cal) - 1):
        sig_dt = cal[pos]
        exec_dt = cal[pos + 1]
        if pos > 0:
            r_day = rets.loc[sig_dt]
            port_r = float((cur_w * r_day).sum())
            nav *= 1.0 + port_r
            cur_w = cur_w * (1.0 + r_day)
            s_sum = float(cur_w.sum())
            if s_sum > 1e-12:
                cur_w = cur_w / s_sum

        reg_s = str(eff_reg.at[sig_dt])
        style = str(regime_df.at[sig_dt, "style"])
        base_eq_budget = float(eff_budget.at[sig_dt])

        st = ctrl.step(pos, nav, concentrated=False, base_eq_budget=base_eq_budget)
        max_true_dd = max(max_true_dd, float(st["true_dd"]))
        if st["breach"] > 0:
            breach_days += 1

        # A2/A3: Disable ICE_10 floor when P0 L2 is locked (reverts to DEFENSIVE 25% capped by L2 10%)
        locked = bool(st["locked"])
        if reg_s == "ICE_10" and locked:
            base_eq_budget = 0.25
            reg_eff = "DEFENSIVE"
        else:
            reg_eff = reg_s

        cap = float(st["buy_cap"])
        target_eq = min(base_eq_budget, cap)

        # Build desired portfolio at exec_dt
        held_codes = {c for c in cols if float(cur_w[c]) > 1e-4}
        desired = pd.Series(0.0, index=cols, dtype=float)

        # Core 25%: 15% Low-Vol + 10% Gold (scaled down if P0 cap < core_risk)
        core_risk_target = lowvol_w + gold_w
        if target_eq >= core_risk_target - 1e-9:
            lv_target = lowvol_w
            g_target = gold_w
            sat_target = target_eq - core_risk_target
        else:
            scale_core = target_eq / max(core_risk_target, 1e-9)
            lv_target = lowvol_w * scale_core
            g_target = gold_w * scale_core
            sat_target = 0.0

        lv_picks = _pick_upward_sticky(LOW_VOL_CHAIN_TS, exec_dt, mask, adj, held_codes, count=2)
        if lv_picks and lv_target > 0:
            for c in lv_picks:
                desired[c] += lv_target / len(lv_picks)

        # Gold with ±400bps wide drift band when not forced down by P0
        if g_target > 0 and bool(mask.at[exec_dt, GOLD_TS]):
            cur_g = float(cur_w[GOLD_TS])
            if cur_g > 1e-4 and abs(cur_g - g_target) < gold_band and st["ctrl_cap"] is None:
                desired[GOLD_TS] = cur_g
                # Adjust sat_target slightly so total equity stays consistent
                sat_target = max(0.0, target_eq - lv_target - cur_g)
            else:
                desired[GOLD_TS] = g_target

        if sat_target > 0.01:
            gro_share, val_share = (
                (0.65, 0.35)
                if style == "GROWTH_LEADING"
                else ((0.35, 0.65) if style == "VALUE_LEADING" else (0.50, 0.50))
            )
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

        # REGIME_ONLY trigger check: regime/budget change, P0 lock/trigger/cap change, or extreme drift
        state_key = (reg_eff, round(float(target_eq), 4), locked)
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

        eq_drift = float((desired.drop(labels=list(BOND_SET_TS), errors="ignore") - cur_w.drop(labels=list(BOND_SET_TS), errors="ignore")).abs().sum())
        extreme_drift = eq_drift >= sat_drift_band or gold_breach or bond_breach

        if pos == 0 or state_changed or unlocked_today or bool(st["trigger"]) or extreme_drift:
            # Keep Gold untouched if inside drift band & not P0 forced
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
        "high_spread_days": int((sp_series == "HIGH_SPREAD").sum()) if arm == "A3" else 0,
        "low_spread_days": int((sp_series == "LOW_SPREAD").sum()) if arm == "A3" else 0,
    }


def select_core40_account_targets(
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
    """Select target equity weights for A1/A2/A3 in unified RQAlpha account replay."""

    def valid(c: str) -> bool:
        return c in features and pd.notna(features[c].ma20) and features[c].raw > 0

    def holdable(c: str) -> bool:
        return bool(held_mv.get(c, 0.0) > 0 and c in features and pd.notna(features[c].raw) and features[c].raw > 0)

    def eligible(c: str) -> bool:
        return holdable(c) or valid(c)

    eff_total = max(0.0, budget_total)
    core_risk = 0.25
    if eff_total >= core_risk - 1e-9:
        lv_w = 0.15
        gold_w = 0.10
    else:
        sc = eff_total / core_risk
        lv_w = 0.15 * sc
        gold_w = 0.10 * sc

    out: dict[str, float] = {}
    lv_picks = [c for c in LOW_VOL_CHAIN_RQ if eligible(c)][:2]
    if lv_picks and lv_w > 0.005:
        for c in lv_picks:
            out[c] = lv_w / len(lv_picks)

    if gold_w > 0.005 and eligible(GOLD):
        cur_gold_w = held_mv.get(GOLD, 0.0) / max(nav, 1.0)
        # Wide ±400bps drift band [6%, 14%] and >= 5000 yuan single leg unless P0 reduces
        if p0_ctrl_cap is None and cur_gold_w > 0.005:
            if abs(cur_gold_w - gold_w) < 0.04 or abs(cur_gold_w - gold_w) * nav < 5000.0:
                out[GOLD] = cur_gold_w
            else:
                out[GOLD] = gold_w
        else:
            out[GOLD] = gold_w

    core_used = sum(out.values())
    sat_room = max(0.0, eff_total - core_used - occupied_weight)
    if sat_room > 0.01:
        val_chain = tuple(ts_to_rq(c) for c in VALUE_CHAIN_TS)
        gro_chain = tuple(ts_to_rq(c) for c in GROWTH_CHAIN_TS)
        val_c = next((c for c in val_chain if eligible(c)), None)
        gro_c = next((c for c in gro_chain if eligible(c)), None)
        gro_share, val_share = (
            (0.65, 0.35)
            if style == "GROWTH_LEADING"
            else ((0.35, 0.65) if style == "VALUE_LEADING" else (0.50, 0.50))
        )
        if val_c and gro_c:
            out[val_c] = sat_room * val_share
            out[gro_c] = sat_room * gro_share
        elif val_c:
            out[val_c] = sat_room
        elif gro_c:
            out[gro_c] = sat_room

    return {c: w for c, w in out.items() if w > 0.01}


def replay_core40_account(
    *,
    days: list[str],
    market_map: dict[str, tuple[str, str, float]],  # date -> (regime, style, eq_budget)
    features: dict[str, dict[str, Any]],
    stock_candidates: dict[str, list[Any]],
    white: set[str],
    capital: float,
    seed: float,
    group_fn: Any,
) -> dict[str, Any]:
    """Native RQAlpha 6.3.0 unified account replay for A1/A2/A3 with CORE40 + REGIME_ONLY."""
    from rqalpha.api import history_bars, instruments, order_shares, subscribe_event

    cfg = build_rqalpha_config(
        days[0],
        days[-1],
        initial_cash=capital,
        fees=0.00025,
        slippage=0,
        bundle_path=BUNDLE_20261126,
        rqalpha_major_version=6,
    )
    cfg["mod"]["sys_accounts"] = {"stock_t1": True, "auto_switch_order_value": False}

    ctrl = DrawdownController(init_nav=capital, mode="c3_gradual", floor_dd=0.15, cppi_m=5.0)
    bond_priority = LOW_TICKET_BONDS_RQ
    bond_drift_band = 0.10
    equity_drift_band = 0.08
    align_glide_cap = 0.35

    lookup = {d: idx for idx, d in enumerate(days)}
    pending: dict[str, dict[str, Any]] = {}
    retries: dict[str, dict[str, Any]] = {}
    armed: dict[str, bool] = {}
    stock_stops: dict[str, dict[str, Any]] = {}
    state: dict[str, Any] = {"regime": None, "budget": None, "locked": False, "active": None}
    rows: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    violations: list[str] = []
    stock_slip_drag = [0.0]

    def audit(ok: bool, msg: str) -> None:
        if not ok:
            violations.append(msg)

    def merge(book: dict[str, dict[str, Any]], a: dict[str, Any]) -> None:
        old = book.get(a["code"])
        if old is None:
            book[a["code"]] = a
        elif a["side"] == "SELL" and old["side"] == "SELL" and a["p"] == 4 and old["p"] == 0:
            merged = dict(old)
            merged["w"] = a["w"]
            merged["qty"] = a["qty"]
            merged["sell_est"] = max(old.get("sell_est", 0), a.get("sell_est", 0))
            if a["reason"] not in str(old["reason"]):
                merged["reason"] = f"{old['reason']}+{a['reason']}"
            book[a["code"]] = merged
        elif (a["p"], -a.get("sell_est", 0)) < (old["p"], -old.get("sell_est", 0)):
            book[a["code"]] = a

    def on_trade(ctx: Any, ev: Any) -> None:
        a = state["active"]
        t = ev.trade
        d = str(ctx.now.date())
        if not a or t.order_book_id != a["code"]:
            violations.append(f"unattributed trade {d} {t.order_book_id}")
            return
        q, px = int(t.last_quantity), float(t.last_price)
        other = float(t.transaction_cost - t.commission - t.tax)
        grp = asset_group(t.order_book_id)
        slip = px * q * 0.0005 if grp == "stock" else 0.0
        if grp == "stock":
            stock_slip_drag[0] += slip
        fills.append(
            {
                "date": d,
                "signal": a["signal"],
                "code": t.order_book_id,
                "side": t.side.name,
                "price": px,
                "open": a["open"],
                "qty": q,
                "order": int(t.order_id),
                "reason": a["reason"],
                "stage": a["p"],
                "commission": float(t.commission),
                "tax": float(t.tax),
                "other": other,
                "notional": px * q,
                "stock_slip_5bp": slip,
                "group": group_fn(t.order_book_id),
            }
        )
        audit(abs(px - a["open"]) <= 1e-6, f"non-opening fill {d}")
        audit(t.side.name == a["side"], f"wrong side {d}")
        audit(
            q % 100 == 0 or (a["side"] == "SELL" and a["requested"] == a["held"]),
            f"illegal odd lot {d} {t.order_book_id} {q}",
        )
        a["filled"] += q
        audit(a["side"] != "SELL" or a["filled"] <= a["sellable"], f"T+1 violation {d}")
        if grp == "stock":
            if a["side"] == "BUY":
                stock_stops[t.order_book_id] = {
                    "stop_pct": float(a.get("stop_pct", 0.08)),
                    "entry_date": d,
                    "entry_px": px,
                }
            elif a["side"] == "SELL" and ctx.portfolio.positions[t.order_book_id].quantity == 0:
                stock_stops.pop(t.order_book_id, None)

    def on_reject(ctx: Any, ev: Any) -> None:
        rejects.append({"date": str(ctx.now.date()), "code": ev.order_book_id, "reason": str(ev.reason)})

    def init(ctx: Any) -> None:
        env = Environment.get_instance()
        fees = TieredFees(env, white)
        for typ in (INSTRUMENT_TYPE.CS, INSTRUMENT_TYPE.ETF):
            env.set_transaction_cost_decider(typ, fees)
        subscribe_event(EVENT.TRADE, on_trade)
        subscribe_event(EVENT.ORDER_CREATION_REJECT, on_reject)

    def open_auction(ctx: Any, bars: Any) -> None:
        d = str(ctx.now.date())
        i = lookup[d]
        env = Environment.get_instance()
        if i == 0 and seed:
            pending[FOCUS] = {
                "signal": "INITIAL",
                "code": FOCUS,
                "p": 2,
                "reason": "SEED",
                "side": "BUY",
                "w": seed,
                "qty": None,
            }
        for a in sorted(pending.values(), key=lambda x: (x["p"], x["side"] == "BUY", x["code"])):
            sym, buy = a["code"], a["side"] == "BUY"
            record = dict(a, date=d, filled=0, requested=0, status=None)
            instrument = instruments(sym)
            pos = ctx.portfolio.positions[sym]
            held, sellable = int(pos.quantity), int(pos.sellable)
            record.update(held=held, sellable=sellable)
            bar = bars[sym]
            px = float(bar.open)
            record["open"] = px if isfinite(px) else None
            is_stock = asset_group(sym) == "stock"

            why = opening_block(
                px,
                bar.limit_up if buy else bar.limit_down,
                buy,
                not instrument.active_at(ctx.now) or env.data_proxy.is_suspended(sym, ctx.now.date()),
            )
            if not why and buy and is_stock:
                prev_c = float(bar.prev_close)
                if isfinite(prev_c) and prev_c > 0 and px > prev_c * 1.02:
                    why = "GAP_GT_2PCT"

            requested = 0
            if not why:
                nav, cash = float(ctx.portfolio.total_value), float(ctx.portfolio.cash)
                if buy:
                    if is_stock:
                        stop_pct = float(a.get("stop_pct", 0.08))
                        risk_per_share = max(px * stop_pct, px * 0.02)
                        eq_now = sum(
                            p.market_value
                            for s, p in ctx.portfolio.positions.items()
                            if p.quantity > 0 and s not in BOND_SET_RQ
                        )
                        room_amt = max(0.0, float(a["budget"]) * nav - eq_now)
                        cap_val = min(
                            (nav * 0.013) / risk_per_share * px,
                            nav * 0.18,
                            room_amt,
                            cash * 0.996,
                        )
                        requested = get_amount_from_value(cap_val, instrument, px, env, cash)
                        minimum = 8000.0
                    else:
                        amount = min(max(0.0, a["w"] * nav - held * px), cash * 0.996)
                        if a["signal"] != "INITIAL" and sym not in BOND_SET_RQ and a.get("eff_cap") is not None:
                            eq_now = sum(
                                p.market_value
                                for s, p in ctx.portfolio.positions.items()
                                if p.quantity > 0 and s not in BOND_SET_RQ
                            )
                            eq_room = max(0.0, nav * float(a["eff_cap"]) - eq_now)
                            amount = min(amount, eq_room)
                        requested = get_amount_from_value(amount, instrument, px, env, cash)
                        minimum = 1000.0 if sym in white else 5000.0
                    why = (
                        "LOT_OR_CASH"
                        if requested == 0
                        else ("BELOW_MINIMUM" if requested * px < minimum else None)
                    )
                else:
                    if a["qty"] is not None:
                        desired = min(held, a["qty"])
                    elif a["w"] == 0:
                        desired = held
                    else:
                        desired = int(round_order_quantity(instrument, max(0.0, held - a["w"] * nav / px)))
                    requested = min(desired, sellable)
                    if not requested:
                        why = "T1_DEFER" if desired > 0 else "NO_SELL_DELTA"

            if not why:
                record["requested"] = requested
                state["active"] = record
                try:
                    o = order_shares(sym, requested if buy else -requested)
                finally:
                    state["active"] = None
                record["status"] = o.status.name if o is not None else "NO_ORDER"
                if not buy and record["filled"] < desired:
                    rem_sell = desired - record["filled"]
                    retries[sym] = dict(a, qty=rem_sell, w=None, sell_est=rem_sell)
                if not buy and record["filled"] == held:
                    armed.pop(sym, None)
                    stock_stops.pop(sym, None)
            else:
                record["status"] = why
                if not buy and held and why != "NO_SELL_DELTA":
                    retries[sym] = a.copy()
        pending.clear()

    def close(ctx: Any, bars: Any) -> None:
        d = str(ctx.now.date())
        i = lookup[d]
        nav, cash = float(ctx.portfolio.total_value), float(ctx.portfolio.cash)
        pp = ctx.portfolio.positions
        held = {s: pp[s] for s in pp if pp[s].quantity > 0}
        w = {s: float(p.market_value / nav) for s, p in held.items()}
        held_mv = {s: float(p.market_value) for s, p in held.items()}
        pnl: Counter[str] = Counter()
        for s in pp:
            pnl[group_fn(s)] += float(pp[s].daily_pnl)

        regime, style, eq_budget = market_map[d]
        risk_row = ctrl.step(i, nav, concentrated=False, base_eq_budget=eq_budget)
        locked, l1 = bool(risk_row["locked"]), bool(risk_row["l1"])
        if regime == "ICE_10" and locked:
            regime_eff = "DEFENSIVE"
            eq_budget_eff = 0.25
        else:
            regime_eff = regime
            eq_budget_eff = eq_budget

        f = features[d]
        risk_w = sum(wt for s, wt in w.items() if s not in BOND_SET_RQ)
        rows.append(
            {
                "date": d,
                "nav": nav,
                "net_nav_after_5bp_stock_slip": max(1.0, nav - stock_slip_drag[0]),
                "cash": cash,
                "weights": w,
                "risk": risk_w,
                "regime": regime_eff,
                "pnl": dict(pnl),
                **risk_row,
            }
        )
        for a in retries.values():
            merge(pending, dict(a, signal=d, original_signal=a.get("original_signal", a["signal"])))
        retries.clear()

        def add(
            p_prio: int,
            sym: str,
            reason: str,
            side: str,
            weight: float | None = None,
            qty: int | None = None,
            **extra: Any,
        ) -> None:
            sell_est = (
                (
                    qty
                    if qty is not None
                    else int(held[sym].quantity * max(0.0, 1.0 - (weight or 0.0) / max(w.get(sym, 1e-9), 1e-9)))
                )
                if side == "SELL"
                else 0
            )
            merge(
                pending,
                {
                    "signal": d,
                    "code": sym,
                    "p": p_prio,
                    "reason": reason,
                    "side": side,
                    "w": weight,
                    "qty": qty,
                    "sell_est": sell_est,
                    **extra,
                },
            )

        held_risk_etfs = [s for s in held if s not in BOND_SET_RQ and asset_group(s) != "stock"]
        provisional_t = select_core40_account_targets(
            regime=regime_eff,
            style=style,
            budget_total=eq_budget_eff,
            occupied_weight=0.0,
            features=f,
            held_mv=held_mv,
            nav=nav,
            p0_ctrl_cap=risk_row["ctrl_cap"],
        )
        non_target_etfs = [s for s in held_risk_etfs if s not in provisional_t]

        # P0 Drawdown reduction
        p0_sold_by_sym: dict[str, float] = {}
        cc = risk_row["ctrl_cap"]
        if cc is not None and risk_w > float(cc) + 0.02 and risk_w > 1e-6:
            need_cut_w = risk_w - float(cc)
            nt_w = sum(w[s] for s in non_target_etfs)
            if nt_w > 1e-6 and need_cut_w > 1e-6:
                cut_nt = min(nt_w, need_cut_w)
                keep_nt_ratio = max(0.0, 1.0 - cut_nt / nt_w)
                for s in non_target_etfs:
                    new_ws = w[s] * keep_nt_ratio
                    if new_ws < 0.02:
                        new_ws = 0.0
                    if new_ws < w[s] - 1e-9:
                        add(0, s, "CTRL_REDUCE_LEGACY", "SELL", new_ws)
                        p0_sold_by_sym[s] = w[s] - new_ws
                need_cut_w = max(0.0, risk_w - float(cc) - sum(p0_sold_by_sym.values()))
            rem_risk = [s for s in held if s not in BOND_SET_RQ and s not in non_target_etfs]
            rem_w = sum(w[s] for s in rem_risk)
            if need_cut_w > 1e-6 and rem_w > 1e-6:
                keep_ratio = max(0.0, 1.0 - need_cut_w / rem_w)
                for s in rem_risk:
                    new_ws = w[s] * keep_ratio
                    add(0, s, "CTRL_REDUCE", "SELL", new_ws)
                    p0_sold_by_sym[s] = w[s] - new_ws
        p0_sold_w = sum(p0_sold_by_sym.values())

        # P1 Exits (strictly STOCK_BP1 only, ETF P1 dormant per v3.3.1)
        active_stocks: set[str] = set()
        from research.batches.v3_account_replay_v2.policy import exit_reason

        for s, p in held.items():
            if s in BOND_SET_RQ:
                continue
            if asset_group(s) == "stock":
                active_stocks.add(s)
                bar = bars[s]
                c_close = float(bar.close)
                if not isfinite(c_close) or c_close <= 0:
                    continue
                h20 = history_bars(s, 20, "1d", "close")
                h10 = history_bars(s, 10, "1d", "close")
                ma20 = float(np.mean(h20)) if h20 is not None and len(h20) == 20 else float("nan")
                ma10 = float(np.mean(h10)) if h10 is not None and len(h10) == 10 else float("nan")
                meta = stock_stops.get(s, {"stop_pct": 0.08, "entry_px": float(p.avg_price)})
                cost = float(p.avg_price) if isfinite(p.avg_price) and p.avg_price > 0 else meta["entry_px"]
                armed[s], why = exit_reason(
                    c_close,
                    cost,
                    ma20,
                    ma10,
                    armed.get(s, False),
                    l1,
                    stock=True,
                    structural_stop=cost * (1.0 - float(meta["stop_pct"])),
                )
                if why:
                    add(1, s, why, "SELL", 0.0)

        # P3 BP1 stocks (>=100k, non-concentrated, OFFENSIVE/STRUCTURAL)
        nt_total_w = sum(w[s] for s in non_target_etfs)
        bp1_permitted = nav >= 100000.0 and nt_total_w <= 0.30
        stock_buy_budget = 0.0
        kept_stocks = {s for s in active_stocks if pending.get(s, {}).get("side") != "SELL"}
        current_stock_w = sum(w[s] for s in kept_stocks)
        slots_left = max(0, 2 - len(active_stocks))
        eff_cap = float(risk_row["buy_cap"])
        if bp1_permitted and regime_eff in ("OFFENSIVE", "STRUCTURAL") and not locked and not l1 and slots_left > 0:
            eff_eq_cap = min(eff_cap, eq_budget_eff)
            # Reserve 25% Core before BP1 satellite headroom
            total_avail = max(0.0, eff_eq_cap - 0.25 - nt_total_w - current_stock_w)
            for cand in stock_candidates.get(d, []):
                if slots_left <= 0 or total_avail < 0.08:
                    break
                ob = cand.order_book_id
                if ob in held or ob in pending:
                    continue
                stop_pct = min(0.08, max(0.025, 1.0 - cand.hard_stop_raw / cand.ref_close_raw))
                est_w = min(0.013 / max(stop_pct, 0.02), 0.18, total_avail)
                if est_w * nav < 8000.0:
                    continue
                add(3, ob, "BP1_ENTRY", "BUY", est_w, None, stop_pct=stop_pct, budget=eq_budget_eff)
                stock_buy_budget += est_w
                total_avail -= est_w
                slots_left -= 1

        # P4 Declarative alignment with REGIME_ONLY low-turnover gate
        bond_pick = next((b for b in bond_priority if b in f), "511010.XSHG")
        planned_equity_buy_amt = sum(
            max(0.0, (a.get("w") or 0.0) * nav - (held[a["code"]].market_value if a["code"] in held else 0.0))
            for a in pending.values()
            if a["side"] == "BUY" and a["code"] not in BOND_SET_RQ
        )

        if not locked:
            reg_or_budget_changed = (regime_eff != state["regime"]) or (
                state["budget"] is None or abs(eq_budget_eff - float(state["budget"])) > 1e-6
            )
            unlocked_today = bool(state["locked"] and not locked)
            p0_triggered = bool(risk_row["trigger"] or p0_sold_w > 0)

            post_p0_w = {s: max(0.0, w[s] - p0_sold_by_sym.get(s, 0.0)) for s in held_risk_etfs}
            nt_p0_sold = sum(p0_sold_by_sym.get(s, 0.0) for s in non_target_etfs)
            nt_glide_sell = (
                nt_total_w
                if nt_total_w <= align_glide_cap + 0.02
                else max(align_glide_cap, nt_total_w - align_glide_cap)
            )
            nt_carryover = max(0.0, nt_total_w - max(nt_p0_sold, nt_glide_sell))
            occupied_for_targets = current_stock_w + stock_buy_budget + nt_carryover

            raw_t = select_core40_account_targets(
                regime=regime_eff,
                style=style,
                budget_total=min(eff_cap, eq_budget_eff),
                occupied_weight=occupied_for_targets,
                features=f,
                held_mv=held_mv,
                nav=nav,
                p0_ctrl_cap=risk_row["ctrl_cap"],
            )
            tot_raw = sum(raw_t.values())
            max_new_eq = max(0.0, eff_cap - occupied_for_targets)
            scale = min(1.0, max_new_eq / tot_raw) if tot_raw > 1e-9 else 1.0
            scaled_t = {k: v * scale for k, v in raw_t.items() if v * scale > 0.01}

            pre_p0_excess = {s: max(0.0, w[s] - scaled_t.get(s, 0.0)) for s in held_risk_etfs}
            total_excess = sum(pre_p0_excess.values())
            desired_glide_sell = (
                total_excess
                if total_excess <= align_glide_cap + 0.02
                else max(align_glide_cap, total_excess - align_glide_cap)
            )
            rem_p3_sell = max(0.0, desired_glide_sell - p0_sold_w)

            post_p0_excess = {s: max(0.0, post_p0_w[s] - scaled_t.get(s, 0.0)) for s in held_risk_etfs}
            p3_sell_target_w: dict[str, float] = {}
            if rem_p3_sell > 1e-6:
                nt_over = [s for s in non_target_etfs if post_p0_excess[s] > 1e-6]
                ov_target = [s for s in held_risk_etfs if s not in non_target_etfs and post_p0_excess[s] > 1e-6]
                for group_syms in (nt_over, ov_target):
                    grp_ex = sum(post_p0_excess[s] for s in group_syms)
                    if grp_ex <= 1e-9 or rem_p3_sell <= 1e-9:
                        continue
                    sell_from_grp = min(grp_ex, rem_p3_sell)
                    ratio = sell_from_grp / grp_ex
                    for s in group_syms:
                        cut = post_p0_excess[s] * ratio
                        new_ws = max(0.0, post_p0_w[s] - cut)
                        if s in non_target_etfs and new_ws < 0.02:
                            new_ws = 0.0
                        p3_sell_target_w[s] = new_ws
                    rem_p3_sell = max(0.0, rem_p3_sell - sell_from_grp)

            post_sell_nt_w = sum(p3_sell_target_w.get(s, post_p0_w[s]) for s in non_target_etfs)
            occupied_final = current_stock_w + stock_buy_budget + post_sell_nt_w
            target_eq_total = max(occupied_final, min(eff_cap, occupied_final + sum(scaled_t.values())))
            target_bond_w = max(0.0, 1.0 - target_eq_total - 0.01)
            cur_bond_w = sum(w.get(b, 0.0) for b in BOND_SET_RQ)
            bond_drift = abs(target_bond_w - cur_bond_w)

            max_target_drift = max(
                (abs(scaled_t[s] - post_p0_w.get(s, 0.0)) for s in scaled_t),
                default=0.0,
            )
            has_non_target_risk = any(w[s] > 1e-6 for s in non_target_etfs)

            # REGIME_ONLY: ignore style flips unless regime/budget changed, unlocked, P0, or wide drift
            align_due = (
                has_non_target_risk
                or reg_or_budget_changed
                or unlocked_today
                or p0_triggered
                or max_target_drift >= equity_drift_band
                or bond_drift >= bond_drift_band
            )

            if align_due:
                for s, new_ws in sorted(p3_sell_target_w.items()):
                    if new_ws < post_p0_w[s] - 1e-9:
                        # Enforce >= 5000 yuan for Gold active rebalance unless full exit
                        if s == GOLD and new_ws > 1e-6 and (post_p0_w[s] - new_ws) * nav < 5000.0:
                            continue
                        reason = (
                            "REGIME_ALIGN_EXIT"
                            if new_ws <= 1e-9
                            else ("REGIME_ALIGN_GLIDE" if s in non_target_etfs else "ALIGN")
                        )
                        add(4, s, reason, "SELL", new_ws, eff_cap=eff_cap)

                buy_headroom = max(0.0, eff_cap - occupied_final - sum(post_p0_w.get(s, 0.0) for s in scaled_t))
                for s in sorted(scaled_t):
                    if s in p3_sell_target_w or s in p0_sold_by_sym or s in pending:
                        continue
                    wt = scaled_t[s]
                    cur_s = w.get(s, 0.0)
                    diff = wt - cur_s
                    if diff <= 1e-6:
                        continue
                    if cur_s > 0 and not (reg_or_budget_changed or unlocked_today or p0_triggered) and diff < equity_drift_band:
                        continue
                    if diff * nav < (1000.0 if s in white else 5000.0):
                        continue
                    if buy_headroom <= 1e-6:
                        continue
                    eff_wt = min(wt, cur_s + buy_headroom)
                    eff_diff = eff_wt - cur_s
                    if eff_diff * nav < (1000.0 if s in white else 5000.0):
                        continue
                    add(4, s, "ALIGN", "BUY", eff_wt, regime=regime_eff, eff_cap=eff_cap)
                    planned_equity_buy_amt += eff_diff * nav
                    buy_headroom = max(0.0, buy_headroom - eff_diff)

                if bond_drift >= bond_drift_band:
                    diff_b = target_bond_w - cur_bond_w
                    if diff_b * nav >= 5000.0 and bond_pick in f:
                        add(5, bond_pick, "BOND_RESERVOIR", "BUY", target_bond_w, regime=regime_eff)
                    elif diff_b < 0:
                        for b in sorted(b for b in held if b in BOND_SET_RQ):
                            add(3, b, "BOND_REDUCE", "SELL", max(0.0, target_bond_w))

        est_sell_cash = sum(
            a["sell_est"] * (held[a["code"]].market_value / max(held[a["code"]].quantity, 1))
            for a in pending.values()
            if a["side"] == "SELL" and a["code"] in held
        )
        shortfall = planned_equity_buy_amt * 1.01 - (cash + est_sell_cash)
        if shortfall >= 5000.0:
            for b in sorted(b for b in held if b in BOND_SET_RQ):
                if shortfall < 1000.0:
                    break
                if b in pending and pending[b]["side"] == "SELL":
                    continue
                b_mv = float(held[b].market_value)
                px_b = b_mv / max(held[b].quantity, 1)
                raw_lots = min(held[b].quantity // 100, np.ceil(shortfall / px_b / 100.0))
                sell_lots = int(raw_lots) * 100
                if sell_lots >= 100 and sell_lots * px_b >= 5000.0:
                    add(3, b, "BOND_FUNDING", "SELL", qty=sell_lots)
                    shortfall -= sell_lots * px_b

        state.update(regime=regime_eff, budget=eq_budget_eff, locked=locked)

    a = run_func(init=init, open_auction=open_auction, handle_bar=close, config=cfg)["sys_analyser"]
    eq_raw = a["portfolio"]["total_value"]
    eq_net = pd.Series(
        [r["net_nav_after_5bp_stock_slip"] for r in rows],
        index=pd.to_datetime([r["date"] for r in rows]),
        dtype=float,
    )
    audit([str(d)[:10] for d in eq_raw.index] == days == [r["date"] for r in rows], "calendar")
    audit(len(a.get("trades", [])) == len(fills), "analyser vs trade count")
    pnl_attr: defaultdict[str, float] = defaultdict(float)
    for r in rows:
        for k, v in r["pnl"].items():
            pnl_attr[k] += float(v)
    bp1_sleeve = compute_roundtrip_stats(fills, group_fn)["by_sleeve"].get("stock_bp1", {})
    return {
        "metrics": compute_calendar_stats(eq_net),
        "raw_metrics": compute_calendar_stats(eq_raw),
        "roundtrips": compute_roundtrip_stats(fills, group_fn),
        "true_max_dd": float(max(r["true_dd"] for r in rows)),
        "breach_days": int(sum(1 for r in rows if r["breach"] > 0)),
        "locks": int(ctrl.locks),
        "relock_loops": int(ctrl.relock_loops),
        "commission_yuan": round(sum(f["commission"] for f in fills), 2),
        "tax_yuan": round(sum(f["tax"] for f in fills), 2),
        "explicit_stock_slip_yuan": round(stock_slip_drag[0], 2),
        "total_friction_yuan": round(
            sum(f["commission"] + f["tax"] + f["other"] + f["stock_slip_5bp"] for f in fills), 2
        ),
        "fill_count": len(fills),
        "pnl_attribution": {k: round(v, 2) for k, v in sorted(pnl_attr.items())},
        "bp1_summary": {
            "closed_trades": int(bp1_sleeve.get("closed_trades", 0)),
            "pnl_yuan": float(pnl_attr.get("stock_bp1", 0.0)),
            "realized_pnl_yuan": float(bp1_sleeve.get("total_realized_pnl_yuan", 0.0)),
        },
        "reject_count": len(rejects),
        "violation_count": len(violations),
        "violations": violations,
    }


def _compute_loyo_metrics(eq: pd.Series) -> dict[str, Any]:
    """Leave-One-Year-Out synthetic series metrics for each year 2018..2026, highlighting ex-2025."""
    ret = eq.pct_change(fill_method=None).dropna()
    out: dict[str, Any] = {}
    for yr in range(2018, 2027):
        sub_ret = ret[ret.index.year != yr]
        syn_eq = pd.Series(np.concatenate([[1.0], (1.0 + sub_ret).cumprod().to_numpy()]), index=pd.RangeIndex(len(sub_ret) + 1))
        years = len(sub_ret) / 252.0
        cagr = float(syn_eq.iloc[-1] ** (1.0 / years) - 1.0)
        dd = float((syn_eq / syn_eq.cummax() - 1.0).min())
        calmar = float(cagr / abs(dd)) if dd < -1e-12 else 0.0
        sharpe = float(sub_ret.mean() / sub_ret.std() * np.sqrt(252.0)) if sub_ret.std() > 1e-12 else 0.0
        out[f"ex_{yr}"] = {
            "cagr": round(cagr, 6),
            "max_drawdown": round(dd, 6),
            "calmar": round(calmar, 4),
            "sharpe": round(sharpe, 4),
        }
    return out


def _compute_walk_forward(eq: pd.Series) -> list[dict[str, Any]]:
    """6 anchored Walk-Forward windows: IS 2018..Y-1 -> OOS Y (for Y in 2021..2026)."""
    rows: list[dict[str, Any]] = []
    for yr in range(2021, 2027):
        is_eq = eq[eq.index.year < yr]
        oos_eq = eq[eq.index.year == yr]
        is_st = compute_calendar_stats(is_eq)
        oos_st = compute_calendar_stats(oos_eq)
        rows.append(
            {
                "oos_year": yr,
                "is_span": f"2018..{yr - 1}",
                "is_cagr": round(is_st["cagr"], 6),
                "is_calmar": round(is_st["calmar"], 4),
                "oos_return": round(oos_st["total_return"], 6),
                "oos_max_dd": round(oos_st["max_drawdown"], 6),
                "oos_calmar": round(oos_st["calmar"], 4),
                "oos_sharpe": round(oos_st["sharpe"], 4),
            }
        )
    return rows


def _compute_deflated_sharpe_and_pbo(
    eq_dict: dict[str, pd.Series],
    candidate_key: str,
    n_trials: int,
) -> dict[str, Any]:
    """Bailey & Lopez de Prado DSR and CSCV PBO (16 subperiod blocks) across tested variants."""
    # DSR on candidate daily returns
    eq = eq_dict[candidate_key]
    ret = eq.pct_change(fill_method=None).dropna().to_numpy(dtype=np.float64)
    t_obs = len(ret)
    sr_daily = float(np.mean(ret) / np.std(ret, ddof=1))
    sr_ann = sr_daily * np.sqrt(252.0)
    skew = float(pd.Series(ret).skew())
    kurt = float(pd.Series(ret).kurtosis() + 3.0)  # regular kurtosis

    # Cross-sectional variance of annual Sharpe across all tested variants
    all_srs = []
    for s in eq_dict.values():
        r = s.pct_change(fill_method=None).dropna().to_numpy(dtype=np.float64)
        all_srs.append(float(np.mean(r) / np.std(r, ddof=1) * np.sqrt(252.0)))
    sr_var = float(np.var(all_srs, ddof=1)) if len(all_srs) > 1 else 0.01
    sr_std = max(np.sqrt(sr_var), 0.05)

    euler_gamma = 0.5772156649
    if n_trials > 1:
        e_max_z = (1.0 - euler_gamma) * norm.ppf(1.0 - 1.0 / n_trials) + euler_gamma * norm.ppf(
            1.0 - 1.0 / (n_trials * math.e)
        )
    else:
        e_max_z = 0.0
    sr0_ann = sr_std * e_max_z
    sr0_daily = sr0_ann / np.sqrt(252.0)

    denom = math.sqrt(max(1e-9, 1.0 - skew * sr_daily + ((kurt - 1.0) / 4.0) * (sr_daily**2)))
    z_dsr = ((sr_daily - sr0_daily) * math.sqrt(t_obs - 1.0)) / denom
    dsr_prob = float(norm.cdf(z_dsr))

    # PBO via CSCV (S = 16 blocks -> C(16, 8) = 12,870 combinations)
    common_idx = eq.index
    mat_rets = np.column_stack(
        [eq_dict[k].reindex(common_idx).pct_change(fill_method=None).fillna(0.0).to_numpy() for k in eq_dict]
    )
    n_blocks = 16
    block_size = len(mat_rets) // n_blocks
    usable = block_size * n_blocks
    mat_rets = mat_rets[:usable]
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
        # Relative rank of IS-best in OOS (1..M)
        rank_oos = int(np.sum(oos_sr <= oos_sr[best_is]))
        w_bar = rank_oos / (len(oos_sr) + 1.0)
        w_bar = min(max(w_bar, 1e-4), 1.0 - 1e-4)
        logits.append(math.log(w_bar / (1.0 - w_bar)))

    pbo = float(np.mean(np.array(logits) < 0.0))
    return {
        "n_trials_total": int(n_trials),
        "n_cscv_strategies": int(len(eq_dict)),
        "candidate": candidate_key,
        "candidate_sharpe_ann": round(sr_ann, 4),
        "expected_max_null_sharpe_ann": round(float(sr0_ann), 4),
        "dsr_z": round(float(z_dsr), 4),
        "dsr_prob": round(dsr_prob, 4),
        "pbo_cscv_16": round(pbo, 4),
    }


def main() -> int:
    _patch_bundle_paths()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "started": utc(),
        "bundle_path": str(BUNDLE_20261126),
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
    spread_df = pd.read_csv(PIT_CSV, parse_dates=["dt"]).set_index("dt")
    sector_pool_ts = load_sector_pioneer_pool()
    sector_pool_rq = tuple(ts_to_rq(c) for c in sector_pool_ts)
    group_fn = make_group_fn(sector_pool_ts)

    # 1) Build target weights & VBT equity for A0..A3 (2018-01-02..2026-11-26)
    overlaid_w: dict[str, pd.DataFrame] = {}
    vbt_eq: dict[str, pd.Series] = {}

    # A0_V331
    a0_base, a0_eff_reg, a0_rec = build_v3_base_chassis_weights(
        p,
        reg,
        sector_pool_ts=sector_pool_ts,
        use_recovery=True,
        use_lowvol_core=True,
        use_low_ticket_bond=True,
        use_sector_pioneer=False,
        end=END_DATE,
    )
    a0_ow, a0_ctrl = apply_drawdown_overlay_202611(
        p, a0_base, a0_eff_reg, ctrl_mode="c3_gradual", use_low_ticket_bond=True, end=END_DATE
    )
    overlaid_w["A0_V331"] = a0_ow
    arm_meta: dict[str, Any] = {"A0_V331": {"rec": a0_rec, "ctrl": a0_ctrl}}

    for arm_code, label in (
        ("A1", "A1_CORE40_G10_REGIME_ONLY"),
        ("A2", "A2_A1_PLUS_ICE10_FLOOR35"),
        ("A3", "A3_A2_PLUS_DIV_SPREAD_GUARD"),
    ):
        ow, meta = build_core40_chassis_weights(p, reg, spread_df, arm=arm_code, end=END_DATE)
        overlaid_w[label] = ow
        arm_meta[label] = {"ctrl": meta}

    gold_crash_start = pd.Timestamp("2026-01-29")
    for label, ow in overlaid_w.items():
        prices, mask, targets_df = (f.loc[:END_DATE] for f in (p.etf_adj_close, p.etf_tradability_mask, ow))
        validate_execution_targets(targets_df, prices, mask, p.etf_lifetimes)
        rates = np.array([SUPER if c in prov.super_etf_codes else NORMAL for c in ow.columns])[None, :]
        eq = run_target_weights(
            prices,
            targets_df,
            fees=rates,
            slippage=0.0002,
            initial_cash=100000.0,
            metric_start=START,
            tradability_mask=mask,
            lifetimes=p.etf_lifetimes,
        ).equity.loc[START:END_DATE]
        vbt_eq[label] = eq
        report["vbt"][label] = {
            **arm_meta[label],
            "full_2018_20261126": compute_calendar_stats(eq),
            "is_2018_2023": compute_calendar_stats(eq.loc[: data.IS_END]),
            "oos_2024_20261126": compute_calendar_stats(eq.loc[data.IS_END :]),
            "stress_2026h2": compute_calendar_stats(eq.loc[STRESS_START:]),
            "stress_gold_peak_to_trough": compute_calendar_stats(eq.loc[gold_crash_start:]),
        }

    # 2) Native RQAlpha 6.3.0 Full-Window Chassis (2018-01-02..2026-11-26) @ 69k & 100k
    rqa_chassis_eq: dict[str, pd.Series] = {}
    for cash in CASH:
        for label, ow in overlaid_w.items():
            key = f"{label}_{cash}"
            sys.stdout.write(f"{utc()} chassis {key}\n")
            sys.stdout.flush()
            eq, run = replay(ow, cash, prov.super_etf_codes, True, start=START, end=END_DATE)
            rqa_chassis_eq[key] = eq
            fees = sum(float(f["commission"]) for f in run["fills"])
            report["chassis_rqa"][key] = {
                "full": compute_calendar_stats(eq),
                "is": compute_calendar_stats(eq.loc[: data.IS_END]),
                "oos": compute_calendar_stats(eq.loc[data.IS_END :]),
                "stress_2026h2": compute_calendar_stats(eq.loc[STRESS_START:]),
                "stress_gold_peak_to_trough": compute_calendar_stats(eq.loc[gold_crash_start:]),
                "roundtrips": compute_roundtrip_stats(run["fills"], group_fn),
                "trade_count": len(run["fills"]),
                "commission_yuan": round(fees, 2),
                "dates_pass": run["dates_pass"],
                "fill_capture_pass": run["fill_capture_pass"],
                "fees_pass": run["commission_audit"]["fees_pass"],
                "illegal_non_lot_fills": len(run["commission_audit"]["illegal_non_lot_fills"]),
            }

    # 3) Native RQAlpha 6.3.0 Unified Account Replays (OOS_CASH, CORE25, LEGACY70 @ 69k & 100k) through 2026-11-26
    all_codes_rq = sorted(
        {
            FOCUS,
            GOLD,
            *(ts_to_rq(c) for c in VALUE_CHAIN_TS),
            *(ts_to_rq(c) for c in GROWTH_CHAIN_TS),
            *LOW_VOL_CHAIN_RQ,
            *LOW_TICKET_BONDS_RQ,
            *sector_pool_rq,
        }
    )
    feat_dfs = {}
    for rq in all_codes_rq:
        ts = rq_to_ts(rq)
        if ts in p.etf_adj_close.columns and ts in p.etf_raw_close.columns:
            df_i = indicators(p.etf_adj_close[ts], p.etf_raw_close[ts])
            df_i["ret60"] = df_i["c"] / df_i["c"].shift(60) - 1.0
            df_i = df_i.where(p.etf_tradability_mask[ts], np.nan)
            feat_dfs[rq] = df_i
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
    stock_cands, _ = build_causal_bp1_candidates_202611(oos_start=OOS_CASH_START, bundle_end=END_DATE)
    cal_full = p.calendar[p.calendar <= END_DATE]
    days_cash = [str(d.date()) for d in cal_full[cal_full >= OOS_CASH_START]]
    days_conc = [str(d.date()) for d in cal_full[cal_full >= OOS_CONC_START]]

    mkt_a0 = {str(dt.date()): (str(a0_eff_reg.at[dt]), str(reg.at[dt, "style"])) for dt in p.calendar}
    mkt_maps: dict[str, dict[str, tuple[str, str, float]]] = {}
    for arm_code, label in (
        ("A1", "A1_CORE40_G10_REGIME_ONLY"),
        ("A2", "A2_A1_PLUS_ICE10_FLOOR35"),
        ("A3", "A3_A2_PLUS_DIV_SPREAD_GUARD"),
    ):
        er, eb, _ = compute_arm_effective_regimes(p, reg, spread_df, arm=arm_code)
        mkt_maps[label] = {
            str(dt.date()): (str(er.at[dt]), str(reg.at[dt, "style"]), float(eb.at[dt])) for dt in p.calendar
        }

    for scenario, s_days, seed in (("OOS_CASH", days_cash, 0.0), ("CORE25", days_conc, 0.25), ("LEGACY70", days_conc, 0.70)):
        for cash in CASH:
            cell_a0 = f"{scenario}_{cash}_A0_V331"
            sys.stdout.write(f"{utc()} acct {cell_a0}\n")
            sys.stdout.flush()
            report["account_replay"][cell_a0] = run_with_upward_sticky(
                days=s_days,
                market=mkt_a0,
                features=features,
                stock_candidates=stock_cands,
                white=white_rq,
                sector_pool_rq=sector_pool_rq,
                capital=float(cash),
                seed=seed,
                use_sector_pioneer=False,
                use_deconc_plan=False,
                align_glide_carryover_w=0.35,
                p1_etf_trailing_sleeves=("SECTOR_PIONEER",),
                sticky_mode="upward",
                use_stateless_align_due=True,
                equity_drift_band=0.05,
                use_v331_budget_merge=True,
                group_fn=group_fn,
            )
            for label, m_map in mkt_maps.items():
                cell = f"{scenario}_{cash}_{label}"
                sys.stdout.write(f"{utc()} acct {cell}\n")
                sys.stdout.flush()
                report["account_replay"][cell] = replay_core40_account(
                    days=s_days,
                    market_map=m_map,
                    features=features,
                    stock_candidates=stock_cands,
                    white=white_rq,
                    capital=float(cash),
                    seed=seed,
                    group_fn=group_fn,
                )

    # 4) LOYO & Walk-Forward on VBT + RQA 69k/100k
    for label, eq in vbt_eq.items():
        report["loyo"][f"VBT_{label}"] = _compute_loyo_metrics(eq)
        report["walk_forward"][f"VBT_{label}"] = _compute_walk_forward(eq)
    for key, eq in rqa_chassis_eq.items():
        report["loyo"][f"RQA_{key}"] = _compute_loyo_metrics(eq)
        report["walk_forward"][f"RQA_{key}"] = _compute_walk_forward(eq)

    # 5) ±5% Parameter Plateau around A3 (in VBT, plus count every variant in N)
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
        ("high_pct_76_71", {"high_enter": 0.76, "high_exit": 0.71}),
        ("high_pct_84_79", {"high_enter": 0.84, "high_exit": 0.79}),
        ("low_pct_1425_19", {"low_enter": 0.1425, "low_exit": 0.19}),
        ("low_pct_1575_21", {"low_enter": 0.1575, "low_exit": 0.21}),
    ]
    plateau_eqs: dict[str, pd.Series] = dict(vbt_eq)
    a0_cal = report["vbt"]["A0_V331"]["full_2018_20261126"]["calmar"]
    a3_cal = report["vbt"]["A3_A2_PLUS_DIV_SPREAD_GUARD"]["full_2018_20261126"]["calmar"]
    peak_gain = max(1e-6, a3_cal - a0_cal)
    plateau_rows: list[dict[str, Any]] = []
    for p_name, p_kw in plateau_specs:
        ow_p, _ = build_core40_chassis_weights(p, reg, spread_df, arm="A3", end=END_DATE, **p_kw)
        prices, mask, targets_df = (f.loc[:END_DATE] for f in (p.etf_adj_close, p.etf_tradability_mask, ow_p))
        validate_execution_targets(targets_df, prices, mask, p.etf_lifetimes)
        rates = np.array([SUPER if c in prov.super_etf_codes else NORMAL for c in ow_p.columns])[None, :]
        eq_p = run_target_weights(
            prices, targets_df, fees=rates, slippage=0.0002, initial_cash=100000.0,
            metric_start=START, tradability_mask=mask, lifetimes=p.etf_lifetimes,
        ).equity.loc[START:END_DATE]
        plateau_eqs[p_name] = eq_p
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
        "a3_calmar": a3_cal,
        "min_gain_retention": round(min_retention, 4),
        "median_gain_retention": round(float(np.median([r["gain_retention"] for r in plateau_rows])), 4),
        "variants": plateau_rows,
    }

    # 6) DSR & PBO (honest N_total = 4 primary arms + 18 plateau variants = 22)
    report["multiple_testing"] = {
        "A1": _compute_deflated_sharpe_and_pbo(plateau_eqs, "A1_CORE40_G10_REGIME_ONLY", len(plateau_eqs)),
        "A2": _compute_deflated_sharpe_and_pbo(plateau_eqs, "A2_A1_PLUS_ICE10_FLOOR35", len(plateau_eqs)),
        "A3": _compute_deflated_sharpe_and_pbo(plateau_eqs, "A3_A2_PLUS_DIV_SPREAD_GUARD", len(plateau_eqs)),
    }

    # 7) Evaluate 7 Hard Gates for A1, A2, A3 vs A0_V331
    integrity_ok = (
        all(r["dates_pass"] and r["fill_capture_pass"] and r["fees_pass"] and r["illegal_non_lot_fills"] == 0 for r in report["chassis_rqa"].values())
        and all(c["violation_count"] == 0 for c in report["account_replay"].values())
    )
    report["integrity_ok"] = integrity_ok

    gate_eval: dict[str, Any] = {}
    for arm_label in ("A1_CORE40_G10_REGIME_ONLY", "A2_A1_PLUS_ICE10_FLOOR35", "A3_A2_PLUS_DIV_SPREAD_GUARD"):
        v_a = report["vbt"][arm_label]
        v_0 = report["vbt"]["A0_V331"]
        r69_a = report["chassis_rqa"][f"{arm_label}_69000"]
        r69_0 = report["chassis_rqa"]["A0_V331_69000"]
        r100_a = report["chassis_rqa"][f"{arm_label}_100000"]
        r100_0 = report["chassis_rqa"]["A0_V331_100000"]

        # Gate 1: IS & OOS CAGR + Calmar dual win vs A0, and Full Calmar >= +35% vs A0
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

        # Gate 2: True Peak MaxDD >= -12.0% across full-window & all 6 accounts (69k >= -10.0%, 0 breach -15%)
        accts_a = {sc: report["account_replay"][f"{sc}_{arm_label}"] for sc in ("OOS_CASH_69000", "OOS_CASH_100000", "CORE25_69000", "CORE25_100000", "LEGACY70_69000", "LEGACY70_100000")}
        full_dds = [v_a["full_2018_20261126"]["max_drawdown"], r69_a["full"]["max_drawdown"], r100_a["full"]["max_drawdown"]]
        acct_true_dds = [-accts_a[k]["true_max_dd"] for k in accts_a]
        acct_69_dds = [-accts_a[k]["true_max_dd"] for k in ("OOS_CASH_69000", "CORE25_69000", "LEGACY70_69000")]
        breaches = sum(accts_a[k]["breach_days"] for k in accts_a)
        g2_pass = bool(
            all(d >= -0.12 for d in full_dds)
            and all(d >= -0.12 for d in acct_true_dds)
            and all(d >= -0.10 for d in acct_69_dds)
            and breaches == 0
        )

        # Gate 3: 2026H2 crash stress test (ret >= -1.5%, max_dd >= -6.0%)
        st_vbt = v_a["stress_2026h2"]
        st_r69 = r69_a["stress_2026h2"]
        g3_pass = bool(
            st_vbt["total_return"] >= -0.015
            and st_vbt["max_drawdown"] >= -0.06
            and st_r69["total_return"] >= -0.015
            and st_r69["max_drawdown"] >= -0.06
        )

        # Gate 4: LOYO ex-2025 gold bull year synthetic Calmar vs A0_V331
        ex25_vbt = report["loyo"][f"VBT_{arm_label}"]["ex_2025"]["calmar"]
        ex25_vbt_0 = report["loyo"]["VBT_A0_V331"]["ex_2025"]["calmar"]
        ex25_r69 = report["loyo"][f"RQA_{arm_label}_69000"]["ex_2025"]["calmar"]
        ex25_r69_0 = report["loyo"]["RQA_A0_V331_69000"]["ex_2025"]["calmar"]
        g4_pass = bool(ex25_vbt > ex25_vbt_0 and ex25_r69 > ex25_r69_0)

        # Gate 5: 6 anchored Walk-Forward windows + +/-5% plateau >= 85% (for A3; A1/A2 check WF)
        wf_a = report["walk_forward"][f"RQA_{arm_label}_69000"]
        wf_0 = report["walk_forward"]["RQA_A0_V331_69000"]
        wf_wins = sum(1 for a_w, z_w in zip(wf_a, wf_0) if a_w["oos_calmar"] >= z_w["oos_calmar"])
        g5_plateau = min_retention >= 0.85 if arm_label == "A3_A2_PLUS_DIV_SPREAD_GUARD" else True
        g5_pass = bool(wf_wins >= 4 and g5_plateau)

        # Gate 6: Multiple testing DSR & PBO
        mt_key = arm_label[:2]
        mt = report["multiple_testing"][mt_key]
        g6_pass = bool(mt["dsr_prob"] >= 0.50 and mt["pbo_cscv_16"] <= 0.50)

        gate_eval[arm_label] = {
            "G1_IS_OOS_and_Calmar_35pct": {
                "pass": g1_pass,
                "vbt_calmar_lift_pct": round((v_a["full_2018_20261126"]["calmar"] / v_0["full_2018_20261126"]["calmar"] - 1.0) * 100.0, 2),
                "r69_calmar_lift_pct": round((r69_a["full"]["calmar"] / r69_0["full"]["calmar"] - 1.0) * 100.0, 2),
            },
            "G2_True_Peak_DD": {
                "pass": g2_pass,
                "worst_full_dd": round(min(full_dds), 4),
                "worst_acct_true_dd": round(min(acct_true_dds), 4),
                "worst_69k_acct_true_dd": round(min(acct_69_dds), 4),
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
                "min_plateau_retention": report["plateau"]["min_gain_retention"] if arm_label == "A3_A2_PLUS_DIV_SPREAD_GUARD" else None,
            },
            "G6_Multiple_Testing": {
                "pass": g6_pass,
                **mt,
            },
        }

    # Gate 7: Occam marginal hurdle A1->A2 and A2->A3 on 69k native RQA
    def _occam_step(prev_arm: str, next_arm: str) -> dict[str, Any]:
        p69 = report["chassis_rqa"][f"{prev_arm}_69000"]
        n69 = report["chassis_rqa"][f"{next_arm}_69000"]
        d_cal = round(n69["full"]["calmar"] - p69["full"]["calmar"], 4)
        d_dd_pp = round((abs(p69["full"]["max_drawdown"]) - abs(n69["full"]["max_drawdown"])) * 100.0, 3)  # positive = DD reduced
        d_cagr_pp = round((n69["full"]["cagr"] - p69["full"]["cagr"]) * 100.0, 3)
        d_is_cagr_pp = round((n69["is"]["cagr"] - p69["is"]["cagr"]) * 100.0, 3)
        d_oos_cagr_pp = round((n69["oos"]["cagr"] - p69["oos"]["cagr"]) * 100.0, 3)

        acct_69_p = [report["account_replay"][f"{s}_69000_{prev_arm}"]["metrics"]["calmar"] for s in ("OOS_CASH", "CORE25", "LEGACY70")]
        acct_69_n = [report["account_replay"][f"{s}_69000_{next_arm}"]["metrics"]["calmar"] for s in ("OOS_CASH", "CORE25", "LEGACY70")]
        d_acct_cal = round(float(np.mean(acct_69_n) - np.mean(acct_69_p)), 4)

        hurdle_ok = (d_cal >= 0.03) or (d_dd_pp >= 0.8 and d_cagr_pp >= -0.05)
        no_deg = (d_is_cagr_pp >= -0.15) and (d_oos_cagr_pp >= -0.15)
        return {
            "pass": bool(hurdle_ok and no_deg),
            "r69_full_calmar_delta": d_cal,
            "r69_full_dd_reduction_pp": d_dd_pp,
            "r69_full_cagr_delta_pp": d_cagr_pp,
            "r69_is_cagr_delta_pp": d_is_cagr_pp,
            "r69_oos_cagr_delta_pp": d_oos_cagr_pp,
            "r69_acct_mean_calmar_delta": d_acct_cal,
        }

    occam_a1_a2 = _occam_step("A1_CORE40_G10_REGIME_ONLY", "A2_A1_PLUS_ICE10_FLOOR35")
    occam_a2_a3 = _occam_step("A2_A1_PLUS_ICE10_FLOOR35", "A3_A2_PLUS_DIV_SPREAD_GUARD")
    report["gates"] = {
        "integrity_ok": integrity_ok,
        "by_arm": gate_eval,
        "G7_Occam": {
            "A1_to_A2": occam_a1_a2,
            "A2_to_A3": occam_a2_a3,
        },
    }

    # Determine winning arm by pre-registered Occam ladder
    winner = "A0_V331"
    if all(v["pass"] for v in gate_eval["A1_CORE40_G10_REGIME_ONLY"].values()):
        winner = "A1_CORE40_G10_REGIME_ONLY"
        if all(v["pass"] for v in gate_eval["A2_A1_PLUS_ICE10_FLOOR35"].values()) and occam_a1_a2["pass"]:
            winner = "A2_A1_PLUS_ICE10_FLOOR35"
            if all(v["pass"] for v in gate_eval["A3_A2_PLUS_DIV_SPREAD_GUARD"].values()) and occam_a2_a3["pass"]:
                winner = "A3_A2_PLUS_DIV_SPREAD_GUARD"
    report["winner"] = winner
    report["finished"] = utc()

    (REPORTS_DIR / "exp_v3_13_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown_report(report)
    return 0


def _write_markdown_report(report: dict[str, Any]) -> None:
    lines: list[str] = [
        "# EXP-V3-13：CORE40 + ICE_10 + 因果股息利差包络正交阶梯回测报告",
        "",
        f"- **Bundle**：`{report['bundle_path']}`（已无损补齐至 `2026-11-26`）",
        f"- **完整性硬门禁**：`{report['integrity_ok']}`",
        f"- **预注册胜出臂**：**`{report['winner']}`**",
        "",
        "## 1. 全窗 VectorBT（2018-01-02..2026-11-26）",
        "",
        "| Arm | Full CAGR / DD / Calmar | IS(18-23) CAGR / Calmar | OOS(24-26) CAGR / DD / Calmar | 2026H2 压力(Ret / DD) | 调仓次数 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm, blk in report["vbt"].items():
        f, is_, oos, st = (
            blk["full_2018_20261126"],
            blk["is_2018_2023"],
            blk["oos_2024_20261126"],
            blk["stress_2026h2"],
        )
        lines.append(
            f"| {arm} | {f['cagr']:.2%} / {f['max_drawdown']:.2%} / {f['calmar']:.3f} "
            f"| {is_['cagr']:.2%} / {is_['calmar']:.3f} "
            f"| {oos['cagr']:.2%} / {oos['max_drawdown']:.2%} / {oos['calmar']:.3f} "
            f"| {st['total_return']:.2%} / {st['max_drawdown']:.2%} | {blk['ctrl'].get('rebal_events', '—')} |"
        )

    lines += [
        "",
        "## 2. 全窗原生 RQAlpha 6.3.0 底盘（2018-01-02..2026-11-26 @ ¥69k & ¥100k）",
        "",
        "| 回放 | Full CAGR | IS CAGR | OOS CAGR | MaxDD | Sharpe | Calmar | 2026H2(Ret/DD) | 笔数 | 佣金(元) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k, r in report["chassis_rqa"].items():
        f, is_, oos, st = r["full"], r["is"], r["oos"], r["stress_2026h2"]
        lines.append(
            f"| {k} | {f['cagr']:.2%} | {is_['cagr']:.2%} | {oos['cagr']:.2%} | {f['max_drawdown']:.2%} "
            f"| {f['sharpe']:.3f} | {f['calmar']:.3f} | {st['total_return']:.2%} / {st['max_drawdown']:.2%} "
            f"| {r['trade_count']} | {r['commission_yuan']:.2f} |"
        )

    lines += [
        "",
        "## 3. 统一账户原生 RQAlpha 6.3.0 回放（2024-02/07..2026-11-26）",
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
        "## 4. LOYO（重点：剔除 2025 黄金牛年）与 6 窗 Walk-Forward",
        "",
        "| 序列 | 全9年 Calmar | 剔除2025年 8年Calmar | RQA69k WF胜出窗(6) |",
        "|---|---:|---:|---:|",
    ]
    for arm in ("A0_V331", "A1_CORE40_G10_REGIME_ONLY", "A2_A1_PLUS_ICE10_FLOOR35", "A3_A2_PLUS_DIV_SPREAD_GUARD"):
        r69 = report["chassis_rqa"][f"{arm}_69000"]["full"]
        ex25 = report["loyo"][f"RQA_{arm}_69000"]["ex_2025"]
        wf_a = report["walk_forward"][f"RQA_{arm}_69000"]
        wf_0 = report["walk_forward"]["RQA_A0_V331_69000"]
        wf_w = sum(1 for a_w, z_w in zip(wf_a, wf_0) if a_w["oos_calmar"] >= z_w["oos_calmar"])
        lines.append(f"| RQA_{arm}_69000 | {r69['calmar']:.3f} | {ex25['calmar']:.3f} | {wf_w}/6 |")

    lines += [
        "",
        "## 5. 7 条硬门禁逐项裁决",
        "",
        "| 臂 / 阶梯 | G1 IS/OOS+35% | G2 TrueDD | G3 2026H2 | G4 LOYO去2025 | G5 WF+高原 | G6 DSR/PBO |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm, gs in report["gates"]["by_arm"].items():
        lines.append(
            f"| {arm} | {'PASS' if gs['G1_IS_OOS_and_Calmar_35pct']['pass'] else 'FAIL'} ({gs['G1_IS_OOS_and_Calmar_35pct']['r69_calmar_lift_pct']:+.1f}%) "
            f"| {'PASS' if gs['G2_True_Peak_DD']['pass'] else 'FAIL'} ({gs['G2_True_Peak_DD']['worst_69k_acct_true_dd']:.2%}) "
            f"| {'PASS' if gs['G3_2026H2_Stress']['pass'] else 'FAIL'} ({gs['G3_2026H2_Stress']['r69_2026h2_ret']:.2%}) "
            f"| {'PASS' if gs['G4_LOYO_Ex2025']['pass'] else 'FAIL'} ({gs['G4_LOYO_Ex2025']['r69_ex2025_calmar']:.3f}) "
            f"| {'PASS' if gs['G5_WalkForward_and_Plateau']['pass'] else 'FAIL'} "
            f"| {'PASS' if gs['G6_Multiple_Testing']['pass'] else 'FAIL'} (DSR={gs['G6_Multiple_Testing']['dsr_prob']:.2f}, PBO={gs['G6_Multiple_Testing']['pbo_cscv_16']:.2f}) |"
        )
    o12 = report["gates"]["G7_Occam"]["A1_to_A2"]
    o23 = report["gates"]["G7_Occam"]["A2_to_A3"]
    lines += [
        "",
        f"- **G7 奥卡姆 A1->A2**：`{'PASS' if o12['pass'] else 'FAIL'}` (69k ΔCalmar={o12['r69_full_calmar_delta']:+.4f}, ΔDD={o12['r69_full_dd_reduction_pp']:+.2f}pp, ΔIS={o12['r69_is_cagr_delta_pp']:+.2f}pp, ΔOOS={o12['r69_oos_cagr_delta_pp']:+.2f}pp)",
        f"- **G7 奥卡姆 A2->A3**：`{'PASS' if o23['pass'] else 'FAIL'}` (69k ΔCalmar={o23['r69_full_calmar_delta']:+.4f}, ΔDD={o23['r69_full_dd_reduction_pp']:+.2f}pp, ΔIS={o23['r69_is_cagr_delta_pp']:+.2f}pp, ΔOOS={o23['r69_oos_cagr_delta_pp']:+.2f}pp)",
    ]
    (REPORTS_DIR / "exp_v3_13_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
