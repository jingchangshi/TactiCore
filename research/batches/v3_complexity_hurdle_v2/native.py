"""Native RQAlpha 6.3.0 replay for V3_COMPLEXITY_HURDLE_V2
with corporate-action full-close odd-lot tracking."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import isclose
from typing import Any

import pandas as pd
from rqalpha import run_func
from rqalpha.const import INSTRUMENT_TYPE
from rqalpha.core.events import EVENT
from rqalpha.environment import Environment
from rqalpha.mod.rqalpha_mod_sys_transaction_cost.deciders import StockTransactionCostDecider

from research.ashare.v3_data import ts_to_rq
from research.ashare.v3_data_202611 import BUNDLE_CUTOFF_202611, BUNDLE_PATH_202611, EXP_START
from tacticore.engines.rqalpha_adapter import build_rqalpha_config

SUPER, NORMAL = 0.00005, 0.00025


class TieredCosts:
    """Apply Eastmoney super-ETF 0.5bp/min-0 vs standard ETF 2.5bp/min-5."""

    def __init__(self, white: set[str], env: Any) -> None:
        self.white = white
        self.super = StockTransactionCostDecider(SUPER / 0.0008, 0, 0, False, env.event_bus)
        self.normal = StockTransactionCostDecider(NORMAL / 0.0008, 5, 0, False, env.event_bus)

    def calc(self, args: Any) -> Any:
        decider = self.super if args.instrument.order_book_id in self.white else self.normal
        return decider.calc(args)


def audit_fills(
    fills: list[dict[str, Any]], white: set[str], tiered: bool
) -> dict[str, Any]:
    """Audit tiered fees; separate corporate-action full liquidations from illegal odd lots."""
    normal_orders: dict[int, float] = defaultdict(float)
    super_count = 0
    bad_super: list[int] = []
    corp_odd_lots: list[dict[str, Any]] = []
    illegal_odd_lots: list[dict[str, Any]] = []

    for fill in fills:
        oid = int(fill["order_id"])
        sym = str(fill["code"])
        amount = float(fill["notional"])
        fee = float(fill["commission"])
        qty = int(fill["quantity"])
        if sym in white or not tiered:
            super_count += 1
            if not isclose(fee, amount * SUPER, rel_tol=1e-6, abs_tol=1e-9):
                bad_super.append(oid)
        else:
            normal_orders[oid] += fee

        if qty % 100 != 0:
            item = {
                "order_id": oid,
                "date": fill["date"],
                "code": sym,
                "side": fill["side"],
                "quantity": qty,
                "full_liquidation": bool(fill.get("full_liquidation", False)),
            }
            if fill["side"] == "SELL" and bool(fill.get("full_liquidation", False)):
                corp_odd_lots.append(item)
            else:
                illegal_odd_lots.append(item)

    bad_normal = [oid for oid, fee in normal_orders.items() if not fee >= 5 - 1e-6]
    return {
        "normal_orders": len(normal_orders),
        "normal_min": min(normal_orders.values(), default=None),
        "super_rate_fills": super_count,
        "bad_normal": bad_normal,
        "bad_super": bad_super,
        "corporate_action_full_close_odd_lots": corp_odd_lots,
        "illegal_non_lot_fills": illegal_odd_lots,
        "non_lot_fills": illegal_odd_lots,
        "fees_pass": not (bad_normal or bad_super),
    }


def replay(
    weights: pd.DataFrame,
    cash: float,
    white: tuple[str, ...] | set[str],
    tiered: bool,
    *,
    start: pd.Timestamp = EXP_START,
    end: pd.Timestamp = BUNDLE_CUTOFF_202611,
) -> tuple[pd.Series, dict[str, Any]]:
    """Run native RQAlpha 6.3.0 replay on bundle_202611."""
    sched = weights.loc[start:end].dropna(how="all")
    sched = sched.loc[:, sched.gt(0).any()]
    sched = sched.rename(columns=ts_to_rq)
    days: set[pd.Timestamp] = set()
    fills: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    calls: Counter[str] = Counter()
    active_ctx: dict[str, Any] = {"order": None}
    white_rq = set(map(ts_to_rq, white))

    config = build_rqalpha_config(
        str(start.date()),
        str(end.date()),
        initial_cash=cash,
        fees=SUPER,
        slippage=0.0002,
        bundle_path=BUNDLE_PATH_202611,
        rqalpha_major_version=6,
        partial_fill_on_insufficient_cash=True,
    )

    def on_fill(context: Any, event: Any) -> None:
        t = event.trade
        meta = active_ctx["order"] or {}
        qty = int(t.last_quantity)
        cum_qty = int(meta.get("cum_qty", 0)) + qty
        meta["cum_qty"] = cum_qty
        held_before = int(meta.get("held_before", 0))
        target_w = meta.get("target_w")
        full_liq = bool(
            t.side.name == "SELL"
            and target_w is not None
            and float(target_w) == 0.0
            and held_before > 0
            and cum_qty == held_before
        )
        fills.append(
            {
                "date": str(context.now.date()),
                "order_id": int(t.order_id),
                "code": t.order_book_id,
                "side": t.side.name,
                "price": float(t.last_price),
                "quantity": qty,
                "notional": float(t.last_price * qty),
                "commission": float(t.commission),
                "held_before": held_before,
                "target_w": float(target_w) if target_w is not None else None,
                "full_liquidation": full_liq,
            }
        )

    def on_reject(context: Any, event: Any) -> None:
        rejects.append(
            {
                "date": str(context.now.date()),
                "code": event.order_book_id,
                "reason": str(event.reason),
            }
        )

    def init(context: Any) -> None:
        from rqalpha.api import subscribe_event

        env = Environment.get_instance()
        if tiered:
            env.set_transaction_cost_decider(INSTRUMENT_TYPE.ETF, TieredCosts(white_rq, env))
        subscribe_event(EVENT.TRADE, on_fill)
        subscribe_event(EVENT.ORDER_CREATION_REJECT, on_reject)

    def handle_bar(context: Any, bar_dict: Any) -> None:
        del bar_dict
        from rqalpha.api import order_target_percent

        dt = pd.Timestamp(context.now).normalize()
        if dt not in sched.index:
            return
        portfolio = context.portfolio
        targets: list[tuple[float, str, float, int]] = []
        for sym, w in sched.loc[dt].dropna().items():
            pos = portfolio.positions.get(sym)
            held_qty = int(pos.quantity) if pos is not None else 0
            cur = pos.market_value / max(portfolio.total_value, 1.0) if pos is not None else 0.0
            targets.append((float(w) - float(cur), sym, float(w), held_qty))
        targets.sort(key=lambda x: x[0])
        for _, sym, w, held_qty in targets:
            rejected_before = len(rejects)
            active_ctx["order"] = {
                "sym": sym,
                "target_w": float(w),
                "held_before": held_qty,
                "cum_qty": 0,
            }
            try:
                order = order_target_percent(sym, w)
            finally:
                active_ctx["order"] = None
            days.add(dt)
            calls["targets"] += 1
            if order is None and len(rejects) == rejected_before:
                calls["silent_zero_quantity"] += 1
            elif len(rejects) > rejected_before and "0 order quantity" in rejects[-1]["reason"]:
                calls["explicit_zero_quantity"] += 1

    analyser = run_func(init=init, handle_bar=handle_bar, config=config)["sys_analyser"]
    equity = analyser["portfolio"]["total_value"].copy()
    equity.index = pd.to_datetime(equity.index)
    planned = set(sched.index)
    audit = audit_fills(fills, white_rq, tiered)
    return equity, {
        "summary_sharpe": float(analyser["summary"]["sharpe"]),
        "summary_cagr": float(analyser["summary"]["annualized_returns"]),
        "planned_dates": sorted(str(d.date()) for d in planned),
        "order_call_dates": sorted(str(d.date()) for d in days),
        "dates_pass": planned == days,
        "order_calls": calls["targets"],
        "zero_quantity_silent": calls["silent_zero_quantity"],
        "zero_quantity_explicit": calls["explicit_zero_quantity"],
        "rejects": rejects,
        "fills": fills,
        "commission_audit": audit,
        "native_fill_count": len(analyser["trades"]),
        "fill_capture_pass": len(analyser["trades"]) == len(fills),
    }
