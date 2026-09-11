#!/usr/bin/env python3
# ruff: noqa: E501
"""Run frozen S8A equity/bond trend historical economic screen."""

from pathlib import Path

import pandas as pd

from research.experiments.batch_01_common import metric_row, row
from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.equity_bond_trend import (
    build_month_end_targets,
    load_equity_bond_trend_config,
)
from tacticore.strategies.multi_asset_trend import (
    build_signal_change_execution_weights,
)

ROOT = Path(__file__).resolve().parents[2]


def decision(comparison: pd.DataFrame) -> str:
    candidate, equity, balanced = (
        row(comparison, "S8A_EQUITY_BOND_TREND_V1"),
        row(comparison, "510300_BUY_AND_HOLD"),
        row(comparison, "STATIC_50_50_EQUITY_BOND"),
    )
    absolute = (
        candidate.cagr > 0
        and candidate.sharpe >= 0.45
        and candidate.max_drawdown > -0.35
        and candidate.annualized_target_change_count <= 6
    )
    against_equity = (
        candidate.max_drawdown >= equity.max_drawdown + 0.10
        and candidate.cagr >= equity.cagr - 0.02
        and candidate.sharpe > equity.sharpe
        and candidate.calmar > equity.calmar
    )
    wins = sum(
        candidate[key] > balanced[key] for key in ["cagr", "max_drawdown", "sharpe", "calmar"]
    )
    return (
        "ADVANCE_S8A_TO_ROBUSTNESS"
        if absolute
        and against_equity
        and wins >= 2
        and candidate.max_drawdown >= balanced.max_drawdown
        else "REJECT_S8A_BASELINE"
    )


def main() -> None:
    config = load_equity_bond_trend_config(ROOT / "config/s8_equity_bond_trend.toml")
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    targets, states = build_month_end_targets(prices, config)
    execution = build_signal_change_execution_weights(prices, targets)
    start = execution.dropna(how="all").index[0]
    common = dict(
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=start,
    )
    candidate = run_target_weights(prices, execution, **common)
    buy_hold = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    buy_hold.loc[start, config.equity_symbol] = 1.0
    equity = run_target_weights(prices, buy_hold, **common)
    balanced_execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    balanced_target = pd.Series(0.0, index=prices.columns)
    balanced_target.loc[[config.equity_symbol, config.bond_symbol]] = 0.5
    balanced_execution.loc[start] = balanced_target
    year_ends = (
        prices.loc[start:]
        .groupby(pd.DatetimeIndex(prices.loc[start:].index).to_period("Y"))
        .tail(1)
        .index
    )
    for signal_date in year_ends:
        location = int(prices.index.get_loc(signal_date)) + 1
        if location < len(prices.index):
            balanced_execution.iloc[location] = balanced_target
    balanced = run_target_weights(prices, balanced_execution, **common)
    comparison = pd.DataFrame(
        [
            metric_row("S8A_EQUITY_BOND_TREND_V1", candidate, start),
            metric_row("510300_BUY_AND_HOLD", equity, start),
            metric_row("STATIC_50_50_EQUITY_BOND", balanced, start),
        ]
    )
    outcome = decision(comparison)
    output = ROOT / "research/results"
    comparison.to_csv(output / "s8a_equity_bond_comparison_v1.csv", index=False)
    states.to_csv(output / "s8a_equity_bond_states_v1.csv")
    print(f"decision={outcome}\n{comparison.to_csv(index=False)}")


if __name__ == "__main__":
    main()
