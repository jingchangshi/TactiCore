"""FIFO round-trip trade analytics and calendar return/win-rate audits for EXP-V3-11."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class _BuyLot:
    qty: int
    price: float
    fee_total: float
    orig_qty: int
    date: pd.Timestamp


def _summarize_trade_list(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "avg_win_pct": None,
            "avg_loss_pct": None,
            "payoff_ratio": None,
            "profit_factor": None,
            "net_expectancy_pct": None,
            "total_realized_pnl_yuan": 0.0,
            "max_consecutive_losses": 0,
            "avg_holding_days": None,
        }

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))

    avg_win_pct = float(np.mean([t["net_ret"] * 100.0 for t in wins])) if wins else None
    avg_loss_pct = (
        float(np.mean([t["net_ret"] * 100.0 for t in losses])) if losses else None
    )
    if wins and losses:
        mean_win_abs = float(np.mean([t["net_ret"] for t in wins]))
        mean_loss_abs = abs(float(np.mean([t["net_ret"] for t in losses])))
        payoff_ratio: float | None = mean_win_abs / mean_loss_abs if mean_loss_abs > 1e-12 else None
    else:
        payoff_ratio = None

    if gross_loss > 1e-9:
        profit_factor: float | None = float(gross_win / gross_loss)
    elif gross_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = None

    max_consec = 0
    cur_consec = 0
    for t in trades:
        if t["net_pnl"] <= 0:
            cur_consec += 1
            if cur_consec > max_consec:
                max_consec = cur_consec
        else:
            cur_consec = 0

    return {
        "closed_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades), 4),
        "avg_win_pct": round(avg_win_pct, 3) if avg_win_pct is not None else None,
        "avg_loss_pct": round(avg_loss_pct, 3) if avg_loss_pct is not None else None,
        "payoff_ratio": round(payoff_ratio, 3) if payoff_ratio is not None else None,
        "profit_factor": (
            round(profit_factor, 3)
            if profit_factor is not None and np.isfinite(profit_factor)
            else None
        ),
        "net_expectancy_pct": round(float(np.mean([t["net_ret"] * 100.0 for t in trades])), 3),
        "total_realized_pnl_yuan": round(float(sum(t["net_pnl"] for t in trades)), 2),
        "max_consecutive_losses": max_consec,
        "avg_holding_days": round(float(np.mean([t["hold_days"] for t in trades])), 1),
    }


def compute_roundtrip_stats(
    fills: list[dict[str, Any]],
    group_fn: Callable[[str], str],
) -> dict[str, Any]:
    """Match BUY fills against SELL fills via strict FIFO per symbol.

    Each SELL event generates one realized round-trip trade aggregating the matched
    FIFO cost basis and proportional entry/exit commissions, stamp tax, transfer fees,
    and explicit stock slippage.
    """
    lots_by_code: dict[str, deque[_BuyLot]] = defaultdict(deque)
    trades_all: list[dict[str, Any]] = []
    trades_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)

    sorted_fills = sorted(
        fills,
        key=lambda f: (
            str(f["date"]),
            0 if str(f["side"]).upper() == "BUY" else 1,
            int(f.get("order_id", f.get("order", 0))),
            str(f["code"]),
        ),
    )

    for fill in sorted_fills:
        code = str(fill["code"])
        side = str(fill["side"]).upper()
        qty = int(fill.get("qty", fill.get("quantity", 0)))
        price = float(fill["price"])
        dt = pd.Timestamp(str(fill["date"]))
        if qty <= 0 or price <= 0:
            continue
        fee_total = (
            float(fill.get("commission", 0.0))
            + float(fill.get("tax", 0.0))
            + float(fill.get("other", 0.0))
            + float(fill.get("stock_slip_5bp", 0.0))
        )

        if side == "BUY":
            lots_by_code[code].append(
                _BuyLot(qty=qty, price=price, fee_total=fee_total, orig_qty=qty, date=dt)
            )
            continue

        if side != "SELL":
            continue

        q_left = qty
        matched_qty = 0
        buy_cost_total = 0.0
        weighted_hold_days = 0.0
        queue = lots_by_code[code]

        while q_left > 0 and queue:
            lot = queue[0]
            take = min(q_left, lot.qty)
            alloc_buy_fee = lot.fee_total * (take / lot.orig_qty)
            buy_cost_total += take * lot.price + alloc_buy_fee
            weighted_hold_days += max(1, (dt - lot.date).days) * take
            matched_qty += take
            q_left -= take
            lot.qty -= take
            if lot.qty == 0:
                queue.popleft()

        if matched_qty <= 0 or buy_cost_total <= 0:
            continue

        sell_fee_alloc = fee_total * (matched_qty / qty)
        sell_rev = matched_qty * price - sell_fee_alloc
        net_pnl = sell_rev - buy_cost_total
        net_ret = net_pnl / buy_cost_total
        grp = group_fn(code)
        rec = {
            "date": str(dt.date()),
            "code": code,
            "group": grp,
            "qty": matched_qty,
            "buy_cost": buy_cost_total,
            "sell_rev": sell_rev,
            "net_pnl": net_pnl,
            "net_ret": net_ret,
            "hold_days": weighted_hold_days / matched_qty,
        }
        trades_all.append(rec)
        trades_by_group[grp].append(rec)

    open_qty_by_group: dict[str, int] = defaultdict(int)
    for code, queue in lots_by_code.items():
        rem = sum(lot.qty for lot in queue)
        if rem > 0:
            open_qty_by_group[group_fn(code)] += rem

    return {
        "overall": _summarize_trade_list(trades_all),
        "by_sleeve": {
            grp: _summarize_trade_list(tlist) for grp, tlist in sorted(trades_by_group.items())
        },
        "open_shares_at_end": dict(sorted(open_qty_by_group.items())),
    }


def compute_calendar_stats(equity: pd.Series) -> dict[str, Any]:
    """Compute return, drawdown, risk-adjusted ratios, and daily/monthly/annual win rates."""
    eq = equity.dropna().astype(float)
    if len(eq) < 2:
        raise ValueError("equity series requires at least 2 observations")
    ret = eq.pct_change(fill_method=None).iloc[1:]
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1.0 / 365.25)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0)
    total_ret = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
    dd = float((eq / eq.cummax() - 1.0).min())
    std = float(ret.std())
    ann_vol = std * float(np.sqrt(252.0))
    sharpe = float(ret.mean() / std * np.sqrt(252.0)) if std > 1e-12 else 0.0
    downside = ret.clip(upper=0.0)
    down_rms = float(np.sqrt((downside**2).mean()))
    sortino = float(ret.mean() / down_rms * np.sqrt(252.0)) if down_rms > 1e-12 else 0.0
    calmar = float(cagr / abs(dd)) if dd < -1e-12 else 0.0

    nonzero = ret[ret.abs() > 1e-12]
    daily_wr = float((nonzero > 0).mean()) if len(nonzero) > 0 else 0.0

    # Monthly, quarterly, annual returns compounded cleanly from first eq observation per period
    def _period_rets(freq: str) -> pd.Series:
        grouped = eq.groupby(eq.index.to_period(freq))
        vals: list[float] = []
        keys: list[str] = []
        prev_end: float | None = None
        for per, grp in grouped:
            base = float(eq.iloc[0]) if prev_end is None else prev_end
            end_v = float(grp.iloc[-1])
            vals.append(end_v / base - 1.0)
            keys.append(str(per))
            prev_end = end_v
        return pd.Series(vals, index=keys, dtype=float)

    m_ret = _period_rets("M")
    q_ret = _period_rets("Q")
    y_ret = _period_rets("Y")

    return {
        "total_return": total_ret,
        "cagr": cagr,
        "max_drawdown": dd,
        "annual_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "calmar": round(calmar, 4),
        "final_nav": round(float(eq.iloc[-1]), 2),
        "daily_win_rate": round(daily_wr, 4),
        "monthly_positive": int((m_ret > 0).sum()),
        "monthly_total": int(len(m_ret)),
        "monthly_win_rate": round(float((m_ret > 0).mean()), 4),
        "quarterly_positive": int((q_ret > 0).sum()),
        "quarterly_total": int(len(q_ret)),
        "quarterly_win_rate": round(float((q_ret > 0).mean()), 4),
        "annual_positive": int((y_ret > 0).sum()),
        "annual_total": int(len(y_ret)),
        "annual_win_rate": round(float((y_ret > 0).mean()), 4),
        "annual_returns": {k: round(float(v), 4) for k, v in y_ret.items()},
    }
