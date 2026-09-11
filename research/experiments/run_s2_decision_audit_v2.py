#!/usr/bin/env python3
# ruff: noqa: E501
"""审计 S2 数据可用性语义，并检验低触达执行方案。"""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.experiments.run_s1_evidence_closure import (
    annual_returns,
    period_metrics,
    realized_turnover,
    rolling_table,
)
from research.experiments.run_s2_economic_screen import (
    COST_BPS,
    assert_frozen_baseline,
    benchmark_table,
)
from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import ResearchResult, run_target_weights
from tacticore.strategies.multi_asset_trend import (
    MultiAssetTrendConfig,
    build_execution_weights,
    build_month_end_targets,
    build_signal_change_execution_weights,
    build_strict_month_end_targets,
    load_trend_config,
    valid_observation_moving_average,
)

ROOT = Path(__file__).resolve().parents[2]
PERIODS = (
    ("2013-2016", "2013-03-29", "2016-12-31"),
    ("2017-2019", "2017-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-2026", "2023-01-01", "2026-08-31"),
)


def run_variant(
    prices: pd.DataFrame,
    config: MultiAssetTrendConfig,
    targets: pd.DataFrame,
    *,
    signal_change_only: bool,
    metric_start: pd.Timestamp,
    total_cost_bps: int | None = None,
) -> ResearchResult:
    execution = (
        build_signal_change_execution_weights(prices, targets)
        if signal_change_only
        else build_execution_weights(prices, targets)
    )
    return run_target_weights(
        prices,
        execution,
        fees=config.fees if total_cost_bps is None else total_cost_bps / 10_000,
        slippage=config.slippage if total_cost_bps is None else 0.0,
        initial_cash=config.initial_cash,
        metric_start=metric_start,
    )


def month_end_states(
    prices: pd.DataFrame, config: MultiAssetTrendConfig, *, strict: bool
) -> tuple[pd.DataFrame, pd.DataFrame]:
    risk_prices = prices[list(config.risk_symbols)]
    if strict:
        moving_average = risk_prices.rolling(
            config.trend_window, min_periods=config.trend_window
        ).mean()
    else:
        moving_average = valid_observation_moving_average(risk_prices, config.trend_window)
    month_ends = prices.groupby(prices.index.to_period("M")).tail(1).index
    available = moving_average.loc[month_ends].notna() & risk_prices.loc[month_ends].notna()
    states = risk_prices.loc[month_ends].gt(moving_average.loc[month_ends]).astype(float)
    return available, states.where(available)


def effort_row(
    variant: str,
    result: ResearchResult,
    monthly_targets: pd.DataFrame,
    states: pd.DataFrame,
    evaluation_start: pd.Timestamp,
) -> dict[str, Any]:
    final_observation = result.equity.index[-1]
    reviews = monthly_targets.loc[evaluation_start:final_observation]
    reviews = reviews.loc[reviews.index < final_observation]
    submissions = result.execution_weights.dropna(how="all").loc[evaluation_start:]
    orders = result.portfolio.orders.records_readable
    orders = orders.loc[orders["Timestamp"] >= evaluation_start]
    order_counts = orders.groupby("Timestamp").size()
    action_months = int(order_counts.size)
    elapsed_years = (result.equity.index[-1] - evaluation_start).days / 365.25
    prior_states = states.shift()
    trend_flips = states.notna() & prior_states.notna() & states.ne(prior_states)
    trend_change_months = int(
        trend_flips.any(axis=1).loc[reviews.index[0] : reviews.index[-1]].sum()
    )
    target_changes = reviews.ne(reviews.shift()).any(axis=1)
    return {
        "variant": variant,
        "monthly_review_count": len(reviews),
        "submitted_target_months": len(submissions),
        "actual_order_months": action_months,
        "no_action_review_months": len(reviews) - action_months,
        "annualized_action_months": action_months / elapsed_years,
        "asset_level_order_count": len(orders),
        "average_instruments_per_action_month": float(order_counts.mean()),
        "maximum_instruments_per_action_month": int(order_counts.max()),
        "trend_state_change_months": trend_change_months,
        "target_change_months": int(target_changes.sum()),
        "turnover": realized_turnover(result.portfolio, evaluation_start, result.equity.index[-1]),
        "average_holding_days": result.metrics["average_holding_days"],
    }


