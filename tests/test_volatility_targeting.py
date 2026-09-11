import numpy as np
import pandas as pd
import pytest

from tacticore.strategies.volatility_targeting import (
    VolatilityTargetingConfig,
    build_month_end_targets,
)


def test_s10a_unlevered_scale_routes_residual_to_bond_without_future_returns() -> None:
    dates = pd.bdate_range("2024-01-02", periods=50)
    shocks = np.where(np.arange(50) % 2, 1.03, 0.97)
    prices = pd.DataFrame(
        {
            "EQ": 100 * np.cumprod(shocks),
            "US": 100 * np.cumprod(shocks),
            "GOLD": 100 * np.cumprod(shocks),
            "BOND": 100.0,
        },
        index=dates,
    )
    config = VolatilityTargetingConfig(
        ("EQ", "US", "GOLD", "BOND"), (0.25, 0.25, 0.25, 0.25), 20, 0.10, 1, 0, "monthly", 0, 0, 1
    )
    targets, diagnostics = build_month_end_targets(prices, config)
    date = diagnostics["realized_vol"].dropna().index[0]
    assert 0 <= diagnostics.loc[date, "scale"] <= 1
    assert diagnostics.loc[date, "scale"] < 1
    assert targets.loc[date].sum() == pytest.approx(1)
    assert targets.loc[date, "BOND"] >= 0.25


def test_s10a_uses_only_unfilled_aligned_daily_returns() -> None:
    dates = pd.bdate_range("2024-01-02", periods=80)
    prices = pd.DataFrame(
        {
            "EQ": np.linspace(100, 140, len(dates)),
            "US": np.linspace(100, 130, len(dates)),
            "GOLD": np.linspace(100, 120, len(dates)),
            "BOND": np.linspace(100, 105, len(dates)),
        },
        index=dates,
    )
    prices.loc[dates[-10], "BOND"] = np.nan
    config = VolatilityTargetingConfig(
        ("EQ", "US", "GOLD", "BOND"), (0.25, 0.25, 0.25, 0.25), 20, 0.10, 1, 0, "monthly", 0, 0, 1
    )
    _, diagnostics = build_month_end_targets(prices, config)
    date = diagnostics["realized_vol"].dropna().index[-1]
    returns = prices.loc[:, list(config.symbols)].pct_change(fill_method=None).dropna(how="any")
    expected = returns.loc[:date].tail(20).mul(config.base_weights, axis=1).sum(axis=1).std(
        ddof=1
    ) * np.sqrt(252)
    assert diagnostics.loc[date, "realized_vol"] == pytest.approx(expected)
