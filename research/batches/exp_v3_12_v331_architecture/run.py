"""EXP-V3-12 runner: V3.3.1 clean architecture validation (no sector pioneer, stateless glide-path, legacy alignment, shadow B对照)."""

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
from research.ashare.v3_data import rq_to_ts, ts_to_rq
from research.batches.exp_v3_06_defensive_rotation.run import (
    LOW_TICKET_BONDS,
    select_bond_reserve,
)
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
    LOW_VOL_PRIMARY_RQ,
    OOS_CASH_START,
    OOS_CONC_START,
    RQA_END,
    START,
    STRESS_START,
    VBT_END,
    apply_drawdown_overlay_202611,
    build_v3_base_chassis_weights,
    load_sector_pioneer_pool,
    make_group_fn,
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
from research.batches.v3_complexity_hurdle_v2.run import four_sleeves, require, reserve, utc
from tacticore.engines.rqalpha_adapter import build_rqalpha_config
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/EXP_V3_12_V331_ARCHITECTURE"
PROTOCOL = ROOT / "research/batches/exp_v3_12_v331_architecture/PROTOCOL_V1.md"


def select_v331_targets(
    *,
    regime: str,
    style: str,
    occupied_weight: float,
    features: dict[str, Any],
    sector_pool_rq: tuple[str, ...],
    use_lowvol_core: bool,
    use_sector_pioneer: bool,
    bp1_active_budget: bool,
    use_v331_budget_merge: bool = True,
    hold_sticky: bool = True,
    held_mv: dict[str, float] | None = None,
) -> dict[str, float]:
    """Select target equity weights for unified account replay at date T.

    - When use_v331_budget_merge=True and use_sector_pioneer=False, the 20% pioneer budget
      is merged back into the chassis core (OFFENSIVE 85% or 65% w/ BP1; STRUCTURAL 60% or 50% w/ BP1).
    - When hold_sticky=True, currently held valid members in a bucket are retained
      (largest market value first if multiple) before falling back to bucket priority order.
    """

    def valid(c: str) -> bool:
        return c in features and pd.notna(features[c].ma20) and features[c].raw > 0

    def pick_bucket_one(bucket: tuple[str, ...]) -> str | None:
        if hold_sticky and held_mv:
            held_valid = [c for c in bucket if held_mv.get(c, 0.0) > 0 and valid(c)]
            if held_valid:
                return max(held_valid, key=lambda c: (held_mv[c], -bucket.index(c)))
        return next((c for c in bucket if valid(c)), None)

    def pick_lowvol_two() -> list[str]:
        if hold_sticky and held_mv:
            held_valid = sorted(
                [c for c in LOW_VOL_PRIMARY_RQ if held_mv.get(c, 0.0) > 0 and valid(c)],
                key=lambda c: (-held_mv[c], LOW_VOL_PRIMARY_RQ.index(c)),
            )[:2]
            if len(held_valid) == 2:
                return held_valid
            rest = [c for c in LOW_VOL_PRIMARY_RQ if c not in held_valid and valid(c)]
            return (held_valid + rest)[:2]
        return [c for c in LOW_VOL_PRIMARY_RQ if valid(c)][:2]

    budget_map = {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "RECOVERY": 0.40, "DEFENSIVE": 0.15}
    room = max(0.0, budget_map[regime] - occupied_weight)
    out: dict[str, float] = {}

    if regime == "DEFENSIVE":
        if room <= 0:
            return {}
        if use_lowvol_core:
            lv = pick_lowvol_two()
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
        if use_sector_pioneer or not use_v331_budget_merge:
            pioneer_cap = 0.40 if bp1_active_budget else 0.20
            base = min(room, 0.45 if bp1_active_budget else 0.65)
            pioneer_room = max(0.0, min(0.20, room - base, pioneer_cap)) if use_sector_pioneer else 0.0
        else:
            base = min(room, 0.65 if bp1_active_budget else 0.85)
            pioneer_room = 0.0
    else:  # STRUCTURAL
        if use_sector_pioneer or not use_v331_budget_merge:
            pioneer_cap = 0.30 if bp1_active_budget else 0.20
            base = min(room, 0.30 if bp1_active_budget else 0.40)
            pioneer_room = max(0.0, min(0.20, room - base, pioneer_cap)) if use_sector_pioneer else 0.0
        else:
            base = min(room, 0.50 if bp1_active_budget else 0.60)
            pioneer_room = 0.0

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
            val_c = pick_bucket_one(VALUE)
            gro_c = pick_bucket_one(GROWTH)
            lv_cs = pick_lowvol_two()
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
                c = pick_bucket_one(grp)
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


