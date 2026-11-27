"""Pure deterministic v3.4.0 Tri-Pillar daily decision reference for cross-repo parity.

Implements the conditionally approved v3.4.0 semantics (EXP-V3-14 + #53 Carbon High):
- CORE_40 all-weather core: 15% no-min-5 LOW_VOL (159549.SZ/159207.SZ), 10% physical gold
  (518880.SH with +/-400bps wide band [6%, 14%] & >=5,000 CNY single-leg), 15% strategic
  treasury bond (159649.SZ -> 511260.SH -> 511010.SH with +/-1000bps band & >=5,000 CNY)
- 60% dynamic satellite: 1 VALUE + 1 GROWTH upward-only sticky ETFs
- ICE_10 15-trade-day 35% damping floor (disabled under P0 L2 lock -> 10% hard lifeline)
- B1 756d strictly causal ERP+B/P dual-confirmed envelope with 5% hysteresis (normal DEFENSIVE=25%)
- REGIME_ONLY low-turnover execution (10% equity/satellite drift band; ignores style-only flips)
- QualityCore v2 (<100k dormant, >=95k re-verify gate, strict ann_date<=T)
- Bounded scalar-only Forward View Overlay (FVO): default 0, +/-1000bps, TTL<=20d,
  positive zeroed on P0>=8% (L1) or EXTREME_BUBBLE, halved to +/-500bps on 60d attr <=-150bps,
  no style_tilt
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from math import floor, isfinite
from typing import Any

from research.ashare.v3_data import WHITELIST_PATH, rq_to_ts, ts_to_rq
from research.batches.exp_v3_06_defensive_rotation.run import LOW_TICKET_BONDS
from research.batches.exp_v3_11_v330_integration.run import BOND_SET_TS
from tacticore.engines.vectorbt_adapter import validate_execution_targets  # noqa: F401

GOLD_TS = "518880.SH"
LOW_VOL_CHAIN_TS: tuple[str, ...] = ("159549.SZ", "159207.SZ", "512890.SH", "510880.SH")
VALUE_CHAIN_TS: tuple[str, ...] = ("159330.SZ", "530050.SH", "510140.SH", "510300.SH")
GROWTH_CHAIN_TS: tuple[str, ...] = (
    "159205.SZ",
    "159337.SZ",
    "589850.SH",
    "159290.SZ",
    "589060.SH",
    "589330.SH",
    "510500.SH",
    "159915.SZ",
)

CORE_LOWVOL_W = 0.15
CORE_GOLD_W = 0.10
GOLD_BAND_W = 0.04
GOLD_MIN_TRADE_CNY = 5000.0
BOND_DRIFT_BAND_W = 0.10
EQUITY_DRIFT_BAND_W = 0.10
GLIDE_CAP_W = 0.35
DUST_DEADBAND_W = 0.02

B1_BUDGET_MATRIX: dict[str, dict[str, float]] = {
    "EXTREME_UNDERVAL": {
        "OFFENSIVE": 0.85,
        "STRUCTURAL": 0.65,
        "RECOVERY": 0.50,
        "ICE_10": 0.425,
        "DEFENSIVE": 0.25,
    },
    "EXTREME_BUBBLE": {
        "OFFENSIVE": 0.70,
        "STRUCTURAL": 0.50,
        "RECOVERY": 0.40,
        "ICE_10": 0.35,
        "DEFENSIVE": 0.25,
    },
    "NEUTRAL": {
        "OFFENSIVE": 0.85,
        "STRUCTURAL": 0.60,
        "RECOVERY": 0.40,
        "ICE_10": 0.35,
        "DEFENSIVE": 0.25,
    },
}

_PERIOD_ANNUALIZATION: dict[str, float] = {
    "0331": 4.0,
    "0630": 2.0,
    "0930": 4.0 / 3.0,
    "1231": 1.0,
}


@dataclass(frozen=True)
class FvoResolution:
    raw_delta_bps: int
    applied_delta_bps: int
    effective_cap_bps: int
    zero_reason: str | None


def load_super_etf_codes() -> frozenset[str]:
    wl = json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))
    return frozenset(str(entry["ts_code"]) for entry in wl["entries"])


def _floor_lots(shares: float) -> int:
    if not isfinite(shares) or shares + 1e-9 < 100.0:
        return 0
    return int(floor((shares + 1e-9) / 100.0)) * 100


def _norm_yyyymmdd(value: str) -> str:
    digits = value.replace("-", "").strip()
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(f"invalid_trade_date:{value}")
    return digits


def _parse_date(value: str) -> date:
    d = _norm_yyyymmdd(value)
    return date(int(d[:4]), int(d[4:6]), int(d[6:8]))


def evaluate_b1_state(
    erp_pct_756: float | None,
    bp_pct_756: float | None,
    prev_b1_state: str = "NEUTRAL",
) -> str:
    """Evaluate strictly causal B1 756d ERP+B/P dual-confirmed envelope with 5% hysteresis."""
    if (
        erp_pct_756 is None
        or bp_pct_756 is None
        or not isfinite(erp_pct_756)
        or not isfinite(bp_pct_756)
    ):
        return "NEUTRAL"
    e_val = float(erp_pct_756)
    b_val = float(bp_pct_756)
    if prev_b1_state == "EXTREME_UNDERVAL":
        if e_val <= 0.15 and b_val <= 0.15:
            return "EXTREME_BUBBLE"
        if e_val < 0.75 or b_val < 0.65:
            return "NEUTRAL"
        return "EXTREME_UNDERVAL"
    if prev_b1_state == "EXTREME_BUBBLE":
        if e_val >= 0.80 and b_val >= 0.70:
            return "EXTREME_UNDERVAL"
        if e_val > 0.20 or b_val > 0.20:
            return "NEUTRAL"
        return "EXTREME_BUBBLE"
    if e_val >= 0.80 and b_val >= 0.70:
        return "EXTREME_UNDERVAL"
    if e_val <= 0.15 and b_val <= 0.15:
        return "EXTREME_BUBBLE"
    return "NEUTRAL"


def resolve_scalar_fvo(
    fvo: dict[str, Any] | None,
    *,
    as_of: str,
    b1_state: str,
    work_dd_bps: int,
    locked: bool,
) -> FvoResolution:
    """Resolve bounded scalar-only FVO; reject style_tilt and enforce TTL/P0/bubble guards."""
    if not fvo:
        return FvoResolution(0, 0, 1000, None)
    if "style_tilt" in fvo:
        raise ValueError("fvo_style_tilt_forbidden")
    raw_delta = int(fvo.get("equity_delta_bps", 0))
    status = str(fvo.get("status", "ACTIVE")).upper()
    if status != "ACTIVE":
        return FvoResolution(raw_delta, 0, 1000, "INACTIVE")

    attr_60d_bps = int(fvo.get("attribution_60d_bps", 0))
    max_cap_bps = 500 if attr_60d_bps <= -150 else 1000

    expires_raw = fvo.get("expires_trade_date")
    if expires_raw is not None and _norm_yyyymmdd(as_of) > _norm_yyyymmdd(str(expires_raw)):
        return FvoResolution(raw_delta, 0, max_cap_bps, "EXPIRED")

    ttl_days = fvo.get("ttl_trade_days")
    if ttl_days is not None and int(ttl_days) > 20:
        raise ValueError(f"fvo_ttl_exceeds_20d:{ttl_days}")

    clamped = max(-max_cap_bps, min(max_cap_bps, raw_delta))
    if clamped > 0 and (locked or work_dd_bps >= 800):
        return FvoResolution(raw_delta, 0, max_cap_bps, "P0_L1_OR_LOCK")
    if clamped > 0 and b1_state == "EXTREME_BUBBLE":
        return FvoResolution(raw_delta, 0, max_cap_bps, "EXTREME_BUBBLE")
    return FvoResolution(raw_delta, clamped, max_cap_bps, None)


def passes_quality_core_v2(
    fundamental: dict[str, Any] | None,
    trade_date: str,
) -> tuple[bool, str | None]:
    """Evaluate 40-quarter PIT QualityCore v2 stock filter with strict ann_date <= T."""
    if not fundamental:
        return False, "MISSING_FUNDAMENTAL"
    ann_raw = fundamental.get("ann_date")
    end_raw = fundamental.get("end_date")
    if not ann_raw or not end_raw:
        return False, "MISSING_DATES"
    t_str = _norm_yyyymmdd(trade_date)
    ann_str = _norm_yyyymmdd(str(ann_raw))
    end_str = _norm_yyyymmdd(str(end_raw))
    if ann_str > t_str:
        return False, "LOOKAHEAD_ANN_DATE"

    age_days = (_parse_date(t_str) - _parse_date(end_str)).days
    if age_days < 0 or age_days > 550:
        return False, "STALE_OR_FUTURE_REPORT"

    roe_dt_raw = fundamental.get("roe_dt")
    eps_raw = fundamental.get("basic_eps")
    ocf_raw = fundamental.get("ocf_to_profit")
    bps_raw = fundamental.get("bps")
    if roe_dt_raw is None or eps_raw is None or ocf_raw is None or bps_raw is None:
        return False, "NAN_METRIC"
    roe_dt = float(roe_dt_raw)
    basic_eps = float(eps_raw)
    ocf_to_profit = float(ocf_raw)
    bps = float(bps_raw)
    if not all(isfinite(v) for v in (roe_dt, basic_eps, ocf_to_profit, bps)):
        return False, "NAN_METRIC"

    mult = _PERIOD_ANNUALIZATION.get(end_str[4:8], 1.0)
    ann_roe_dt = roe_dt * mult
    if ann_roe_dt <= 6.0:
        return False, "LOW_ROE_DT"
    if basic_eps <= 0.0:
        return False, "NON_POSITIVE_EPS"
    if ocf_to_profit < 50.0:
        return False, "LOW_OCF_TO_PROFIT"
    if bps <= 0.0:
        return False, "NON_POSITIVE_BPS"
    return True, None


def _effective_caps(
    base_budget: float, drawdown: dict[str, Any]
) -> tuple[float | None, float, bool, bool]:
    """Return (ctrl_cap, eff_buy_cap, locked, l1_active) under TWO_STAGE_GRADUAL."""
    locked = bool(drawdown["locked"])
    dd_bps = int(drawdown["work_dd_bps"])
    l1_active = locked or dd_bps >= 800
    if locked:
        return 0.10, 0.10, True, True
    if dd_bps >= 1100:
        ctrl_cap: float | None = 0.25
    elif dd_bps >= 800:
        ctrl_cap = 0.50
    else:
        ctrl_cap = None

    eff_cap = base_budget
    if ctrl_cap is not None:
        eff_cap = min(eff_cap, ctrl_cap)
    ramp_factor = float(drawdown.get("ramp_factor_bps", 10000)) / 10000.0
    if ramp_factor < 1.0 - 1e-9:
        eff_cap = min(eff_cap, base_budget * ramp_factor)
    return ctrl_cap, eff_cap, False, l1_active


def _eligible_etf(
    code: str,
    market: dict[str, dict[str, Any]],
    held_mv: dict[str, float],
    *,
    require_buyable: bool = False,
) -> bool:
    info = market.get(code)
    if not info:
        return False
    px = info.get("price")
    if px is None or not isfinite(float(px)) or float(px) <= 0.0:
        return False
    held_ok = held_mv.get(code, 0.0) > 0.0
    if held_ok and not require_buyable:
        return True
    if bool(info.get("buy_blocked", False)):
        return False
    ma20 = info.get("ma20")
    return ma20 is not None and isfinite(float(ma20))


def select_core40_targets(
    *,
    style: str,
    budget_total: float,
    occupied_weight: float,
    market: dict[str, dict[str, Any]],
    held_mv: dict[str, float],
    nav: float,
    p0_ctrl_cap: float | None,
) -> dict[str, float]:
    """Select CORE_40 + 60% satellite ETF target weights with upward-only sticky logic."""
    eff_total = max(0.0, budget_total)
    core_risk = CORE_LOWVOL_W + CORE_GOLD_W
    if eff_total >= core_risk - 1e-9:
        lv_w = CORE_LOWVOL_W
        gold_w = CORE_GOLD_W
    else:
        sc = eff_total / core_risk
        lv_w = CORE_LOWVOL_W * sc
        gold_w = CORE_GOLD_W * sc

    out: dict[str, float] = {}
    lv_picks = [c for c in LOW_VOL_CHAIN_TS if _eligible_etf(c, market, held_mv)][:2]
    if lv_picks and lv_w > 0.005:
        for c in lv_picks:
            out[c] = lv_w / len(lv_picks)

    if gold_w > 0.005 and _eligible_etf(GOLD_TS, market, held_mv):
        cur_gold_w = held_mv.get(GOLD_TS, 0.0) / max(nav, 1.0)
        if p0_ctrl_cap is None and cur_gold_w > 0.005:
            diff_g = abs(cur_gold_w - gold_w)
            if diff_g < GOLD_BAND_W or diff_g * nav < GOLD_MIN_TRADE_CNY:
                out[GOLD_TS] = cur_gold_w
            else:
                out[GOLD_TS] = gold_w
        else:
            out[GOLD_TS] = gold_w

    core_used = sum(out.values())
    sat_room = max(0.0, eff_total - core_used - occupied_weight)
    if sat_room > 0.01:
        val_c = next((c for c in VALUE_CHAIN_TS if _eligible_etf(c, market, held_mv)), None)
        gro_c = next((c for c in GROWTH_CHAIN_TS if _eligible_etf(c, market, held_mv)), None)
        if style == "GROWTH_LEADING":
            gro_share, val_share = 0.65, 0.35
        elif style == "VALUE_LEADING":
            gro_share, val_share = 0.35, 0.65
        else:
            gro_share, val_share = 0.50, 0.50

        if val_c and gro_c:
            out[val_c] = sat_room * val_share
            out[gro_c] = sat_room * gro_share
        elif val_c:
            out[val_c] = sat_room
        elif gro_c:
            out[gro_c] = sat_room

    return {c: wt for c, wt in out.items() if wt > 0.01}


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


def _is_stock_code(code: str, market: dict[str, dict[str, Any]]) -> bool:
    info = market.get(code, {})
    if info.get("asset_type") == "STOCK":
        return True
    prefix = code.split(".", 1)[0]
    return prefix.startswith(("000", "001", "002", "003", "600", "601", "603", "605"))


def evaluate_v340_decision(scenario: dict[str, Any]) -> dict[str, Any]:
    """Compute deterministic v3.4.0 decision output for one parity fixture scenario."""
    if any(k == "implied_expectation_tilt" or k.startswith("b2_") for k in scenario):
        raise ValueError("b2_trading_keys_forbidden")

    as_of = str(scenario["as_of"])
    base_regime = str(scenario["regime"])
    style = str(scenario["style"])
    ice10_remaining = int(scenario.get("ice10_remaining_days", 0))
    pct_above_ma60 = float(scenario.get("pct_above_ma60", 1.0))
    drawdown = scenario["drawdown"]
    locked = bool(drawdown["locked"])
    work_dd_bps = int(drawdown["work_dd_bps"])

    # ICE_10 activates on DEFENSIVE within 15d window of pct_above_ma60 < 10%,
    # but is explicitly disabled when P0 L2 lock is active.
    ice10_active = ice10_remaining > 0 or pct_above_ma60 < 0.10
    if base_regime == "DEFENSIVE" and ice10_active and not locked:
        effective_regime = "ICE_10"
    elif base_regime == "ICE_10" and locked:
        effective_regime = "DEFENSIVE"
    else:
        effective_regime = base_regime

    fund = scenario.get("fundamental") or {}
    b1_state = evaluate_b1_state(
        fund.get("erp_pct_756"),
        fund.get("bp_pct_756"),
        str(fund.get("prev_b1_state", "NEUTRAL")),
    )
    base_budget = B1_BUDGET_MATRIX[b1_state][effective_regime]

    fvo_res = resolve_scalar_fvo(
        scenario.get("fvo"),
        as_of=as_of,
        b1_state=b1_state,
        work_dd_bps=work_dd_bps,
        locked=locked,
    )
    budget_after_fvo = min(0.85, max(0.25, base_budget + fvo_res.applied_delta_bps / 10000.0))
    ctrl_cap, eff_cap, locked, l1_active = _effective_caps(budget_after_fvo, drawdown)

    if not scenario.get("quote_ready", True):
        return {
            "b1_state": b1_state,
            "effective_regime": effective_regime,
            "fvo_applied_delta_bps": fvo_res.applied_delta_bps,
            "fvo_zero_reason": fvo_res.zero_reason,
            "align_due": False,
            "bp1_permitted": False,
            "qualified_bp1_codes": [],
            "rejected_bp1_reasons": {},
            "router_effective_cap_bps": round(eff_cap * 10000.0),
            "target_weights_bps": {},
            "target_bond_bps": 0,
            "actions_by_code": {},
            "orders": [],
            "post_buy_risk_bps": 0,
        }

    nav = float(scenario["investable_nav_cny"])
    cash = float(scenario["cash_cny"])
    market: dict[str, dict[str, Any]] = scenario["market"]
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

    held_stocks = [c for c in held_qty if c not in BOND_SET_TS and _is_stock_code(c, market)]
    held_risk_etfs = [c for c in held_qty if c not in BOND_SET_TS and c not in held_stocks]

    provisional_t = select_core40_targets(
        style=style,
        budget_total=budget_after_fvo,
        occupied_weight=0.0,
        market=market,
        held_mv=held_mv,
        nav=nav,
        p0_ctrl_cap=ctrl_cap,
    )
    non_target_etfs = [c for c in held_risk_etfs if c not in provisional_t]
    risk_w = sum(w[c] for c in held_risk_etfs) + sum(w[c] for c in held_stocks)
    nt_total_w = sum(w[c] for c in non_target_etfs)

    # P0: Drawdown controller trim
    p0_sold_by_sym: dict[str, float] = {}
    p0_target_w: dict[str, float] = {}
    if ctrl_cap is not None and risk_w > ctrl_cap + DUST_DEADBAND_W and risk_w > 1e-6:
        need_cut_w = risk_w - ctrl_cap
        if nt_total_w > 1e-6 and need_cut_w > 1e-6:
            cut_nt = min(nt_total_w, need_cut_w)
            keep_nt_ratio = max(0.0, 1.0 - cut_nt / nt_total_w)
            for s in non_target_etfs:
                new_ws = w[s] * keep_nt_ratio
                if new_ws < DUST_DEADBAND_W:
                    new_ws = 0.0
                if new_ws < w[s] - 1e-9:
                    p0_sold_by_sym[s] = w[s] - new_ws
                    p0_target_w[s] = new_ws
            need_cut_w = max(0.0, risk_w - ctrl_cap - sum(p0_sold_by_sym.values()))
        rem_risk = [s for s in (*held_risk_etfs, *held_stocks) if s not in non_target_etfs]
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

    post_sell_w = dict(w)
    for s in p0_target_w:
        if s in orders:
            px = float(market[s]["price"])
            post_sell_w[s] = max(0.0, (held_qty[s] - orders[s]["qty"]) * px / nav)

    # QualityCore v2 BP1 stock evaluation (>=100k unlock, >=95k pre-order reverify gate)
    qualified_bp1: list[dict[str, Any]] = []
    rejected_bp1: dict[str, str] = {}
    for cand in scenario.get("stock_candidates", []):
        code = str(cand["code"])
        ok, rej = passes_quality_core_v2(cand.get("fundamental"), as_of)
        if ok:
            qualified_bp1.append(cand)
        else:
            rejected_bp1[code] = rej or "FAILED_QC_V2"

    reverify_ok = True if nav < 95000.0 else bool(scenario.get("bp1_reverified", True))
    bp1_permitted = bool(
        nav >= 100000.0
        and reverify_ok
        and nt_total_w <= 0.30
        and effective_regime in ("OFFENSIVE", "STRUCTURAL")
        and not locked
        and not l1_active
    )

    current_stock_w = sum(post_sell_w.get(s, 0.0) for s in held_stocks)
    slots_left = max(0, 2 - len(held_stocks))
    stock_buy_budget = 0.0
    bp1_target_weights: dict[str, float] = {}
    if bp1_permitted and slots_left > 0 and qualified_bp1:
        core_reserve = CORE_LOWVOL_W + CORE_GOLD_W
        total_avail = max(0.0, eff_cap - core_reserve - nt_total_w - current_stock_w)
        working_stock_cash = cash + sum(
            o["qty"] * float(market[o["code"]]["price"])
            for o in orders.values()
            if o["side"] == "SELL"
        )
        for cand in qualified_bp1:
            if slots_left <= 0 or total_avail < 0.08:
                break
            code = str(cand["code"])
            if code in held_qty or code in orders:
                continue
            ref_close = float(cand["ref_close"])
            hard_stop = float(cand["hard_stop"])
            stop_pct = min(0.08, max(0.025, 1.0 - hard_stop / ref_close))
            est_w = min(0.013 / max(stop_pct, 0.02), 0.18, total_avail)
            cap_val = min(est_w * nav, working_stock_cash * 0.996)
            lots = _floor_lots(cap_val / ref_close)
            if lots < 100 or lots * ref_close < 8000.0:
                continue
            eff_w = (lots * ref_close) / nav
            orders[code] = {
                "code": code,
                "side": "BUY",
                "stage": 3,
                "reason": "BP1_ENTRY",
                "target_weight_bps": round(eff_w * 10000.0),
                "qty": lots,
            }
            bp1_target_weights[code] = eff_w
            stock_buy_budget += eff_w
            total_avail -= eff_w
            working_stock_cash = max(0.0, working_stock_cash - lots * ref_close)
            post_sell_w[code] = post_sell_w.get(code, 0.0) + eff_w
            slots_left -= 1

    align_due = False
    target_bond_w = max(0.0, 1.0 - eff_cap - 0.01) if locked else 0.0
    scaled_t: dict[str, float] = {}

    if not locked:
        prev_eff_regime = str(scenario.get("prev_effective_regime", effective_regime))
        prev_budget_bps = scenario.get("prev_eff_budget_bps")
        cur_budget_bps = round(eff_cap * 10000.0)
        reg_or_budget_changed = (effective_regime != prev_eff_regime) or (
            prev_budget_bps is not None and int(prev_budget_bps) != cur_budget_bps
        )
        prev_fvo_bps = scenario.get("prev_fvo_applied_delta_bps")
        fvo_changed = prev_fvo_bps is not None and int(prev_fvo_bps) != fvo_res.applied_delta_bps
        unlocked_today = bool(drawdown.get("unlocked_today", False))
        p0_triggered = bool(drawdown.get("trigger", False) or p0_sold_w > 0)

        post_p0_w = {s: max(0.0, w[s] - p0_sold_by_sym.get(s, 0.0)) for s in held_risk_etfs}
        nt_p0_sold = sum(p0_sold_by_sym.get(s, 0.0) for s in non_target_etfs)
        nt_glide_sell = (
            nt_total_w
            if nt_total_w <= GLIDE_CAP_W + DUST_DEADBAND_W
            else max(GLIDE_CAP_W, nt_total_w - GLIDE_CAP_W)
        )
        nt_carryover = max(0.0, nt_total_w - max(nt_p0_sold, nt_glide_sell))
        occupied_for_targets = current_stock_w + stock_buy_budget + nt_carryover

        raw_t = select_core40_targets(
            style=style,
            budget_total=eff_cap,
            occupied_weight=occupied_for_targets,
            market=market,
            held_mv=held_mv,
            nav=nav,
            p0_ctrl_cap=ctrl_cap,
        )
        tot_raw = sum(raw_t.values())
        max_new_eq = max(0.0, eff_cap - occupied_for_targets)
        scale = min(1.0, max_new_eq / tot_raw) if tot_raw > 1e-9 else 1.0
        scaled_t = {code: wt * scale for code, wt in raw_t.items() if wt * scale > 0.01}

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
                    if s in non_target_etfs and new_ws < DUST_DEADBAND_W:
                        new_ws = 0.0
                    p3_sell_target_w[s] = new_ws
                rem_p3_sell = max(0.0, rem_p3_sell - sell_from_grp)

        post_sell_nt_w = sum(p3_sell_target_w.get(s, post_p0_w[s]) for s in non_target_etfs)
        occupied_final = current_stock_w + stock_buy_budget + post_sell_nt_w
        target_eq_total = max(occupied_final, min(eff_cap, occupied_final + sum(scaled_t.values())))
        target_bond_w = max(0.0, 1.0 - target_eq_total - 0.01)
        cur_bond_w = sum(w.get(b, 0.0) for b in BOND_SET_TS)
        bond_drift = abs(target_bond_w - cur_bond_w)

        cur_g = w.get(GOLD_TS, 0.0)
        g_target = scaled_t.get(GOLD_TS, 0.0)
        gold_diff = abs(g_target - cur_g)
        gold_breach = bool(
            g_target > 0.005
            and (
                (cur_g < 1e-4 and g_target * nav >= GOLD_MIN_TRADE_CNY)
                or (gold_diff >= GOLD_BAND_W and gold_diff * nav >= GOLD_MIN_TRADE_CNY)
            )
        )

        all_eq_etfs = set(scaled_t) | set(held_risk_etfs)
        eq_drift_sum = sum(
            abs(scaled_t.get(s, 0.0) - post_p0_w.get(s, 0.0)) for s in all_eq_etfs if s != GOLD_TS
        )
        has_non_target_risk = any(w[s] > 1e-6 for s in non_target_etfs)

        align_due = bool(
            has_non_target_risk
            or reg_or_budget_changed
            or fvo_changed
            or unlocked_today
            or p0_triggered
            or eq_drift_sum >= EQUITY_DRIFT_BAND_W
            or gold_breach
            or bond_drift >= BOND_DRIFT_BAND_W
            or stock_buy_budget > 0.0
        )

        if align_due:
            for s, new_ws in sorted(p3_sell_target_w.items()):
                if new_ws < post_p0_w[s] - 1e-9:
                    if s == GOLD_TS and new_ws > 1e-6:
                        sell_cny = (post_p0_w[s] - new_ws) * nav
                        if sell_cny < GOLD_MIN_TRADE_CNY:
                            continue
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
            est_stock_buy_cash = sum(
                o["qty"] * float(market[o["code"]]["price"])
                for o in orders.values()
                if o["side"] == "BUY" and o["code"] in bp1_target_weights
            )
            working_cash = max(0.0, cash + est_sell_cash - est_stock_buy_cash)
            held_risk_sum = sum(post_sell_w.get(s, 0.0) for s in (*held_risk_etfs, *held_stocks))
            post_sell_total_risk = held_risk_sum + stock_buy_budget
            buy_headroom = max(0.0, eff_cap - post_sell_total_risk)
            allow_sub_band = reg_or_budget_changed or fvo_changed or unlocked_today or p0_triggered

            def _buy_candidate(sym: str, room_w: float) -> tuple[float, float, float] | None:
                if sym in p3_sell_target_w or sym in p0_sold_by_sym or sym in orders:
                    return None
                if bool(market.get(sym, {}).get("buy_blocked", False)):
                    return None
                cur_s = w.get(sym, 0.0)
                diff = scaled_t[sym] - cur_s
                if diff <= 1e-6 or room_w <= 1e-6:
                    return None
                if cur_s > 0 and not allow_sub_band:
                    if sym == GOLD_TS and diff < GOLD_BAND_W:
                        return None
                    if sym != GOLD_TS and diff < EQUITY_DRIFT_BAND_W:
                        return None
                is_super = bool(market[sym].get("is_super_etf", sym in super_set))
                min_ticket = 1000.0 if is_super else GOLD_MIN_TRADE_CNY
                if diff * nav < min_ticket:
                    return None
                eff_wt = min(scaled_t[sym], cur_s + room_w)
                eff_diff = eff_wt - cur_s
                if eff_diff * nav < min_ticket:
                    return None
                return eff_wt, eff_diff, min_ticket

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
        | set(held_stocks)
        | set(scaled_t)
        | set(bp1_target_weights)
        | {o["code"] for o in ordered_list if o["code"] not in BOND_SET_TS}
    )
    post_buy_risk = sum(post_sell_w.get(s, 0.0) for s in risk_codes)
    merged_targets = dict(scaled_t)
    merged_targets.update(bp1_target_weights)
    target_weights_bps = {s: round(wt * 10000.0) for s, wt in sorted(merged_targets.items())}
    if locked:
        target_weights_bps = {}

    return {
        "b1_state": b1_state,
        "effective_regime": effective_regime,
        "fvo_applied_delta_bps": fvo_res.applied_delta_bps,
        "fvo_zero_reason": fvo_res.zero_reason,
        "align_due": align_due,
        "bp1_permitted": bp1_permitted,
        "qualified_bp1_codes": [str(c["code"]) for c in qualified_bp1],
        "rejected_bp1_reasons": rejected_bp1,
        "router_effective_cap_bps": round(eff_cap * 10000.0),
        "target_weights_bps": target_weights_bps,
        "target_bond_bps": round(target_bond_w * 10000.0),
        "actions_by_code": actions_by_code,
        "orders": ordered_list,
        "post_buy_risk_bps": round(post_buy_risk * 10000.0),
    }


__all__ = [
    "B1_BUDGET_MATRIX",
    "FvoResolution",
    "evaluate_b1_state",
    "evaluate_v340_decision",
    "passes_quality_core_v2",
    "resolve_scalar_fvo",
    "rq_to_ts",
    "select_core40_targets",
    "ts_to_rq",
]
