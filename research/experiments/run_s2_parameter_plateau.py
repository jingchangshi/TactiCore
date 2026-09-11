#!/usr/bin/env python3
"""在冻结的 S2 V2B 语义上检验粗粒度趋势窗口参数平台。"""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from research.experiments.run_s1_evidence_closure import (
    annual_returns,
    period_metrics,
    realized_turnover,
    rolling_table,
)
from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import ResearchResult, run_target_weights
from tacticore.strategies.multi_asset_trend import (
    MultiAssetTrendConfig,
    build_month_end_targets,
    build_signal_change_execution_weights,
    load_trend_config,
)

ROOT = Path(__file__).resolve().parents[2]
PARAMETER_WINDOWS = (160, 180, 200, 220, 240)
BASELINE_WINDOW = 200
EVALUATION_START = pd.Timestamp("2013-03-29")
EVALUATION_END = pd.Timestamp("2026-08-31")
PERIODS = (
    ("2013-2016", "2013-03-29", "2016-12-31"),
    ("2017-2019", "2017-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-2026", "2023-01-01", "2026-08-31"),
)

# 以下门槛在运行参数结果前预声明，只判断邻域形状，不用于寻找“最佳”窗口。
FULL_SAMPLE_SPREAD_LIMITS = {"cagr": 0.03, "max_drawdown": 0.07, "sharpe": 0.35}
PERIOD_SPREAD_LIMITS = {"cagr": 0.06, "max_drawdown": 0.10, "sharpe": 0.75}
MIN_PERIOD_CAGR = -0.05
MIN_PERIOD_SHARPE = -0.25
MIN_ROLLING_POSITIVE_SHARE = 0.75
MAX_ROLLING_MEDIAN_CAGR_SPREAD = 0.04
MAX_ANNUALIZED_TARGET_CHANGES = 10.0
MAX_OPERATIONAL_RATIO = 1.35
MIN_AVERAGE_HOLDING_DAYS = 180.0


def parameter_configs(base: MultiAssetTrendConfig) -> dict[int, MultiAssetTrendConfig]:
    """仅替换趋势窗口，并保持预声明顺序。"""
    if base.trend_window != BASELINE_WINDOW:
        raise ValueError("仓库 S2 基线必须保持 trend_window = 200")
    return {window: replace(base, trend_window=window) for window in PARAMETER_WINDOWS}


def run_parameter(
    prices: pd.DataFrame, config: MultiAssetTrendConfig
) -> tuple[pd.DataFrame, ResearchResult]:
    """使用冻结的 SIGNAL_CHANGE_ONLY 与下一观测日执行语义。"""
    targets = build_month_end_targets(prices, config)
    execution = build_signal_change_execution_weights(prices, targets)
    result = run_target_weights(
        prices,
        execution,
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=EVALUATION_START,
    )
    return targets, result


def _actual_order_months(result: ResearchResult) -> int:
    orders = result.portfolio.orders.records_readable
    mask = (orders["Timestamp"] >= EVALUATION_START) & (orders["Timestamp"] <= EVALUATION_END)
    return int(orders.loc[mask, "Timestamp"].nunique())


def summary_row(
    window: int,
    result: ResearchResult,
) -> dict[str, Any]:
    end = min(EVALUATION_END, result.equity.index[-1])
    executions = result.execution_weights.loc[EVALUATION_START:end].dropna(how="all")
    elapsed_years = (end - EVALUATION_START).days / 365.25
    actual_order_months = _actual_order_months(result)
    metrics = period_metrics(result.equity, result.execution_weights, EVALUATION_START, end)
    return {
        "trend_window": window,
        "evaluation_start": EVALUATION_START.date().isoformat(),
        "evaluation_end": end.date().isoformat(),
        **{name: metrics[name] for name in ("cagr", "max_drawdown", "sharpe", "calmar")},
        "worst_year": float(annual_returns(result.equity.loc[EVALUATION_START:end]).min()),
        "turnover": realized_turnover(result.portfolio, EVALUATION_START, end),
        "trade_count": int(result.metrics["trade_count"]),
        "average_holding_days": result.metrics["average_holding_days"],
        "target_change_months": len(executions),
        "annualized_target_change_months": len(executions) / elapsed_years,
        "actual_order_months": actual_order_months,
        "annualized_action_months": actual_order_months / elapsed_years,
    }


def period_rows(window: int, result: ResearchResult) -> list[dict[str, Any]]:
    rows = []
    for period, start, end in PERIODS:
        observations = result.equity.loc[start:end]
        metrics = period_metrics(
            result.equity,
            result.execution_weights,
            observations.index[0],
            observations.index[-1],
        )
        rows.append(
            {
                "trend_window": window,
                "period": period,
                "start": observations.index[0].date().isoformat(),
                "end": observations.index[-1].date().isoformat(),
                **{name: metrics[name] for name in ("cagr", "max_drawdown", "sharpe", "calmar")},
            }
        )
    return rows


