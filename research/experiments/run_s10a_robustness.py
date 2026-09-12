#!/usr/bin/env python3
# ruff: noqa: E501
"""预注册的 S10A 单因素稳健性检验。"""

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from research.experiments.batch_01_common import metric_row, row
from research.experiments.run_s1_evidence_closure import period_metrics, rolling_table
from research.metrics import drawdown_better, drawdown_no_worse
from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import ResearchResult, run_target_weights
from tacticore.strategies.multi_asset_trend import build_execution_weights
from tacticore.strategies.volatility_targeting import (
    build_month_end_targets as build_frozen_targets,
)
from tacticore.strategies.volatility_targeting import load_volatility_targeting_config

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = (10, 20, 40)
TARGETS = (0.08, 0.10, 0.12)
PERIODS = (
    ("2013-2016", "2013-03-29", "2016-12-31"),
    ("2017-2019", "2017-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-2026", "2023-01-01", "2026-08-31"),
)


@dataclass(frozen=True)
class RobustnessSpec:
    symbols: tuple[str, ...]
    base_weights: tuple[float, ...]
    vol_window: int
    target_volatility: float
    max_scale: float
    min_scale: float
    fees: float
    slippage: float
    initial_cash: float


def fixed_period_drawdown_gate(periods: pd.DataFrame) -> bool:
    return (
        periods.apply(
            lambda row: drawdown_no_worse(row.max_drawdown, row.comparator_max_drawdown), axis=1
        ).sum()
        >= 3
    )


def build_targets(prices: pd.DataFrame, spec: RobustnessSpec) -> tuple[pd.DataFrame, pd.DataFrame]:
    """在实验层重现冻结公式，只暴露预注册的两个单因素。"""
    base = prices.loc[:, list(spec.symbols)]
    returns = base.pct_change(fill_method=None).dropna(how="any")
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=ends, columns=prices.columns)
    diagnostics: list[dict[str, object]] = []
    bond = spec.symbols[-1]
    for date in ends:
        history = returns.loc[:date].tail(spec.vol_window)
        if len(history) != spec.vol_window:
            realized, scale = float("nan"), spec.min_scale
        else:
            base_return = history.mul(spec.base_weights, axis=1).sum(axis=1)
            realized = float(base_return.std(ddof=1) * np.sqrt(252))
            scale = max(spec.min_scale, min(spec.max_scale, spec.target_volatility / realized))
        target = pd.Series(0.0, index=prices.columns)
        target.loc[list(spec.symbols)] = np.array(spec.base_weights) * scale
        target.loc[bond] += 1.0 - scale
        targets.loc[date] = target
        diagnostics.append(
            {
                "signal_date": date,
                "realized_vol": realized,
                "scale": scale,
                "risk_reduction": 1 - scale,
                "bond_weight": target[bond],
            }
        )
    return targets, pd.DataFrame(diagnostics).set_index("signal_date")


def static_targets(prices: pd.DataFrame, spec: RobustnessSpec) -> pd.DataFrame:
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=ends, columns=prices.columns)
    targets.loc[:, list(spec.symbols)] = list(spec.base_weights)
    return targets


def run_case(
    prices: pd.DataFrame, spec: RobustnessSpec
) -> tuple[ResearchResult, ResearchResult, pd.DataFrame, pd.Timestamp]:
    targets, diagnostics = build_targets(prices, spec)
    execution = build_execution_weights(prices, targets)
    start = execution.dropna(how="all").index[0]
    common = dict(
        fees=spec.fees,
        slippage=spec.slippage,
        initial_cash=spec.initial_cash,
        metric_start=start,
    )
    candidate = run_target_weights(prices, execution, **common)
    comparator = run_target_weights(
        prices, build_execution_weights(prices, static_targets(prices, spec)), **common
    )
    return candidate, comparator, diagnostics.loc[diagnostics.index >= start], start


