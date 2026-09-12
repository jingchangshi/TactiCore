#!/usr/bin/env python3
"""Run frozen S10A unlevered volatility-targeting historical adjudication."""

from pathlib import Path

import pandas as pd

from research.experiments.batch_01_common import metric_row, row
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.multi_asset_trend import build_execution_weights
from tacticore.strategies.volatility_targeting import (
    build_month_end_targets,
    load_volatility_targeting_config,
)

ROOT = Path(__file__).resolve().parents[2]


def decision(comparison: pd.DataFrame, diagnostics: pd.DataFrame) -> str:
    candidate = row(comparison, "S10A_UNLEVERED_VOL_TARGETING_V1")
    comparator = row(comparison, "MONTHLY_STATIC_25_25_25_25")
    average_scale = float(diagnostics["scale"].mean())
    if average_scale >= 0.95:
        return "REJECT_S10A_FILTER_DEGENERATION"
    if average_scale <= 0.40:
        return "REJECT_S10A_DEFENSIVE_DEGENERATION"
    absolute = candidate.cagr > 0 and candidate.sharpe >= 0.80 and candidate.max_drawdown > -0.25
    relative = (
        candidate.max_drawdown >= comparator.max_drawdown + 0.02
        and candidate.cagr >= comparator.cagr - 0.015
        and (candidate.sharpe > comparator.sharpe or candidate.calmar > comparator.calmar)
    )
    if absolute and relative:
        return "ADVANCE_S10A_VOL_TARGETING_TO_ROBUSTNESS"
    return "REJECT_S10A_VOL_TARGETING"


def main() -> None:
    config = load_volatility_targeting_config(ROOT / "config/s10a_vol_targeting.toml")
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    tradability_mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))
    targets, diagnostics = build_month_end_targets(prices, config)
    execution = build_execution_weights(prices, targets)
    static_targets = pd.DataFrame(0.0, index=targets.index, columns=prices.columns)
    static_targets.loc[:, list(config.symbols)] = list(config.base_weights)
    static_execution = build_execution_weights(prices, static_targets)
    start = execution.dropna(how="all").index[0]
    common = dict(
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=start,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )
    candidate = run_target_weights(prices, execution, **common)
    comparator = run_target_weights(prices, static_execution, **common)
    comparison = pd.DataFrame(
        [
            metric_row("S10A_UNLEVERED_VOL_TARGETING_V1", candidate, start),
            metric_row("MONTHLY_STATIC_25_25_25_25", comparator, start),
        ]
    )
    output = ROOT / "research/results"
    diagnostics.to_csv(output / "s10a_vol_targeting_diagnostics_v1.csv")
    comparison.to_csv(output / "s10a_vol_targeting_comparison_v1.csv", index=False)
    outcome = decision(comparison, diagnostics.loc[diagnostics.index >= start])
    print(f"decision={outcome}\n{comparison.to_csv(index=False)}")


if __name__ == "__main__":
    main()