def rolling_rows(window: int, result: ResearchResult) -> list[dict[str, Any]]:
    rolling = rolling_table(result).rename(columns={"window_years": "years"})
    rolling.insert(0, "trend_window", window)
    return rolling.to_dict("records")


def validate_parameter_coverage(frame: pd.DataFrame) -> None:
    """防止输出缺失、重复或偷偷扩展参数。"""
    actual = tuple(frame["trend_window"].astype(int))
    if actual != PARAMETER_WINDOWS:
        raise ValueError(f"参数输出必须且只能按顺序包含 {PARAMETER_WINDOWS}，实际为 {actual}")


def _spread_within(frame: pd.DataFrame, limits: dict[str, float]) -> bool:
    return all(
        float(frame[name].max() - frame[name].min()) <= limit for name, limit in limits.items()
    )


def rolling_summary(rolling: pd.DataFrame) -> pd.DataFrame:
    return (
        rolling.groupby(["trend_window", "years"], as_index=False)
        .agg(
            window_count=("cagr", "size"),
            cagr_min=("cagr", "min"),
            cagr_median=("cagr", "median"),
            cagr_positive_share=("cagr", lambda values: float((values > 0).mean())),
            max_drawdown_worst=("max_drawdown", "min"),
            sharpe_min=("sharpe", "min"),
            sharpe_median=("sharpe", "median"),
        )
        .sort_values(["years", "trend_window"])
    )


def decide(summary: pd.DataFrame, periods: pd.DataFrame, rolling: pd.DataFrame) -> str:
    """按预声明门槛给出唯一门控决策；通过仍固定保留 200。"""
    validate_parameter_coverage(summary)
    full_sample_pass = (
        _spread_within(summary, FULL_SAMPLE_SPREAD_LIMITS)
        and bool((summary["cagr"] > 0).all())
        and bool((summary["sharpe"] > 0).all())
    )
    period_pass = (
        bool((periods["cagr"] >= MIN_PERIOD_CAGR).all())
        and bool((periods["sharpe"] >= MIN_PERIOD_SHARPE).all())
        and all(
            _spread_within(group, PERIOD_SPREAD_LIMITS) for _, group in periods.groupby("period")
        )
    )
    rolling_stats = rolling_summary(rolling)
    rolling_pass = bool(
        (rolling_stats["cagr_positive_share"] >= MIN_ROLLING_POSITIVE_SHARE).all()
    ) and all(
        float(group["cagr_median"].max() - group["cagr_median"].min())
        <= MAX_ROLLING_MEDIAN_CAGR_SPREAD
        for _, group in rolling_stats.groupby("years")
    )
    baseline = summary.set_index("trend_window").loc[BASELINE_WINDOW]
    operational_pass = (
        bool((summary["annualized_target_change_months"] <= MAX_ANNUALIZED_TARGET_CHANGES).all())
        and float(summary["turnover"].max()) <= float(baseline["turnover"]) * MAX_OPERATIONAL_RATIO
        and float(summary["trade_count"].max())
        <= float(baseline["trade_count"]) * MAX_OPERATIONAL_RATIO
        and bool((summary["average_holding_days"] >= MIN_AVERAGE_HOLDING_DAYS).all())
    )
    if full_sample_pass and period_pass and rolling_pass and operational_pass:
        return "PASS_S2_PARAMETER_PLATEAU"
    return "REJECT_S2_PARAMETER_FRAGILITY"


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/results")
    args = parser.parse_args()

    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    base = load_trend_config(ROOT / "config/strategy.toml")
    configs = parameter_configs(base)
    summary_records: list[dict[str, Any]] = []
    period_records: list[dict[str, Any]] = []
    rolling_records: list[dict[str, Any]] = []
    for window, config in configs.items():
        _, result = run_parameter(prices, config)
        summary_records.append(summary_row(window, result))
        period_records.extend(period_rows(window, result))
        rolling_records.extend(rolling_rows(window, result))

    summary = pd.DataFrame(summary_records)
    periods = pd.DataFrame(period_records)
    rolling = pd.DataFrame(rolling_records)
    validate_parameter_coverage(summary)
    decision = decide(summary, periods, rolling)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in (
        ("s2_parameter_plateau_summary.csv", summary),
        ("s2_parameter_periods.csv", periods),
        ("s2_parameter_rolling.csv", rolling),
    ):
        frame.to_csv(args.output_dir / name, index=False, float_format="%.8f", lineterminator="\n")

    print(summary.to_string(index=False))
    print("\n滚动汇总:")
    print(rolling_summary(rolling).to_string(index=False))
    print(f"\n最终决策: {decision}")
    if decision == "PASS_S2_PARAMETER_PLATEAU":
        print("参数动作: KEEP_200")


if __name__ == "__main__":
    main()
