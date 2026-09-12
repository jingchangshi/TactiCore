#!/usr/bin/env python3
"""Batch 05 bounded S4C ERC robustness: one return-window dimension only."""
# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.experiments.batch_01_common import metric_row
from research.experiments.frozen_target_replay import freeze_pit_legal_schedule, replay_vectorbt
from research.experiments.run_s1_evidence_closure import PERIODS, period_metrics, rolling_table
from research.experiments.run_s4c_erc_skfolio_transfer import (
    MIN_ELIGIBLE,
    S4CConfig,
    SolverFailure,
    build_targets,
)
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs
from tacticore.strategies.multi_asset_trend import build_execution_weights, load_trend_config

ROOT = Path(__file__).resolve().parents[2]
RETURN_WINDOWS = (40, 60, 80)


def _rolling(candidate, comparator, years: int) -> pd.DataFrame:
    left = rolling_table(candidate)
    right = rolling_table(comparator).rename(
        columns={
            "cagr": "inverse_cagr",
            "sharpe": "inverse_sharpe",
            "max_drawdown": "inverse_max_drawdown",
        }
    )
    merged = left.merge(
        right[
            ["window_years", "window_end", "inverse_cagr", "inverse_sharpe", "inverse_max_drawdown"]
        ],
        on=["window_years", "window_end"],
    )
    merged = merged.loc[merged.window_years.eq(years)].copy()
    merged["sharpe_improves"] = merged.sharpe > merged.inverse_sharpe
    merged["max_drawdown_improves"] = merged.max_drawdown > merged.inverse_max_drawdown
    return merged


def _case(prices, risk_symbols, config, returns_window, mask, lifetimes):
    targets = build_targets(prices, risk_symbols, config, price_window=returns_window + 1)
    schedules = [
        freeze_pit_legal_schedule(prices, build_execution_weights(prices, frame), mask, lifetimes)
        for frame in targets[:3]
    ]
    starts = {start for _, start in schedules}
    if len(starts) != 1 or not all(
        schedule.index.equals(schedules[0][0].index) for schedule, _ in schedules
    ):
        raise RuntimeError("same-eligible controls must share corrected execution dates")
    runs = [
        replay_vectorbt(
            prices,
            schedule,
            fees=config.fees,
            slippage=config.slippage,
            initial_cash=config.initial_cash,
            tradability_mask=mask,
            lifetimes=lifetimes,
        )
        for schedule, _ in schedules
    ]
    return schedules, runs, targets[3]


def _decision(summary, periods, rolling, costs, reproduced):
    if not reproduced:
        return "BLOCK_S4C_ROBUSTNESS_REPRODUCTION"
    absolute = (
        (summary.cagr > 0).all()
        and (summary.sharpe > 0).all()
        and (summary.max_drawdown > -0.30).all()
    )
    relative = (
        (summary.cagr >= summary.inverse_cagr - 0.015)
        & (summary.max_drawdown >= summary.inverse_max_drawdown - 0.02)
        & (
            (summary.sharpe >= summary.inverse_sharpe + 0.02)
            | (summary.calmar >= summary.inverse_calmar + 0.03)
        )
    )
    center_periods = periods.loc[periods.returns_window.eq(60)]
    periods_ok = (center_periods.cagr > 0).all() and (
        (center_periods.sharpe > center_periods.inverse_sharpe)
        | (center_periods.calmar > center_periods.inverse_calmar)
    ).sum() >= 3
    rolling_ok = (
        rolling.loc[rolling.years.eq(3), "positive_cagr_share"].iloc[0] >= 0.90
        and rolling.loc[rolling.years.eq(5), "positive_cagr_share"].iloc[0] >= 0.95
        and rolling.loc[rolling.years.eq(3), "either_improves_share"].iloc[0] >= 0.60
    )
    cost = costs.loc[costs.cost_bps.eq(50)].iloc[0]
    return (
        "ADVANCE_S4C_TO_EXECUTION_REVIEW"
        if absolute
        and relative.sum() >= 2
        and periods_ok
        and rolling_ok
        and cost.cagr > 0
        and cost.sharpe >= 0.60
        else "REJECT_S4C_ROBUSTNESS"
    )


