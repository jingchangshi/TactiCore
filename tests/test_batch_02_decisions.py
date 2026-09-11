import numpy as np
import pandas as pd

from research.experiments.run_s10a_vol_targeting import decision as s10a_decision
from research.experiments.run_s27a_robustness import (
    RobustnessSpec,
    build_targets,
)
from research.experiments.run_s27a_robustness import (
    decision as s27a_decision,
)
from tacticore.strategies.trend_inverse_vol import (
    TrendInverseVolConfig,
    build_month_end_targets,
)


def test_s27a_experiment_evaluator_reproduces_frozen_target_formula() -> None:
    dates = pd.bdate_range("2024-01-02", periods=260)
    symbols = ("A", "B", "C")
    prices = pd.DataFrame(
        {
            symbol: 100 * np.cumprod(np.full(len(dates), 1.001 + index * 0.0001))
            for index, symbol in enumerate(symbols)
        },
        index=dates,
    )
    frozen = TrendInverseVolConfig(200, 60, "monthly", "C", 0.001, 0.0005, 1_000_000)
    actual, _ = build_targets(
        prices, RobustnessSpec(200, 60, "C", 0.001, 0.0005, 1_000_000), symbols
    )
    expected, _ = build_month_end_targets(prices, frozen, symbols)
    pd.testing.assert_frame_equal(actual, expected)


def test_s27a_decision_requires_every_predeclared_gate() -> None:
    summary = pd.DataFrame(
        [
            {
                "trend_window": window,
                "vol_window": 60,
                "cagr": 0.08,
                "sharpe": 1.0,
                "max_drawdown": -0.12,
            }
            for window in (160, 180, 200, 220, 240)
        ]
        + [
            {
                "trend_window": 200,
                "vol_window": window,
                "cagr": 0.08,
                "sharpe": 1.0,
                "max_drawdown": -0.12,
            }
            for window in (40, 80)
        ]
    )
    periods = pd.DataFrame({"cagr": [0.01] * 28})
    rolling = pd.DataFrame({"years": [3] * 7 + [5] * 7, "cagr_positive_share": [0.95] * 14})
    costs = pd.DataFrame(
        {"cost_bps": [15, 30, 50], "cagr": [0.07, 0.06, 0.05], "sharpe": [0.9, 0.7, 0.5]}
    )
    assert (
        s27a_decision(summary, periods, rolling, costs, True) == "ADVANCE_S27A_TO_EXECUTION_REVIEW"
    )
    assert (
        s27a_decision(summary, periods, rolling, costs, False)
        == "BLOCK_S27A_ROBUSTNESS_REPRODUCTION"
    )
    costs.loc[costs.cost_bps.eq(50), "sharpe"] = 0.49
    assert s27a_decision(summary, periods, rolling, costs, True) == "REJECT_S27A_ROBUSTNESS"


def test_s10a_decision_prioritizes_degeneration_and_requires_relative_gate() -> None:
    comparison = pd.DataFrame(
        [
            {
                "series": "S10A_UNLEVERED_VOL_TARGETING_V1",
                "cagr": 0.07,
                "max_drawdown": -0.18,
                "sharpe": 0.9,
                "calmar": 0.4,
            },
            {
                "series": "MONTHLY_STATIC_25_25_25_25",
                "cagr": 0.08,
                "max_drawdown": -0.21,
                "sharpe": 0.8,
                "calmar": 0.38,
            },
        ]
    )
    diagnostics = pd.DataFrame({"scale": [0.7, 0.8]})
    assert s10a_decision(comparison, diagnostics) == "ADVANCE_S10A_VOL_TARGETING_TO_ROBUSTNESS"
    assert (
        s10a_decision(comparison, pd.DataFrame({"scale": [0.95]}))
        == "REJECT_S10A_FILTER_DEGENERATION"
    )
    assert (
        s10a_decision(comparison, pd.DataFrame({"scale": [0.4]}))
        == "REJECT_S10A_DEFENSIVE_DEGENERATION"
    )
