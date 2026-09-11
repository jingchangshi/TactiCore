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