def variant_table(
    variants: dict[str, ResearchResult],
    availability: dict[str, pd.DataFrame],
    effort: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for name, result in variants.items():
        annual = annual_returns(result.equity)
        available = availability["V1" if name == "V1" else "V2"]
        row = {
            "variant": name,
            "availability_semantics": ("连续全局行" if name == "V1" else "逐资产最近有效观测"),
            "execution_semantics": "仅目标变化" if name == "V2B" else "每月提交目标",
            **result.metrics,
            "worst_year": float(annual.min()),
            "eligible_asset_months": int(available.sum().sum()),
            "average_eligible_assets": float(available.sum(axis=1).mean()),
        }
        effort_values = effort.set_index("variant").loc[name]
        row.update(
            {
                "actual_order_months": effort_values["actual_order_months"],
                "annualized_action_months": effort_values["annualized_action_months"],
                "asset_level_order_count": effort_values["asset_level_order_count"],
                "turnover": effort_values["turnover"],
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def temporal_tables(
    variants: dict[str, ResearchResult],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    period_rows = []
    rolling_rows = []
    for name, result in variants.items():
        for period, start, end in PERIODS:
            window = result.equity.loc[start:end]
            metrics = period_metrics(
                result.equity, result.execution_weights, window.index[0], window.index[-1]
            )
            metrics["turnover"] = realized_turnover(
                result.portfolio, window.index[0], window.index[-1]
            )
            period_rows.append(
                {
                    "variant": name,
                    "period": period,
                    "start": window.index[0].date().isoformat(),
                    "end": window.index[-1].date().isoformat(),
                    **metrics,
                }
            )
        rolling = rolling_table(result)
        rolling.insert(0, "variant", name)
        rolling_rows.extend(rolling.to_dict("records"))
    return pd.DataFrame(period_rows), pd.DataFrame(rolling_rows)


def cost_table(
    prices: pd.DataFrame,
    config: MultiAssetTrendConfig,
    targets: pd.DataFrame,
    evaluation_start: pd.Timestamp,
) -> pd.DataFrame:
    rows = []
    for bps in COST_BPS:
        result = run_variant(
            prices,
            replace(config, fees=bps / 10_000, slippage=0.0),
            targets,
            signal_change_only=True,
            metric_start=evaluation_start,
            total_cost_bps=bps,
        )
        rows.append(
            {
                "total_per_side_bps": bps,
                **result.metrics,
                "turnover": realized_turnover(
                    result.portfolio, evaluation_start, result.equity.index[-1]
                ),
            }
        )
    return pd.DataFrame(rows)


def target_difference(v1: pd.DataFrame, v2: pd.DataFrame) -> pd.Series:
    left, right = v1.align(v2, join="outer", fill_value=np.nan)
    return ~(left.eq(right) | (left.isna() & right.isna())).all(axis=1)


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/results")
    args = parser.parse_args()
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    config = load_trend_config(ROOT / "config/strategy.toml")
    assert_frozen_baseline(config)

    v1_targets = build_strict_month_end_targets(prices, config)
    v2_targets = build_month_end_targets(prices, config)
    first_execution = build_execution_weights(prices, v1_targets).dropna(how="all").index[0]
    evaluation_start = prices.index[max(prices.index.get_loc(first_execution) - 1, 0)]
    variants = {
        "V1": run_variant(
            prices, config, v1_targets, signal_change_only=False, metric_start=evaluation_start
        ),
        "V2A": run_variant(
            prices, config, v2_targets, signal_change_only=False, metric_start=evaluation_start
        ),
        "V2B": run_variant(
            prices, config, v2_targets, signal_change_only=True, metric_start=evaluation_start
        ),
    }
    availability_v1, states_v1 = month_end_states(prices, config, strict=True)
    availability_v2, states_v2 = month_end_states(prices, config, strict=False)
    availability = {"V1": availability_v1, "V2": availability_v2}
    states = {"V1": states_v1, "V2A": states_v2, "V2B": states_v2}
    targets = {"V1": v1_targets, "V2A": v2_targets, "V2B": v2_targets}
    effort = pd.DataFrame(
        [
            effort_row(name, result, targets[name], states[name], evaluation_start)
            for name, result in variants.items()
        ]
    )
    comparison = variant_table(variants, availability, effort)
    target_changed = target_difference(v1_targets, v2_targets)
    v1_states_aligned, v2_states_aligned = states_v1.align(states_v2, join="outer")
    state_changed = ~(
        v1_states_aligned.eq(v2_states_aligned)
        | (v1_states_aligned.isna() & v2_states_aligned.isna())
    )
    semantic_columns = {
        "changed_state_months_vs_v1": int(state_changed.any(axis=1).sum()),
        "changed_state_asset_months_vs_v1": int(state_changed.sum().sum()),
        "changed_target_months_vs_v1": int(target_changed.sum()),
        "changed_target_months_2015_vs_v1": int(target_changed.loc["2015"].sum()),
    }
    for column, value in semantic_columns.items():
        comparison[column] = [0, value, value]
    periods, rolling = temporal_tables(variants)
    benchmarks = benchmark_table(prices, variants["V2B"], config, evaluation_start)
    benchmarks["series"] = benchmarks["series"].str.replace("S2", "S2_V2B", regex=False)
    v1_benchmark = {
        "series": "S2_V1_完整基线",
        "comparison_group": "FULL",
        "evaluation_start": evaluation_start.date().isoformat(),
        "evaluation_end": prices.index[-1].date().isoformat(),
        "availability_note": "冻结 S2 V1 同区间对照",
        **period_metrics(
            variants["V1"].equity,
            variants["V1"].execution_weights,
            evaluation_start,
            prices.index[-1],
        ),
        "turnover": realized_turnover(variants["V1"].portfolio, evaluation_start, prices.index[-1]),
    }
    benchmarks = pd.concat([benchmarks, pd.DataFrame([v1_benchmark])], ignore_index=True)
    costs = cost_table(prices, config, v2_targets, evaluation_start)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "s2_v2_variant_comparison.csv": comparison,
        "s2_v2_benchmark_comparison.csv": benchmarks,
        "s2_v2_period_performance.csv": periods,
        "s2_v2_rolling_performance.csv": rolling,
        "s2_v2_user_effort.csv": effort,
        "s2_v2_cost_sensitivity.csv": costs,
    }
    for filename, frame in outputs.items():
        frame.to_csv(
            args.output_dir / filename, index=False, float_format="%.8f", lineterminator="\n"
        )
    print(f"评价区间: {evaluation_start.date()} 至 {prices.index[-1].date()}")
    print(comparison[["variant", "cagr", "max_drawdown", "sharpe"]].to_string(index=False))
    print(
        "语义影响: "
        f"{semantic_columns['changed_state_asset_months_vs_v1']} 个趋势状态资产月，"
        f"{semantic_columns['changed_target_months_vs_v1']} 个目标月份"
    )
    print("最终决策: CONTINUE_S2_TO_RQALPHA")


if __name__ == "__main__":
    main()
