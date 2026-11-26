"""EXP-V3-11 runner: V3.3.0 five-mechanism integration & win-rate/payoff audit."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from importlib.metadata import version
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

from research.ashare import v3_data_202611 as data
from research.ashare.experiments import exp_v3_01_regime_super_etf as e1
from research.ashare.v3_data import rq_to_ts, ts_to_rq
from research.batches.exp_v3_06_defensive_rotation.run import (
    LOW_TICKET_BONDS,
    select_bond_reserve,
)
from research.batches.exp_v3_07_lowvol_risk_budget.run import LOWVOL_FALLBACKS
from research.batches.exp_v3_08_icepoint_recovery.run import compute_recovery_overlay_series
from research.batches.exp_v3_09_drawdown_control.run import DrawdownController
from research.batches.exp_v3_10_pioneer_alpha.run import PIT_INDUSTRY_PROXIES
from research.batches.exp_v3_11_v330_integration.analytics import (
    compute_calendar_stats,
    compute_roundtrip_stats,
)
from research.batches.v3_account_replay_v2.native import TieredFees, asset_group, opening_block
from research.batches.v3_account_replay_v2.policy import (
    FOCUS,
    GOLD,
    GROWTH,
    VALUE,
    Plan,
    exit_reason,
    indicators,
)
from research.batches.v3_account_replay_v2.stock_signals import (
    build_causal_bp1_candidates_202611,
)
from research.batches.v3_complexity_hurdle_v2.native import NORMAL, SUPER, replay
from research.batches.v3_complexity_hurdle_v2.run import require, reserve, utc
from tacticore.engines.rqalpha_adapter import build_rqalpha_config
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/EXP_V3_11_V330_INTEGRATION"
PROTOCOL = ROOT / "research/batches/exp_v3_11_v330_integration/PROTOCOL_V1.md"

START = data.EXP_START
RQA_END = data.BUNDLE_CUTOFF_202611
VBT_END = data.EXP_END_202611
STRESS_START = pd.Timestamp("2026-07-01")
OOS_CASH_START = pd.Timestamp("2024-02-01")
OOS_CONC_START = pd.Timestamp("2024-07-01")
CASH = (69000, 100000)

LOW_VOL_EXCLUDED_FROM_PIONEER = frozenset({"159549.SZ", "159207.SZ", "159321.SZ"})
BOND_SET_TS = frozenset({"159649.SZ", "511260.SH", "511010.SH", "511360.SH", "511880.SH"})
BOND_SET_RQ = frozenset(ts_to_rq(c) for c in BOND_SET_TS)
LOW_TICKET_BONDS_RQ = tuple(ts_to_rq(c) for c in LOW_TICKET_BONDS)
LOW_VOL_PRIMARY_RQ = ("159549.XSHE", "159207.XSHE", "512890.XSHG", "510880.XSHG")


def load_sector_pioneer_pool(wl_path: Path = data.base_v3.WHITELIST_PATH) -> tuple[str, ...]:
    """Return 20 industry_theme Super ETFs (excluding low-vol core & gold-equity) + PIT proxies."""
    wl = json.loads(wl_path.read_text(encoding="utf-8"))
    super_sector = [
        str(e["ts_code"])
        for e in wl["entries"]
        if e["category"] == "industry_theme"
        and str(e["ts_code"]) not in LOW_VOL_EXCLUDED_FROM_PIONEER
    ]
    return tuple(dict.fromkeys([*super_sector, *PIT_INDUSTRY_PROXIES]))


def build_v3_base_chassis_weights(
    panels: Any,
    regime_df: pd.DataFrame,
    *,
    sector_pool_ts: tuple[str, ...],
    use_recovery: bool,
    use_lowvol_core: bool,
    use_low_ticket_bond: bool,
    use_sector_pioneer: bool,
    end: pd.Timestamp = VBT_END,
) -> tuple[pd.DataFrame, pd.Series, dict[str, int]]:
    """Build strictly causal T+1 target weights before drawdown overlay."""
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    adj = panels.etf_adj_close
    mask = panels.etf_tradability_mask
    cols = list(adj.columns)
    weights = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)

    if use_recovery:
        eff_reg, _, rec_stats = compute_recovery_overlay_series(
            panels, regime_df, mode="m2_thrust", ice_th=0.15, recovery_weight=0.40
        )
    else:
        eff_reg = regime_df["confirmed_regime"].astype(str)
        rec_stats = {"recovery_entries": 0, "false_breakout_stops": 0, "upgrades": 0}

    ma60_panel = adj.rolling(60, min_periods=60).mean()
    ret20_panel = adj / adj.shift(20) - 1.0
    ret60_panel = adj / adj.shift(60) - 1.0

    current_target = pd.Series(0.0, index=cols, dtype=float)
    prev_state: str | None = None
    last_rebal_pos = -999
    drift_band = 0.10 if use_low_ticket_bond else 0.08
    bond_candidates = LOW_TICKET_BONDS if use_low_ticket_bond else ("511010.SH",)

    for pos in range(len(cal) - 1):
        sig_dt = cal[pos]
        exec_dt = cal[pos + 1]
        state = str(eff_reg.at[sig_dt])
        style = str(regime_df.at[sig_dt, "style"])

        desired: dict[str, float] = {}
        val_list = e1._available_bucket(exec_dt, e1.VALUE_SUPER_ETFS, e1.VALUE_FALLBACKS, mask, adj)
        gro_list = e1._available_bucket(
            exec_dt, e1.GROWTH_SUPER_ETFS, e1.GROWTH_FALLBACKS, mask, adj
        )
        lov_list = e1._available_bucket(
            exec_dt, e1.DEFENSIVE_SUPER_ETFS, LOWVOL_FALLBACKS, mask, adj
        )

        if state == "DEFENSIVE":
            for c in lov_list:
                desired[c] = desired.get(c, 0.0) + 0.15 / len(lov_list)
        else:
            pioneer_w = (
                0.20 if (use_sector_pioneer and state in ("OFFENSIVE", "STRUCTURAL")) else 0.0
            )
            total_eq = 0.85 if state == "OFFENSIVE" else (0.60 if state == "STRUCTURAL" else 0.40)
            chassis_w = total_eq - pioneer_w

            if use_lowvol_core:
                shares = (
                    {"VALUE": 0.25, "GROWTH": 0.45, "LOW_VOL": 0.30}
                    if style == "GROWTH_LEADING"
                    else (
                        {"VALUE": 0.45, "GROWTH": 0.25, "LOW_VOL": 0.30}
                        if style == "VALUE_LEADING"
                        else {"VALUE": 0.35, "GROWTH": 0.35, "LOW_VOL": 0.30}
                    )
                )
            else:
                shares = (
                    {"VALUE": 0.35, "GROWTH": 0.65, "LOW_VOL": 0.0}
                    if style == "GROWTH_LEADING"
                    else (
                        {"VALUE": 0.65, "GROWTH": 0.35, "LOW_VOL": 0.0}
                        if style == "VALUE_LEADING"
                        else {"VALUE": 0.50, "GROWTH": 0.50, "LOW_VOL": 0.0}
                    )
                )

            for bname, bcodes in (("VALUE", val_list), ("GROWTH", gro_list), ("LOW_VOL", lov_list)):
                bw = shares[bname]
                if bw > 0:
                    for c in bcodes:
                        desired[c] = desired.get(c, 0.0) + (chassis_w * bw) / len(bcodes)

            if pioneer_w > 0:
                scored: list[tuple[float, str]] = []
                for c in sector_pool_ts:
                    if c not in adj.columns or not bool(mask.at[exec_dt, c]):
                        continue
                    c_sig = adj.at[sig_dt, c]
                    m60 = ma60_panel.at[sig_dt, c]
                    r20 = ret20_panel.at[sig_dt, c]
                    r60 = ret60_panel.at[sig_dt, c]
                    if pd.isna(c_sig) or pd.isna(m60) or pd.isna(r20) or pd.isna(r60):
                        continue
                    if float(c_sig) > float(m60):
                        scored.append((0.5 * float(r20) + 0.5 * float(r60), c))
                if scored:
                    scored.sort(key=lambda x: (-x[0], x[1]))
                    pick = scored[0][1]
                    desired[pick] = desired.get(pick, 0.0) + pioneer_w

        res_code = select_bond_reserve(exec_dt, mask, adj, bond_candidates)
        rem = max(0.0, 1.0 - sum(desired.values()))
        if res_code is not None and rem > 1e-6:
            desired[res_code] = desired.get(res_code, 0.0) + rem

        cand = pd.Series(0.0, index=cols, dtype=float)
        for k, v in desired.items():
            cand[k] = float(v)

        l1_diff = float((cand - current_target).abs().sum())
        state_changed = prev_state is None or state != prev_state
        periodic = (pos - last_rebal_pos >= 10) and l1_diff >= drift_band
        if state_changed or periodic:
            cand_row = pd.Series(np.nan, index=cols, dtype=float)
            for sym in cols:
                if cand[sym] > 0:
                    cand_row[sym] = cand[sym]
                elif current_target[sym] > 0:
                    cand_row[sym] = 0.0
            weights.loc[exec_dt] = cand_row
            current_target = cand
            last_rebal_pos = pos
        prev_state = state

    return weights, eff_reg, rec_stats


def apply_drawdown_overlay_202611(
    panels: Any,
    base_weights: pd.DataFrame,
    eff_reg: pd.Series,
    *,
    ctrl_mode: str,
    use_low_ticket_bond: bool,
    end: pd.Timestamp = VBT_END,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply causal DrawdownController onto V3.x base weights and re-route surplus to bond."""
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    adj = panels.etf_adj_close.loc[cal].ffill()
    cols = list(panels.etf_adj_close.columns)
    base_full = base_weights.loc[cal].ffill().fillna(0.0)
    mask = panels.etf_tradability_mask
    rets = adj.pct_change(fill_method=None).fillna(0.0)
    ctrl = DrawdownController(init_nav=1.0, mode=ctrl_mode, floor_dd=0.15, cppi_m=5.0)
    bond_candidates = LOW_TICKET_BONDS if use_low_ticket_bond else ("511010.SH",)
    eq_cols = [c for c in cols if c not in BOND_SET_TS]

    nav = 1.0
    prev_w = pd.Series(0.0, index=cols, dtype=float)
    out_w = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)
    max_true_dd = 0.0
    breach_days = 0
    prev_locked = False
    prev_reg_s: str | None = None
    drift_th = 0.10 if use_low_ticket_bond else 0.08

    for pos in range(len(cal) - 1):
        sig_dt = cal[pos]
        exec_dt = cal[pos + 1]
        if pos > 0:
            nav *= 1.0 + float((prev_w * rets.loc[sig_dt]).sum())

        base_row = base_full.loc[exec_dt]
        reg_s = str(eff_reg.at[sig_dt])
        base_eq = float(base_row[eq_cols].sum())
        st = ctrl.step(pos, nav, concentrated=False, base_eq_budget=max(base_eq, 0.15))
        max_true_dd = max(max_true_dd, float(st["true_dd"]))
        if st["breach"] > 0:
            breach_days += 1

        cap = float(st["buy_cap"])
        scale = min(1.0, max(0.0, cap / base_eq)) if base_eq > 1e-9 else 1.0
        cand = pd.Series(0.0, index=cols, dtype=float)
        for c in eq_cols:
            if base_row[c] > 0:
                cand[c] = float(base_row[c]) * scale

        res_code = select_bond_reserve(exec_dt, mask, panels.etf_adj_close, bond_candidates)
        rem = max(0.0, 1.0 - float(cand.sum()))
        if res_code is not None and rem > 1e-6:
            cand[res_code] = rem

        l1_diff = float((cand - prev_w).abs().sum())
        changed = (
            pos == 0
            or reg_s != prev_reg_s
            or st["locked"] != prev_locked
            or st["trigger"]
            or l1_diff >= drift_th
        )
        if changed:
            cand_row = pd.Series(np.nan, index=cols, dtype=float)
            for sym in cols:
                if cand[sym] > 0:
                    cand_row[sym] = cand[sym]
                elif prev_w[sym] > 0:
                    cand_row[sym] = 0.0
            out_w.loc[exec_dt] = cand_row
            prev_w = cand
        prev_locked = bool(st["locked"])
        prev_reg_s = reg_s

    return out_w, {
        "locks": ctrl.locks,
        "relock_loops": ctrl.relock_loops,
        "breach_days": breach_days,
        "proxy_max_true_dd": round(max_true_dd, 4),
    }


