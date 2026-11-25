"""Frozen ETF schedule replay. Orders, fees, matching and end-of-day values are native."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import isclose

import pandas as pd
from rqalpha import run_func
from rqalpha.const import INSTRUMENT_TYPE
from rqalpha.core.events import EVENT
from rqalpha.environment import Environment
from rqalpha.mod.rqalpha_mod_sys_transaction_cost.deciders import StockTransactionCostDecider

from research.ashare.v3_data import BUNDLE_CUTOFF, BUNDLE_PATH, EXP_START, ts_to_rq
from tacticore.engines.rqalpha_adapter import build_rqalpha_config

SUPER, NORMAL = 0.00005, 0.00025


class TieredCosts:
    """order_target_percent uses calc for estimates (no order_id) and fills."""

    def __init__(self, white, env):
        self.white = white
        self.super = StockTransactionCostDecider(SUPER / 0.0008, 0, 0, False, env.event_bus)
        self.normal = StockTransactionCostDecider(NORMAL / 0.0008, 5, 0, False, env.event_bus)

    def calc(self, args):
        decider = self.super if args.instrument.order_book_id in self.white else self.normal
        return decider.calc(args)


def audit_fills(fills, white, tiered):
    normal_orders = defaultdict(float)
    super_count = 0
    bad_super = []
    for fill in fills:
        oid, sym, amount, fee = (fill[k] for k in ("order_id", "code", "notional", "commission"))
        if sym in white or not tiered:
            super_count += 1
            if not isclose(fee, amount * SUPER, rel_tol=1e-6, abs_tol=0):
                bad_super.append(oid)
        else:
            normal_orders[oid] += fee
    bad_normal = [oid for oid, fee in normal_orders.items() if not fee >= 5 - 1e-6]
    odd = [f["order_id"] for f in fills if f["quantity"] % 100 != 0]
    return dict(
        normal_orders=len(normal_orders),
        normal_min=min(normal_orders.values(), default=None),
        super_rate_fills=super_count,
        bad_normal=bad_normal,
        bad_super=bad_super,
        non_lot_fills=odd,
        fees_pass=not (bad_normal or bad_super),
    )


def replay(weights, cash, white, tiered):
    sched = weights.loc[EXP_START:BUNDLE_CUTOFF].dropna(how="all")
    sched = sched.loc[:, sched.gt(0).any()]
    sched = sched.rename(columns=ts_to_rq)
    days, fills, rejects = set(), [], []
    calls = Counter()
    white = set(map(ts_to_rq, white))
    config = build_rqalpha_config(
        str(EXP_START.date()),
        str(BUNDLE_CUTOFF.date()),
        initial_cash=cash,
        fees=SUPER,
        slippage=0.0002,
        bundle_path=BUNDLE_PATH,
        rqalpha_major_version=6,
        partial_fill_on_insufficient_cash=True,
    )

    def on_fill(context, event):
        t = event.trade
        fills.append(
            dict(
                date=str(context.now.date()),
                order_id=int(t.order_id),
                code=t.order_book_id,
                side=t.side.name,
                price=float(t.last_price),
                quantity=int(t.last_quantity),
                notional=float(t.last_price * t.last_quantity),
                commission=float(t.commission),
            )
        )

    def on_reject(context, event):
        # ORDER_CREATION_REJECT has a reason and instrument, NOT an order object.
        rejects.append(
            dict(date=str(context.now.date()), code=event.order_book_id, reason=str(event.reason))
        )

    def init(context):
        from rqalpha.api import subscribe_event

        env = Environment.get_instance()
        if tiered:
            env.set_transaction_cost_decider(INSTRUMENT_TYPE.ETF, TieredCosts(white, env))
        subscribe_event(EVENT.TRADE, on_fill)
        subscribe_event(EVENT.ORDER_CREATION_REJECT, on_reject)

    def handle_bar(context, bar_dict):
        from rqalpha.api import order_target_percent

        dt = pd.Timestamp(context.now).normalize()
        if dt not in sched.index:
            return
        portfolio = context.portfolio
        targets = []
        for sym, w in sched.loc[dt].dropna().items():
            pos = portfolio.positions.get(sym)
            cur = pos.market_value / max(portfolio.total_value, 1) if pos is not None else 0
            targets.append((w - cur, sym, w))
        targets.sort(key=lambda x: x[0])  # same stable sell-before-buy ordering as EXP-V3-01
        for _, sym, w in targets:
            rejected_before = len(rejects)
            order = order_target_percent(sym, w)
            days.add(dt)
            calls["targets"] += 1
            if order is None and len(rejects) == rejected_before:
                # Native positive target delta rounds/clips to zero (cash cap included).
                calls["silent_zero_quantity"] += 1
            elif len(rejects) > rejected_before and "0 order quantity" in rejects[-1]["reason"]:
                calls["explicit_zero_quantity"] += 1

    analyser = run_func(init=init, handle_bar=handle_bar, config=config)["sys_analyser"]
    equity = analyser["portfolio"]["total_value"].copy()
    equity.index = pd.to_datetime(equity.index)
    planned = set(sched.index)
    audit = audit_fills(fills, white, tiered)
    return equity, dict(
        summary_sharpe=float(analyser["summary"]["sharpe"]),
        summary_cagr=float(analyser["summary"]["annualized_returns"]),
        planned_dates=sorted(str(d.date()) for d in planned),
        order_call_dates=sorted(str(d.date()) for d in days),
        dates_pass=planned == days,
        order_calls=calls["targets"],
        zero_quantity_silent=calls["silent_zero_quantity"],
        zero_quantity_explicit=calls["explicit_zero_quantity"],
        rejects=rejects,
        fills=fills,
        commission_audit=audit,
        native_fill_count=len(analyser["trades"]),
        fill_capture_pass=len(analyser["trades"]) == len(fills),
    )
