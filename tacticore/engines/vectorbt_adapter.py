from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

from tacticore.strategies.global_dual_momentum import (
    GlobalDualMomentumConfig,
    build_execution_weights,
    build_month_end_targets,
)


@dataclass(frozen=True)
class ResearchResult:
    equity: pd.Series
    execution_weights: pd.DataFrame
    metrics: dict[str, float]
    portfolio: Any


def _calculate_metrics(
    equity: pd.Series, execution_weights: pd.DataFrame, portfolio: Any
) -> dict[str, float]:
    returns = equity.pct_change().dropna()
    elapsed_years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / elapsed_years) - 1.0
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    sharpe = float(np.sqrt(252) * returns.mean() / returns.std(ddof=1))
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else float("nan")

    targets = execution_weights.dropna(how="all").fillna(0.0)
    turnover = 0.0
    if not targets.empty:
        turnover = 1.0 + float(targets.diff().abs().sum(axis=1).iloc[1:].sum() / 2.0)
    trades = portfolio.trades.records_readable
    holding_period = trades["Exit Timestamp"] - trades["Entry Timestamp"]
    average_holding_days = float(holding_period.dt.total_seconds().mean() / 86400.0)
    return {
        "cagr": float(cagr),
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "calmar": calmar,
        "turnover": turnover,
        "trade_count": float(len(trades)),
        "average_holding_days": average_holding_days,
    }


def run_vectorbt(prices: pd.DataFrame, config: GlobalDualMomentumConfig) -> ResearchResult:
    """运行月频双动量 baseline；VectorBT 只负责研究探索与指标输出。"""
    targets = build_month_end_targets(prices, config)
    execution_weights = build_execution_weights(prices, targets)
    portfolio = vbt.Portfolio.from_orders(
        close=prices,
        size=execution_weights,
        size_type="targetpercent",
        group_by=True,
        cash_sharing=True,
        call_seq="auto",
        fees=config.fees,
        slippage=config.slippage,
        init_cash=config.initial_cash,
        freq="1D",
    )
    equity = portfolio.value(group_by=True)
    metrics = _calculate_metrics(equity, execution_weights, portfolio)
    return ResearchResult(equity, execution_weights, metrics, portfolio)
