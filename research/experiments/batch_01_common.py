# ruff: noqa: E501
"""Small, batch-specific presentation helpers; VectorBT remains the portfolio engine."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tacticore.engines.vectorbt_adapter import ResearchResult


def metric_row(name: str, result: ResearchResult, start: pd.Timestamp) -> dict[str, float | str]:
    equity = result.equity.loc[start:]
    annual = equity.resample("YE").last().pct_change().dropna()
    executions = result.execution_weights.loc[start:].dropna(how="all")
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    return {
        "series": name,
        **result.metrics,
        "worst_year": float(annual.min()),
        "target_change_count": float(len(executions)),
        "annualized_target_change_count": float(len(executions) / years),
    }


def annual_returns(result: ResearchResult, start: pd.Timestamp) -> pd.Series:
    return result.equity.loc[start:].resample("YE").last().pct_change().dropna()


def markdown_metrics(row: pd.Series) -> str:
    return (
        f"CAGR {row.cagr:.2%}，最大回撤 {row.max_drawdown:.2%}，Sharpe {row.sharpe:.3f}，"
        f"Calmar {row.calmar:.3f}，最差年度 {row.worst_year:.2%}，turnover {row.turnover:.2f}，"
        f"交易 {row.trade_count:.0f}，平均持有 {row.average_holding_days:.1f} 天，"
        f"年化目标变化 {row.annualized_target_change_count:.2f}。"
    )


def versions() -> dict[str, str]:
    import numpy
    import pandas
    import vectorbt

    return {
        "vectorbt": vectorbt.__version__,
        "pandas": pandas.__version__,
        "numpy": numpy.__version__,
    }


def row(comparison: pd.DataFrame, series: str) -> pd.Series:
    return comparison.loc[comparison["series"].eq(series)].iloc[0]


def serializable(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (value.item() if hasattr(value, "item") else value) for key, value in metrics.items()
    }