def main() -> None:
    strategy = load_trend_config(ROOT / "config/strategy.toml")
    config = S4CConfig(
        strategy.fallback_symbol, strategy.fees, strategy.slippage, strategy.initial_cash
    )
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))
    summaries, period_rows, rolling_rows = [], [], []
    center = None
    try:
        for returns_window in RETURN_WINDOWS:
            schedules, runs, diagnostics = _case(
                prices, strategy.risk_symbols, config, returns_window, mask, lifetimes
            )
            erc, equal, inverse = runs
            start = schedules[0][1]
            summaries.append(
                {
                    "returns_window": returns_window,
                    **metric_row("ERC", erc, start),
                    **{
                        f"inverse_{key}": value
                        for key, value in metric_row("INVERSE", inverse, start).items()
                        if key != "series"
                    },
                    **{
                        f"equal_{key}": value
                        for key, value in metric_row("EQUAL", equal, start).items()
                        if key != "series"
                    },
                }
            )
            for name, begin, end in PERIODS:
                candidate_metrics = period_metrics(erc.equity, erc.execution_weights, begin, end)
                inverse_metrics = period_metrics(
                    inverse.equity, inverse.execution_weights, begin, end
                )
                equal_metrics = period_metrics(equal.equity, equal.execution_weights, begin, end)
                period_rows.append(
                    {
                        "returns_window": returns_window,
                        "period": name,
                        **candidate_metrics,
                        **{f"inverse_{key}": value for key, value in inverse_metrics.items()},
                        **{f"equal_{key}": value for key, value in equal_metrics.items()},
                    }
                )
            if returns_window == 60:
                center = (schedules[0][0], erc, inverse, diagnostics, start)
                for years in (3, 5):
                    pair = _rolling(erc, inverse, years)
                    rolling_rows.append(
                        {
                            "years": years,
                            "positive_cagr_share": float(pair.cagr.gt(0).mean()),
                            "sharpe_improves_share": float(pair.sharpe_improves.mean()),
                            "max_drawdown_improves_share": float(pair.max_drawdown_improves.mean()),
                            "either_improves_share": float(
                                (pair.sharpe_improves | pair.max_drawdown_improves).mean()
                            ),
                        }
                    )
    except SolverFailure as error:
        print(f"decision=BLOCK_S4C_UPSTREAM_EXECUTION reason={error}")
        return
    if center is None:
        raise RuntimeError("missing frozen 60-return center")
    schedule, erc, inverse, diagnostics, start = center
    expected = pd.read_csv(ROOT / "research/results/s4c_pit_corrected_comparison_v1.csv").iloc[0]
    reproduced = all(
        abs(float(erc.metrics[key]) - float(expected[key])) < 1e-12
        for key in ("cagr", "max_drawdown", "sharpe", "calmar", "turnover")
    )
    costs = []
    for cost_bps in (15, 30, 50):
        result = replay_vectorbt(
            prices,
            schedule,
            fees=cost_bps / 10_000,
            slippage=0.0,
            initial_cash=config.initial_cash,
            tradability_mask=mask,
            lifetimes=lifetimes,
        )
        costs.append({"cost_bps": cost_bps, **metric_row("ERC_60", result, start)})
    summary, periods, rolling, costs_frame = map(
        pd.DataFrame, (summaries, period_rows, rolling_rows, costs)
    )
    active = diagnostics.loc[diagnostics.index >= start]
    concentration = active.loc[
        active.eligible_asset_count.ge(MIN_ELIGIBLE), ["maximum_weight", "effective_number_assets"]
    ]
    concentration_summary = pd.DataFrame(
        [
            {
                "median_maximum_weight": concentration.maximum_weight.median(),
                "p95_maximum_weight": concentration.maximum_weight.quantile(0.95),
                "maximum_observed_weight": concentration.maximum_weight.max(),
                "months_any_asset_gt_50pct": int(concentration.maximum_weight.gt(0.50).sum()),
                "median_effective_number_assets": concentration.effective_number_assets.median(),
                "p05_effective_number_assets": concentration.effective_number_assets.quantile(0.05),
            }
        ]
    )
    outcome = _decision(summary, periods, rolling, costs_frame, reproduced)
    output = ROOT / "research/results"
    for name, frame in (
        ("s4c_bounded_robustness_summary_v1.csv", summary),
        ("s4c_bounded_robustness_periods_v1.csv", periods),
        ("s4c_bounded_robustness_rolling_v1.csv", rolling),
        ("s4c_bounded_robustness_costs_v1.csv", costs_frame),
        ("s4c_bounded_robustness_concentration_v1.csv", concentration_summary),
    ):
        frame.to_csv(output / name, index=False)
    print(f"decision={outcome} reproduced={reproduced}")


if __name__ == "__main__":
    main()
