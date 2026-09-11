#!/usr/bin/env python3
# ruff: noqa: E501
"""Run frozen S4A inverse-volatility historical economic screen."""

from pathlib import Path

import pandas as pd

from research.experiments.batch_01_common import metric_row, row
from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.inverse_vol_allocation import (
    build_month_end_targets,
    load_inverse_vol_config,
)
from tacticore.strategies.multi_asset_trend import build_execution_weights, load_trend_config

ROOT = Path(__file__).resolve().parents[2]


def decision(comparison: pd.DataFrame, diagnostics: pd.DataFrame) -> str:
    candidate, comparator = (
        row(comparison, "S4A_INVERSE_VOL_V1"),
        row(comparison, "ELIGIBLE_EQUAL_WEIGHT_MULTI_ASSET"),
    )
    if diagnostics["eligible_asset_count"].ge(6).mean() < 0.8:
        return "BLOCK_S4A_COVERAGE"
    absolute = candidate.cagr > 0 and candidate.sharpe >= 0.45 and candidate.max_drawdown > -0.35
    relative = (
        candidate.max_drawdown >= comparator.max_drawdown + 0.03
        and candidate.cagr >= comparator.cagr - 0.015
        and candidate.sharpe >= comparator.sharpe + 0.03
    )
    return "ADVANCE_S4A_TO_ROBUSTNESS" if absolute and relative else "REJECT_S4A_BASELINE"


def main() -> None:
    config = load_inverse_vol_config(ROOT / "config/s4_inverse_vol.toml")
    s2 = load_trend_config(ROOT / "config/strategy.toml")
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    targets, diagnostics = build_month_end_targets(prices, config, s2.risk_symbols)
    equal, _ = build_month_end_targets(prices, config, s2.risk_symbols, equal_weight=True)
    start = build_execution_weights(prices, targets).dropna(how="all").index[0]
    common = dict(
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=start,
    )
    candidate = run_target_weights(prices, build_execution_weights(prices, targets), **common)
    comparator = run_target_weights(prices, build_execution_weights(prices, equal), **common)
    comparison = pd.DataFrame(
        [
            metric_row("S4A_INVERSE_VOL_V1", candidate, start),
            metric_row("ELIGIBLE_EQUAL_WEIGHT_MULTI_ASSET", comparator, start),
        ]
    )
    diagnostics["max_target_weight"] = targets.loc[diagnostics.index, list(s2.risk_symbols)].max(
        axis=1
    )
    outcome = decision(comparison, diagnostics.loc[diagnostics.index >= start])
    output = ROOT / "research/results"
    comparison.to_csv(output / "s4a_inverse_vol_comparison_v1.csv", index=False)
    diagnostics.to_csv(output / "s4a_inverse_vol_diagnostics_v1.csv")
    print(f"decision={outcome}\n{comparison.to_csv(index=False)}")


if __name__ == "__main__":
    main()
