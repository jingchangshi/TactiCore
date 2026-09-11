import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import run_vectorbt
from tacticore.strategies.global_dual_momentum import load_strategy_config
from tacticore.strategies.multi_asset_trend import (
    MultiAssetTrendConfig,
    build_execution_weights,
    build_month_end_targets,
    load_trend_config,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def trend_config() -> MultiAssetTrendConfig:
    return MultiAssetTrendConfig(
        trend_window=3,
        fallback_symbol="BOND",
        risk_symbols=("A", "B", "C"),
        fees=0.0,
        slippage=0.0,
        initial_cash=100_000,
    )


def _prices() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-22", "2024-02-09")
    step = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame(
        {
            "A": 100 + step,
            "B": 100 - step,
            "C": 100 + step,
            "BOND": 100 + step * 0.01,
        },
        index=dates,
    )
    frame.loc[frame.index < "2024-01-30", "C"] = np.nan
    return frame


def test_repository_s2_baseline_is_exactly_frozen() -> None:
    config = load_trend_config(ROOT / "config/strategy.toml")

    assert config.trend_window == 200
    assert config.rebalance_frequency == "monthly"
    assert config.fallback_symbol == "511010.SS"
    assert config.risk_symbols == load_strategy_config(ROOT / "config/strategy.toml").risk_symbols


def test_mixed_trends_exclude_future_asset_and_route_inactive_sleeve(
    trend_config: MultiAssetTrendConfig,
) -> None:
    targets = build_month_end_targets(_prices(), trend_config)
    january = targets.loc["2024-01-31"]

    assert january["A"] == 0.5
    assert january["B"] == 0.0
    assert january["C"] == 0.0
    assert january["BOND"] == 0.5
    assert (targets.sum(axis=1) == 1.0).all()


def test_all_negative_is_fully_defensive(trend_config: MultiAssetTrendConfig) -> None:
    prices = _prices()
    values = 200 - np.arange(len(prices))[:, None]
    prices[["A", "B", "C"]] = np.tile(values, (1, 3))

    target = build_month_end_targets(prices, trend_config).loc["2024-01-31"]

    assert target["BOND"] == 1.0
    assert target[list(trend_config.risk_symbols)].sum() == 0.0


def test_all_positive_is_equal_weight_eligible_assets(
    trend_config: MultiAssetTrendConfig,
) -> None:
    prices = _prices()
    values = 100 + np.arange(len(prices))[:, None]
    prices[["A", "B", "C"]] = np.tile(values, (1, 3))

    target = build_month_end_targets(prices, trend_config).loc["2024-01-31"]

    assert target[list(trend_config.risk_symbols)].tolist() == pytest.approx([1 / 3] * 3)
    assert target["BOND"] == 0.0


def test_month_end_signal_executes_next_day_without_future_data(
    trend_config: MultiAssetTrendConfig,
) -> None:
    prices = _prices()
    original = build_month_end_targets(prices, trend_config)
    changed = prices.copy()
    changed.loc[changed.index > "2024-01-31", "A"] *= 100
    recalculated = build_month_end_targets(changed, trend_config)
    execution = build_execution_weights(prices, original)

    pd.testing.assert_series_equal(original.loc["2024-01-31"], recalculated.loc["2024-01-31"])
    assert execution.loc["2024-01-31"].isna().all()
    assert execution.loc["2024-02-01"].notna().all()


def test_s1_frozen_output_survives_shared_adapter_extraction() -> None:
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    config = load_strategy_config(ROOT / "config/strategy.toml")
    expected = json.loads(
        (ROOT / "research/results/gdm_baseline_metrics.json").read_text(encoding="utf-8")
    )["metrics"]

    actual = run_vectorbt(prices, config).metrics

    for name, expected_value in expected.items():
        assert actual[name] == pytest.approx(expected_value, abs=1e-10)