def make_group_fn(sector_pool_ts: tuple[str, ...]) -> Any:
    """Return sleeve classifier for EXP-V3-11 fills & roundtrips."""
    sector_rq = {ts_to_rq(c) for c in sector_pool_ts} | {
        "512480.XSHG",
        "159994.XSHE",
        "515790.XSHG",
    }
    main_pf = ("000", "001", "002", "003", "600", "601", "603", "605")

    def _fn(code: str) -> str:
        rq = ts_to_rq(code) if code.endswith((".SH", ".SZ")) else code
        if rq == FOCUS:
            return "concentrated_159558"
        if rq in BOND_SET_RQ:
            return "bond_reservoir"
        if rq.endswith((".XSHG", ".XSHE")) and rq[:3] in main_pf:
            return "stock_bp1"
        if rq in sector_rq:
            return "sector_pioneer"
        return "chassis"

    return _fn


def select_v330_targets(
    *,
    regime: str,
    style: str,
    occupied_weight: float,
    features: dict[str, Any],
    sector_pool_rq: tuple[str, ...],
    use_lowvol_core: bool,
    use_sector_pioneer: bool,
    bp1_active_budget: bool,
) -> dict[str, float]:
    """Select target equity weights for unified account replay at date T."""

    def valid(c: str) -> bool:
        return c in features and pd.notna(features[c].ma20) and features[c].raw > 0

    budget_map = {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "RECOVERY": 0.40, "DEFENSIVE": 0.15}
    room = max(0.0, budget_map[regime] - occupied_weight)
    out: dict[str, float] = {}

    if regime == "DEFENSIVE":
        if room <= 0:
            return {}
        if use_lowvol_core:
            lv = [c for c in LOW_VOL_PRIMARY_RQ if valid(c)][:2]
            if lv:
                for c in lv:
                    out[c] = room / len(lv)
                return out
        if valid(GOLD):
            out[GOLD] = min(room, 0.10)
            return out
        return {}

    if regime == "RECOVERY":
        base = room
        pioneer_room = 0.0
    elif regime == "OFFENSIVE":
        pioneer_cap = 0.40 if bp1_active_budget else 0.20
        base = min(room, 0.45 if bp1_active_budget else 0.65)
        pioneer_room = max(0.0, min(0.20, room - base, pioneer_cap))
    else:  # STRUCTURAL
        pioneer_cap = 0.30 if bp1_active_budget else 0.20
        base = min(room, 0.30 if bp1_active_budget else 0.40)
        pioneer_room = max(0.0, min(0.20, room - base, pioneer_cap))

    if base > 0:
        if use_lowvol_core:
            shares = (
                {"VALUE": 0.25, "GROWTH": 0.45, "LOW_VOL": 0.30}
                if style == "GROWTH_LEADING"
                else (
                    {"VALUE": 0.45, "GROWTH": 0.25, "LOW_VOL": 0.30}
                    if style == "VALUE_LEADING"
                    else {"VALUE": 0.35, "GROWTH": 0.35, "LOW_VOL": 0.30}
                )
            )
            val_c = next((c for c in VALUE if valid(c)), None)
            gro_c = next((c for c in GROWTH if valid(c)), None)
            lv_cs = [c for c in LOW_VOL_PRIMARY_RQ if valid(c)][:2]
            if val_c:
                out[val_c] = base * shares["VALUE"]
            if gro_c:
                out[gro_c] = base * shares["GROWTH"]
            if lv_cs:
                for c in lv_cs:
                    out[c] = (base * shares["LOW_VOL"]) / len(lv_cs)
        else:
            gold = min(base, 0.10)
            if gold > 0 and valid(GOLD):
                out[GOLD] = gold
            growth = {"GROWTH_LEADING": 0.65, "VALUE_LEADING": 0.35}.get(style, 0.50)
            for grp, share in ((VALUE, 1.0 - growth), (GROWTH, growth)):
                c = next((x for x in grp if valid(x)), None)
                if c and base > gold:
                    out[c] = (base - gold) * share

    if use_sector_pioneer and pioneer_room >= 0.02:
        scored: list[tuple[float, str]] = []
        for c in sector_pool_rq:
            if not valid(c):
                continue
            r = features[c]
            if pd.notna(r.ma60) and pd.notna(r.ret20) and pd.notna(r.ret60) and r.c > r.ma60:
                scored.append((0.5 * float(r.ret20) + 0.5 * float(r.ret60), c))
        if scored:
            scored.sort(key=lambda x: (-x[0], x[1]))
            pick = scored[0][1]
            out[pick] = out.get(pick, 0.0) + min(pioneer_room, 0.20)

    return {c: w for c, w in out.items() if w > 0.01}