def apply_drawdown_overlay_m2_early_release(
    panels: Any,
    base_weights: pd.DataFrame,
    eff_reg: pd.Series,
    *,
    use_low_ticket_bond: bool,
    end: pd.Timestamp = VBT_END,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """TWO_STAGE_GRADUAL overlay matching apply_drawdown_overlay_202611 verbatim except for
    the single M2 early-release branch (locked >= 5 trading days AND M2 just triggered ->
    early unlock/re-anchor with 20% probe cap for that recovery ramp).
    """
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    adj = panels.etf_adj_close.loc[cal].ffill()
    cols = list(panels.etf_adj_close.columns)
    base_full = base_weights.loc[cal].ffill().fillna(0.0)
    mask = panels.etf_tradability_mask
    rets = adj.pct_change(fill_method=None).fillna(0.0)
    ctrl = DrawdownController(init_nav=1.0, mode="c3_gradual", floor_dd=0.15, cppi_m=5.0)
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
    early_releases = 0
    lock_start_pos = -1000
    early_ramp_until = -1000

    for pos in range(len(cal) - 1):
        sig_dt = cal[pos]
        exec_dt = cal[pos + 1]
        if pos > 0:
            nav *= 1.0 + float((prev_w * rets.loc[sig_dt]).sum())

        base_row = base_full.loc[exec_dt]
        reg_s = str(eff_reg.at[sig_dt])
        base_eq = float(base_row[eq_cols].sum())
        m2_just_triggered = reg_s == "RECOVERY" and prev_reg_s == "DEFENSIVE"

        if pos <= ctrl.until and (pos - lock_start_pos) >= 5 and m2_just_triggered:
            ctrl.until = pos - 1
            early_ramp_until = pos + ctrl.ramp_days
            early_releases += 1

        was_locked = pos <= ctrl.until
        st = ctrl.step(pos, nav, concentrated=False, base_eq_budget=max(base_eq, 0.15))
        if st["trigger"] and not was_locked:
            lock_start_pos = pos

        max_true_dd = max(max_true_dd, float(st["true_dd"]))
        if st["breach"] > 0:
            breach_days += 1

        cap = float(st["buy_cap"])
        if pos <= early_ramp_until and reg_s == "RECOVERY":
            cap = min(cap, 0.20)
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
        "early_releases": early_releases,
    }


