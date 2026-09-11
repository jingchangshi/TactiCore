#!/usr/bin/env python3
# ruff: noqa: E501
"""Run frozen S27A trend plus inverse-volatility historical screen."""

from pathlib import Path

import pandas as pd

from research.experiments.batch_01_common import metric_row, row
from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.multi_asset_trend import build_execution_weights, load_trend_config
from tacticore.strategies.multi_asset_trend import build_month_end_targets as s2_targets
from tacticore.strategies.trend_inverse_vol import (
    build_month_end_targets,
    load_trend_inverse_vol_config,
)

ROOT = Path(__file__).resolve().parents[2]


def decision(comparison: pd.DataFrame) -> str:
    candidate, comparator = (
        row(comparison, "S27A_TREND_INVERSE_VOL_V1"),
        row(comparison, "S2_V2B_COMPARATOR_REPRODUCTION_ONLY"),
    )
    absolute = (
        candidate.cagr >= 0.05 and candidate.sharpe >= 0.60 and candidate.max_drawdown > -0.30
    )
    relative = (
        candidate.cagr >= comparator.cagr - 0.01
        and candidate.max_drawdown >= comparator.max_drawdown - 0.02
        and candidate.sharpe > comparator.sharpe
        and candidate.calmar >= comparator.calmar
        and candidate.turnover <= 1.5 * comparator.turnover
    )
    return "ADVANCE_S27A_TO_ROBUSTNESS" if absolute and relative else "REJECT_S27A_BASELINE"


def main() -> None:
    config = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    s2 = load_trend_config(ROOT / "config/strategy.toml")
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    targets, diagnostics = build_month_end_targets(prices, config, s2.risk_symbols)
    execution = build_execution_weights(prices, targets)
    s2_execution = build_execution_weights(prices, s2_targets(prices, s2))
    start = execution.dropna(how="all").index[0]
    common = dict(
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=start,
    )
    candidate = run_target_weights(prices, execution, **common)
    comparator = run_target_weights(prices, s2_execution, **common)
    comparison = pd.DataFrame(
        [
            metric_row("S27A_TREND_INVERSE_VOL_V1", candidate, start),
            metric_row("S2_V2B_COMPARATOR_REPRODUCTION_ONLY", comparator, start),
        ]
    )
    outcome = decision(comparison)
    output = ROOT / "research/results"
    comparison.to_csv(output / "s27a_trend_inverse_vol_comparison_v1.csv", index=False)
    diagnostics.to_csv(output / "s27a_trend_inverse_vol_diagnostics_v1.csv")
    print(f"decision={outcome}\n{comparison.to_csv(index=False)}")


if __name__ == "__main__":
    main()
