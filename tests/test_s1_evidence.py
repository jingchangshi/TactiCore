from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from research.experiments import run_s1_evidence_closure as evidence
from tacticore.strategies.global_dual_momentum import load_strategy_config

ROOT = Path(__file__).resolve().parents[1]


def test_repository_strategy_parameters_are_frozen() -> None:
    config = load_strategy_config(ROOT / "config/strategy.toml")

    evidence.assert_frozen_parameters(config)
    with pytest.raises(ValueError, match="冻结参数"):
        evidence.assert_frozen_parameters(replace(config, top_k=1))


def test_period_metrics_do_not_use_returns_outside_slice() -> None:
    dates = pd.bdate_range("2024-01-01", periods=8)
    equity = pd.Series([100, 200, 202, 204, 206, 208, 210, 1], index=dates, dtype=float)
    weights = pd.DataFrame(
        {"A": [np.nan, 1, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan]}, index=dates
    )

    metrics = evidence.period_metrics(equity, weights, dates[2], dates[6])

    assert metrics["cagr"] > 0
    assert metrics["max_drawdown"] == 0
    assert metrics["turnover"] == 0


def test_static_benchmark_starts_only_when_every_asset_exists(
    strategy_config: Any,
) -> None:
    dates = pd.bdate_range("2024-01-01", periods=10)
    prices = pd.DataFrame(
        {"A": np.arange(10) + 100.0, "B": [np.nan] * 3 + list(np.arange(7) + 100.0)},
        index=dates,
    )

    equity, _, portfolio = evidence.build_static_portfolio(
        prices, {"A": 0.5, "B": 0.5}, strategy_config, rebalance="buy_hold"
    )

    assert equity.index[0] == dates[3]
    assert evidence.realized_turnover(portfolio, equity.index[0], equity.index[-1]) > 0.99


def test_cost_scenarios_are_fixed_and_use_vectorbt_parameters(
    monkeypatch: Any, strategy_config: Any, simple_prices: pd.DataFrame
) -> None:
    seen: list[tuple[float, float]] = []

    def fake_run(prices: pd.DataFrame, config: Any) -> Any:
        del prices
        seen.append((config.fees, config.slippage))
        return SimpleNamespace(
            metrics={name: 0.0 for name in ("cagr", "max_drawdown", "sharpe", "calmar", "turnover")}
        )

    monkeypatch.setattr(evidence, "run_vectorbt", fake_run)

    result = evidence.cost_table(simple_prices, strategy_config)

    assert result["total_per_side_bps"].tolist() == [5, 15, 30, 50]
    assert seen == [(0.0005, 0.0), (0.0015, 0.0), (0.003, 0.0), (0.005, 0.0)]


def test_partial_top_k_measurement_finds_single_risk_allocation(
    strategy_config: Any,
) -> None:
    targets = pd.DataFrame(
        {
            "A": [1.0, 0.5, 0.0],
            "B": [0.0, 0.5, 0.0],
            "C": [0.0, 0.0, 0.0],
            "BOND": [0.0, 0.0, 1.0],
        },
        index=pd.date_range("2024-01-31", periods=3, freq="ME"),
    )

    partial = evidence.partial_top_k(targets, strategy_config)

    assert partial["selected_symbol"].tolist() == ["A"]
    assert partial["risk_weight"].tolist() == [1.0]


def test_availability_uses_observations_instead_of_backfill(strategy_config: Any) -> None:
    dates = pd.bdate_range("2023-01-02", periods=270)
    prices = pd.DataFrame(
        {
            "A": np.arange(270) + 100.0,
            "B": [np.nan] * 10 + list(np.arange(260) + 100.0),
        },
        index=dates,
    )
    universe = pd.DataFrame(
        {
            "symbol": ["A", "B"],
            "asset_class": ["equity", "equity"],
            "start_date": [dates[0], dates[10]],
        }
    ).set_index("symbol", drop=False)
    config = replace(
        strategy_config,
        lookback_trading_days=252,
        top_k=1,
        risk_symbols=("A",),
        fallback_symbol="B",
    )

    availability = evidence.availability_table(prices, universe, config).set_index("symbol")

    assert availability.loc["B", "first_market_observation"] == dates[10].date().isoformat()
    assert availability.loc["B", "first_usable_signal_date"] == dates[262].date().isoformat()