def replay_v331_account(
    *,
    days: list[str],
    market: dict[str, tuple[str, str]],
    features: dict[str, dict[str, Any]],
    stock_candidates: dict[str, list[Any]],
    white: set[str],
    sector_pool_rq: tuple[str, ...],
    capital: float,
    seed: float,
    use_sector_pioneer: bool,
    use_deconc_plan: bool,
    align_glide_carryover_w: float | None,
    p1_etf_trailing_sleeves: tuple[str, ...],
    hold_sticky: bool,
    use_stateless_align_due: bool,
    equity_drift_band: float,
    use_v331_budget_merge: bool,
    group_fn: Any = None,
) -> dict[str, Any]:
    """Unified RQAlpha 6.3.0 account replay supporting both V3.3.0 baseline and V3.3.1 clean rules."""
    from rqalpha.api import history_bars, instruments, order_shares, subscribe_event

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

    budget_map = {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "RECOVERY": 0.40, "DEFENSIVE": 0.15}
    ctrl = DrawdownController(init_nav=capital, mode="c3_gradual", floor_dd=0.15, cppi_m=5.0)
    plan = Plan()
    bond_priority = LOW_TICKET_BONDS_RQ
    bond_drift_band = 0.10

    lookup = {d: idx for idx, d in enumerate(days)}
    pending: dict[str, dict[str, Any]] = {}
    retries: dict[str, dict[str, Any]] = {}
    armed: dict[str, bool] = {}
    stock_stops: dict[str, dict[str, Any]] = {}
    state: dict[str, Any] = {"regime": None, "style": None, "align": -100, "locked": False, "active": None}
    rows: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
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
        elif not use_deconc_plan and a["side"] == "SELL" and old["side"] == "SELL" and a["p"] == 4 and old["p"] == 0:
            # Rule 2: merge P0 and P3-SELL into one SELL leg keeping P0 priority & combined reasons
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
        if use_deconc_plan and t.order_book_id == FOCUS:
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
                        elif a["signal"] != "INITIAL" and sym not in BOND_SET_RQ and a.get("eff_cap") is not None:
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
        held_mv = {s: float(p.market_value) for s, p in held.items()}
        pnl: Counter[str] = Counter()
        for s in pp:
            pnl[group_fn(s)] += float(pp[s].daily_pnl)

        focus_w = w.get(FOCUS, 0.0)
        concentrated = (focus_w > 0.30 or any(plan.batches)) if use_deconc_plan else False
        regime, style = market[d]
        risk_row = ctrl.step(i, nav, concentrated=concentrated, base_eq_budget=budget_map[regime])
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
        # Determine target ETF symbol set for legacy/non-target classification
        provisional_t = select_v331_targets(
            regime=regime,
            style=style,
            occupied_weight=0.0,
            features=f,
            sector_pool_rq=sector_pool_rq,
            use_lowvol_core=True,
            use_sector_pioneer=use_sector_pioneer,
            bp1_active_budget=False,
            use_v331_budget_merge=use_v331_budget_merge,
            hold_sticky=hold_sticky,
            held_mv=held_mv,
        )
        non_target_etfs = [s for s in held_risk_etfs if s not in provisional_t]

        # P0: Drawdown controller
        p0_sold_by_sym: dict[str, float] = {}
        cc = risk_row["ctrl_cap"]
        if cc is not None and risk_w > float(cc) + 0.02 and risk_w > 1e-6:
            if not use_deconc_plan:
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
            else:
                for s in held:
                    if s in BOND_SET_RQ:
                        continue
                    new_ws = w[s] * float(cc) / risk_w
                    add(0, s, "CTRL_REDUCE", "SELL", new_ws)
                    p0_sold_by_sym[s] = w[s] - new_ws
        p0_sold_w = sum(p0_sold_by_sym.values())

        # P1: Exits (stocks + allowed trailing ETF sleeves)
        active_stocks: set[str] = set()
        for s, p in held.items():
            if (use_deconc_plan and s == FOCUS) or s in BOND_SET_RQ:
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
            elif s in f:
                allow_etf_p1 = ("ALL" in p1_etf_trailing_sleeves) or (
                    "SECTOR_PIONEER" in p1_etf_trailing_sleeves and s in sector_pool_rq
                )
                if allow_etf_p1:
                    r = f[s]
                    armed[s], why = exit_reason(
                        r.raw, float(p.avg_price), r.raw * r.ma20 / r.c, r.raw * r.ma10 / r.c, armed.get(s, False), l1
                    )
                    if why:
                        add(1, s, why, "SELL", 0.0)

        # P2: 159558.SZ BOTTOM_GRIND_25 (only when use_deconc_plan=True)
        if use_deconc_plan and FOCUS in held and FOCUS in f:
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

        # P3: BP1 stocks (gated >=100k, non-concentrated)
        nt_total_w = sum(w[s] for s in non_target_etfs)
        bp1_permitted = nav >= 100000.0 and (
            (not concentrated) if use_deconc_plan else (nt_total_w <= 0.30)
        )
        stock_buy_budget = 0.0
        kept_stocks = {s for s in active_stocks if pending.get(s, {}).get("side") != "SELL"}
        current_stock_w = sum(w[s] for s in kept_stocks)
        slots_left = max(0, 2 - len(active_stocks))
        eff_cap = float(risk_row["buy_cap"])
        if bp1_permitted and regime in ("OFFENSIVE", "STRUCTURAL") and not locked and not l1 and slots_left > 0:
            focus_committed = (
                max(
                    focus_w,
                    (pending.get(FOCUS, {}).get("w") or 0.0)
                    if pending.get(FOCUS, {}).get("side") == "BUY"
                    else 0.0,
                )
                if use_deconc_plan
                else nt_total_w
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

        # P4: Declarative two-way target alignment
        bond_pick = next((b for b in bond_priority if b in f), "511010.XSHG")
        planned_equity_buy_amt = sum(
            max(0.0, (a.get("w") or 0.0) * nav - (held[a["code"]].market_value if a["code"] in held else 0.0))
            for a in pending.values()
            if a["side"] == "BUY" and a["code"] not in BOND_SET_RQ
        )

        if not locked:
            reg_or_style_changed = (regime != state["regime"]) or (style != state["style"])
            unlocked_today = bool(state["locked"] and not locked)
            p0_triggered = bool(risk_row["trigger"] or p0_sold_w > 0)

            if use_deconc_plan:
                # Exact V3.3.0 P4 alignment
                align = (
                    regime != state["regime"]
                    or unlocked_today
                    or risk_row["trigger"]
                    or i - state["align"] >= 10
                )
                if align:
                    focus_b = max(
                        focus_w,
                        (pending.get(FOCUS, {}).get("w") or 0.0)
                        if pending.get(FOCUS, {}).get("side") == "BUY"
                        else 0.0,
                    )
                    occupied = focus_b + current_stock_w + stock_buy_budget
                    raw_t = select_v331_targets(
                        regime=regime,
                        style=style,
                        occupied_weight=occupied,
                        features=f,
                        sector_pool_rq=sector_pool_rq,
                        use_lowvol_core=True,
                        use_sector_pioneer=use_sector_pioneer,
                        bp1_active_budget=bp1_permitted,
                        use_v331_budget_merge=use_v331_budget_merge,
                        hold_sticky=hold_sticky,
                        held_mv=held_mv,
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
                    if abs(target_bond_w - cur_bond_w) >= bond_drift_band:
                        diff_b = target_bond_w - cur_bond_w
                        if diff_b * nav >= 5000.0 and bond_pick in f:
                            add(5, bond_pick, "BOND_RESERVOIR", "BUY", target_bond_w)
                        elif diff_b < 0:
                            for b in sorted(b for b in held if b in BOND_SET_RQ):
                                add(3, b, "BOND_REDUCE", "SELL", max(0.0, target_bond_w))
                    state["align"] = i
            else:
                # V3.3.1: Stateless 2-day glide-path across ALL non-target/excess risk ETFs + max(P0, glide) + align_due
                cap = align_glide_carryover_w if align_glide_carryover_w is not None else 1.0
                post_p0_w = {s: max(0.0, w[s] - p0_sold_by_sym.get(s, 0.0)) for s in held_risk_etfs}
                for s in held_risk_etfs:
                    if s in pending and pending[s]["p"] == 1:
                        post_p0_w[s] = 0.0
                # Estimate carryover of non_target_etfs for target construction
                nt_p0_sold = sum(p0_sold_by_sym.get(s, 0.0) for s in non_target_etfs)
                if nt_total_w <= cap + 0.02:
                    nt_glide_sell = nt_total_w
                else:
                    nt_glide_sell = max(cap, nt_total_w - cap)
                nt_carryover = max(0.0, nt_total_w - max(nt_p0_sold, nt_glide_sell))
                occupied_for_targets = current_stock_w + stock_buy_budget + nt_carryover

                raw_t = select_v331_targets(
                    regime=regime,
                    style=style,
                    occupied_weight=occupied_for_targets,
                    features=f,
                    sector_pool_rq=sector_pool_rq,
                    use_lowvol_core=True,
                    use_sector_pioneer=use_sector_pioneer,
                    bp1_active_budget=bp1_permitted,
                    use_v331_budget_merge=use_v331_budget_merge,
                    hold_sticky=hold_sticky,
                    held_mv=held_mv,
                )
                tot_raw = sum(raw_t.values())
                max_new_eq = max(0.0, eff_cap - occupied_for_targets)
                scale = min(1.0, max_new_eq / tot_raw) if tot_raw > 1e-9 else 1.0
                scaled_t = {k: v * scale for k, v in raw_t.items() if v * scale > 0.01}

                # Compute total excess pre-P0 across ALL held risk ETFs
                pre_p0_excess = {s: max(0.0, w[s] - scaled_t.get(s, 0.0)) for s in held_risk_etfs}
                total_excess = sum(pre_p0_excess.values())
                desired_glide_sell = (
                    total_excess if total_excess <= cap + 0.02 else max(cap, total_excess - cap)
                )
                rem_p3_sell = max(0.0, desired_glide_sell - p0_sold_w)

                # Distribute rem_p3_sell over post-P0 excess (non-target ETFs first, then overweight target ETFs)
                post_p0_excess = {
                    s: max(0.0, post_p0_w[s] - scaled_t.get(s, 0.0)) for s in held_risk_etfs
                }
                p3_sell_target_w: dict[str, float] = {}
                if rem_p3_sell > 1e-6:
                    # Clean-sweep < 2% dust on non-target ETFs first
                    nt_over = [s for s in non_target_etfs if post_p0_excess[s] > 1e-6]
                    ov_target = [
                        s for s in held_risk_etfs if s not in non_target_etfs and post_p0_excess[s] > 1e-6
                    ]
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

                # Actual post-sell legacy carryover & bond target
                post_sell_nt_w = sum(
                    p3_sell_target_w.get(s, post_p0_w[s]) for s in non_target_etfs
                )
                occupied_final = current_stock_w + stock_buy_budget + post_sell_nt_w
                target_eq_total = max(
                    occupied_final, min(eff_cap, occupied_final + sum(scaled_t.values()))
                )
                target_bond_w = max(0.0, 1.0 - target_eq_total - 0.01)
                cur_bond_w = sum(w.get(b, 0.0) for b in BOND_SET_RQ)
                bond_drift = abs(target_bond_w - cur_bond_w)

                max_target_drift = max(
                    (abs(scaled_t[s] - post_p0_w.get(s, 0.0)) for s in scaled_t),
                    default=0.0,
                )
                has_non_target_risk = any(w[s] > 1e-6 for s in non_target_etfs)
                if use_stateless_align_due:
                    align_due = (
                        has_non_target_risk
                        or reg_or_style_changed
                        or unlocked_today
                        or p0_triggered
                        or max_target_drift >= equity_drift_band
                        or bond_drift >= bond_drift_band
                    )
                else:
                    align_due = (
                        has_non_target_risk
                        or regime != state["regime"]
                        or unlocked_today
                        or risk_row["trigger"]
                        or i - state["align"] >= 10
                    )

                if align_due:
                    # Emit P3-SELL legs (or merge into P0)
                    for s, new_ws in sorted(p3_sell_target_w.items()):
                        if new_ws < post_p0_w[s] - 1e-9:
                            reason = (
                                "REGIME_ALIGN_EXIT"
                                if new_ws <= 1e-9
                                else ("REGIME_ALIGN_GLIDE" if s in non_target_etfs else "ALIGN")
                            )
                            add(4, s, reason, "SELL", new_ws, eff_cap=eff_cap)

                    # Emit P3-BUY legs (only if not sold today and room allows)
                    planned_new_buy_w = 0.0
                    buy_headroom = max(0.0, eff_cap - occupied_final - sum(post_p0_w.get(s, 0.0) for s in scaled_t))
                    for s in sorted(scaled_t):
                        if s in p3_sell_target_w or s in p0_sold_by_sym or s in pending:
                            continue
                        wt = scaled_t[s]
                        cur_s = w.get(s, 0.0)
                        diff = wt - cur_s
                        if diff <= 1e-6:
                            continue
                        if cur_s > 0 and not (reg_or_style_changed or unlocked_today or p0_triggered) and diff < equity_drift_band:
                            continue
                        if diff * nav < (1000.0 if s in white else 5000.0):
                            continue
                        if buy_headroom <= 1e-6:
                            continue
                        eff_wt = min(wt, cur_s + buy_headroom)
                        eff_diff = eff_wt - cur_s
                        if eff_diff * nav < (1000.0 if s in white else 5000.0):
                            continue
                        add(4, s, "ALIGN", "BUY", eff_wt, regime=regime, eff_cap=eff_cap)
                        planned_equity_buy_amt += eff_diff * nav
                        planned_new_buy_w += eff_diff
                        buy_headroom = max(0.0, buy_headroom - eff_diff)

                    if bond_drift >= bond_drift_band:
                        diff_b = target_bond_w - cur_bond_w
                        if diff_b * nav >= 5000.0 and bond_pick in f:
                            add(5, bond_pick, "BOND_RESERVOIR", "BUY", target_bond_w, regime=regime)
                        elif diff_b < 0:
                            for b in sorted(b for b in held if b in BOND_SET_RQ):
                                add(3, b, "BOND_REDUCE", "SELL", max(0.0, target_bond_w))
                    state["align"] = i

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

        state.update(regime=regime, style=style, locked=locked)

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
        "reject_count": len(rejects),
        "violation_count": len(violations),
        "violations": violations,
    }


def main() -> int:
    reserve(STEM)
    report: dict[str, Any] = {
        "started": utc(),
        "runner_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
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

        overlaid_w: dict[str, pd.DataFrame] = {}
        eff_reg_by_arm: dict[str, pd.Series] = {}

        # 1) V3.3.0 (with pioneer), V3.3.1 Clean (no pioneer), V3.3.1 M2 Early Release
        for name, use_pioneer, early_m2 in (
            ("V3_3_0_WITH_PIONEER", True, False),
            ("V3_3_1_CLEAN_NO_PIONEER", False, False),
            ("V3_3_1_M2_EARLY_RELEASE", False, True),
        ):
            base_w, eff_reg, rec_stats = build_v3_base_chassis_weights(
                p,
                reg,
                sector_pool_ts=sector_pool_ts,
                use_recovery=True,
                use_lowvol_core=True,
                use_low_ticket_bond=True,
                use_sector_pioneer=use_pioneer,
                end=VBT_END,
            )
            eff_reg_by_arm[name] = eff_reg
            if early_m2:
                ow, ctrl_info = apply_drawdown_overlay_m2_early_release(
                    p, base_w, eff_reg, use_low_ticket_bond=True, end=VBT_END
                )
            else:
                ow, ctrl_info = apply_drawdown_overlay_202611(
                    p, base_w, eff_reg, ctrl_mode="c3_gradual", use_low_ticket_bond=True, end=VBT_END
                )
            overlaid_w[name] = ow
            prices, mask, targets_df = (f.loc[:VBT_END] for f in (p.etf_adj_close, p.etf_tradability_mask, ow))
            validate_execution_targets(targets_df, prices, mask, p.etf_lifetimes)
            rates = np.array([SUPER if c in prov.super_etf_codes else NORMAL for c in ow.columns])[None, :]
            eq = run_target_weights(
                prices, targets_df, fees=rates, slippage=0.0002, initial_cash=100000.0,
                metric_start=START, tradability_mask=mask, lifetimes=p.etf_lifetimes,
            ).equity.loc[START:VBT_END]
            report["vbt"][name] = {
                "recovery_stats": rec_stats,
                "ctrl": ctrl_info,
                "full_2018_20261126": compute_calendar_stats(eq),
                "is_2018_2023": compute_calendar_stats(eq.loc[: data.IS_END]),
                "oos_2024_20261126": compute_calendar_stats(eq.loc[data.IS_END :]),
                "stress_202607_20261126": compute_calendar_stats(eq.loc[STRESS_START:]),
            }

        # 2) Shadow B (Static 4-sleeve) and Shadow B + TWO_STAGE_GRADUAL
        b_raw = four_sleeves(p, erc=False, start=START, end=VBT_END)
        b_grad, b_ctrl = apply_drawdown_overlay_202611(
            p, b_raw, reg["confirmed_regime"].astype(str), ctrl_mode="c3_gradual", use_low_ticket_bond=False, end=VBT_END
        )
        for name, ow, ci in (
            ("SHADOW_B_STATIC_4SLEEVE", b_raw, {"locks": 0, "relock_loops": 0}),
            ("SHADOW_B_GRADUAL", b_grad, b_ctrl),
        ):
            overlaid_w[name] = ow
            prices, mask, targets_df = (f.loc[:VBT_END] for f in (p.etf_adj_close, p.etf_tradability_mask, ow))
            validate_execution_targets(targets_df, prices, mask, p.etf_lifetimes)
            rates = np.array([SUPER if c in prov.super_etf_codes else NORMAL for c in ow.columns])[None, :]
            eq = run_target_weights(
                prices, targets_df, fees=rates, slippage=0.0002, initial_cash=100000.0,
                metric_start=START, tradability_mask=mask, lifetimes=p.etf_lifetimes,
            ).equity.loc[START:VBT_END]
            report["vbt"][name] = {
                "ctrl": ci,
                "full_2018_20261126": compute_calendar_stats(eq),
                "is_2018_2023": compute_calendar_stats(eq.loc[: data.IS_END]),
                "oos_2024_20261126": compute_calendar_stats(eq.loc[data.IS_END :]),
                "stress_202607_20261126": compute_calendar_stats(eq.loc[STRESS_START:]),
            }

        # 3) Full-window RQAlpha chassis replay (2018-01-02..2026-10-30) @ ¥69k & ¥100k
        for cash in CASH:
            for name in overlaid_w:
                label = f"{name}_{cash}"
                sys.stdout.write(f"{utc()} chassis {label}\n")
                sys.stdout.flush()
                eq, run = replay(overlaid_w[name], cash, prov.super_etf_codes, True, start=START, end=RQA_END)
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

        # 4) Unified account replays (OOS_CASH, CORE25, LEGACY70_ALIGN)
        codes_rq = sorted({FOCUS, GOLD, *VALUE, *GROWTH, *LOW_VOL_PRIMARY_RQ, *LOW_TICKET_BONDS_RQ, *sector_pool_rq})
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
                rq: row for rq, df in feat_dfs.items() for row in [df.loc[dt]]
                if pd.notna(row["c"]) and pd.notna(row["raw"]) and float(row["raw"]) > 0
            }
        white_rq = {ts_to_rq(c) for c in prov.super_etf_codes}
        stock_cands, _ = build_causal_bp1_candidates_202611(oos_start=OOS_CASH_START, bundle_end=RQA_END)
        cal_rqa = p.calendar[p.calendar <= RQA_END]
        days_cash = [str(d.date()) for d in cal_rqa[cal_rqa >= OOS_CASH_START]]
        days_conc = [str(d.date()) for d in cal_rqa[cal_rqa >= OOS_CONC_START]]

        market_v330 = {str(dt.date()): (str(eff_reg_by_arm["V3_3_0_WITH_PIONEER"].at[dt]), str(reg.at[dt, "style"])) for dt in p.calendar}
        market_v331 = {str(dt.date()): (str(eff_reg_by_arm["V3_3_1_CLEAN_NO_PIONEER"].at[dt]), str(reg.at[dt, "style"])) for dt in p.calendar}

        for scenario, s_days, seed in (("OOS_CASH", days_cash, 0.0), ("CORE25", days_conc, 0.25)):
            for cash in CASH:
                cell_v330 = f"{scenario}_{cash}_V3_3_0_WITH_PIONEER"
                sys.stdout.write(f"{utc()} acct {cell_v330}\n")
                sys.stdout.flush()
                report["account_replay"][cell_v330] = replay_v331_account(
                    days=s_days,
                    market=market_v330,
                    features=features,
                    stock_candidates=stock_cands,
                    white=white_rq,
                    sector_pool_rq=sector_pool_rq,
                    capital=float(cash),
                    seed=seed,
                    use_sector_pioneer=True,
                    use_deconc_plan=True,
                    align_glide_carryover_w=None,
                    p1_etf_trailing_sleeves=("ALL",),
                    hold_sticky=False,
                    use_stateless_align_due=False,
                    equity_drift_band=0.0,
                    use_v331_budget_merge=False,
                    group_fn=group_fn,
                )
                cell_v331 = f"{scenario}_{cash}_V3_3_1_CLEAN_NO_PIONEER"
                sys.stdout.write(f"{utc()} acct {cell_v331}\n")
                sys.stdout.flush()
                report["account_replay"][cell_v331] = replay_v331_account(
                    days=s_days,
                    market=market_v331,
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
                    hold_sticky=True,
                    use_stateless_align_due=True,
                    equity_drift_band=0.05,
                    use_v331_budget_merge=True,
                    group_fn=group_fn,
                )

        # LEGACY70: V3.3.0 (with BOTTOM_GRIND_25 + pioneer) vs V3.3.1 (deconc cancelled + stateless 35% glide-path + no pioneer)
        for cash in CASH:
            cell_old = f"LEGACY70_{cash}_V3_3_0_GRIND25"
            sys.stdout.write(f"{utc()} acct {cell_old}\n")
            sys.stdout.flush()
            report["account_replay"][cell_old] = replay_v331_account(
                days=days_conc,
                market=market_v330,
                features=features,
                stock_candidates=stock_cands,
                white=white_rq,
                sector_pool_rq=sector_pool_rq,
                capital=float(cash),
                seed=0.70,
                use_sector_pioneer=True,
                use_deconc_plan=True,
                align_glide_carryover_w=None,
                p1_etf_trailing_sleeves=("ALL",),
                hold_sticky=False,
                use_stateless_align_due=False,
                equity_drift_band=0.0,
                use_v331_budget_merge=False,
                group_fn=group_fn,
            )
            cell_new = f"LEGACY70_{cash}_V3_3_1_ALIGN_GLIDE"
            sys.stdout.write(f"{utc()} acct {cell_new}\n")
            sys.stdout.flush()
            report["account_replay"][cell_new] = replay_v331_account(
                days=days_conc,
                market=market_v331,
                features=features,
                stock_candidates=stock_cands,
                white=white_rq,
                sector_pool_rq=sector_pool_rq,
                capital=float(cash),
                seed=0.70,
                use_sector_pioneer=False,
                use_deconc_plan=False,
                align_glide_carryover_w=0.35,
                p1_etf_trailing_sleeves=("SECTOR_PIONEER",),
                hold_sticky=True,
                use_stateless_align_due=True,
                equity_drift_band=0.05,
                use_v331_budget_merge=True,
                group_fn=group_fn,
            )

        rqa_list = list(report["chassis_rqa"].values())
        acct_list = list(report["account_replay"].values())
        report["gates"] = {
            "chassis_order_dates": all(r["dates_pass"] for r in rqa_list),
            "chassis_lots_and_capture": all(r["fill_capture_pass"] and r["illegal_non_lot_fills"] == 0 for r in rqa_list),
            "chassis_commissions": all(r["fees_pass"] for r in rqa_list),
            "account_zero_violations": all(c["violation_count"] == 0 for c in acct_list),
        }
        require(all(report["gates"].values()), "EXP-V3-12 integrity gate failed")

        c_clean_69 = report["chassis_rqa"]["V3_3_1_CLEAN_NO_PIONEER_69000"]["full"]
        c_clean_100 = report["chassis_rqa"]["V3_3_1_CLEAN_NO_PIONEER_100000"]["full"]
        c_m2_100 = report["chassis_rqa"]["V3_3_1_M2_EARLY_RELEASE_100000"]["full"]
        m2_early_justified = (
            c_m2_100["calmar"] >= c_clean_100["calmar"] + 0.02
            and c_m2_100["max_drawdown"] >= c_clean_100["max_drawdown"]
        )
        acct_pairs = [
            (
                f"{scen}_{cash}",
                report["account_replay"][f"{scen}_{cash}_{old_s}"],
                report["account_replay"][f"{scen}_{cash}_{new_s}"],
            )
            for scen, old_s, new_s in (
                ("OOS_CASH", "V3_3_0_WITH_PIONEER", "V3_3_1_CLEAN_NO_PIONEER"),
                ("CORE25", "V3_3_0_WITH_PIONEER", "V3_3_1_CLEAN_NO_PIONEER"),
                ("LEGACY70", "V3_3_0_GRIND25", "V3_3_1_ALIGN_GLIDE"),
            )
            for cash in CASH
        ]
        calmar_ge_count = sum(
            1 for _, old_r, new_r in acct_pairs if new_r["metrics"]["calmar"] >= old_r["metrics"]["calmar"]
        )
        friction_le_count = sum(
            1 for _, old_r, new_r in acct_pairs if new_r["total_friction_yuan"] <= old_r["total_friction_yuan"]
        )
        calmar_or_friction_count = sum(
            1
            for _, old_r, new_r in acct_pairs
            if (
                new_r["metrics"]["calmar"] >= old_r["metrics"]["calmar"]
                or new_r["total_friction_yuan"] <= old_r["total_friction_yuan"]
            )
        )
        leg_old_69 = report["account_replay"]["LEGACY70_69000_V3_3_0_GRIND25"]
        leg_new_69 = report["account_replay"]["LEGACY70_69000_V3_3_1_ALIGN_GLIDE"]
        v331_approved = (
            c_clean_69["max_drawdown"] > -0.15
            and c_clean_100["max_drawdown"] > -0.15
            and calmar_or_friction_count >= 4
            and leg_new_69["breach_days"] <= 5
            and leg_new_69["true_max_dd"] <= leg_old_69["true_max_dd"] + 1e-6
        )
        report["selection"] = {
            "v331_clean_approved": v331_approved,
            "l2_lock_allow_m2_early_release": m2_early_justified,
            "acct_calmar_ge_v330_count": calmar_ge_count,
            "acct_friction_le_v330_count": friction_le_count,
            "acct_calmar_or_friction_ge_count": calmar_or_friction_count,
            "legacy70_69k_breach_days": leg_new_69["breach_days"],
            "legacy70_69k_true_max_dd_v331": round(leg_new_69["true_max_dd"], 4),
            "legacy70_69k_true_max_dd_v330": round(leg_old_69["true_max_dd"], 4),
            "m2_early_releases_vbt": report["vbt"]["V3_3_1_M2_EARLY_RELEASE"]["ctrl"]["early_releases"],
        }
        report["verdict"] = "V3_3_1_CLEAN_APPROVED" if v331_approved else "V3_3_1_NEEDS_REVIEW"
    except Exception as exc:
        import traceback
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        report["verdict"] = "ERROR"
    finally:
        report["finished"] = utc()
        report["exit_code"] = 0 if report.get("verdict") == "V3_3_1_CLEAN_APPROVED" else 1
        STEM.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if report.get("verdict") != "ERROR":
            lines = [
                "# EXP-V3-12：V3.3.1 精简架构与简单基准全口径对照",
                "",
                f"裁决：`{report['verdict']}` | `l2_lock_allow_m2_early_release`：`{report['selection']['l2_lock_allow_m2_early_release']}`",
                "",
                "## 1. 全窗 VBT 分段审计（IS 2018-2023 vs OOS 2024-2026-11-26 vs 2026 H2 深熊）",
                "",
                "| Arm | Full CAGR / DD / Calmar | IS(18-23) CAGR / DD | OOS(24-26) CAGR / DD / Calmar | 2026 H2 熊市 |",
                "|---|---:|---:|---:|---:|",
            ]
            for arm, blk in report["vbt"].items():
                f, is_, oos, st = blk["full_2018_20261126"], blk["is_2018_2023"], blk["oos_2024_20261126"], blk["stress_202607_20261126"]
                cal_f = f"{f['calmar']:.3f}" if f.get("calmar") is not None else "—"
                cal_o = f"{oos['calmar']:.3f}" if oos.get("calmar") is not None else "—"
                lines.append(
                    f"| {arm} | {f['cagr']:.2%} / {f['max_drawdown']:.2%} / {cal_f} "
                    f"| {is_['cagr']:.2%} / {is_['max_drawdown']:.2%} "
                    f"| {oos['cagr']:.2%} / {oos['max_drawdown']:.2%} / {cal_o} "
                    f"| {st['total_return']:.2%} |"
                )
            lines += [
                "",
                "## 2. 全窗底盘 RQAlpha 6.3.0 原生回放（2018-01-02..2026-10-30）",
                "",
                "| 回放 | Full CAGR | IS CAGR | OOS CAGR | MaxDD | Sharpe | Calmar | 笔数 | 佣金(元) |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for label, r in report["chassis_rqa"].items():
                f, is_, oos = r["full"], r["is"], r["oos"]
                lines.append(
                    f"| {label} | {f['cagr']:.2%} | {is_['cagr']:.2%} | {oos['cagr']:.2%} "
                    f"| {f['max_drawdown']:.2%} | {f['sharpe']:.3f} | {f['calmar']:.3f} "
                    f"| {r['trade_count']} | {r['commission_yuan']:.2f} |"
                )
            lines += [
                "",
                "## 3. 统一账户原生回放（2024-02/07..2026-10-30，含 5bp 滑点，补全 CORE25_100000）",
                "",
                "| 场景 | CAGR(净) | MaxDD(净) | 真实Peak DD | 穿-15%天 | Sharpe | 月胜率 | FIFO胜率 / 盈亏比 | 摩擦(元) |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for cell, r in report["account_replay"].items():
                m, rt = r["metrics"], r["roundtrips"]["overall"]
                wr_s = f"{rt['win_rate']:.1%}" if rt["win_rate"] is not None else "—"
                pr_s = f"{rt['payoff_ratio']:.2f}" if rt["payoff_ratio"] is not None else "—"
                lines.append(
                    f"| {cell} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {-r['true_max_dd']:.2%} "
                    f"| {r['breach_days']} | {m['sharpe']:.3f} | {m['monthly_win_rate']:.1%} "
                    f"| {wr_s} / {pr_s} | {r['total_friction_yuan']:.2f} |"
                )
            STEM.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
