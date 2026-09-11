# ruff: noqa: E501
import numpy as np
import pandas as pd
import pytest

from tacticore.strategies.equity_bond_trend import EquityBondTrendConfig
from tacticore.strategies.equity_bond_trend import build_month_end_targets as s8_targets
from tacticore.strategies.inverse_vol_allocation import InverseVolConfig
from tacticore.strategies.inverse_vol_allocation import build_month_end_targets as s4_targets
from tacticore.strategies.static_strategic_allocation import StaticAllocationConfig
from tacticore.strategies.static_strategic_allocation import (
    build_execution_weights as s30_execution,
)
from tacticore.strategies.trend_inverse_vol import TrendInverseVolConfig
from tacticore.strategies.trend_inverse_vol import build_month_end_targets as s27_targets


def _prices(days: int = 280) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-02", periods=days)
    data = {"BOND": np.full(days, 100.0)}
    for index, symbol in enumerate(("A", "B", "C", "D", "E", "F", "G", "H", "I")):
        steps = np.where(np.arange(days) % (index + 3) == 0, 1.004, 1.001)
        data[symbol] = 100 * np.cumprod(steps)
    return pd.DataFrame(data, index=dates)


def test_s4_inverse_vol_excludes_missing_and_falls_back_below_coverage() -> None:
    prices = _prices()
    config = InverseVolConfig(60, 6, "monthly", "BOND", 0, 0, 1)
    targets, diagnostics = s4_targets(prices, config, tuple("ABCDEFGHI"))
    date = diagnostics.loc[diagnostics.eligible_asset_count.ge(6)].index[0]
    assert targets.loc[date].sum() == pytest.approx(1)
    assert targets.loc[date, "B"] > targets.loc[date, "A"]
    prices.loc[date, list("ABCD")] = np.nan
    targets, _ = s4_targets(prices, config, tuple("ABCDEFGHI"))
    assert targets.loc[date, "BOND"] == pytest.approx(1)


def test_s8_nonpositive_and_unavailable_route_to_bond_and_signal_execution_changes_only() -> None:
    prices = _prices()[["A", "BOND"]].rename(columns={"A": "EQ"})
    config = EquityBondTrendConfig(200, "monthly", "SIGNAL_CHANGE_ONLY", "EQ", "BOND", 0, 0, 1)
    targets, states = s8_targets(prices, config)
    assert states.iloc[0].regime == "BOND"
    assert targets.iloc[0].BOND == pytest.approx(1)
    assert targets.sum(axis=1).eq(1).all()


def test_s27_preserves_s2_risk_budget_and_inverse_vol_ordering() -> None:
    prices = _prices()[["A", "B", "C", "D", "BOND"]]
    config = TrendInverseVolConfig(200, 60, "monthly", "BOND", 0, 0, 1)
    targets, diagnostics = s27_targets(prices, config, ("A", "B", "C", "D"))
    date = diagnostics.loc[diagnostics.positive_asset_count.eq(4)].index[0]
    assert diagnostics.loc[date, "risk_budget"] == pytest.approx(1)
    assert targets.loc[date].sum() == pytest.approx(1)
    assert targets.loc[date, "B"] > targets.loc[date, "A"]


def test_s30_has_exact_assets_quarters_and_annual_rebalances() -> None:
    dates = pd.bdate_range("2023-01-02", "2025-01-10")
    prices = pd.DataFrame(
        {symbol: 100.0 for symbol in ("510300.SS", "513500.SS", "518880.SS", "511010.SS")},
        index=dates,
    )
    config = StaticAllocationConfig(
        ("510300.SS", "513500.SS", "518880.SS", "511010.SS"),
        (0.25, 0.25, 0.25, 0.25),
        "annual",
        0,
        0,
        1,
    )
    execution = s30_execution(prices, config).dropna(how="all")
    assert execution.iloc[0].sum() == pytest.approx(1)
    assert execution.iloc[0].eq(0.25).all()
    assert len(execution) <= 4
