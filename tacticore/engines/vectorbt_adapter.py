from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

from tacticore.data.tradability import AssetLifetime, validate_execution_targets
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
    equity: pd.Series,
    execution_weights: pd.DataFrame,
    portfolio: Any,
    metric_start: pd.Timestamp,
) -> dict[str, float]:
    equity = equity.loc[metric_start:]
    returns = equity.pct_change().dropna()
    elapsed_years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / elapsed_years) - 1.0
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    # 零方差（横盘、空仓或只有一条收益）时 Sharpe 无定义：既不是 0 风险也不是
    # 无限可加杠杆。按约定记 0.0（"无风险调整信号"），而不是让 0/0 产生
    # RuntimeWarning 与 NaN 污染下游比较。
    returns_std = float(returns.std(ddof=1))
    if returns.empty or not np.isfinite(returns_std) or returns_std == 0.0:
        sharpe = 0.0
    else:
        sharpe = float(np.sqrt(252) * returns.mean() / returns_std)
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else float("nan")

    targets = execution_weights.loc[metric_start:].dropna(how="all").fillna(0.0)
    turnover = 0.0
    if not targets.empty:
        # 首次执行从全现金建仓：单边换手等于该行目标权重的绝对值之和（满仓即 1.0），
        # 与 execution_audit 的 `1 + Σ|Δtarget| / 2` 口径一致。若该行是 no-signal
        # 全零目标，则没有建仓、换手为 0，而不是凭空记 1.0。后续调仓按
        # Σ|Δtarget| / 2 计单边换手。
        initial_turnover = float(targets.iloc[0].abs().sum())
        subsequent_turnover = float(targets.diff().abs().sum(axis=1).iloc[1:].sum() / 2.0)
        turnover = initial_turnover + subsequent_turnover
    trades = portfolio.trades.records_readable
    trades = trades.loc[trades["Exit Timestamp"] >= metric_start].copy()
    effective_entry = trades["Entry Timestamp"].clip(lower=metric_start)
    holding_period = trades["Exit Timestamp"] - effective_entry
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


def run_vectorbt(
    prices: pd.DataFrame,
    config: GlobalDualMomentumConfig,
    *,
    metric_start: pd.Timestamp | None = None,
    tradability_mask: pd.DataFrame,
    lifetimes: dict[str, AssetLifetime],
) -> ResearchResult:
    """运行月频双动量 baseline；VectorBT 只负责研究探索与指标输出。"""
    targets = build_month_end_targets(prices, config)
    execution_weights = build_execution_weights(prices, targets)
    return run_target_weights(
        prices,
        execution_weights,
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=metric_start,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )


def run_target_weights(
    prices: pd.DataFrame,
    execution_weights: pd.DataFrame,
    *,
    fees: float,
    slippage: float,
    initial_cash: float,
    metric_start: pd.Timestamp | None = None,
    tradability_mask: pd.DataFrame,
    lifetimes: dict[str, AssetLifetime],
) -> ResearchResult:
    """将策略已生成的目标权重交给 VectorBT 执行和记账。"""
    validate_execution_targets(execution_weights, prices, tradability_mask, lifetimes)
    portfolio = vbt.Portfolio.from_orders(
        close=prices,
        size=execution_weights,
        size_type="targetpercent",
        group_by=True,
        cash_sharing=True,
        call_seq="auto",
        fees=fees,
        slippage=slippage,
        init_cash=initial_cash,
        freq="1D",
    )
    equity = portfolio.value(group_by=True)
    executions = execution_weights.dropna(how="all")
    if executions.empty:
        raise ValueError("价格区间不足以生成可执行信号")
    first_execution = executions.index[0]
    first_execution_location = int(prices.index.get_indexer(pd.Index([first_execution]))[0])
    default_metric_start = prices.index[max(first_execution_location - 1, 0)]
    evaluation_start = metric_start or default_metric_start
    if evaluation_start not in equity.index:
        raise ValueError("metric_start 必须是价格数据中的交易日")
    metrics = _calculate_metrics(equity, execution_weights, portfolio, evaluation_start)
    return ResearchResult(equity, execution_weights, metrics, portfolio)
