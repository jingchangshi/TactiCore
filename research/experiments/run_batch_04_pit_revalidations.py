#!/usr/bin/env python3
# ruff: noqa: E501
"""仅以 Batch 04 PIT inception 修正既有 S27A/S10A/S4C 历史 replay。"""

from pathlib import Path

import pandas as pd

from research.experiments.batch_01_common import metric_row
from research.experiments.run_s4c_erc_skfolio_transfer import S4CConfig
from research.experiments.run_s4c_erc_skfolio_transfer import build_targets as s4c_targets
from research.experiments.run_s10a_robustness import RobustnessSpec
from research.experiments.run_s10a_robustness import build_targets as s10_targets
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import (
    build_tradability_mask,
    first_executable_complete_target,
    lifetimes_from_universe,
    validate_execution_targets,
)
from tacticore.data.universe import load_universe
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.multi_asset_trend import build_execution_weights, load_trend_config
from tacticore.strategies.trend_inverse_vol import build_month_end_targets as s27_targets
from tacticore.strategies.trend_inverse_vol import load_trend_inverse_vol_config
from tacticore.strategies.volatility_targeting import load_volatility_targeting_config

ROOT = Path(__file__).resolve().parents[2]


def executable(prices, targets, mask, lifetimes):
    execution = build_execution_weights(prices, targets)
    start = first_executable_complete_target(execution, mask)
    corrected = execution.copy()
    corrected.loc[corrected.index < start] = float("nan")
    validate_execution_targets(corrected, prices, mask, lifetimes)
    return corrected, start


def evaluate(
    prices, execution, start, *, fees, slippage, initial_cash, tradability_mask, lifetimes
):
    return run_target_weights(
        prices,
        execution,
        fees=fees,
        slippage=slippage,
        initial_cash=initial_cash,
        metric_start=start,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )


def main() -> None:
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    universe = load_universe(ROOT / "config/universe.csv")
    lifetimes = lifetimes_from_universe(universe)
    mask = build_tradability_mask(prices.index, list(prices.columns), lifetimes, prices)
    trend = load_trend_config(ROOT / "config/strategy.toml")
    s27 = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    s27_execution, s27_start = executable(
        prices, s27_targets(prices, s27, trend.risk_symbols)[0], mask, lifetimes
    )
    s27_result = evaluate(
        prices,
        s27_execution,
        s27_start,
        fees=s27.fees,
        slippage=s27.slippage,
        initial_cash=s27.initial_cash,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )
    s10 = load_volatility_targeting_config(ROOT / "config/s10a_vol_targeting.toml")
    spec = RobustnessSpec(
        s10.symbols,
        s10.base_weights,
        s10.vol_window,
        s10.target_volatility,
        s10.max_scale,
        s10.min_scale,
        s10.fees,
        s10.slippage,
        s10.initial_cash,
    )
    s10_execution, s10_start = executable(prices, s10_targets(prices, spec)[0], mask, lifetimes)
    s10_result = evaluate(
        prices,
        s10_execution,
        s10_start,
        fees=s10.fees,
        slippage=s10.slippage,
        initial_cash=s10.initial_cash,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )
    s4c_targets_frame, _, _, s4c_diagnostics = s4c_targets(
        prices,
        trend.risk_symbols,
        S4CConfig(trend.fallback_symbol, trend.fees, trend.slippage, trend.initial_cash),
    )
    s4c_execution, s4c_start = executable(prices, s4c_targets_frame, mask, lifetimes)
    s4c_result = evaluate(
        prices,
        s4c_execution,
        s4c_start,
        fees=trend.fees,
        slippage=trend.slippage,
        initial_cash=trend.initial_cash,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )
    s27_summary = pd.DataFrame([metric_row("S27A_PIT_CORRECTED", s27_result, s27_start)]).assign(
        corrected_inception=s27_start.date().isoformat(),
        decision="RESTORE_S27A_EXECUTION_REVIEW_ELIGIBILITY"
        if s27_result.metrics["cagr"] > 0
        else "REJECT_S27A_AFTER_PIT_CORRECTION",
    )
    s10_summary = pd.DataFrame(
        [metric_row("S10A_20_10_PIT_CORRECTED", s10_result, s10_start)]
    ).assign(
        corrected_inception=s10_start.date().isoformat(),
        decision="RESTORE_S10A_EXECUTION_REVIEW_ELIGIBILITY"
        if s10_result.metrics["max_drawdown"] > -0.20
        else "REJECT_S10A_AFTER_CORRECTNESS_CLOSURE",
    )
    s4c_summary = pd.DataFrame([metric_row("S4C_PIT_CORRECTED", s4c_result, s4c_start)]).assign(
        corrected_inception=s4c_start.date().isoformat(),
        coverage=float(
            s4c_diagnostics.loc[s4c_diagnostics.index >= s4c_start, "eligible_asset_count"]
            .ge(6)
            .mean()
        ),
        decision="RESTORE_S4C_ROBUSTNESS_ELIGIBILITY"
        if s4c_result.metrics["sharpe"] >= 0.50
        else "DO_NOT_ADVANCE_S4C_AFTER_PIT_CORRECTION",
    )
    output = ROOT / "research/results"
    s27_summary.to_csv(output / "s27a_pit_corrected_summary_v1.csv", index=False)
    s10_summary.to_csv(output / "s10a_corrected_robustness_summary_v1.csv", index=False)
    s4c_summary.to_csv(output / "s4c_pit_corrected_comparison_v1.csv", index=False)
    print(pd.concat([s27_summary, s10_summary, s4c_summary], ignore_index=True).to_csv(index=False))


if __name__ == "__main__":
    main()
