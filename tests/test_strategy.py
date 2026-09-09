import pandas as pd

from tacticore.strategies.global_dual_momentum import (
    GlobalDualMomentumConfig,
    build_execution_weights,
    build_month_end_targets,
    select_assets,
)


def test_relative_ranking_after_absolute_filter(
    strategy_config: GlobalDualMomentumConfig,
) -> None:
    momentum = pd.Series({"A": 0.10, "B": 0.20, "C": -0.01})

    assert select_assets(momentum, strategy_config) == ["B", "A"]


def test_fallback_when_no_asset_has_positive_momentum(
    strategy_config: GlobalDualMomentumConfig,
) -> None:
    momentum = pd.Series({"A": -0.10, "B": 0.0, "C": float("nan")})

    assert select_assets(momentum, strategy_config) == ["BOND"]


def test_missing_asset_is_excluded_not_filled(
    strategy_config: GlobalDualMomentumConfig,
) -> None:
    momentum = pd.Series({"A": 0.10, "B": float("nan"), "C": 0.20})

    assert select_assets(momentum, strategy_config) == ["C", "A"]


def test_month_end_signal_executes_on_next_observation_without_lookahead(
    simple_prices: pd.DataFrame, strategy_config: GlobalDualMomentumConfig
) -> None:
    targets = build_month_end_targets(simple_prices, strategy_config)
    execution = build_execution_weights(simple_prices, targets)

    january_signal = pd.Timestamp("2024-01-31")
    february_execution = pd.Timestamp("2024-02-01")
    assert january_signal in targets.index
    assert execution.loc[january_signal].isna().all()
    assert execution.loc[february_execution].notna().all()
    assert execution.loc[february_execution].sum() == 1.0


def test_future_price_change_does_not_change_prior_signal(
    simple_prices: pd.DataFrame, one_asset_config: GlobalDualMomentumConfig
) -> None:
    original = build_month_end_targets(simple_prices, one_asset_config)
    changed = simple_prices.copy()
    changed.loc[changed.index > "2024-01-31", "C"] *= 100.0

    recalculated = build_month_end_targets(changed, one_asset_config)

    pd.testing.assert_series_equal(original.loc["2024-01-31"], recalculated.loc["2024-01-31"])


def test_every_target_is_fully_invested(
    simple_prices: pd.DataFrame, strategy_config: GlobalDualMomentumConfig
) -> None:
    targets = build_month_end_targets(simple_prices, strategy_config)

    assert (targets.sum(axis=1) == 1.0).all()
    assert ((targets >= 0.0) & (targets <= 1.0)).all().all()
