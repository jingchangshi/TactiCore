#!/usr/bin/env python3
"""运行唯一预声明的 S3B 行业 breadth regime historical hypothesis screen。"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

import pandas as pd

from research.experiments.run_s3_sector_baseline import sector_symbols
from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe
from tacticore.engines.vectorbt_adapter import ResearchResult, run_target_weights
from tacticore.strategies.china_sector_breadth import (
    ChinaSectorBreadthConfig,
    build_execution_weights,
    build_month_end_targets,
    load_sector_breadth_config,
    sector_breadth_state,
)
from tacticore.strategies.china_sector_rotation import valid_observation_momentum

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/canonical/s3_sector_rotation_v1"


def evaluation_start(states: pd.DataFrame, prices: pd.DataFrame) -> pd.Timestamp:
    valid = states.loc[states["eligible_sector_count"] >= 8]
    if valid.empty:
        raise ValueError("BLOCK_S3B_COVERAGE")
    signal = valid.index[0]
    location = int(prices.index.get_indexer(pd.Index([signal]))[0]) + 1
    return prices.index[location]


def ungated_targets(
    prices: pd.DataFrame, config: ChinaSectorBreadthConfig, sectors: tuple[str, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    states = sector_breadth_state(prices, config, sectors)
    momentums = valid_observation_momentum(prices.loc[:, list(sectors)], config.momentum_lookback)
    targets = pd.DataFrame(0.0, index=states.index, columns=prices.columns)
    for date, state in states.iterrows():
        if state["eligible_sector_count"] >= config.min_eligible_sectors:
            eligible = momentums.loc[date].notna()
            symbols = eligible[eligible].index
            targets.loc[date, symbols] = 1.0 / len(symbols)
        else:
            targets.loc[date, config.fallback_symbol] = 1.0
    return targets, states


def metrics(name: str, result: ResearchResult, start: pd.Timestamp) -> dict[str, float | str]:
    equity = result.equity.loc[start:]
    annual = equity.resample("YE").last().pct_change().dropna()
    changes = result.execution_weights.loc[start:].dropna(how="all")
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    return {
        "series": name,
        "cagr": result.metrics["cagr"],
        "max_drawdown": result.metrics["max_drawdown"],
        "sharpe": result.metrics["sharpe"],
        "calmar": result.metrics["calmar"],
        "worst_year": float(annual.min()),
        "turnover": result.metrics["turnover"],
        "trade_count": result.metrics["trade_count"],
        "average_holding_days": result.metrics["average_holding_days"],
        "target_change_months": float(len(changes)),
        "annualized_target_change_months": float(len(changes) / years),
    }


def regime_summary(states: pd.DataFrame, start: pd.Timestamp) -> dict[str, float]:
    sample = states.loc[states.index >= start]
    regimes = sample["regime"]
    transitions = int(regimes.ne(regimes.shift()).sum() - 1)
    durations = regimes.groupby(regimes.ne(regimes.shift()).cumsum()).agg(["first", "size"])
    on_duration = durations.loc[durations["first"].eq("RISK_ON"), "size"]
    off_duration = durations.loc[durations["first"].eq("RISK_OFF"), "size"]
    return {
        "risk_on_months": float(regimes.eq("RISK_ON").sum()),
        "risk_off_months": float(regimes.eq("RISK_OFF").sum()),
        "unavailable_months": float(regimes.eq("UNAVAILABLE").sum()),
        "risk_on_share": float(regimes.eq("RISK_ON").mean()),
        "risk_off_share": float(regimes.eq("RISK_OFF").mean()),
        "regime_transitions": float(transitions),
        "average_risk_on_duration": float(on_duration.mean()),
        "average_risk_off_duration": float(off_duration.mean()),
    }


def decision(comparison: pd.DataFrame, summary: dict[str, float], coverage: pd.Series) -> str:
    if (coverage >= 8).mean() < 0.8:
        return "BLOCK_S3B_COVERAGE"
    if summary["risk_off_share"] < 0.05 or summary["risk_on_share"] < 0.20:
        return "REJECT_S3B_DEGENERATE_REGIME"
    s3b = comparison.loc[comparison["series"].eq("S3B_V1")].iloc[0]
    ungated = comparison.loc[comparison["series"].eq("UNGATED_SECTOR_BASKET")].iloc[0]
    absolute = (
        s3b["cagr"] > 0
        and s3b["sharpe"] >= 0.4
        and s3b["max_drawdown"] > -0.4
        and s3b["annualized_target_change_months"] <= 10
    )
    relative = (
        s3b["max_drawdown"] >= ungated["max_drawdown"] + 0.05
        and s3b["cagr"] >= ungated["cagr"] - 0.02
        and (s3b["sharpe"] > ungated["sharpe"] or s3b["calmar"] > ungated["calmar"])
        and s3b["max_drawdown"] > ungated["max_drawdown"]
    )
    return (
        "ADVANCE_S3B_BREADTH_TO_ROBUSTNESS"
        if absolute and relative
        else "REJECT_S3B_BREADTH_BASELINE"
    )


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/results")
    args = parser.parse_args()
    universe = load_universe(ROOT / "config/s3_sector_universe.csv")
    config = load_sector_breadth_config(ROOT / "config/s3_sector_breadth.toml")
    sectors = sector_symbols(universe)
    prices = load_price_csv(DATA_DIR / "etf_adjusted_close.csv")
    targets, states = build_month_end_targets(prices, config, sectors)
    start = evaluation_start(states, prices)
    execution = build_execution_weights(prices, targets)
    ungated, _ = ungated_targets(prices, config, sectors)
    common = {
        "fees": config.fees,
        "slippage": config.slippage,
        "initial_cash": config.initial_cash,
        "metric_start": start,
    }
    s3b = run_target_weights(prices, execution, **common)
    basket = run_target_weights(prices, build_execution_weights(prices, ungated), **common)
    market_prices = (
        load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")[["510300.SS"]]
        .reindex(prices.index)
        .dropna()
    )
    market_execution = pd.DataFrame(
        float("nan"), index=market_prices.index, columns=market_prices.columns
    )
    market_execution.loc[start, "510300.SS"] = 1.0
    market = run_target_weights(market_prices, market_execution, **common)
    comparison = pd.DataFrame(
        [
            metrics("S3B_V1", s3b, start),
            metrics("UNGATED_SECTOR_BASKET", basket, start),
            metrics("510300", market, start),
        ]
    )
    summary = regime_summary(states, start)
    outcome = decision(
        comparison, summary, states.loc[states.index >= start, "eligible_sector_count"]
    )
    states = states.copy()
    states["target_changed"] = targets.ne(targets.shift()).any(axis=1)
    dates = {date: "" for date in states.index}
    for date in execution.dropna(how="all").index:
        dates[prices.index[prices.index.get_loc(date) - 1]] = date.date().isoformat()
    states["execution_date"] = pd.Series(dates)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    states.to_csv(args.output_dir / "s3b_sector_breadth_states_v1.csv")
    comparison.to_csv(args.output_dir / "s3b_sector_breadth_comparison_v1.csv", index=False)
    print(f"decision={outcome}")
    print(comparison.to_csv(index=False))
    print(summary)


if __name__ == "__main__":
    main()
