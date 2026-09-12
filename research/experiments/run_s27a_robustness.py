#!/usr/bin/env python3
# ruff: noqa: E501
"""Predeclared one-factor-at-a-time S27A robustness screen."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from research.experiments.batch_01_common import metric_row
from research.experiments.run_s1_evidence_closure import period_metrics, rolling_table
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.inverse_vol_allocation import valid_return_volatility
from tacticore.strategies.multi_asset_trend import (
    build_execution_weights,
    build_signal_change_execution_weights,
    load_trend_config,
    valid_observation_moving_average,
)
from tacticore.strategies.multi_asset_trend import (
    build_month_end_targets as build_s2_targets,
)
from tacticore.strategies.trend_inverse_vol import load_trend_inverse_vol_config

ROOT = Path(__file__).resolve().parents[2]
TREND_WINDOWS = (160, 180, 200, 220, 240)
VOL_WINDOWS = (40, 60, 80)
PERIODS = (
    ("2013-2016", "2013-03-29", "2016-12-31"),
    ("2017-2019", "2017-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-2026", "2023-01-01", "2026-08-31"),
)


@dataclass(frozen=True)
class RobustnessSpec:
    """Experiment-only generalization of the frozen S27A target formula."""

    trend_window: int
    vol_window: int
    fallback_symbol: str
    fees: float
    slippage: float
    initial_cash: float


def build_targets(
    prices: pd.DataFrame, spec: RobustnessSpec, risk_symbols: tuple[str, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reproduce S27A's formula while varying only its predeclared windows."""
    risk = prices.loc[:, list(risk_symbols)]
    average = valid_observation_moving_average(risk, spec.trend_window)
    volatility = valid_return_volatility(risk, spec.vol_window)
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=ends, columns=prices.columns)
    diagnostics: list[dict[str, object]] = []
    for date in ends:
        eligible = average.loc[date].notna() & volatility.loc[date].notna() & risk.loc[date].notna()
        positive = eligible & risk.loc[date].gt(average.loc[date]) & volatility.loc[date].gt(0)
        symbols = list(positive[positive].index)
        budget = len(symbols) / len(risk_symbols)
        if symbols:
            raw = 1.0 / volatility.loc[date, symbols]
            targets.loc[date, symbols] = budget * raw / raw.sum()
        targets.loc[date, spec.fallback_symbol] = 1.0 - budget
        diagnostics.append(
            {
                "signal_date": date,
                "positive_asset_count": len(symbols),
                "risk_budget": budget,
                "fallback_weight": 1.0 - budget,
            }
        )
    return targets, pd.DataFrame(diagnostics).set_index("signal_date")


def run_case(prices: pd.DataFrame, spec: RobustnessSpec, symbols: tuple[str, ...], tradability_mask, lifetimes):
    targets, diagnostics = build_targets(prices, spec, symbols)
    execution = build_execution_weights(prices, targets)
    start = execution.dropna(how="all").index[0]
    result = run_target_weights(
        prices,
        execution,
        fees=spec.fees,
        slippage=spec.slippage,
        initial_cash=spec.initial_cash,
        metric_start=start,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )
    return result, diagnostics, start


def decision(
    summary: pd.DataFrame,
    periods: pd.DataFrame,
    rolling: pd.DataFrame,
    costs: pd.DataFrame,
    reproduced: bool,
) -> str:
    if not reproduced:
        return "BLOCK_S27A_ROBUSTNESS_REPRODUCTION"
    baseline = summary.query("trend_window == 200 and vol_window == 60").iloc[0]
    trend = summary.query("vol_window == 60")
    vol = summary.query("trend_window == 200")
    trend_pass = (trend.cagr > 0).all() and (
        (trend.cagr >= 0.7 * baseline.cagr)
        & (trend.sharpe >= 0.7 * baseline.sharpe)
        & (trend.max_drawdown > -0.25)
    ).sum() >= 4
    vol_pass = (
        (vol.cagr > 0).all()
        and (vol.sharpe > 0).all()
        and (vol.max_drawdown > -0.25).all()
        and (vol.sharpe >= 0.8 * baseline.sharpe).sum() >= 2
    )
    periods_pass = (periods.cagr > 0).all()
    rolling_pass = (rolling.query("years == 3").cagr_positive_share >= 0.9).all() and (
        rolling.query("years == 5").cagr_positive_share >= 0.95
    ).all()
    cost_pass = (
        costs.query("cost_bps == 50").iloc[0].cagr > 0
        and costs.query("cost_bps == 50").iloc[0].sharpe >= 0.5
    )
    return (
        "ADVANCE_S27A_TO_EXECUTION_REVIEW"
        if trend_pass and vol_pass and periods_pass and rolling_pass and cost_pass
        else "REJECT_S27A_ROBUSTNESS"
    )


