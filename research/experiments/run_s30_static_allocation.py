#!/usr/bin/env python3
# ruff: noqa: E501
"""Run frozen S30 static strategic-allocation reference baseline."""

from pathlib import Path

import pandas as pd

from research.experiments.batch_01_common import metric_row
from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.static_strategic_allocation import (
    build_execution_weights,
    load_static_allocation_config,
)

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    config = load_static_allocation_config(ROOT / "config/s30_static_allocation.toml")
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    execution = build_execution_weights(prices, config)
    start = execution.dropna(how="all").index[0]
    result = run_target_weights(
        prices,
        execution,
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=start,
    )
    comparison = pd.DataFrame([metric_row("S30_REFERENCE_V1", result, start)])
    output = ROOT / "research/results"
    comparison.to_csv(output / "s30_static_allocation_comparison_v1.csv", index=False)
    result.equity.loc[start:].resample("YE").last().pct_change().dropna().rename("return").to_csv(
        output / "s30_static_allocation_annual_returns_v1.csv"
    )
    print("decision=REFERENCE_BASELINE\n" + comparison.to_csv(index=False))


if __name__ == "__main__":
    main()
