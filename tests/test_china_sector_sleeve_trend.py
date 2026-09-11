import numpy as np
import pandas as pd
import pytest

from tacticore.strategies.china_sector_rotation import build_execution_weights
from tacticore.strategies.china_sector_sleeve_trend import (
    ChinaSectorSleeveTrendConfig,
    build_month_end_targets,
)


def _config() -> ChinaSectorSleeveTrendConfig:
    return ChinaSectorSleeveTrendConfig(
        3, 0.0, "monthly", "SIGNAL_CHANGE_ONLY", "BOND", 0.0, 0.0, 100_000
    )


def test_fixed_sleeves_route_negative_and_unavailable_to_fallback_without_ranking() -> None:
    dates = pd.bdate_range("2024-01-01", "2024-03-01")
    prices = pd.DataFrame(
        {
            "A": 100 + np.arange(len(dates)),
            "B": 200 - np.arange(len(dates)),
            "C": 100.0,
            "BOND": 100.0,
        },
        index=dates,
    )
    prices.loc["2024-01-31", "C"] = np.nan
    targets, states = build_month_end_targets(prices, _config(), ("A", "B", "C"))
    target = targets.loc["2024-01-31"]
    assert target["A"] == pytest.approx(1 / 3)
    assert target["B"] == target["C"] == 0
    assert target["BOND"] == pytest.approx(2 / 3)
    assert states.loc["2024-01-31", "C"] == "UNAVAILABLE"
    assert states.loc["2024-01-31", "B"] == "NEGATIVE_SIGNAL"
    assert target.sum() == pytest.approx(1.0)


def test_target_executes_next_day_and_unchanged_state_skips_rebalance() -> None:
    dates = pd.bdate_range("2024-01-01", "2024-04-02")
    prices = pd.DataFrame(
        {"A": 100 + np.arange(len(dates)), "B": 100.0, "BOND": 100.0}, index=dates
    )
    targets, _ = build_month_end_targets(prices, _config(), ("A", "B"))
    execution = build_execution_weights(prices, targets)
    assert execution.loc["2024-01-31"].isna().all()
    assert execution.loc["2024-02-01"].notna().all()
    assert execution.loc["2024-03-01"].isna().all()
