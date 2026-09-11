import numpy as np
import pandas as pd
import pytest

from tacticore.strategies.china_sector_rotation import (
    ChinaSectorRotationConfig,
    build_execution_weights,
    build_month_end_targets,
    valid_observation_momentum,
)


def _config() -> ChinaSectorRotationConfig:
    return ChinaSectorRotationConfig(
        3, 3, 0.0, "BOND", 0.0, 0.0, 100_000, "monthly", "SIGNAL_CHANGE_ONLY"
    )


def _prices() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", "2024-04-02")
    return pd.DataFrame(
        {
            "A": 100 + np.arange(len(dates)),
            "B": 200 - np.arange(len(dates)),
            "C": 100.0,
            "BOND": 100.0,
        },
        index=dates,
    )


def test_valid_observation_momentum_keeps_missing_distinct_from_negative() -> None:
    prices = _prices()
    prices.loc["2024-01-31", "A"] = np.nan
    momentum = valid_observation_momentum(prices[["A", "B"]], 3)

    assert pd.isna(momentum.loc["2024-01-31", "A"])
    assert momentum.loc["2024-01-31", "B"] < 0


def test_positive_ranking_uses_symbol_tie_break_and_unused_sleeves_go_to_fallback() -> None:
    prices = _prices()
    prices["C"] = prices["A"]
    targets = build_month_end_targets(prices, _config(), ("C", "B", "A"))
    january = targets.loc["2024-01-31"]

    assert january["A"] == pytest.approx(1 / 3)
    assert january["C"] == pytest.approx(1 / 3)
    assert january["B"] == 0
    assert january["BOND"] == pytest.approx(1 / 3)
    assert january.sum() == pytest.approx(1.0)
    assert january[["A", "B", "C"]].max() <= 1 / 3 + 1e-12


def test_month_end_target_executes_next_observation_and_unchanged_target_is_skipped() -> None:
    prices = _prices()
    targets = build_month_end_targets(prices, _config(), ("A", "B", "C"))
    execution = build_execution_weights(prices, targets)

    assert execution.loc["2024-01-31"].isna().all()
    assert execution.loc["2024-02-01"].notna().all()
    assert execution.loc["2024-03-01"].isna().all()