def replay_v330_account(
    *,
    days: list[str],
    market: dict[str, tuple[str, str]],
    features: dict[str, dict[str, Any]],
    stock_candidates: dict[str, list[Any]],
    white: set[str],
    sector_pool_rq: tuple[str, ...],
    capital: float,
    seed: float,
    ctrl_mode: str,
    use_lowvol_core: bool,
    use_low_ticket_bond: bool,
    use_sector_pioneer: bool,
    gate_bp1: bool,
    group_fn: Any,
) -> dict[str, Any]:
    """Native RQAlpha 6.3.0 unified account replay (V3.3.0 vs V3.2.1 baseline)."""
    from rqalpha.api import history_bars, instruments, order_shares, subscribe_event

    lookup = {d: i for i, d in enumerate(days)}
    rows, orders, fills, rejects, violations = [], [], [], [], []
    pending: dict[str, dict[str, Any]] = {}
    retries: dict[str, dict[str, Any]] = {}
    armed: dict[str, bool] = {}
    stock_stops: dict[str, dict[str, Any]] = {}
    ctrl = DrawdownController(init_nav=capital, mode=ctrl_mode, floor_dd=0.15, cppi_m=5.0)
    plan = Plan()
    state: dict[str, Any] = {"regime": None, "align": -100, "locked": False, "active": None}
    stock_slip_drag = [0.0]
    budget_map = {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "RECOVERY": 0.40, "DEFENSIVE": 0.15}
    bond_priority = LOW_TICKET_BONDS_RQ if use_low_ticket_bond else ("511010.XSHG",)
    drift_band = 0.10 if use_low_ticket_bond else 0.08

    cfg = build_rqalpha_config(
        days[0],
        days[-1],
        initial_cash=capital,
        fees=0.00025,
        slippage=0,
        bundle_path=data.BUNDLE_PATH_202611,
        rqalpha_major_version=6,
    )
    cfg["mod"]["sys_accounts"] = {"stock_t1": True, "auto_switch_order_value": False}

    def audit(ok: bool, msg: str) -> None:
        if not ok:
            violations.append(msg)

    def merge(book: dict[str, dict[str, Any]], a: dict[str, Any]) -> None:
        sym = a["code"]
        if sym in book:
            old = book[sym]
            if (a["p"], -a.get("sell_est", 0)) >= (old["p"], -old.get("sell_est", 0)):
                book[sym] = old
            else:
                book[sym] = a
        else:
            book[sym] = a

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
        a["filled"] += q
        if t.order_book_id == FOCUS:
            i = lookup[d]
            if a["reason"] == "SEED":
                plan.seed(a["filled"], int(capital * 0.25 / px / 100), px, i)
            elif a["side"] == "SELL":
                plan.sell(q, px, i)
            elif a["reason"] == "SLOT":
                plan.slot_px = (plan.slot_px * plan.slot + px * q) / (plan.slot + q)
                plan.slot += q
                plan.last_fill = i
        elif grp == "stock":
            if a["side"] == "BUY":
                stock_stops[t.order_book_id] = {
                    "stop_pct": float(a.get("stop_pct", 0.08)),
                    "entry_date": d,
                    "entry_px": px,
                }
            elif a["side"] == "SELL" and ctx.portfolio.positions[t.order_book_id].quantity == 0:
                stock_stops.pop(t.order_book_id, None)

    def on_reject(ctx: Any, ev: Any) -> None:
        rejects.append(
            {"date": str(ctx.now.date()), "code": ev.order_book_id, "reason": str(ev.reason)}
        )

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
        # Execute lower priority numbers first, and sells before buys
        for a in sorted(pending.values(), key=lambda x: (x["p"], x["side"] == "BUY", x["code"])):
            sym, buy = a["code"], a["side"] == "BUY"
            record = dict(a, date=d, filled=0, requested=0, status=None)
            orders.append(record)
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
                not instrument.active_at(ctx.now)
                or env.data_proxy.is_suspended(sym, ctx.now.date()),
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
                        room_amt = max(0.0, budget_map[a["regime"]] * nav - eq_now)
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
                        if a["reason"] == "SLOT":
                            eq_now = sum(
                                p.market_value
                                for s, p in ctx.portfolio.positions.items()
                                if p.quantity > 0 and s not in BOND_SET_RQ
                            )
                            eq_room = max(0.0, nav * budget_map[a["regime"]] - eq_now)
                            amount = min(amount, eq_room, nav * 0.10)
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
                        desired = int(
                            round_order_quantity(instrument, max(0.0, held - a["w"] * nav / px))
                        )
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
        pnl: Counter[str] = Counter()
        for s in pp:
            pnl[group_fn(s)] += float(pp[s].daily_pnl)

        focus_w = w.get(FOCUS, 0.0)
        concentrated = focus_w > 0.30 or any(plan.batches)
        regime, style = market[d]
        risk_row = ctrl.step(i, nav, concentrated, budget_map[regime])
        f = features[d]
        locked, l1 = bool(risk_row["locked"]), bool(risk_row["l1"])

        risk_w = sum(wt for s, wt in w.items() if s not in BOND_SET_RQ)
        rows.append(
            {
                "date": d,
                "nav": nav,
                "net_nav_after_5bp_stock_slip": max(1.0, nav - stock_slip_drag[0]),
                "cash": cash,
                "weights": w,
                "risk": risk_w,
                "regime": regime,
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
                    else int(held[sym].quantity * max(0.0, 1.0 - weight / w[sym]))
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

        # P0: Drawdown controller proportional risk reduction (excluding bond reservoir)
        cc = risk_row["ctrl_cap"]
        if cc is not None and risk_w > float(cc) + 0.02 and risk_w > 1e-6:
            for s in held:
                if s in BOND_SET_RQ:
                    continue
                add(0, s, "CTRL_REDUCE", "SELL", w[s] * float(cc) / risk_w)

        # P1: Exits (stocks + non-focus risk ETFs)
        active_stocks: set[str] = set()
        for s, p in held.items():
            if s == FOCUS or s in BOND_SET_RQ:
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
                cost = (
                    float(p.avg_price)
                    if isfinite(p.avg_price) and p.avg_price > 0
                    else meta["entry_px"]
                )
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
            elif s in f:
                r = f[s]
                armed[s], why = exit_reason(
                    r.raw,
                    float(p.avg_price),
                    r.raw * r.ma20 / r.c,
                    r.raw * r.ma10 / r.c,
                    armed.get(s, False),
                    l1,
                )
                if why:
                    add(1, s, why, "SELL", 0.0)

        # P2: 159558.SZ BOTTOM_GRIND_25
        if FOCUS in held and FOCUS in f:
            r = f[FOCUS]
            dec = plan.decision(
                r, i, focus_w, regime, l1 or locked, float(risk_row["buy_cap"]) - risk_w
            )
            if dec:
                reason, qty, wt = dec
                add(
                    2,
                    FOCUS,
                    reason,
                    "BUY" if reason == "SLOT" else "SELL",
                    wt,
                    abs(qty) if qty else None,
                    regime=regime,
                )

        # P3: BP1_PULLBACK Stocks (gated by capital >= 100k & non-concentrated in v3.3.0)
        bp1_permitted = (not gate_bp1) or (nav >= 100000.0 and not concentrated)
        stock_buy_budget = 0.0
        kept_stocks = {s for s in active_stocks if pending.get(s, {}).get("side") != "SELL"}
        current_stock_w = sum(w[s] for s in kept_stocks)
        slots_left = max(0, 2 - len(active_stocks))
        eff_cap = float(risk_row["buy_cap"])
        bp1_open = (
            bp1_permitted
            and regime in ("OFFENSIVE", "STRUCTURAL")
            and not locked
            and not l1
            and slots_left > 0
        )
        if bp1_open:
            focus_committed = max(
                focus_w,
                (pending.get(FOCUS, {}).get("w") or 0.0)
                if pending.get(FOCUS, {}).get("side") == "BUY"
                else 0.0,
            )
            eff_eq_cap = min(eff_cap, budget_map[regime])
            total_avail = max(0.0, eff_eq_cap - focus_committed - current_stock_w)
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
                add(3, ob, "BP1_ENTRY", "BUY", est_w, None, stop_pct=stop_pct, regime=regime)
                stock_buy_budget += est_w
                total_avail -= est_w
                slots_left -= 1

        # P4: Chassis + Sector Pioneer + Bond Reservoir alignment
        bond_pick = next((b for b in bond_priority if b in f), "511010.XSHG")
        align = (
            regime != state["regime"]
            or (state["locked"] and not locked)
            or risk_row["trigger"]
            or i - state["align"] >= 10
        )
        planned_equity_buy_amt = sum(
            max(
                0.0,
                (a.get("w") or 0.0) * nav
                - (held[a["code"]].market_value if a["code"] in held else 0.0),
            )
            for a in pending.values()
            if a["side"] == "BUY" and a["code"] not in BOND_SET_RQ
        )
        if align and not locked:
            focus_b = max(
                focus_w,
                (pending.get(FOCUS, {}).get("w") or 0.0)
                if pending.get(FOCUS, {}).get("side") == "BUY"
                else 0.0,
            )
            occupied = focus_b + current_stock_w + stock_buy_budget
            raw_t = select_v330_targets(
                regime=regime,
                style=style,
                occupied_weight=occupied,
                features=f,
                sector_pool_rq=sector_pool_rq,
                use_lowvol_core=use_lowvol_core,
                use_sector_pioneer=use_sector_pioneer,
                bp1_active_budget=bp1_permitted,
            )
            tot_raw = sum(raw_t.values())
            max_new_eq = max(0.0, eff_cap - occupied)
            scale = min(1.0, max_new_eq / tot_raw) if tot_raw > 1e-9 else 1.0
            scaled_t = {k: v * scale for k, v in raw_t.items() if v * scale > 0.01}

            for s in sorted((set(held) - active_stocks - BOND_SET_RQ | set(scaled_t)) - {FOCUS}):
                wt = scaled_t.get(s, 0.0)
                diff = wt - w.get(s, 0.0)
                if abs(diff) < 1e-12:
                    continue
                if wt > 0 and abs(diff) * nav < (1000.0 if s in white else 5000.0):
                    continue
                add(4, s, "ALIGN", "BUY" if diff > 0 else "SELL", wt)
                if diff > 0:
                    planned_equity_buy_amt += diff * nav

            target_eq_total = min(eff_cap, occupied + sum(scaled_t.values()))
            target_bond_w = max(0.0, 1.0 - target_eq_total - 0.01)
            cur_bond_w = sum(w.get(b, 0.0) for b in BOND_SET_RQ)
            if abs(target_bond_w - cur_bond_w) >= drift_band:
                diff_b = target_bond_w - cur_bond_w
                if diff_b * nav >= 5000.0 and bond_pick in f:
                    add(5, bond_pick, "BOND_RESERVOIR", "BUY", target_bond_w)
                elif diff_b < 0:
                    for b in sorted(b for b in held if b in BOND_SET_RQ):
                        add(3, b, "BOND_REDUCE", "SELL", max(0.0, target_bond_w))
            state["align"] = i

        # Bond funding sell if pending equity buys exceed current cash
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

        state.update(regime=regime, locked=locked)

    a = run_func(init=init, open_auction=open_auction, handle_bar=close, config=cfg)["sys_analyser"]
    eq_raw = a["portfolio"]["total_value"]
    eq_net = pd.Series(
        [r["net_nav_after_5bp_stock_slip"] for r in rows],
        index=pd.to_datetime([r["date"] for r in rows]),
        dtype=float,
    )
    audit([str(d)[:10] for d in eq_raw.index] == days == [r["date"] for r in rows], "calendar")
    audit(len(a.get("trades", [])) == len(fills), "analyser vs trade count")

    pnl_attr: dict[str, float] = defaultdict(float)
    for r in rows:
        for grp, val in r["pnl"].items():
            pnl_attr[grp] += float(val)

    return {
        "metrics": compute_calendar_stats(eq_net),
        "roundtrips": compute_roundtrip_stats(fills, group_fn),
        "true_max_dd": float(max(r["true_dd"] for r in rows)),
        "breach_days": sum(1 for r in rows if r["breach"] > 0),
        "locks": ctrl.locks,
        "relock_loops": ctrl.relock_loops,
        "commission_yuan": round(sum(f["commission"] for f in fills), 2),
        "tax_yuan": round(sum(f["tax"] for f in fills), 2),
        "explicit_stock_slip_yuan": round(stock_slip_drag[0], 2),
        "total_friction_yuan": round(
            sum(f["commission"] + f["tax"] + f["other"] + f["stock_slip_5bp"] for f in fills), 2
        ),
        "fill_count": len(fills),
        "pnl_attribution": {k: round(v, 2) for k, v in sorted(pnl_attr.items())},
        "reject_count": len(rejects),
        "violation_count": len(violations),
        "violations": violations,
    }


def main() -> int:
    reserve(STEM)
    report: dict[str, Any] = {
        "started": utc(),
        "runner_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "versions": {k: version(k) for k in ("rqalpha", "vectorbt")},
        "protocol_sha256": data.sha256_file(PROTOCOL),
        "vbt": {},
        "chassis_rqa": {},
        "account_replay": {},
        "selection": {},
        "gates": {},
    }
    try:
        prov = data.verify_v3_202611_provenance(verify_content=True)
        report["snapshot_id"] = prov.snapshot_id
        p = data.load_stitched_panels_202611(prov)
        reg = data.compute_v3_regime_series_202611(prov, p.index_close, p.calendar, use_cache=True)
        sector_pool_ts = load_sector_pioneer_pool()
        sector_pool_rq = tuple(ts_to_rq(c) for c in sector_pool_ts)
        group_fn = make_group_fn(sector_pool_ts)

        arms = {
            "V3_2_1_BASELINE": dict(
                use_recovery=False,
                use_lowvol_core=False,
                use_low_ticket_bond=False,
                use_sector_pioneer=False,
                ctrl_mode="c0_hard",
                gate_bp1=False,
            ),
            "V3_3_0_GRADUAL": dict(
                use_recovery=True,
                use_lowvol_core=True,
                use_low_ticket_bond=True,
                use_sector_pioneer=True,
                ctrl_mode="c3_gradual",
                gate_bp1=True,
            ),
            "V3_3_0_CPPI": dict(
                use_recovery=True,
                use_lowvol_core=True,
                use_low_ticket_bond=True,
                use_sector_pioneer=True,
                ctrl_mode="c2_cppi",
                gate_bp1=True,
            ),
        }

        overlaid_w: dict[str, pd.DataFrame] = {}
        eff_reg_by_arm: dict[str, pd.Series] = {}
        for name, cfg_arm in arms.items():
            base_w, eff_reg, rec_stats = build_v3_base_chassis_weights(
                p,
                reg,
                sector_pool_ts=sector_pool_ts,
                use_recovery=bool(cfg_arm["use_recovery"]),
                use_lowvol_core=bool(cfg_arm["use_lowvol_core"]),
                use_low_ticket_bond=bool(cfg_arm["use_low_ticket_bond"]),
                use_sector_pioneer=bool(cfg_arm["use_sector_pioneer"]),
                end=VBT_END,
            )
            eff_reg_by_arm[name] = eff_reg
            ow, ctrl_info = apply_drawdown_overlay_202611(
                p,
                base_w,
                eff_reg,
                ctrl_mode=str(cfg_arm["ctrl_mode"]),
                use_low_ticket_bond=bool(cfg_arm["use_low_ticket_bond"]),
                end=VBT_END,
            )
            overlaid_w[name] = ow
            prices, mask, targets_df = (
                f.loc[:VBT_END] for f in (p.etf_adj_close, p.etf_tradability_mask, ow)
            )
            validate_execution_targets(targets_df, prices, mask, p.etf_lifetimes)
            rates = np.array(
                [SUPER if c in prov.super_etf_codes else NORMAL for c in ow.columns]
            )[None, :]
            eq = run_target_weights(
                prices,
                targets_df,
                fees=rates,
                slippage=0.0002,
                initial_cash=100000.0,
                metric_start=START,
                tradability_mask=mask,
                lifetimes=p.etf_lifetimes,
            ).equity.loc[START:VBT_END]
            report["vbt"][name] = {
                "recovery_stats": rec_stats,
                "ctrl": ctrl_info,
                "full_2018_20261126": compute_calendar_stats(eq),
                "is_2018_2023": compute_calendar_stats(eq.loc[: data.IS_END]),
                "oos_2024_20261126": compute_calendar_stats(eq.loc[data.IS_END :]),
                "stress_202607_20261126": compute_calendar_stats(eq.loc[STRESS_START:]),
            }

        # Full-window RQAlpha chassis replay (2018-01-02..2026-10-30) @ ¥69k & ¥100k
        for cash in CASH:
            for name in arms:
                label = f"{name}_{cash}"
                sys.stdout.write(f"{utc()} chassis {label}\n")
                sys.stdout.flush()
                eq, run = replay(
                    overlaid_w[name], cash, prov.super_etf_codes, True, start=START, end=RQA_END
                )
                fees = sum(float(f["commission"]) for f in run["fills"])
                report["chassis_rqa"][label] = {
                    "full": compute_calendar_stats(eq),
                    "is": compute_calendar_stats(eq.loc[: data.IS_END]),
                    "oos": compute_calendar_stats(eq.loc[data.IS_END :]),
                    "roundtrips": compute_roundtrip_stats(run["fills"], group_fn),
                    "trade_count": len(run["fills"]),
                    "commission_yuan": round(fees, 2),
                    "dates_pass": run["dates_pass"],
                    "fill_capture_pass": run["fill_capture_pass"],
                    "fees_pass": run["commission_audit"]["fees_pass"],
                    "illegal_non_lot_fills": len(run["commission_audit"]["illegal_non_lot_fills"]),
                }

        # Unified account replay (OOS_CASH 2024-02.., CORE25/HEAVY70 2024-07..2026-10-30)
        codes_rq = sorted(
            {
                FOCUS,
                GOLD,
                *VALUE,
                *GROWTH,
                *LOW_VOL_PRIMARY_RQ,
                *LOW_TICKET_BONDS_RQ,
                *sector_pool_rq,
            }
        )
        feat_dfs = {}
        for rq in codes_rq:
            ts = rq_to_ts(rq)
            if ts in p.etf_adj_close.columns and ts in p.etf_raw_close.columns:
                df = indicators(p.etf_adj_close[ts], p.etf_raw_close[ts])
                df["ret60"] = df["c"] / df["c"].shift(60) - 1.0
                df = df.where(p.etf_tradability_mask[ts], np.nan)
                feat_dfs[rq] = df
        features: dict[str, dict[str, Any]] = {}
        for dt in p.calendar:
            d_s = str(dt.date())
            features[d_s] = {
                rq: row
                for rq, df in feat_dfs.items()
                for row in [df.loc[dt]]
                if pd.notna(row["c"]) and pd.notna(row["raw"]) and float(row["raw"]) > 0
            }
        white_rq = {ts_to_rq(c) for c in prov.super_etf_codes}
        stock_cands, _ = build_causal_bp1_candidates_202611(
            oos_start=OOS_CASH_START, bundle_end=RQA_END
        )
        cal_rqa = p.calendar[p.calendar <= RQA_END]
        days_cash = [str(d.date()) for d in cal_rqa[cal_rqa >= OOS_CASH_START]]
        days_conc = [str(d.date()) for d in cal_rqa[cal_rqa >= OOS_CONC_START]]

        market_by_arm: dict[str, dict[str, tuple[str, str]]] = {}
        for name in arms:
            er = eff_reg_by_arm[name]
            market_by_arm[name] = {
                str(dt.date()): (str(er.at[dt]), str(reg.at[dt, "style"])) for dt in p.calendar
            }

        for scenario, s_days, seed in (
            ("OOS_CASH", days_cash, 0.0),
            ("CORE25", days_conc, 0.25),
            ("HEAVY70", days_conc, 0.70),
        ):
            for cash in CASH:
                for name, cfg_arm in arms.items():
                    cell = f"{scenario}_{cash}_{name}"
                    sys.stdout.write(f"{utc()} acct {cell}\n")
                    sys.stdout.flush()
                    report["account_replay"][cell] = replay_v330_account(
                        days=s_days,
                        market=market_by_arm[name],
                        features=features,
                        stock_candidates=stock_cands,
                        white=white_rq,
                        sector_pool_rq=sector_pool_rq,
                        capital=float(cash),
                        seed=seed,
                        ctrl_mode=str(cfg_arm["ctrl_mode"]),
                        use_lowvol_core=bool(cfg_arm["use_lowvol_core"]),
                        use_low_ticket_bond=bool(cfg_arm["use_low_ticket_bond"]),
                        use_sector_pioneer=bool(cfg_arm["use_sector_pioneer"]),
                        gate_bp1=bool(cfg_arm["gate_bp1"]),
                        group_fn=group_fn,
                    )

        # Gates and deterministic winner selection
        rqa_list = list(report["chassis_rqa"].values())
        acct_list = list(report["account_replay"].values())
        report["gates"] = {
            "chassis_order_dates": all(r["dates_pass"] for r in rqa_list),
            "chassis_lots_and_capture": all(
                r["fill_capture_pass"] and r["illegal_non_lot_fills"] == 0 for r in rqa_list
            ),
            "chassis_commissions": all(r["fees_pass"] for r in rqa_list),
            "account_zero_violations": all(c["violation_count"] == 0 for c in acct_list),
        }
        require(all(report["gates"].values()), "EXP-V3-11 integrity gate failed")

        b_ch100 = report["chassis_rqa"]["V3_2_1_BASELINE_100000"]["full"]
        g_ch100 = report["chassis_rqa"]["V3_3_0_GRADUAL_100000"]["full"]
        c_ch100 = report["chassis_rqa"]["V3_3_0_CPPI_100000"]["full"]

        b_h69 = report["account_replay"]["HEAVY70_69000_V3_2_1_BASELINE"]["metrics"]["cagr"]
        g_h69 = report["account_replay"]["HEAVY70_69000_V3_3_0_GRADUAL"]["metrics"]["cagr"]
        c_h69 = report["account_replay"]["HEAVY70_69000_V3_3_0_CPPI"]["metrics"]["cagr"]
        b_h100 = report["account_replay"]["HEAVY70_100000_V3_2_1_BASELINE"]["metrics"]["cagr"]
        g_h100 = report["account_replay"]["HEAVY70_100000_V3_3_0_GRADUAL"]["metrics"]["cagr"]
        c_h100 = report["account_replay"]["HEAVY70_100000_V3_3_0_CPPI"]["metrics"]["cagr"]

        g_breach_69 = max(
            report["account_replay"]["CORE25_69000_V3_3_0_GRADUAL"]["breach_days"],
            report["account_replay"]["HEAVY70_69000_V3_3_0_GRADUAL"]["breach_days"],
        )
        c_breach_all = max(
            report["account_replay"][k]["breach_days"]
            for k in report["account_replay"]
            if k.endswith("V3_3_0_CPPI")
        )

        gradual_eligible = (
            g_ch100["max_drawdown"] > -0.15
            and g_ch100["calmar"] >= b_ch100["calmar"]
            and g_h69 > b_h69
            and g_h100 > b_h100
            and g_breach_69 <= 10
            and (g_ch100["cagr"] > c_ch100["cagr"] or g_ch100["calmar"] > c_ch100["calmar"])
        )
        cppi_eligible = (
            c_breach_all == 0
            and c_ch100["calmar"] >= b_ch100["calmar"]
            and c_h69 > b_h69
            and c_h100 > b_h100
        )

        if gradual_eligible:
            winner = "V3_3_0_GRADUAL"
            ctrl_param = "TWO_STAGE_GRADUAL"
            verdict = "V3_3_0_GRADUAL_APPROVED"
        elif cppi_eligible:
            winner = "V3_3_0_CPPI"
            ctrl_param = "CPPI_F15_M5"
            verdict = "V3_3_0_CPPI_APPROVED"
        else:
            winner = "NONE"
            ctrl_param = "NONE"
            verdict = "V3_3_0_NO_DOMINANCE"

        report["selection"] = {
            "winner_arm": winner,
            "drawdown_control_mode": ctrl_param,
            "gradual_eligible": gradual_eligible,
            "cppi_eligible": cppi_eligible,
            "gradual_conc_69k_max_breach_days": g_breach_69,
            "cppi_max_breach_days": c_breach_all,
        }
        report["verdict"] = verdict
    except Exception as exc:
        import traceback

        traceback.print_exc()
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["verdict"] = "INVALID_RUN"

    code = int(report["verdict"] == "INVALID_RUN")
    report.update(finished=utc(), exit_code=code)
    with STEM.with_suffix(".json").open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, allow_nan=False, indent=1)
        f.write("\n")

    lines = [
        "# EXP-V3-11：V3.3.0 五机制联合集成验证与胜率/盈亏比审计",
        "",
        (
            f"裁决：`{report['verdict']}` | 当选风控模式："
            f"`{report['selection'].get('drawdown_control_mode')}`"
        ),
        "",
        "## 1. 全窗底盘 RQAlpha 原生回放（2018-01-02..2026-10-30）",
        "",
        (
            "| 回放 | CAGR | 累计收益 | MaxDD | Sharpe | Sortino | Calmar "
            "| 月胜率 | 年胜率 | FIFO胜率 | 盈亏比 | 盈利因子 | 佣金(元) |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, r in report["chassis_rqa"].items():
        m, rt = r["full"], r["roundtrips"]["overall"]
        wr_s = f"{rt['win_rate']:.1%}" if rt["win_rate"] is not None else "—"
        pr_s = f"{rt['payoff_ratio']:.2f}" if rt["payoff_ratio"] is not None else "—"
        pf_s = f"{rt['profit_factor']:.2f}" if rt["profit_factor"] is not None else "—"
        lines.append(
            f"| {label} | {m['cagr']:.2%} | {m['total_return']:.2%} | {m['max_drawdown']:.2%} "
            f"| {m['sharpe']:.3f} | {m['sortino']:.3f} | {m['calmar']:.3f} "
            f"| {m['monthly_win_rate']:.1%} | {m['annual_win_rate']:.1%} | {wr_s} | {pr_s} "
            f"| {pf_s} | {r['commission_yuan']:.2f} |"
        )
    lines += [
        "",
        (
            "## 2. 统一账户原生回放"
            "（OOS_CASH 2024-02.. / CORE25 & HEAVY70 2024-07..2026-10-30，含 5bp 滑点）"
        ),
        "",
        (
            "| 场景 | CAGR | MaxDD(净) | 真实Peak DD | 穿-15%天 | Sharpe "
            "| 月胜率 | FIFO胜率 | 盈亏比 | 总摩擦(元) |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell, c in report["account_replay"].items():
        m, rt = c["metrics"], c["roundtrips"]["overall"]
        wr_s = f"{rt['win_rate']:.1%}" if rt["win_rate"] is not None else "—"
        pr_s = f"{rt['payoff_ratio']:.2f}" if rt["payoff_ratio"] is not None else "—"
        lines.append(
            f"| {cell} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {-c['true_max_dd']:.2%} "
            f"| {c['breach_days']} | {m['sharpe']:.3f} | {m['monthly_win_rate']:.1%} "
            f"| {wr_s} | {pr_s} | {c['total_friction_yuan']:.2f} |"
        )
    with STEM.with_suffix(".md").open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    sys.stdout.write(f"{report['verdict']}\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
