"""审计补充守卫：可选退市生命周期与“持仓转 0 但当日不可交易”。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tacticore.data.execution_guards import (
    lifetimes_from_universe_with_delisting,
    load_tradability_inputs_with_delisting,
    optional_delisted_date,
    validate_execution_targets_with_liquidations,
    validate_held_liquidations,
)
from tacticore.data.tradability import (
    AssetLifetime,
    UntradableTargetError,
    build_tradability_mask,
    validate_execution_targets,
)


def _universe(*, delisted: object = None, with_column: bool = True) -> pd.DataFrame:
    data: dict[str, list[object]] = {
        "start_date": [pd.Timestamp("2024-01-01")] * 2,
    }
    if with_column:
        data["delisted_date"] = [delisted, None]
    return pd.DataFrame(data, index=pd.Index(["A", "BOND"], name="symbol"))


def _mask(prices: pd.DataFrame, lifetimes: dict[str, AssetLifetime]) -> pd.DataFrame:
    return build_tradability_mask(prices.index, list(prices.columns), lifetimes, prices)


def test_lifetimes_without_the_optional_column_keep_the_frozen_semantics() -> None:
    lifetimes = lifetimes_from_universe_with_delisting(_universe(with_column=False))

    assert lifetimes["A"] == AssetLifetime("A", pd.Timestamp("2024-01-01"), None)
    assert lifetimes["BOND"].delisted_date is None


@pytest.mark.parametrize("raw", [None, "", np.nan, pd.NaT])
def test_empty_delisted_values_mean_not_delisted(raw: object) -> None:
    assert optional_delisted_date(raw) is None
    lifetime = lifetimes_from_universe_with_delisting(_universe(delisted=raw))["A"]
    assert lifetime.delisted_date is None


@pytest.mark.parametrize(
    "raw",
    [
        20240201,
        20240201.0,
        np.int64(20240201),
        np.float64(20240201.0),
        "20240201",
        "2024-02-01",
        "2024-02-01 09:30:00",
    ],
)
def test_integer_and_string_yyyymmdd_parse_as_dates(raw: object) -> None:
    """整数 YYYYMMDD 不得被解释成 1970 纳秒时间戳。"""
    assert optional_delisted_date(raw) == pd.Timestamp("2024-02-01")


@pytest.mark.parametrize("raw", [20240102.5, 123, 123.0, float("inf"), float("-inf")])
def test_non_yyyymmdd_numbers_are_rejected_instead_of_becoming_1970(raw: object) -> None:
    with pytest.raises(ValueError, match="YYYYMMDD|不可解析"):
        optional_delisted_date(raw)


def test_boolean_delisted_date_is_rejected() -> None:
    with pytest.raises(ValueError, match="不可解析"):
        optional_delisted_date(True)


def test_delisted_date_is_normalized_and_malformed_values_fail_closed() -> None:
    lifetimes = lifetimes_from_universe_with_delisting(_universe(delisted="2024-02-01 09:30:00"))

    assert lifetimes["A"].delisted_date == pd.Timestamp("2024-02-01")
    with pytest.raises(ValueError, match="不可解析"):
        lifetimes_from_universe_with_delisting(_universe(delisted="not-a-date"))


def test_load_tradability_inputs_with_delisting_reads_the_optional_csv_column(
    tmp_path: Path,
) -> None:
    path = tmp_path / "universe.csv"
    path.write_text(
        "symbol,tushare_symbol,rqalpha_symbol,asset_class,region,currency,role,"
        "data_source,start_date,delisted_date\n"
        "A,000001.SZ,000001.XSHE,equity,CN,CNY,tradable,fixture,2024-01-01,2024-02-01\n",
        encoding="utf-8",
        newline="\n",
    )
    dates = pd.DatetimeIndex(["2024-01-02", "2024-02-02"])
    prices = pd.DataFrame({"A": [10.0, 10.0]}, index=dates)

    mask, lifetimes = load_tradability_inputs_with_delisting(prices, str(path))

    assert lifetimes["A"].delisted_date == pd.Timestamp("2024-02-01")
    assert bool(mask.at[dates[1], "A"]) is False


def test_held_liquidation_on_an_untradable_day_closes_the_frozen_validator_gap() -> None:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    prices = pd.DataFrame({"A": [10.0, np.nan]}, index=dates)
    lifetimes = {"A": AssetLifetime("A", dates[0])}
    mask = _mask(prices, lifetimes)
    targets = pd.DataFrame({"A": [1.0, 0.0]}, index=dates)

    # 冻结 validator 只检查正目标，因此会放过这次不可执行的清仓。
    validate_execution_targets(targets, prices, mask, lifetimes)
    with pytest.raises(UntradableTargetError, match="不可交易清仓目标"):
        validate_held_liquidations(targets, prices, mask, lifetimes)
    with pytest.raises(UntradableTargetError, match="不可交易清仓目标"):
        validate_execution_targets_with_liquidations(targets, prices, mask, lifetimes)


def test_held_liquidation_after_delisting_is_rejected() -> None:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = pd.DataFrame({"A": [10.0, 10.0, 10.0]}, index=dates)
    lifetimes = {"A": AssetLifetime("A", dates[0], pd.Timestamp("2024-01-03"))}
    mask = _mask(prices, lifetimes)
    targets = pd.DataFrame({"A": [1.0, 1.0, 0.0]}, index=dates)

    assert bool(mask.at[dates[2], "A"]) is False
    with pytest.raises(UntradableTargetError, match="不可交易清仓目标"):
        validate_held_liquidations(targets, prices, mask, lifetimes)


def test_normal_liquidation_and_never_held_zero_targets_pass() -> None:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = pd.DataFrame({"A": [10.0, 10.0, 10.0]}, index=dates)
    lifetimes = {"A": AssetLifetime("A", dates[0])}
    mask = _mask(prices, lifetimes)
    targets = pd.DataFrame({"A": [0.0, 1.0, 0.0]}, index=dates)

    validate_execution_targets_with_liquidations(targets, prices, mask, lifetimes)


def test_nan_rows_do_not_reset_the_held_state() -> None:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = pd.DataFrame({"A": [10.0, 10.0, np.nan]}, index=dates)
    lifetimes = {"A": AssetLifetime("A", dates[0])}
    mask = _mask(prices, lifetimes)
    targets = pd.DataFrame({"A": [1.0, np.nan, 0.0]}, index=dates)

    with pytest.raises(UntradableTargetError, match="不可交易清仓目标"):
        validate_held_liquidations(targets, prices, mask, lifetimes)


def test_composed_validator_keeps_the_frozen_positive_target_check() -> None:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    prices = pd.DataFrame({"A": [10.0, np.nan]}, index=dates)
    lifetimes = {"A": AssetLifetime("A", dates[0])}
    mask = _mask(prices, lifetimes)
    targets = pd.DataFrame({"A": [0.0, 0.5]}, index=dates)

    with pytest.raises(UntradableTargetError, match="不可交易正目标"):
        validate_execution_targets_with_liquidations(targets, prices, mask, lifetimes)
