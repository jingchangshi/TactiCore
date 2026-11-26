"""Native RQAlpha 6.3.0 full V3 single-account replay (ETF + BOTTOM_GRIND_25 + BP1)."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import isfinite
from typing import Any

import numpy as np
from rqalpha import run_func
from rqalpha.const import INSTRUMENT_TYPE
from rqalpha.core.events import EVENT
from rqalpha.environment import Environment
from rqalpha.mod.rqalpha_mod_sys_accounts.trade_utils import get_amount_from_value
from rqalpha.mod.rqalpha_mod_sys_transaction_cost.deciders import StockTransactionCostDecider
from rqalpha.mod.utils import round_order_quantity

from research.ashare.v3_data_202611 import BUNDLE_PATH_202611
from tacticore.engines.rqalpha_adapter import build_rqalpha_config

from .policy import BUDGET, FOCUS, GOLD, SECTORS, Plan, Risk, exit_reason, targets


class TieredFees:
    def __init__(self, env: Any, white: set[str]) -> None:
        self.white = white
        self.super = StockTransactionCostDecider(0.00005 / 0.0008, 0, 0, False, env.event_bus)
        self.normal = StockTransactionCostDecider(0.00025 / 0.0008, 5, 1, False, env.event_bus)

    def calc(self, args: Any) -> Any:
        base = (self.super if args.instrument.order_book_id in self.white else self.normal).calc(
            args
        )
        if args.instrument.type == INSTRUMENT_TYPE.CS:
            return base._replace(other_fees=args.price * args.quantity * 0.00001)
        return base


def opening_block(px: float, limit: float, buy: bool, suspended: bool) -> str | None:
    if suspended or not isfinite(px) or px <= 0:
        return "SUSPENDED_OR_MISSING_OPEN"
    if limit > 0 and ((buy and px >= limit - 1e-7) or (not buy and px <= limit + 1e-7)):
        return "LIMIT_UP" if buy else "LIMIT_DOWN"
    return None


def asset_group(code: str, stock_codes: set[str] | None = None) -> str:
    if code == FOCUS:
        return "concentrated"
    if code == GOLD:
        return "gold"
    if stock_codes is not None and code in stock_codes:
        return "stock"
    main_pf = ("000", "001", "002", "003", "600", "601", "603", "605")
    if code.endswith((".XSHG", ".XSHE")) and code[:3] in main_pf:
        return "stock"
    return "industry" if code in SECTORS else "broad"


def replay_full_account(
    days: list[str],
    market: dict[str, tuple[str, str]],
    features: dict[str, dict[str, Any]],
    stock_candidates: dict[str, list[Any]],
    white: set[str],
    capital: float,
    seed: float,
    enabled: bool,
    *,
    enable_stocks: bool = True,
) -> dict[str, Any]:
    from rqalpha.api import history_bars, instruments, order_shares, subscribe_event

    lookup = {d: i for i, d in enumerate(days)}
    rows, orders, fills, rejects, conflicts, violations = [], [], [], [], [], []
    pending: dict[str, dict[str, Any]] = {}
    retries: dict[str, dict[str, Any]] = {}
    armed: dict[str, bool] = {}
    stock_stops: dict[str, dict[str, Any]] = {}
    risk, plan = Risk(capital), Plan()
    state: dict[str, Any] = {"regime": None, "align": -100, "locked": False, "active": None}
    stock_slip_drag = [0.0]

    cfg = build_rqalpha_config(
        days[0],
        days[-1],
        initial_cash=capital,
        fees=0.00025,
        slippage=0,
        bundle_path=BUNDLE_PATH_202611,
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
                win, lose = old, a
            else:
                win, lose = a, old
            conflicts.append(
                {"date": a["signal"], "code": sym, "kept": win["reason"], "dropped": lose["reason"]}
            )
            book[sym] = win
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
                "group": grp,
            }
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
        # Process lowest numerical priority first; sells execute before buys.
        for a in sorted(pending.values(), key=lambda x: (x["p"], x["side"] == "BUY", x["code"])):
            sym, buy = a["code"], a["side"] == "BUY"
            record = dict(a, date=d, filled=0, requested=0, status=None)
            orders.append(record)
            audit(
                a["signal"] == "INITIAL" or (i > 0 and a["signal"] == days[i - 1]),
                f"non-next-open {d}",
            )
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

            requested = None
            if not why:
                nav, cash = float(ctx.portfolio.total_value), float(ctx.portfolio.cash)
                if buy:
                    if is_stock:
                        stop_pct = float(a.get("stop_pct", 0.08))
                        risk_per_share = max(px * stop_pct, px * 0.02)
                        room_amt = max(0.0, BUDGET[a["regime"]] * nav - (nav - cash))
                        cap_val = min(
                            (nav * 0.013) / risk_per_share * px,
                            nav * 0.18,
                            room_amt,
                            cash * 0.996,
                        )
                        requested = get_amount_from_value(cap_val, instrument, px, env, cash)
                        minimum = 8000.0
                    else:
                        amount = min(max(0.0, a["w"] * nav - held * px), cash)
                        if a["reason"] == "SLOT":
                            room = max(0.0, nav * BUDGET[a["regime"]] - (nav - cash))
                            amount = min(amount, room, nav * 0.10)
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
            pnl[asset_group(s)] += float(pp[s].daily_pnl)
        focus_w = w.get(FOCUS, 0.0)
        risk_row = risk.observe(i, nav, focus_w > 0.30 or any(plan.batches), enabled)
        regime, style = market[d]
        f = features[d]
        locked, l1 = risk_row["locked"], risk_row["l1"]

        row = {
            "date": d,
            "nav": nav,
            "net_nav_after_5bp_stock_slip": max(1.0, nav - stock_slip_drag[0]),
            "stock_slip_drag": stock_slip_drag[0],
            "cash": cash,
            "weights": w,
            "risk": sum(w.values()),
            "regime": regime,
            "batches": list(plan.batches),
            "slot": plan.slot,
            "pnl": dict(pnl),
            **risk_row,
        }
        rows.append(row)
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
            if side == "SELL":
                sell_est = (
                    qty
                    if qty is not None
                    else int(held[sym].quantity * max(0.0, 1.0 - weight / w[sym]))
                )
            else:
                sell_est = 0
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

        # Priority 0: L2 hard cap reduction
        if locked and row["risk"] > risk_row["cap"]:
            for s in held:
                add(0, s, "L2_REDUCE", "SELL", w[s] * risk_row["cap"] / row["risk"])

        # Priority 1: Exits (both non-focus ETFs and BP1 stocks under v3.2.1 rules)
        active_stocks: set[str] = set()
        for s, p in held.items():
            if s == FOCUS:
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
                struct_stop = cost * (1.0 - float(meta["stop_pct"]))
                armed[s], why = exit_reason(
                    c_close,
                    cost,
                    ma20,
                    ma10,
                    armed.get(s, False),
                    l1,
                    stock=True,
                    structural_stop=struct_stop,
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

        # Priority 2: 159558 BOTTOM_GRIND_25
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

        # Priority 3: BP1_PULLBACK Stock Pioneer (max 2 stocks, OFFENSIVE/STRUCTURAL, not locked/l1)
        stock_buy_budget = 0.0
        kept_stocks = {s for s in active_stocks if pending.get(s, {}).get("side") != "SELL"}
        current_stock_w = sum(w[s] for s in kept_stocks)
        slots_left = max(0, 2 - len(active_stocks))
        if enable_stocks and regime != "DEFENSIVE" and not locked and not l1 and slots_left > 0:
            focus_committed = max(
                focus_w,
                (pending.get(FOCUS, {}).get("w") or 0.0)
                if pending.get(FOCUS, {}).get("side") == "BUY"
                else 0.0,
            )
            total_avail_room = max(0.0, BUDGET[regime] - focus_committed - current_stock_w)
            for cand in stock_candidates.get(d, []):
                if slots_left <= 0 or total_avail_room < 0.08:
                    break
                ob = cand.order_book_id
                if ob in held or ob in pending:
                    continue
                stop_pct = min(0.08, max(0.025, 1.0 - cand.hard_stop_raw / cand.ref_close_raw))
                est_w = min(0.013 / max(stop_pct, 0.02), 0.18, total_avail_room)
                if est_w * nav < 8000.0:
                    continue
                add(3, ob, "BP1_ENTRY", "BUY", est_w, None, stop_pct=stop_pct, regime=regime)
                stock_buy_budget += est_w
                total_avail_room -= est_w
                slots_left -= 1

        # Priority 4: ETF chassis & sector alignment (never double-spend focus or stock budget)
        align = (
            regime != state["regime"]
            or (state["locked"] and not locked)
            or i - state["align"] >= 10
        )
        if align and not locked:
            focus_budget = max(
                focus_w,
                (pending.get(FOCUS, {}).get("w") or 0.0)
                if pending.get(FOCUS, {}).get("side") == "BUY"
                else 0.0,
            )
            occupied = focus_budget + current_stock_w + stock_buy_budget
            target = targets(regime, style, occupied, f)
            for s in sorted((set(held) - active_stocks | set(target)) - {FOCUS}):
                wt = target.get(s, 0.0)
                diff = wt - w.get(s, 0.0)
                if abs(diff) < 1e-12:
                    continue
                if wt and abs(diff) * nav < (1000.0 if s in white else 5000.0):
                    orders.append(
                        {
                            "date": d,
                            "signal": d,
                            "code": s,
                            "p": 4,
                            "reason": "ALIGN",
                            "side": "BUY" if diff > 0 else "SELL",
                            "status": "SIGNAL_MINIMUM",
                            "filled": 0,
                        }
                    )
                    continue
                add(4, s, "ALIGN", "BUY" if diff > 0 else "SELL", wt)
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

    fees: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for f in fills:
        fees[f["order"]].append(f)
    for oid, group in fees.items():
        notional = sum(f["notional"] for f in group)
        if group[0]["group"] == "stock":
            expected_comm = max(5.0, notional * 0.00025)
            expected_tax = notional * 0.0005 if group[0]["side"] == "SELL" else 0.0
            expected_other = notional * 0.00001
            audit(
                abs(expected_comm - sum(f["commission"] for f in group)) <= 0.02
                and abs(expected_tax - sum(f["tax"] for f in group)) <= 0.02
                and abs(expected_other - sum(f["other"] for f in group)) <= 0.02,
                f"CS fees {oid}",
            )
        else:
            if group[0]["code"] in white:
                expected = notional * 0.00005
            else:
                expected = max(5.0, notional * 0.00025)
            audit(
                abs(expected - sum(f["commission"] for f in group)) <= 0.01
                and abs(sum(f["tax"] + f["other"] for f in group)) <= 0.01,
                f"ETF fees {oid}",
            )
    return {
        "daily": rows,
        "fills": fills,
        "orders": orders,
        "rejects": rejects,
        "conflicts": conflicts,
        "violations": violations,
        "outstanding_at_end": list(pending.values()),
    }
