"""Pure deterministic v3.3.1 daily decision reference for cross-repo parity conformance.

Implements the v3.3.1 Execution Architecture v2 daily close decision semantics:
- Unconditional 1+1+2 chassis selection via ``select_v331_targets_upward_sticky``
- Declarative target weights (``occupied_weight=0.0`` scaled by ``eff_cap / base_budget``)
- P0 drawdown trim (non-target legacy first, dust <2% clean-sweep, then proportional in-target)
- P1 ETF trailing scoped to ``SECTOR_PIONEER`` only (dormant in v3.3.1; no ETF -8% hard stop)
- Stateless P3-SELL 2-day glide-path (``cap=0.35``, ``max(P0, glide)``, <2% non-target clean-sweep)
- P3-BUY headroom computed strictly against **post-P3-SELL** risk equity (coordinator #21 ruling,
  aligned with ``FinanceMCP/actionEngine.ts`` workingQty) and ``post_buy_risk <= eff_cap``
- Bidirectional ``align_due`` and 100-share integer lot sizing / super-ETF vs normal-ETF min tickets
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import floor, isfinite
from typing import Any

from research.ashare.v3_data import WHITELIST_PATH, rq_to_ts, ts_to_rq
from research.batches.exp_v3_06_defensive_rotation.run import LOW_TICKET_BONDS
from research.batches.exp_v3_11_v330_integration.run import BOND_SET_TS
from research.batches.exp_v3_12_v331_architecture.run_r2 import select_v331_targets_upward_sticky

BUDGET_MAP: dict[str, float] = {
    "OFFENSIVE": 0.85,
    "STRUCTURAL": 0.60,
    "RECOVERY": 0.40,
    "DEFENSIVE": 0.15,
}
GLIDE_CAP_W = 0.35
DUST_DEADBAND_W = 0.02
EQUITY_DRIFT_BAND_W = 0.05
BOND_DRIFT_BAND_W = 0.10


@dataclass(frozen=True)
class _Feat:
    raw: float
    ma20: float
    c: float = 0.0
    ma60: float = float("nan")
    ret20: float = 0.0
    ret60: float = 0.0


def load_super_etf_codes() -> frozenset[str]:
    wl = json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))
    return frozenset(str(entry["ts_code"]) for entry in wl["entries"])


def _floor_lots(shares: float) -> int:
    if not isfinite(shares) or shares + 1e-9 < 100.0:
        return 0
    return int(floor((shares + 1e-9) / 100.0)) * 100


def _effective_caps(regime: str, drawdown: dict[str, Any]) -> tuple[float | None, float, bool]:
    """Return ``(ctrl_cap, eff_buy_cap, locked)`` mirroring c3_gradual / strategyRouter."""
    base_eq = BUDGET_MAP[regime]
    locked = bool(drawdown["locked"])
    if locked:
        return 0.10, 0.10, True
    dd = float(drawdown["work_dd_bps"]) / 10000.0
    if dd + 1e-12 >= 0.11:
        ctrl_cap: float | None = 0.25
    elif dd + 1e-12 >= 0.08:
        ctrl_cap = 0.50
    else:
        ctrl_cap = None
    eff_cap = base_eq
    if ctrl_cap is not None:
        eff_cap = min(eff_cap, ctrl_cap)
    ramp_factor = float(drawdown.get("ramp_factor_bps", 10000)) / 10000.0
    if ramp_factor < 1.0 - 1e-9:
        eff_cap = min(eff_cap, base_eq * ramp_factor)
    return ctrl_cap, eff_cap, False


def _merge_sell_order(
    orders: dict[str, dict[str, Any]],
    *,
    code: str,
    stage: int,
    reason: str,
    target_w: float,
    qty: int,
    sellable: int,
) -> None:
    if qty <= 0:
        return
    capped_qty = min(qty, _floor_lots(float(sellable)))
    if capped_qty < 100:
        return
    old = orders.get(code)
    if old is None:
        orders[code] = {
            "code": code,
            "side": "SELL",
            "stage": stage,
            "reason": reason,
            "target_weight_bps": round(target_w * 10000.0),
            "qty": capped_qty,
        }
        return
    merged_stage = min(int(old["stage"]), stage)
    merged_reason = old["reason"] if reason in old["reason"] else f"{old['reason']}+{reason}"
    orders[code] = {
        "code": code,
        "side": "SELL",
        "stage": merged_stage,
        "reason": merged_reason,
        "target_weight_bps": round(target_w * 10000.0),
        "qty": capped_qty,
    }


def evaluate_v331_decision(scenario: dict[str, Any]) -> dict[str, Any]:
    """Compute expected v3.3.1 decision output for one parity fixture scenario."""
    regime = str(scenario["regime"])
    style = str(scenario["style"])
    prev_regime = str(scenario.get("prev_regime", regime))
    prev_style = str(scenario.get("prev_style", style))
    drawdown = scenario["drawdown"]
    ctrl_cap, eff_cap, locked = _effective_caps(regime, drawdown)

    if not scenario.get("quote_ready", True):
        return {
            "align_due": False,
            "router_effective_cap_bps": round(eff_cap * 10000.0),
            "target_weights_bps": {},
            "target_bond_bps": 0,
            "actions_by_code": {},
            "orders": [],
            "post_buy_risk_bps": 0,
        }

    nav = float(scenario["investable_nav_cny"])
    cash = float(scenario["cash_cny"])
    market = scenario["market"]
    super_set = load_super_etf_codes()

    held_qty: dict[str, int] = {}
    sellable_qty: dict[str, int] = {}
    held_mv: dict[str, float] = {}
    w: dict[str, float] = {}
    for pos in scenario["positions"]:
        code = str(pos["code"])
        qty = int(pos["qty"])
        if qty <= 0:
            continue
        px = float(pos["price"])
        mv = qty * px
        held_qty[code] = qty
        sellable_qty[code] = int(pos.get("sellable", qty))
        held_mv[code] = mv
        w[code] = mv / nav

    features_rq: dict[str, _Feat] = {}
    for code, info in market.items():
        px = info.get("price")
        ma20 = info.get("ma20")
        if px is None or float(px) <= 0:
            continue
        buy_blocked = bool(info.get("buy_blocked", False))
        ma20_val = float("nan") if (buy_blocked or ma20 is None) else float(ma20)
        features_rq[ts_to_rq(code)] = _Feat(raw=float(px), ma20=ma20_val, c=float(px))

    held_mv_rq = {ts_to_rq(code): mv for code, mv in held_mv.items()}
    raw_t_rq = select_v331_targets_upward_sticky(
        regime=regime,
        style=style,
        occupied_weight=0.0,
        features=features_rq,
        sector_pool_rq=(),
        use_lowvol_core=True,
        use_sector_pioneer=False,
        bp1_active_budget=False,
        use_v331_budget_merge=True,
        sticky_mode="upward",
        held_mv=held_mv_rq,
    )
    raw_t = {rq_to_ts(rq): wt for rq, wt in raw_t_rq.items()}
    base_budget = BUDGET_MAP[regime]
    scale = min(1.0, eff_cap / base_budget) if base_budget > 1e-9 else 1.0
    scaled_t = {code: wt * scale for code, wt in raw_t.items() if wt * scale > 0.01}

    held_risk_etfs = [code for code in held_qty if code not in BOND_SET_TS]
    non_target_etfs = [code for code in held_risk_etfs if code not in scaled_t]
    risk_w = sum(w[code] for code in held_risk_etfs)

    # P0: Drawdown controller trim (non-target legacy first, then proportional in-target)
    p0_sold_by_sym: dict[str, float] = {}
    p0_target_w: dict[str, float] = {}
    if ctrl_cap is not None and risk_w > ctrl_cap + DUST_DEADBAND_W and risk_w > 1e-6:
        need_cut_w = risk_w - ctrl_cap
        nt_w = sum(w[s] for s in non_target_etfs)
        if nt_w > 1e-6 and need_cut_w > 1e-6:
            cut_nt = min(nt_w, need_cut_w)
            keep_nt_ratio = max(0.0, 1.0 - cut_nt / nt_w)
            for s in non_target_etfs:
                new_ws = w[s] * keep_nt_ratio
                if new_ws < DUST_DEADBAND_W:
                    new_ws = 0.0
                if new_ws < w[s] - 1e-9:
                    p0_sold_by_sym[s] = w[s] - new_ws
                    p0_target_w[s] = new_ws
            need_cut_w = max(0.0, risk_w - ctrl_cap - sum(p0_sold_by_sym.values()))
        rem_risk = [s for s in held_risk_etfs if s not in non_target_etfs]
        rem_w = sum(w[s] for s in rem_risk)
        if need_cut_w > 1e-6 and rem_w > 1e-6:
            keep_ratio = max(0.0, 1.0 - need_cut_w / rem_w)
            for s in rem_risk:
                new_ws = w[s] * keep_ratio
                if new_ws < w[s] - 1e-9:
                    p0_sold_by_sym[s] = w[s] - new_ws
                    p0_target_w[s] = new_ws
    p0_sold_w = sum(p0_sold_by_sym.values())

    orders: dict[str, dict[str, Any]] = {}
    for s, new_ws in sorted(p0_target_w.items()):
        px = float(market[s]["price"])
        desired = (
            held_qty[s]
            if new_ws <= 1e-9
            else _floor_lots(max(0.0, held_qty[s] - new_ws * nav / px))
        )
        reason = "CTRL_REDUCE_LEGACY" if s in non_target_etfs else "CTRL_REDUCE"
        _merge_sell_order(
            orders,
            code=s,
            stage=0,
            reason=reason,
            target_w=new_ws,
            qty=desired,
            sellable=sellable_qty[s],
        )

    align_due = False
    target_bond_w = max(0.0, 1.0 - eff_cap - 0.01) if locked else 0.0
    post_sell_w = dict(w)
    for s in p0_target_w:
        if s in orders:
            px = float(market[s]["price"])
            post_sell_w[s] = max(0.0, (held_qty[s] - orders[s]["qty"]) * px / nav)

    if not locked:
        reg_or_style_changed = (regime != prev_regime) or (style != prev_style)
        unlocked_today = bool(drawdown.get("unlocked_today", False))
        p0_triggered = bool(drawdown.get("trigger", False) or p0_sold_w > 0)
        post_p0_w = {s: max(0.0, w[s] - p0_sold_by_sym.get(s, 0.0)) for s in held_risk_etfs}

        pre_p0_excess = {s: max(0.0, w[s] - scaled_t.get(s, 0.0)) for s in held_risk_etfs}
        total_excess = sum(pre_p0_excess.values())
        desired_glide_sell = (
            total_excess
            if total_excess <= GLIDE_CAP_W + DUST_DEADBAND_W
            else max(GLIDE_CAP_W, total_excess - GLIDE_CAP_W)
        )
        rem_p3_sell = max(0.0, desired_glide_sell - p0_sold_w)

        post_p0_excess = {s: max(0.0, post_p0_w[s] - scaled_t.get(s, 0.0)) for s in held_risk_etfs}
        p3_sell_target_w: dict[str, float] = {}
        if rem_p3_sell > 1e-6:
            nt_over = [s for s in non_target_etfs if post_p0_excess[s] > 1e-6]
            ov_target = [
                s
                for s in held_risk_etfs
                if s not in non_target_etfs and post_p0_excess[s] > 1e-6
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
                    if s in non_target_etfs and new_ws < DUST_DEADBAND_W:
                        new_ws = 0.0
                    p3_sell_target_w[s] = new_ws
                rem_p3_sell = max(0.0, rem_p3_sell - sell_from_grp)

        post_sell_nt_w = sum(p3_sell_target_w.get(s, post_p0_w[s]) for s in non_target_etfs)
        target_eq_total = max(post_sell_nt_w, min(eff_cap, post_sell_nt_w + sum(scaled_t.values())))
        target_bond_w = max(0.0, 1.0 - target_eq_total - 0.01)
        cur_bond_w = sum(w.get(b, 0.0) for b in BOND_SET_TS)
        bond_drift = abs(target_bond_w - cur_bond_w)
        max_target_drift = max(
            (abs(scaled_t[s] - post_p0_w.get(s, 0.0)) for s in scaled_t), default=0.0
        )
        has_non_target_risk = any(w[s] > 1e-6 for s in non_target_etfs)

        align_due = bool(
            has_non_target_risk
            or reg_or_style_changed
            or unlocked_today
            or p0_triggered
            or max_target_drift >= EQUITY_DRIFT_BAND_W
            or bond_drift >= BOND_DRIFT_BAND_W
        )

        if align_due:
            for s, new_ws in sorted(p3_sell_target_w.items()):
                if new_ws < post_p0_w[s] - 1e-9:
                    px = float(market[s]["price"])
                    desired = (
                        held_qty[s]
                        if new_ws <= 1e-9
                        else _floor_lots(max(0.0, held_qty[s] - new_ws * nav / px))
                    )
                    reason = (
                        "REGIME_ALIGN_EXIT"
                        if new_ws <= 1e-9
                        else ("REGIME_ALIGN_GLIDE" if s in non_target_etfs else "ALIGN")
                    )
                    _merge_sell_order(
                        orders,
                        code=s,
                        stage=4,
                        reason=reason,
                        target_w=new_ws,
                        qty=desired,
                        sellable=sellable_qty[s],
                    )
                    if s in orders:
                        post_sell_w[s] = max(0.0, (held_qty[s] - orders[s]["qty"]) * px / nav)

            # Stage 3 bond reduce runs before stage 4 buys so T+0 bond proceeds fund buys
            bond_pick = next(
                (b for b in LOW_TICKET_BONDS if b in market and market[b].get("price")),
                "511010.SH",
            )
            diff_b = target_bond_w - cur_bond_w
            if bond_drift >= BOND_DRIFT_BAND_W and diff_b < 0:
                for b in sorted(b for b in held_qty if b in BOND_SET_TS):
                    px_b = float(market[b]["price"])
                    desired = _floor_lots(max(0.0, held_qty[b] - target_bond_w * nav / px_b))
                    _merge_sell_order(
                        orders,
                        code=b,
                        stage=3,
                        reason="BOND_REDUCE",
                        target_w=max(0.0, target_bond_w),
                        qty=desired,
                        sellable=sellable_qty[b],
                    )

            est_sell_cash = sum(
                o["qty"] * float(market[o["code"]]["price"])
                for o in orders.values()
                if o["side"] == "SELL"
            )
            working_cash = cash + est_sell_cash
            post_sell_total_risk = sum(post_sell_w.get(s, 0.0) for s in held_risk_etfs)
            buy_headroom = max(0.0, eff_cap - post_sell_total_risk)
            allow_sub_band = reg_or_style_changed or unlocked_today or p0_triggered

            def _buy_candidate(sym: str, room_w: float) -> tuple[float, float, float] | None:
                if sym in p3_sell_target_w or sym in p0_sold_by_sym or sym in orders:
                    return None
                if bool(market.get(sym, {}).get("buy_blocked", False)):
                    return None
                cur_s = w.get(sym, 0.0)
                diff = scaled_t[sym] - cur_s
                if diff <= 1e-6 or room_w <= 1e-6:
                    return None
                if cur_s > 0 and not allow_sub_band and diff < EQUITY_DRIFT_BAND_W:
                    return None
                is_super = bool(market[sym].get("is_super_etf", sym in super_set))
                min_ticket = 1000.0 if is_super else 5000.0
                if diff * nav < min_ticket:
                    return None
                eff_wt = min(scaled_t[sym], cur_s + room_w)
                eff_diff = eff_wt - cur_s
                if eff_diff * nav < min_ticket:
                    return None
                return eff_wt, eff_diff, min_ticket

            # Pre-check cash shortfall; sell excess bond funding if >=5000 CNY
            intended_buy_amt = 0.0
            sim_room = buy_headroom
            for s in sorted(scaled_t):
                cand = _buy_candidate(s, sim_room)
                if cand is not None:
                    _, eff_diff, _ = cand
                    intended_buy_amt += eff_diff * nav
                    sim_room = max(0.0, sim_room - eff_diff)

            shortfall = intended_buy_amt * 1.01 - working_cash
            if shortfall >= 5000.0:
                for b in sorted(b for b in held_qty if b in BOND_SET_TS):
                    if shortfall < 1000.0 or b in orders:
                        continue
                    px_b = float(market[b]["price"])
                    sell_lots = min(
                        _floor_lots(float(sellable_qty[b])),
                        _floor_lots(shortfall / px_b + 99.0),
                    )
                    if sell_lots * px_b >= 5000.0:
                        _merge_sell_order(
                            orders,
                            code=b,
                            stage=3,
                            reason="BOND_FUNDING",
                            target_w=max(0.0, (held_qty[b] - sell_lots) * px_b / nav),
                            qty=sell_lots,
                            sellable=sellable_qty[b],
                        )
                        working_cash += sell_lots * px_b
                        shortfall -= sell_lots * px_b

            for s in sorted(scaled_t):
                cand = _buy_candidate(s, buy_headroom)
                if cand is None:
                    continue
                eff_wt, eff_diff, min_ticket = cand
                px = float(market[s]["price"])
                max_buy_amt = min(eff_diff * nav, working_cash * 0.996)
                lots = _floor_lots(max_buy_amt / px)
                if lots < 100 or lots * px < min_ticket:
                    continue
                orders[s] = {
                    "code": s,
                    "side": "BUY",
                    "stage": 4,
                    "reason": "ALIGN",
                    "target_weight_bps": round(eff_wt * 10000.0),
                    "qty": lots,
                }
                buy_amt = lots * px
                working_cash = max(0.0, working_cash - buy_amt)
                post_sell_w[s] = post_sell_w.get(s, 0.0) + buy_amt / nav
                buy_headroom = max(0.0, buy_headroom - eff_diff)

            if (
                bond_drift >= BOND_DRIFT_BAND_W
                and diff_b > 0
                and diff_b * nav >= 5000.0
                and bond_pick in market
            ):
                px_b = float(market[bond_pick]["price"])
                avail = min(diff_b * nav, working_cash * 0.996)
                lots_b = _floor_lots(avail / px_b)
                if lots_b >= 100 and lots_b * px_b >= 5000.0:
                    orders[bond_pick] = {
                        "code": bond_pick,
                        "side": "BUY",
                        "stage": 5,
                        "reason": "BOND_RESERVOIR",
                        "target_weight_bps": round(target_bond_w * 10000.0),
                        "qty": lots_b,
                    }

    ordered_list = sorted(
        orders.values(), key=lambda x: (x["stage"], x["side"] == "BUY", x["code"])
    )
    actions_by_code = {o["code"]: o["side"] for o in ordered_list}
    risk_codes = (
        set(held_risk_etfs)
        | set(scaled_t)
        | {o["code"] for o in ordered_list if o["code"] not in BOND_SET_TS}
    )
    post_buy_risk = sum(post_sell_w.get(s, 0.0) for s in risk_codes)
    target_weights_bps = {s: round(wt * 10000.0) for s, wt in sorted(scaled_t.items())}
    if locked:
        target_weights_bps = {}

    return {
        "align_due": align_due,
        "router_effective_cap_bps": round(eff_cap * 10000.0),
        "target_weights_bps": target_weights_bps,
        "target_bond_bps": round(target_bond_w * 10000.0),
        "actions_by_code": actions_by_code,
        "orders": ordered_list,
        "post_buy_risk_bps": round(post_buy_risk * 10000.0),
    }
