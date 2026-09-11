#!/usr/bin/env python3
"""以预声明的 S3A V1 行业 ETF universe 运行单一 VectorBT 经济筛选。"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

import pandas as pd

from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe
from tacticore.engines.vectorbt_adapter import ResearchResult, run_target_weights
from tacticore.strategies.china_sector_rotation import (
    ChinaSectorRotationConfig,
    build_execution_weights,
    build_month_end_targets,
    load_sector_rotation_config,
    valid_observation_momentum,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/canonical/s3_sector_rotation_v1"


def sector_symbols(universe: pd.DataFrame) -> tuple[str, ...]:
    sectors = universe.loc[universe["sector"].notna() & universe["sector"].ne(""), "symbol"]
    if len(sectors) < 8 or sectors.duplicated().any():
        raise ValueError("S3A 需要至少 8 个唯一行业 ETF")
    if universe.loc[sectors, "sector"].duplicated().any():
        raise ValueError("S3A 的行业类别必须唯一")
    return tuple(sectors)


def eligible_sector_counts(
    prices: pd.DataFrame, config: ChinaSectorRotationConfig, sectors: tuple[str, ...]
) -> pd.Series:
    momentums = valid_observation_momentum(prices.loc[:, list(sectors)], config.momentum_lookback)
    month_ends = prices.groupby(prices.index.to_period("M")).tail(1).index
    return momentums.loc[month_ends].notna().sum(axis=1)


def evaluation_start(
    prices: pd.DataFrame, config: ChinaSectorRotationConfig, sectors: tuple[str, ...]
) -> pd.Timestamp:
    coverage = eligible_sector_counts(prices, config, sectors)
    eligible = coverage.loc[coverage >= 8]
    if eligible.empty:
        raise ValueError("BLOCK_S3A_UNIVERSE_COVERAGE")
    first_signal = eligible.index[0]
    location = int(prices.index.get_indexer(pd.Index([first_signal]))[0]) + 1
    if location >= len(prices.index):
        raise ValueError("没有可执行的 S3A evaluation start")
    return prices.index[location]


def build_equal_weight_execution(
    prices: pd.DataFrame,
    config: ChinaSectorRotationConfig,
    sectors: tuple[str, ...],
) -> pd.DataFrame:
    """实验本地的 availability-aware 月频 equal-weight sector comparator。"""
    momentums = valid_observation_momentum(prices.loc[:, list(sectors)], config.momentum_lookback)
    month_ends = prices.groupby(prices.index.to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=month_ends, columns=prices.columns)
    for date in month_ends:
        available = momentums.loc[date].dropna().index
        if len(available):
            targets.loc[date, available] = 1.0 / len(available)
        else:
            targets.loc[date, config.fallback_symbol] = 1.0
    execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    for date, target in targets.iterrows():
        location = int(prices.index.get_indexer(pd.Index([date]))[0]) + 1
        if location < len(prices.index):
            execution.iloc[location] = target
    return execution


def extended_metrics(result: ResearchResult, evaluation_start: pd.Timestamp) -> dict[str, float]:
    equity = result.equity.loc[evaluation_start:]
    annual = equity.resample("YE").last().pct_change().dropna()
    target_dates = result.execution_weights.loc[evaluation_start:].dropna(how="all")
    target_change_months = int(len(target_dates))
    elapsed_years = (equity.index[-1] - equity.index[0]).days / 365.25
    return {
        **result.metrics,
        "worst_year": float(annual.min()) if not annual.empty else float("nan"),
        "target_change_months": float(target_change_months),
        "annualized_target_change_months": float(target_change_months / elapsed_years),
    }


def metric_row(name: str, result: ResearchResult, evaluation_start: pd.Timestamp) -> dict[str, Any]:
    return {
        "series": name,
        "evaluation_start": evaluation_start.date().isoformat(),
        **extended_metrics(result, evaluation_start),
    }


def decision(metrics: pd.DataFrame, coverage: pd.Series) -> str:
    strategy = metrics.loc[metrics["series"].eq("S3A_V1")].iloc[0]
    equal = metrics.loc[metrics["series"].eq("行业等权")].iloc[0]
    coverage_ok = len(coverage) > 0 and (coverage >= 8).mean() >= 0.8
    floor_ok = (
        strategy["cagr"] > 0
        and strategy["sharpe"] >= 0.4
        and strategy["max_drawdown"] > -0.4
        and strategy["annualized_target_change_months"] <= 10
    )
    better = sum(
        [
            strategy["cagr"] > equal["cagr"],
            strategy["max_drawdown"] > equal["max_drawdown"],
            strategy["sharpe"] > equal["sharpe"],
            strategy["calmar"] > equal["calmar"],
        ]
    )
    if coverage_ok and floor_ok and better >= 2:
        return "ADVANCE_S3A_BASELINE_TO_ROBUSTNESS"
    return "REJECT_S3A_BASELINE"


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/results")
    args = parser.parse_args()
    universe = load_universe(ROOT / "config/s3_sector_universe.csv")
    config = load_sector_rotation_config(ROOT / "config/s3_sector_rotation.toml")
    sectors = sector_symbols(universe)
    prices = load_price_csv(DATA_DIR / "etf_adjusted_close.csv")
    coverage = eligible_sector_counts(prices, config, sectors)
    start = evaluation_start(prices, config, sectors)
    targets = build_month_end_targets(prices, config, sectors)
    execution = build_execution_weights(prices, targets)
    run_kwargs = {
        "fees": config.fees,
        "slippage": config.slippage,
        "initial_cash": config.initial_cash,
        "metric_start": start,
    }
    strategy = run_target_weights(prices, execution, **run_kwargs)
    equal_execution = build_equal_weight_execution(prices, config, sectors)
    equal = run_target_weights(prices, equal_execution, **run_kwargs)
    market_prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    market_prices = market_prices[["510300.SS"]].reindex(prices.index).dropna()
    market_execution = pd.DataFrame(
        float("nan"), index=market_prices.index, columns=market_prices.columns
    )
    market_execution.loc[start, "510300.SS"] = 1.0
    market = run_target_weights(market_prices, market_execution, **run_kwargs)
    metrics = pd.DataFrame(
        [
            metric_row("S3A_V1", strategy, start),
            metric_row("行业等权", equal, start),
            metric_row("510300", market, start),
        ]
    )
    outcome = decision(metrics, coverage.loc[coverage.index >= start])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    universe.reset_index(drop=True).to_csv(
        args.output_dir / "s3_sector_universe_v1.csv", index=False
    )
    execution.dropna(how="all").to_csv(
        args.output_dir / "s3_sector_targets_v1.csv", float_format="%.8f"
    )
    metrics.to_csv(args.output_dir / "s3_sector_benchmark_comparison_v1.csv", index=False)
    print(f"decision={outcome}")
    print(metrics.to_csv(index=False))
    evaluation_coverage = coverage.loc[coverage.index >= start]
    print(f"evaluation_start={start.date()} coverage_min={evaluation_coverage.min()}")


if __name__ == "__main__":
    main()
