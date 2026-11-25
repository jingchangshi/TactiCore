"""RQAlpha callbacks for PROTOCOL_V1. No simulated cash, holdings or fills."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import isfinite

from rqalpha import run_func
from rqalpha.const import INSTRUMENT_TYPE
from rqalpha.core.events import EVENT
from rqalpha.environment import Environment
from rqalpha.mod.rqalpha_mod_sys_accounts.trade_utils import get_amount_from_value
from rqalpha.mod.rqalpha_mod_sys_transaction_cost.deciders import StockTransactionCostDecider
from rqalpha.mod.utils import round_order_quantity

from research.ashare.v3_data import BUNDLE_PATH
from tacticore.engines.rqalpha_adapter import build_rqalpha_config

from .policy import BUDGET, FOCUS, GOLD, SECTORS, Plan, Risk, exit_reason, targets


class TieredFees:
    def __init__(self, env, white):
        self.white = white
        self.super = StockTransactionCostDecider(0.00005 / 0.0008, 0, 0, False, env.event_bus)
        self.normal = StockTransactionCostDecider(0.00025 / 0.0008, 5, 1, False, env.event_bus)

    def calc(self, args):
        base = (self.super if args.instrument.order_book_id in self.white else self.normal).calc(
            args
        )
        if args.instrument.type == INSTRUMENT_TYPE.CS:
            return base._replace(other_fees=args.price * args.quantity * 0.00001)
        return base


def opening_block(px, limit, buy, suspended):
    if suspended or not isfinite(px) or px <= 0:
        return "SUSPENDED_OR_MISSING_OPEN"
    if limit > 0 and ((buy and px >= limit - 1e-7) or (not buy and px <= limit + 1e-7)):
        return "LIMIT_UP" if buy else "LIMIT_DOWN"
    return None


def asset_group(code):
    if code == FOCUS:
        return "concentrated"
    if code == GOLD:
        return "gold"
    return "industry" if code in SECTORS else "broad"


def replay(days, market, features, white, capital, seed, enabled):
    from rqalpha.api import instruments, order_shares, subscribe_event

    lookup = {d: i for i, d in enumerate(days)}
    rows, orders, fills, rejects, conflicts, violations = [], [], [], [], [], []
    pending, retries, armed = {}, {}, {}
    risk, plan = Risk(capital), Plan()
    state = dict(regime=None, align=-100, locked=False, active=None)
    cfg = build_rqalpha_config(
        days[0],
        days[-1],
        initial_cash=capital,
        fees=0.00025,
        slippage=0,
        bundle_path=BUNDLE_PATH,
        rqalpha_major_version=6,
    )
    cfg["mod"]["sys_accounts"] = dict(stock_t1=True, auto_switch_order_value=False)

    def audit(ok, msg):
        if not ok:
            violations.append(msg)

    def merge(book, a):
        sym = a["code"]
        if sym in book:
            old = book[sym]
            # Lower numerical priority wins; same-priority unfilled sales win unless
            # the new sale is larger. Retry quantity is always actual unsold shares.
            if (a["p"], -a.get("sell_est", 0)) >= (old["p"], -old.get("sell_est", 0)):
                win, lose = old, a
            else:
                win, lose = a, old
            conflicts.append(
                dict(date=a["signal"], code=sym, kept=win["reason"], dropped=lose["reason"])
            )
            book[sym] = win
        else:
            book[sym] = a

    def on_trade(ctx, ev):
        a = state["active"]
        t = ev.trade
        d = str(ctx.now.date())
        if not a or t.order_book_id != a["code"]:
            violations.append(f"unattributed trade {d} {t.order_book_id}")
            return
        q, px = int(t.last_quantity), float(t.last_price)
        other = float(t.transaction_cost - t.commission - t.tax)
        fills.append(
            dict(
                date=d,
                signal=a["signal"],
                code=t.order_book_id,
                side=t.side.name,
                price=px,
                open=a["open"],
                qty=q,
                order=int(t.order_id),
                reason=a["reason"],
                stage=a["p"],
                commission=float(t.commission),
                tax=float(t.tax),
                other=other,
                notional=px * q,
                group=asset_group(t.order_book_id),
            )
        )
        audit(abs(px - a["open"]) <= 1e-6, f"non-opening fill {d}")
        audit(t.side.name == a["side"], f"wrong side {d}")
        audit(
            q % 100 == 0 or (a["side"] == "SELL" and a["requested"] == a["held"]),
            f"illegal odd lot {d}",
        )
        a["filled"] += q
        audit(a["side"] != "SELL" or a["filled"] <= a["sellable"], f"T+1 violation {d}")
        if t.order_book_id == FOCUS:
            i = lookup[d]
            if a["reason"] == "SEED":
                plan.seed(a["filled"], int(capital * 0.25 / px / 100), px, i)
            elif a["side"] == "SELL":
                plan.sell(q, px, i)
            elif a["reason"] == "SLOT":
                audit(all(a["gates"]), f"gate violation {d}")
                plan.slot_px = (plan.slot_px * plan.slot + px * q) / (plan.slot + q)
                plan.slot += q
                plan.last_fill = i

    def on_reject(ctx, ev):
        rejects.append(dict(date=str(ctx.now.date()), code=ev.order_book_id, reason=str(ev.reason)))

    def init(ctx):
        env = Environment.get_instance()
        fees = TieredFees(env, white)
        for typ in (INSTRUMENT_TYPE.CS, INSTRUMENT_TYPE.ETF):
            env.set_transaction_cost_decider(typ, fees)
        subscribe_event(EVENT.TRADE, on_trade)
        subscribe_event(EVENT.ORDER_CREATION_REJECT, on_reject)

    def open_auction(ctx, bars):
        d = str(ctx.now.date())
        i = lookup[d]
        env = Environment.get_instance()
        if i == 0 and seed:
            pending[FOCUS] = dict(
                signal="INITIAL", code=FOCUS, p=2, reason="SEED", side="BUY", w=seed, qty=None
            )
        for a in sorted(pending.values(), key=lambda x: (x["p"], x["side"] == "BUY", x["code"])):
            sym, buy = a["code"], a["side"] == "BUY"
            # Freeze intention & signal independently from audit fields of this attempt.
            record = dict(a, date=d, filled=0, requested=0, status=None)
            orders.append(record)
            audit(
                a["signal"] == "INITIAL" or (i > 0 and a["signal"] == days[i - 1]),
                f"non-next-open {d}",
            )
            instrument = instruments(sym)
            pos = ctx.portfolio.positions[sym]
            held = int(pos.quantity)
            sellable = int(pos.sellable)
            record.update(held=held, sellable=sellable)
            bar = bars[sym]
            px = float(bar.open)
            record["open"] = px if isfinite(px) else None
            why = opening_block(
                px,
                bar.limit_up if buy else bar.limit_down,
                buy,
                not instrument.active_at(ctx.now)
                or env.data_proxy.is_suspended(sym, ctx.now.date()),
            )
            requested = None
            if not why:
                nav, cash = float(ctx.portfolio.total_value), float(ctx.portfolio.cash)
                if buy:
                    amount = min(max(0.0, a["w"] * nav - held * px), cash)
                    if a["reason"] == "SLOT":
                        room = max(0.0, nav * BUDGET[a["regime"]] - (nav - cash))
                        amount = min(amount, room, nav * 0.10)
                    requested = get_amount_from_value(amount, instrument, px, env, cash)
                    minimum = 1000 if sym in white else 5000
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
                if o is not None:
                    record.update(order=int(o.order_id), native_message=str(o.message))
                if not buy and record["filled"] < desired:
                    retries[sym] = dict(
                        a,
                        qty=desired - record["filled"],
                        w=None,
                        sell_est=desired - record["filled"],
                    )
                if not buy and record["filled"] == held:
                    armed.pop(sym, None)
            else:
                record["status"] = why
                if not buy and held and why != "NO_SELL_DELTA":
                    retries[sym] = a.copy()
        pending.clear()

    def close(ctx, bars):
        d = str(ctx.now.date())
        i = lookup[d]
        nav, cash = float(ctx.portfolio.total_value), float(ctx.portfolio.cash)
        pp = ctx.portfolio.positions
        held = {s: pp[s] for s in pp if pp[s].quantity > 0}
        w = {s: float(p.market_value / nav) for s, p in held.items()}
        pnl = Counter()
        for s in pp:
            pnl[asset_group(s)] += float(pp[s].daily_pnl)
        focus_w = w.get(FOCUS, 0.0)
        risk_row = risk.observe(i, nav, focus_w > 0.30 or any(plan.batches), enabled)
        regime, style = market[d]
        f = features[d]
        locked, l1 = risk_row["locked"], risk_row["l1"]
        row = dict(
            date=d,
            nav=nav,
            cash=cash,
            weights=w,
            risk=sum(w.values()),
            regime=regime,
            batches=list(plan.batches),
            slot=plan.slot,
            pnl=dict(pnl),
            **risk_row,
        )
        rows.append(row)
        for a in retries.values():
            merge(pending, dict(a, signal=d, original_signal=a.get("original_signal", a["signal"])))
        retries.clear()

        def add(p, sym, reason, side, weight=None, qty=None, **extra):
            sell_est = (
                (qty if qty is not None else int(held[sym].quantity * max(0, 1 - weight / w[sym])))
                if side == "SELL"
                else 0
            )
            merge(
                pending,
                dict(
                    signal=d,
                    code=sym,
                    p=p,
                    reason=reason,
                    side=side,
                    w=weight,
                    qty=qty,
                    sell_est=sell_est,
                    **extra,
                ),
            )

        if locked and row["risk"] > risk_row["cap"]:
            for s in held:
                add(0, s, "L2_REDUCE", "SELL", w[s] * risk_row["cap"] / row["risk"])
        for s, p in held.items():
            if s == FOCUS or s not in f:
                continue
            r = f[s]
            armed[s], why = exit_reason(
                r.raw,
                p.avg_price,
                r.raw * r.ma20 / r.c,
                r.raw * r.ma10 / r.c,
                armed.get(s, False),
                l1,
            )
            if why:
                add(1, s, why, "SELL", 0.0)
        if FOCUS in held and FOCUS in f:
            r = f[FOCUS]
            decision = plan.decision(
                r, i, focus_w, regime, l1 or locked, BUDGET[regime] - row["risk"]
            )
            if decision:
                reason, qty, wt = decision
                add(
                    2,
                    FOCUS,
                    reason,
                    "BUY" if reason == "SLOT" else "SELL",
                    wt,
                    abs(qty) if qty else None,
                    gates=[bool(v) for v in plan.gates(r, i)],
                    regime=regime,
                )
        align = (
            regime != state["regime"]
            or (state["locked"] and not locked)
            or i - state["align"] >= 10
        )
        if align and not locked:
            # Slot is a higher-priority claim; never allocate its cash twice.
            focus_budget = max(
                focus_w,
                (pending.get(FOCUS, {}).get("w") or 0.0)
                if pending.get(FOCUS, {}).get("side") == "BUY"
                else 0.0,
            )
            target = targets(regime, style, focus_budget, f)
            for s in sorted((set(held) | set(target)) - {FOCUS}):
                wt = target.get(s, 0.0)
                diff = wt - w.get(s, 0.0)
                if abs(diff) < 1e-12:
                    continue
                if wt and abs(diff) * nav < (1000 if s in white else 5000):
                    orders.append(
                        dict(
                            date=d,
                            signal=d,
                            code=s,
                            p=3,
                            reason="ALIGN",
                            side="BUY" if diff > 0 else "SELL",
                            status="SIGNAL_MINIMUM",
                            filled=0,
                        )
                    )
                    continue
                add(3, s, "ALIGN", "BUY" if diff > 0 else "SELL", wt)
            state["align"] = i
        state.update(regime=regime, locked=locked)
        audit(not locked or all(a["side"] == "SELL" for a in pending.values()), f"locked buy {d}")

    a = run_func(init=init, open_auction=open_auction, handle_bar=close, config=cfg)["sys_analyser"]
    eq = a["portfolio"]["total_value"]
    audit([str(d)[:10] for d in eq.index] == days == [r["date"] for r in rows], "calendar")
    for r, native in zip(rows, eq, strict=True):
        audit(
            isfinite(r["nav"]) and r["nav"] > 0 and abs(native - r["nav"]) <= 0.01,
            "NAV " + r["date"],
        )
        audit(isfinite(r["cash"]) and r["cash"] >= -0.01, "cash " + r["date"])
    audit(len(a.get("trades", [])) == len(fills), "analyser vs trade count")
    audit(not seed or any(f["reason"] == "SEED" for f in fills), "missing seed")
    audit(enabled or not any(r["locked"] for r in rows), "locked counterfactual")
    fees = defaultdict(list)
    for f in fills:
        fees[f["order"]].append(f)
    for oid, group in fees.items():
        notional = sum(f["notional"] for f in group)
        expected = notional * 0.00005 if group[0]["code"] in white else max(5.0, notional * 0.00025)
        audit(
            abs(expected - sum(f["commission"] for f in group)) <= 0.01
            and abs(sum(f["tax"] + f["other"] for f in group)) <= 0.01,
            f"ETF fees {oid}",
        )
    return dict(
        daily=rows,
        fills=fills,
        orders=orders,
        rejects=rejects,
        conflicts=conflicts,
        violations=violations,
        outstanding_at_end=list(pending.values()),
    )