def decision(
    summary: pd.DataFrame,
    periods: pd.DataFrame,
    rolling: pd.DataFrame,
    costs: pd.DataFrame,
    reproduced: bool,
) -> str:
    if not reproduced:
        return "BLOCK_S10A_ROBUSTNESS_REPRODUCTION"
    variants = summary.loc[summary.series.ne("MONTHLY_STATIC_25_25_25_25")]
    absolute = (
        (variants.cagr > 0).all()
        and (variants.sharpe > 0).all()
        and (variants.max_drawdown > -0.20).all()
    )
    relative = (
        (variants.cagr >= variants.comparator_cagr - 0.015)
        & variants.apply(
            lambda row: drawdown_better(row.max_drawdown, row.comparator_max_drawdown), axis=1
        )
        & (
            (variants.sharpe > variants.comparator_sharpe)
            | (variants.calmar > variants.comparator_calmar)
        )
    )
    window_pass = relative.loc[variants.dimension.eq("window")].sum() >= 2
    target_variants = variants.loc[
        variants.vol_window.eq(20) & variants.target_volatility.isin(TARGETS)
    ]
    target_pass = relative.loc[target_variants.index].sum() >= 2
    central = variants.loc[(variants.vol_window == 20) & (variants.target_volatility == 0.10)].iloc[
        0
    ]
    central_scale_pass = 0.40 < central.average_scale < 0.95
    target_scale_pass = (
        (target_variants.average_scale > 0.40) & (target_variants.average_scale < 0.95)
    ).sum() >= 2
    central_periods = periods.loc[periods.series.eq("S10A_20_10")]
    period_pass = (
        (central_periods.cagr > 0).all()
        and fixed_period_drawdown_gate(central_periods)
        and (
            (central_periods.sharpe > central_periods.comparator_sharpe)
            | (central_periods.calmar > central_periods.comparator_calmar)
        ).sum()
        >= 3
    )
    central_rolling = rolling.loc[rolling.series.eq("S10A_20_10")]
    rolling_pass = (
        (central_rolling.loc[central_rolling.years.eq(3), "cagr_positive_share"] >= 0.90).all()
        and (central_rolling.loc[central_rolling.years.eq(5), "cagr_positive_share"] >= 0.95).all()
        and (
            central_rolling.loc[central_rolling.years.eq(3), "either_improves_share"] >= 0.60
        ).all()
    )
    cost = costs.loc[costs.cost_bps.eq(50)].iloc[0]
    cost_pass = cost.cagr > 0 and cost.sharpe >= 0.70
    if all(
        (
            absolute,
            window_pass,
            target_pass,
            central_scale_pass,
            target_scale_pass,
            period_pass,
            rolling_pass,
            cost_pass,
        )
    ):
        return "ADVANCE_S10A_TO_EXECUTION_REVIEW"
    return "REJECT_S10A_ROBUSTNESS"


def _rolling_pair(
    candidate: ResearchResult, comparator: ResearchResult, label: str
) -> pd.DataFrame:
    left = rolling_table(candidate).rename(columns={"window_years": "years"})
    right = rolling_table(comparator).rename(
        columns={
            "window_years": "years",
            "cagr": "comparator_cagr",
            "sharpe": "comparator_sharpe",
            "max_drawdown": "comparator_max_drawdown",
        }
    )
    merged = left.merge(
        right[
            [
                "years",
                "window_end",
                "comparator_cagr",
                "comparator_sharpe",
                "comparator_max_drawdown",
            ]
        ],
        on=["years", "window_end"],
    )
    merged["either_improves"] = (merged.sharpe > merged.comparator_sharpe) | (
        merged.max_drawdown > merged.comparator_max_drawdown
    )
    return (
        merged.groupby("years", as_index=False)
        .agg(
            cagr_positive_share=("cagr", lambda values: float((values > 0).mean())),
            sharpe_improves_share=(
                "sharpe",
                lambda values: float(
                    (values > merged.loc[values.index, "comparator_sharpe"]).mean()
                ),
            ),
            max_drawdown_improves_share=(
                "max_drawdown",
                lambda values: float(
                    (values > merged.loc[values.index, "comparator_max_drawdown"]).mean()
                ),
            ),
            either_improves_share=("either_improves", "mean"),
        )
        .assign(series=label)
    )


