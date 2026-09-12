import numpy as np
import pandas as pd
import pytest

from tacticore.data.tradability import (
    AssetLifetime,
    UntradableTargetError,
    active_at,
    build_tradability_mask,
    first_executable_complete_target,
    price_available_at,
    validate_execution_targets,
)


def test_asset_lifetime_boundaries_and_price_availability() -> None:
    asset = AssetLifetime("A", pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03"))
    prices = pd.DataFrame({"A": [np.nan, 10.0, 11.0]}, index=pd.date_range("2024-01-01", periods=3))
    assert not active_at(asset, pd.Timestamp("2024-01-01"))
    assert active_at(asset, pd.Timestamp("2024-01-02"))
    assert not active_at(asset, pd.Timestamp("2024-01-04"))
    assert not price_available_at(prices, "A", pd.Timestamp("2024-01-01"))
    assert price_available_at(prices, "A", pd.Timestamp("2024-01-02"))


def test_positive_targets_require_tradability_but_zero_targets_do_not() -> None:
    dates = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    prices = pd.DataFrame({"A": [10.0, 10.0]}, index=dates)
    lifetime = {"A": AssetLifetime("A", dates[1])}
    mask = build_tradability_mask(dates, ["A"], lifetime, prices)
    invalid = pd.DataFrame({"A": [1.0, np.nan]}, index=dates)
    with pytest.raises(UntradableTargetError, match="execution_date=2024-01-01"):
        validate_execution_targets(invalid, prices, mask, lifetime)
    validate_execution_targets(pd.DataFrame({"A": [0.0, 1.0]}, index=dates), prices, mask, lifetime)


def test_fallback_before_listing_has_no_executable_target_and_inception_is_first_complete() -> None:
    dates = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    prices = pd.DataFrame({"RISK": [10.0, 10.0], "BOND": [10.0, 10.0]}, index=dates)
    lifetimes = {"RISK": AssetLifetime("RISK", dates[0]), "BOND": AssetLifetime("BOND", dates[1])}
    mask = build_tradability_mask(dates, ["RISK", "BOND"], lifetimes, prices)
    targets = pd.DataFrame({"RISK": [0.0, 0.0], "BOND": [1.0, 1.0]}, index=dates)
    with pytest.raises(UntradableTargetError):
        validate_execution_targets(targets.iloc[:1], prices, mask, lifetimes)
    assert first_executable_complete_target(targets, mask) == dates[1]
