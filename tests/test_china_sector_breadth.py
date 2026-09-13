import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tacticore.strategies.china_sector_breadth import (
    ChinaSectorBreadthConfig,
    build_execution_weights,
    build_month_end_targets,
    sector_breadth_state,
)


def _config(minimum: int = 2) -> ChinaSectorBreadthConfig:
    return ChinaSectorBreadthConfig(
        3, 0.50, minimum, "monthly", "SIGNAL_CHANGE_ONLY", "BOND", 0.0, 0.0, 100_000
    )


def _prices() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", "2024-04-02")
    upward = 100 + np.arange(len(dates))
    return pd.DataFrame(
        {"A": upward, "B": upward, "C": 200 - np.arange(len(dates)), "BOND": 100.0}, index=dates
    )


def test_breadth_counts_and_majority_rule_are_strict() -> None:
    prices = _prices()
    states = sector_breadth_state(prices, _config(), ("A", "B", "C"))

    january = states.loc["2024-01-31"]
    assert january["eligible_sector_count"] == 3
    assert january["positive_sector_count"] == 2
    assert january["negative_sector_count"] == 1
    assert january["breadth"] == pytest.approx(2 / 3)
    assert january["regime"] == "RISK_ON"
    prices["B"] = prices["C"]
    assert (
        sector_breadth_state(prices, _config(), ("A", "B", "C")).loc["2024-01-31", "regime"]
        == "RISK_OFF"
    )


def test_unavailable_is_not_negative_and_uses_fallback() -> None:
    prices = _prices()
    prices.loc["2024-01-31", "B"] = np.nan
    targets, states = build_month_end_targets(prices, _config(3), ("A", "B", "C"))

    assert states.loc["2024-01-31", "regime"] == "UNAVAILABLE"
    assert targets.loc["2024-01-31", "BOND"] == 1.0


def test_risk_on_holds_all_eligible_equally_and_execution_is_next_day_only() -> None:
    prices = _prices()
    targets, _ = build_month_end_targets(prices, _config(), ("A", "B", "C"))
    execution = build_execution_weights(prices, targets)

    january = targets.loc["2024-01-31"]
    assert january[["A", "B", "C"]].tolist() == pytest.approx([1 / 3] * 3)
    assert january["BOND"] == 0.0
    assert execution.loc["2024-01-31"].isna().all()
    assert execution.loc["2024-02-01"].notna().all()
    assert execution.loc["2024-03-01"].isna().all()


def test_s3a_historical_report_remains_frozen() -> None:
    report = Path(__file__).resolve().parents[1] / "research/results/S3_SECTOR_BASELINE_V1.md"

    assert hashlib.sha256(report.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == (
        "981eb6396876f73f6996372627074dbfaf754c585c3f44bb86fb41668bdce8a7"
    )
