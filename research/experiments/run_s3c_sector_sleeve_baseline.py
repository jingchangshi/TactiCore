#!/usr/bin/env python3
"""运行唯一预声明的 S3C 固定行业 sleeve 趋势过滤历史筛选。"""

from pathlib import Path

import pandas as pd

from research.experiments.run_s3_sector_baseline import sector_symbols
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs
from tacticore.data.universe import load_universe
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.china_sector_rotation import (
    build_execution_weights,
    valid_observation_momentum,
)
from tacticore.strategies.china_sector_sleeve_trend import (
    build_month_end_targets,
    load_sector_sleeve_trend_config,
)

ROOT = Path(__file__).resolve().parents[2]


def _metrics(name, result, start):
    equity = result.equity.loc[start:]
    annual = equity.resample("YE").last().pct_change().dropna()
    changes = result.execution_weights.loc[start:].dropna(how="all")
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    return {
        "series": name,
        **result.metrics,
        "worst_year": float(annual.min()),
        "target_change_months": float(len(changes)),
        "annualized_target_change_months": float(len(changes) / years),
    }


def main():
    universe = load_universe(ROOT / "config/s3_sector_universe.csv")
    config = load_sector_sleeve_trend_config(ROOT / "config/s3_sector_sleeve_trend.toml")
    sectors = sector_symbols(universe)
    prices = load_price_csv(ROOT / "data/canonical/s3_sector_rotation_v1/etf_adjusted_close.csv")
    tradability_mask, lifetimes = load_tradability_inputs(
        prices, str(ROOT / "config/s3_sector_universe.csv")
    )
    targets, states = build_month_end_targets(prices, config, sectors)
    momentums = valid_observation_momentum(prices.loc[:, list(sectors)], config.trend_window)
    eligible = momentums.notna().sum(axis=1)
    signal = states.index[eligible.loc[states.index].ge(8)][0]
    start = prices.index[prices.index.get_loc(signal) + 1]
    execution = build_execution_weights(prices, targets)
    sleeve = 1 / len(sectors)
    comparator = pd.DataFrame(0.0, index=states.index, columns=prices.columns)
    for date in states.index:
        available = momentums.loc[date].notna()
        symbols = available[available].index
        comparator.loc[date, symbols] = sleeve
        comparator.loc[date, config.fallback_symbol] = 1 - sleeve * len(symbols)
    common = {
        "fees": config.fees,
        "slippage": config.slippage,
        "initial_cash": config.initial_cash,
        "metric_start": start,
        "tradability_mask": tradability_mask,
        "lifetimes": lifetimes,
    }
    s3c = run_target_weights(prices, execution, **common)
    ungated = run_target_weights(prices, build_execution_weights(prices, comparator), **common)
    market_prices = (
        load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")[["510300.SS"]]
        .reindex(prices.index)
        .dropna()
    )
    market_execution = pd.DataFrame(
        float("nan"), index=market_prices.index, columns=market_prices.columns
    )
    market_execution.loc[start, "510300.SS"] = 1.0
    market_mask, market_lifetimes = load_tradability_inputs(
        market_prices, str(ROOT / "config/universe.csv")
    )
    market = run_target_weights(
        market_prices,
        market_execution,
        **{
            **common,
            "tradability_mask": market_mask,
            "lifetimes": market_lifetimes,
        },
    )
    comparison = pd.DataFrame(
        [
            _metrics("S3C_V1", s3c, start),
            _metrics("UNGATED_FIXED_SLEEVE_BASKET", ungated, start),
            _metrics("510300", market, start),
        ]
    )
    sample = states.loc[states.index >= start]
    diag = pd.DataFrame(index=sample.index)
    diag["eligible_sector_count"] = sample.ne("UNAVAILABLE").sum(axis=1)
    diag["positive_sector_count"] = sample.eq("POSITIVE").sum(axis=1)
    diag["negative_sector_count"] = sample.eq("NEGATIVE_SIGNAL").sum(axis=1)
    diag["unavailable_sector_count"] = sample.eq("UNAVAILABLE").sum(axis=1)
    diag["risk_asset_weight"] = diag["positive_sector_count"] / len(sectors)
    diag["fallback_weight"] = 1 - diag["risk_asset_weight"]
    diag["target_changed"] = targets.loc[sample.index].ne(targets.shift()).any(axis=1)
    diag["execution_date"] = ""
    for date in execution.dropna(how="all").index:
        previous = prices.index[prices.index.get_loc(date) - 1]
        if previous in diag.index:
            diag.loc[previous, "execution_date"] = date.date().isoformat()
    diag.to_csv(ROOT / "research/results/s3c_sector_sleeve_states_v1.csv")
    comparison.to_csv(ROOT / "research/results/s3c_sector_sleeve_comparison_v1.csv", index=False)
    s = comparison.iloc[0]
    u = comparison.iloc[1]
    avg = diag["risk_asset_weight"].mean()
    decision = (
        "ADVANCE_S3C_TO_ROBUSTNESS"
        if (
            s.cagr > 0
            and s.sharpe >= 0.45
            and s.max_drawdown > -0.35
            and s.annualized_target_change_months <= 10
            and s.max_drawdown >= u.max_drawdown + 0.05
            and s.cagr >= u.cagr - 0.015
            and s.sharpe > u.sharpe
            and s.calmar > u.calmar
            and 0.3 <= avg <= 0.95
        )
        else "REJECT_S3C_BASELINE"
    )
    print("decision=" + decision)
    print(comparison.to_csv(index=False))
    print(
        {
            "average_risk_asset_weight": avg,
            "average_fallback_weight": diag["fallback_weight"].mean(),
            "min_risk": diag["risk_asset_weight"].min(),
            "max_risk": diag["risk_asset_weight"].max(),
        }
    )


if __name__ == "__main__":
    main()