def main() -> None:
    base = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    s2 = load_trend_config(ROOT / "config/strategy.toml")
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    tradability_mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))
    frozen = RobustnessSpec(
        trend_window=base.trend_window,
        vol_window=base.vol_window,
        fallback_symbol=base.fallback_symbol,
        fees=base.fees,
        slippage=base.slippage,
        initial_cash=base.initial_cash,
    )
    rows, period_rows, rolling_rows = [], [], []
    cases = [(window, 60) for window in TREND_WINDOWS] + [
        (200, window) for window in VOL_WINDOWS if window != 60
    ]
    for trend_window, vol_window in cases:
        result, _, start = run_case(
            prices,
            RobustnessSpec(
                trend_window=trend_window,
                vol_window=vol_window,
                fallback_symbol=frozen.fallback_symbol,
                fees=frozen.fees,
                slippage=frozen.slippage,
                initial_cash=frozen.initial_cash,
            ),
            s2.risk_symbols, tradability_mask, lifetimes,
        )
        rows.append(
            {
                "trend_window": trend_window,
                "vol_window": vol_window,
                **metric_row("S27A", result, start),
            }
        )
        for name, begin, end in PERIODS:
            equity = result.equity.loc[begin:end]
            period_rows.append(
                {
                    "trend_window": trend_window,
                    "vol_window": vol_window,
                    "period": name,
                    **period_metrics(
                        result.equity, result.execution_weights, equity.index[0], equity.index[-1]
                    ),
                }
            )
        table = rolling_table(result).rename(columns={"window_years": "years"})
        for years, group in table.groupby("years"):
            rolling_rows.append(
                {
                    "trend_window": trend_window,
                    "vol_window": vol_window,
                    "years": years,
                    "cagr_positive_share": float((group.cagr > 0).mean()),
                }
            )
    summary, periods, rolling = (
        pd.DataFrame(rows),
        pd.DataFrame(period_rows),
        pd.DataFrame(rolling_rows),
    )
    baseline_result, _, baseline_start = run_case(prices, frozen, s2.risk_symbols, tradability_mask, lifetimes)
    cost_rows = []
    baseline_targets, _ = build_targets(prices, frozen, s2.risk_symbols)
    baseline_execution = build_execution_weights(prices, baseline_targets)
    for cost_bps in (15, 30, 50):
        result = run_target_weights(
            prices,
            baseline_execution,
            fees=cost_bps / 10_000,
            slippage=0.0,
            initial_cash=frozen.initial_cash,
            metric_start=baseline_start,
            tradability_mask=tradability_mask,
            lifetimes=lifetimes,
        )
        cost_rows.append({"cost_bps": cost_bps, **metric_row("S27A", result, baseline_start)})
    costs = pd.DataFrame(cost_rows)
    s2_targets = build_s2_targets(prices, s2)
    s2_execution = build_signal_change_execution_weights(prices, s2_targets)
    s2_result = run_target_weights(
        prices,
        s2_execution,
        fees=frozen.fees,
        slippage=frozen.slippage,
        initial_cash=frozen.initial_cash,
        metric_start=baseline_start,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )
    s30 = pd.read_csv(ROOT / "research/results/s30_static_allocation_comparison_v1.csv")
    comparators = pd.DataFrame(
        [
            metric_row("S27A_200_60", baseline_result, baseline_start),
            metric_row("S2_V2B_FIXED_SLEEVE", s2_result, baseline_start),
            s30.iloc[0].to_dict(),
        ]
    )
    reproduced = bool(abs(float(baseline_result.metrics["cagr"]) - 0.0778665897002686) < 1e-12)
    outcome = decision(summary, periods, rolling, costs, reproduced)
    output = ROOT / "research/results"
    summary.to_csv(output / "s27a_robustness_summary_v1.csv", index=False)
    periods.to_csv(output / "s27a_robustness_periods_v1.csv", index=False)
    rolling.to_csv(output / "s27a_robustness_rolling_v1.csv", index=False)
    costs.to_csv(output / "s27a_robustness_costs_v1.csv", index=False)
    comparators.to_csv(output / "s27a_robustness_comparators_v1.csv", index=False)
    print(f"decision={outcome}\n{summary.to_csv(index=False)}")


if __name__ == "__main__":
    main()