def main() -> None:
    config = load_volatility_targeting_config(ROOT / "config/s10a_vol_targeting.toml")
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    frozen = RobustnessSpec(
        config.symbols,
        config.base_weights,
        config.vol_window,
        config.target_volatility,
        config.max_scale,
        config.min_scale,
        config.fees,
        config.slippage,
        config.initial_cash,
    )
    existing_targets, _ = build_frozen_targets(prices, config)
    generalized_targets, _ = build_targets(prices, frozen)
    reproduced_targets = existing_targets.equals(generalized_targets)
    cases = [("window", value, 0.10) for value in WINDOWS] + [
        ("target", 20, value) for value in TARGETS if value != 0.10
    ]
    summary_rows, period_rows, rolling_rows = [], [], []
    baseline_result = None
    baseline_start = None
    for dimension, window, target_vol in cases:
        spec = replace(frozen, vol_window=window, target_volatility=target_vol)
        candidate, comparator, diagnostics, start = run_case(prices, spec)
        label = f"S10A_{window}_{int(target_vol * 100)}"
        candidate_row = metric_row(label, candidate, start)
        comparison_row = metric_row("MONTHLY_STATIC_25_25_25_25", comparator, start)
        summary_rows.append(
            {
                "dimension": dimension,
                "vol_window": window,
                "target_volatility": target_vol,
                "average_scale": diagnostics.scale.mean(),
                **candidate_row,
                **{
                    f"comparator_{key}": value
                    for key, value in comparison_row.items()
                    if key != "series"
                },
            }
        )
        for name, begin, end in PERIODS:
            candidate_window = candidate.equity.loc[begin:end]
            comparator_window = comparator.equity.loc[begin:end]
            actual_start = max(candidate_window.index[0], comparator_window.index[0])
            actual_end = min(candidate_window.index[-1], comparator_window.index[-1])
            period_rows.append(
                {
                    "series": label,
                    "period": name,
                    **period_metrics(
                        candidate.equity, candidate.execution_weights, actual_start, actual_end
                    ),
                    **{
                        f"comparator_{key}": value
                        for key, value in period_metrics(
                            comparator.equity,
                            comparator.execution_weights,
                            actual_start,
                            actual_end,
                        ).items()
                    },
                }
            )
        rolling_rows.extend(_rolling_pair(candidate, comparator, label).to_dict("records"))
        if window == 20 and target_vol == 0.10:
            baseline_result, baseline_start = candidate, start
    if baseline_result is None or baseline_start is None:
        raise RuntimeError("缺少 S10A 中心规格")
    costs = []
    execution = build_execution_weights(prices, generalized_targets)
    for cost_bps in (15, 30, 50):
        result = run_target_weights(
            prices,
            execution,
            fees=cost_bps / 10_000,
            slippage=0.0,
            initial_cash=frozen.initial_cash,
            metric_start=baseline_start,
        )
        costs.append({"cost_bps": cost_bps, **metric_row("S10A_20_10", result, baseline_start)})
    summary, periods, rolling, costs_frame = (
        pd.DataFrame(summary_rows),
        pd.DataFrame(period_rows),
        pd.DataFrame(rolling_rows),
        pd.DataFrame(costs),
    )
    baseline = summary.loc[(summary.vol_window.eq(20)) & (summary.target_volatility.eq(0.10))].iloc[
        0
    ]
    expected = pd.read_csv(ROOT / "research/results/s10a_vol_targeting_comparison_v1.csv")
    expected_row = row(expected, "S10A_UNLEVERED_VOL_TARGETING_V1")
    reproduced = reproduced_targets and all(
        abs(float(baseline[key]) - float(expected_row[key])) < 1e-12
        for key in ("cagr", "max_drawdown", "sharpe", "calmar", "turnover")
    )
    outcome = decision(summary, periods, rolling, costs_frame, reproduced)
    output = ROOT / "research/results"
    for name, frame in (
        ("s10a_robustness_summary_v1.csv", summary),
        ("s10a_robustness_periods_v1.csv", periods),
        ("s10a_robustness_rolling_v1.csv", rolling),
        ("s10a_robustness_costs_v1.csv", costs_frame),
    ):
        frame.to_csv(output / name, index=False)
    print(f"decision={outcome}\n{summary.to_csv(index=False)}")


if __name__ == "__main__":
    main()
