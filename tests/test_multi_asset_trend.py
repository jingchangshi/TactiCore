import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import AssetLifetime, build_tradability_mask
from tacticore.data.universe import load_universe
from tacticore.engines.vectorbt_adapter import run_target_weights, run_vectorbt
from tacticore.strategies.global_dual_momentum import load_strategy_config
from tacticore.strategies.multi_asset_trend import (
    MultiAssetTrendConfig,
    build_execution_weights,
    build_month_end_targets,
    build_signal_change_execution_weights,
    build_strict_month_end_targets,
    load_trend_config,
    valid_observation_moving_average,
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


def _synthetic_pit(prices: pd.DataFrame):
    lifetimes = {symbol: AssetLifetime(symbol, prices.index[0]) for symbol in prices}
    return build_tradability_mask(prices.index, list(prices), lifetimes, prices), lifetimes


def test_repository_s2_baseline_is_exactly_frozen() -> None:
    config = load_trend_config(ROOT / "config/strategy.toml")

    assert config.trend_window == 200
    assert config.rebalance_frequency == "monthly"
    assert config.fallback_symbol == "511010.SS"
    assert config.risk_symbols == load_strategy_config(ROOT / "config/strategy.toml").risk_symbols


def test_s2_v1_report_is_unchanged() -> None:
    report = ROOT / "research/results/S2_BASELINE_ECONOMIC_SCREEN_V1.md"

    assert hashlib.sha256(report.read_bytes()).hexdigest() == (
        "f27ca774015eaeda77521b8d590d15ef76a27531aaa5d6b6eb419b785abc6b04"
    )


def test_internal_nan_does_not_invalidate_latest_200_valid_observations() -> None:
    dates = pd.bdate_range("2023-01-02", periods=205)
    prices = pd.DataFrame({"A": np.arange(205, dtype=float)}, index=dates)
    prices.loc[dates[-100], "A"] = np.nan

    valid = valid_observation_moving_average(prices, 200)
    strict = prices.rolling(200, min_periods=200).mean()

    assert valid.loc[dates[-1], "A"] == pytest.approx(prices["A"].dropna().tail(200).mean())
    assert pd.isna(strict.loc[dates[-1], "A"])


def test_exactly_200_valid_observations_are_sufficient() -> None:
    dates = pd.bdate_range("2023-01-02", periods=201)
    prices = pd.DataFrame({"A": np.arange(201, dtype=float)}, index=dates)
    prices.loc[dates[0], "A"] = np.nan

    moving_average = valid_observation_moving_average(prices, 200)

    assert moving_average.loc[dates[-1], "A"] == pytest.approx(prices["A"].dropna().mean())


def test_current_missing_price_is_unavailable(
    trend_config: MultiAssetTrendConfig,
) -> None:
    prices = _prices()
    prices.loc["2024-01-31", "A"] = np.nan

    target = build_month_end_targets(prices, trend_config).loc["2024-01-31"]

    assert target["A"] == 0.0
    assert target["B"] == 0.0
    assert target["BOND"] == 1.0


def test_insufficient_valid_observations_are_unavailable(
    trend_config: MultiAssetTrendConfig,
) -> None:
    prices = _prices()
    prices.loc[prices.index < "2024-01-31", "A"] = np.nan

    target = build_month_end_targets(prices, trend_config).loc["2024-01-31"]

    assert target["A"] == 0.0


def test_missing_value_outside_latest_valid_window_does_not_change_target() -> None:
    dates = pd.bdate_range("2023-01-02", periods=205)
    values = np.arange(205, dtype=float) + 100
    original = pd.DataFrame({"A": values, "BOND": values}, index=dates)
    changed = original.copy()
    changed.loc[dates[0], "A"] = np.nan
    config = MultiAssetTrendConfig(200, "BOND", ("A",), 0.0, 0.0, 100_000)

    original_target = build_month_end_targets(original, config).iloc[-1]
    changed_target = build_month_end_targets(changed, config).iloc[-1]

    pd.testing.assert_series_equal(original_target, changed_target)


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


def test_signal_change_only_skips_unchanged_target() -> None:
    dates = pd.bdate_range("2024-01-30", "2024-04-02")
    targets = pd.DataFrame(
        [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        index=pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-29"]),
        columns=["A", "BOND"],
    )

    execution = build_signal_change_execution_weights(
        pd.DataFrame(100.0, index=dates, columns=targets.columns), targets
    )

    assert execution.loc["2024-02-01"].notna().all()
    assert execution.loc["2024-03-01"].isna().all()
    assert execution.loc["2024-04-01"].notna().all()


def test_trend_change_creates_signal_change_order() -> None:
    dates = pd.bdate_range("2024-01-01", "2024-03-01")
    prices = pd.DataFrame({"A": 100.0, "BOND": 100.0}, index=dates)
    prices.loc[dates <= "2024-01-31", "A"] = (
        np.arange((dates <= "2024-01-31").sum(), dtype=float) + 100
    )
    prices.loc[dates > "2024-01-31", "A"] = (
        np.arange((dates > "2024-01-31").sum(), dtype=float)[::-1] + 80
    )
    config = MultiAssetTrendConfig(3, "BOND", ("A",), 0.0, 0.0, 100_000)

    targets = build_month_end_targets(prices, config)
    execution = build_signal_change_execution_weights(prices, targets)
    mask, lifetimes = _synthetic_pit(prices)

    assert targets.loc["2024-01-31", "A"] == 1.0
    assert targets.loc["2024-02-29", "BOND"] == 1.0
    assert execution.loc["2024-03-01"].notna().all()


def test_availability_change_creates_signal_change_order() -> None:
    dates = pd.bdate_range("2024-01-01", "2024-03-01")
    prices = pd.DataFrame(
        {
            "A": np.arange(len(dates), dtype=float) + 100,
            "B": np.arange(len(dates), dtype=float) + 100,
            "BOND": 100.0,
        },
        index=dates,
    )
    prices.loc["2024-02-29", "A"] = np.nan
    config = MultiAssetTrendConfig(3, "BOND", ("A", "B"), 0.0, 0.0, 100_000)

    targets = build_month_end_targets(prices, config)
    execution = build_signal_change_execution_weights(prices, targets)

    assert targets.loc["2024-01-31", "A"] == 0.5
    assert targets.loc["2024-02-29", "A"] == 0.0
    assert targets.loc["2024-02-29", "B"] == 1.0
    assert execution.loc["2024-03-01"].notna().all()


def test_vectorbt_accounts_for_v2_orders_cash_and_fees() -> None:
    prices = _prices().ffill()
    targets = build_month_end_targets(
        prices, MultiAssetTrendConfig(3, "BOND", ("A", "B", "C"), 0.001, 0.0005, 100_000)
    )
    execution = build_signal_change_execution_weights(prices, targets)
    mask, lifetimes = _synthetic_pit(prices)

    result = run_target_weights(
        prices,
        execution,
        fees=0.001,
        slippage=0.0005,
        initial_cash=100_000,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )

    assert len(result.portfolio.orders.records_readable) > 0
    assert result.portfolio.orders.records_readable["Fees"].sum() > 0
    assert result.portfolio.cash(group_by=True).notna().all()


def test_v1_and_v2_semantics_are_explicitly_distinct(
    trend_config: MultiAssetTrendConfig,
) -> None:
    prices = _prices()
    prices.loc["2024-01-29", "A"] = np.nan

    v1 = build_strict_month_end_targets(prices, trend_config).loc["2024-01-31"]
    v2 = build_month_end_targets(prices, trend_config).loc["2024-01-31"]

    assert v1["A"] == 0.0
    assert v2["A"] == 0.5


def test_s1_frozen_output_survives_shared_adapter_extraction() -> None:
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    config = load_strategy_config(ROOT / "config/strategy.toml")
    expected = json.loads(
        (ROOT / "research/results/gdm_baseline_metrics.json").read_text(encoding="utf-8")
    )["metrics"]

    lifetimes = {
        symbol: AssetLifetime(symbol, row.start_date)
        for symbol, row in load_universe(ROOT / "config/universe.csv").iterrows()
    }
    actual = run_vectorbt(
        prices,
        config,
        tradability_mask=build_tradability_mask(prices.index, list(prices), lifetimes, prices),
        lifetimes=lifetimes,
    ).metrics

    for name, expected_value in expected.items():
        assert actual[name] == pytest.approx(expected_value, abs=1e-10)
