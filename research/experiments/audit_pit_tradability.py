#!/usr/bin/env python3
"""Batch 04 bounded scan: only existing strategy targets, no performance replay."""

from pathlib import Path

import pandas as pd

from research.experiments.run_s4c_erc_skfolio_transfer import S4CConfig
from research.experiments.run_s4c_erc_skfolio_transfer import build_targets as s4c_targets
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import build_tradability_mask, lifetimes_from_universe
from tacticore.data.universe import load_universe
from tacticore.strategies.inverse_vol_allocation import build_month_end_targets as s4a_targets
from tacticore.strategies.inverse_vol_allocation import load_inverse_vol_config
from tacticore.strategies.multi_asset_trend import (
    build_execution_weights,
    build_signal_change_execution_weights,
    load_trend_config,
)
from tacticore.strategies.multi_asset_trend import (
    build_month_end_targets as s2_targets,
)
from tacticore.strategies.static_strategic_allocation import (
    build_execution_weights as s30_execution,
)
from tacticore.strategies.static_strategic_allocation import load_static_allocation_config
from tacticore.strategies.trend_inverse_vol import build_month_end_targets as s27_targets
from tacticore.strategies.trend_inverse_vol import load_trend_inverse_vol_config
from tacticore.strategies.volatility_targeting import build_month_end_targets as s10_targets
from tacticore.strategies.volatility_targeting import load_volatility_targeting_config

ROOT = Path(__file__).resolve().parents[2]


def violations(
    strategy: str, execution: pd.DataFrame, prices: pd.DataFrame, mask: pd.DataFrame, lifetimes
):
    rows = []
    for date, target in execution.dropna(how="all").iterrows():
        for symbol, weight in target.fillna(0.0).items():
            if weight <= 1e-12 or bool(mask.at[date, symbol]):
                continue
            lifetime = lifetimes.get(symbol)
            price = symbol in prices and date in prices.index and pd.notna(prices.at[date, symbol])
            rows.append(
                {
                    "strategy": strategy,
                    "execution_date": pd.Timestamp(date).date().isoformat(),
                    "symbol": symbol,
                    "target_weight": weight,
                    "listed_date": (
                        lifetime.listed_date.date().isoformat() if lifetime else "UNKNOWN"
                    ),
                    "price_available": bool(price),
                    "violation_type": (
                        "INACTIVE_ASSET"
                        if lifetime and date < lifetime.listed_date
                        else "MISSING_EXECUTION_PRICE"
                    ),
                }
            )
    return rows


def main() -> None:
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    universe = load_universe(ROOT / "config/universe.csv")
    lifetimes = lifetimes_from_universe(universe)
    mask = build_tradability_mask(prices.index, list(prices.columns), lifetimes, prices)
    trend = load_trend_config(ROOT / "config/strategy.toml")
    s27 = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    s10 = load_volatility_targeting_config(ROOT / "config/s10a_vol_targeting.toml")
    s4a = load_inverse_vol_config(ROOT / "config/s4_inverse_vol.toml")
    s30 = load_static_allocation_config(ROOT / "config/s30_static_allocation.toml")
    s2_execution = build_signal_change_execution_weights(prices, s2_targets(prices, trend))
    s27_execution = build_execution_weights(prices, s27_targets(prices, s27, trend.risk_symbols)[0])
    s10_execution = build_execution_weights(prices, s10_targets(prices, s10)[0])
    s4c_execution = build_execution_weights(
        prices, s4c_targets(prices, trend.risk_symbols, S4CConfig(trend.fallback_symbol))[0]
    )
    s4a_execution = build_execution_weights(prices, s4a_targets(prices, s4a, trend.risk_symbols)[0])
    schedules = {
        "S2_R1": s2_execution,
        "S27A": s27_execution,
        "S10A": s10_execution,
        "S4C": s4c_execution,
        "S4A": s4a_execution,
        "S30": s30_execution(prices, s30),
    }
    rows = [
        row
        for strategy, execution in schedules.items()
        for row in violations(strategy, execution, prices, mask, lifetimes)
    ]
    result = pd.DataFrame(
        rows,
        columns=[
            "strategy",
            "execution_date",
            "symbol",
            "target_weight",
            "listed_date",
            "price_available",
            "violation_type",
        ],
    )
    result.to_csv(ROOT / "research/results/pit_tradability_violations_v1.csv", index=False)
    counts = {name: sum(1 for row in rows if row["strategy"] == name) for name in schedules}
    report = ROOT / "research/results/PIT_TRADABILITY_IMPACT_AUDIT_V1.md"
    report.write_text(
        "# PIT tradability 影响审计 V1\n\n"
        + "\n".join(f"- {name}: {count} violations" for name, count in counts.items())
        + "\n\nS3A/S3B/S3C 使用独立行业 canonical 与独立 universe；其已关闭实验的执行起点晚于 "
        "511010 上市日，归类为 `UNAFFECTED`，不重跑。\n"
    )
    print(result.to_csv(index=False))


if __name__ == "__main__":
    main()
