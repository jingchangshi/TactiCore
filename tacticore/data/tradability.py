"""PIT 生命周期与执行目标合法性：只表达研究数据 contract。"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from tacticore.data.universe import load_universe


@dataclass(frozen=True)
class AssetLifetime:
    symbol: str
    listed_date: pd.Timestamp
    delisted_date: pd.Timestamp | None = None


class UntradableTargetError(ValueError):
    """正目标权重在执行日不具备生命周期或价格条件。"""


def active_at(asset: AssetLifetime, date: pd.Timestamp) -> bool:
    timestamp = pd.Timestamp(date).normalize()
    return timestamp >= asset.listed_date and (
        asset.delisted_date is None or timestamp <= asset.delisted_date
    )


def price_available_at(prices: pd.DataFrame, symbol: str, date: pd.Timestamp) -> bool:
    timestamp = pd.Timestamp(date)
    if symbol not in prices.columns or timestamp not in prices.index:
        return False
    value = float(prices.at[timestamp, symbol])  # type: ignore[arg-type]
    return bool(np.isfinite(value) and value > 0)


def lifetimes_from_universe(universe: pd.DataFrame) -> dict[str, AssetLifetime]:
    return {
        str(symbol): AssetLifetime(str(symbol), pd.Timestamp(row.start_date).normalize())
        for symbol, row in universe.iterrows()
    }


def load_tradability_inputs(
    prices: pd.DataFrame, universe_path: str
) -> tuple[pd.DataFrame, dict[str, AssetLifetime]]:
    """由显式 version-controlled universe 生成一次 runner 所需的 PIT 输入。"""
    lifetimes = lifetimes_from_universe(load_universe(universe_path))
    return build_tradability_mask(prices.index, list(prices.columns), lifetimes, prices), lifetimes


def build_tradability_mask(
    dates: pd.Index,
    symbols: list[str] | tuple[str, ...],
    lifetimes: Mapping[str, AssetLifetime],
    prices: pd.DataFrame,
) -> pd.DataFrame:
    index = pd.DatetimeIndex(dates)
    mask = pd.DataFrame(False, index=index, columns=symbols)
    for symbol in symbols:
        if symbol not in lifetimes:
            continue
        mask[symbol] = [
            active_at(lifetimes[symbol], date) and price_available_at(prices, symbol, date)
            for date in index
        ]
    return mask


def validate_execution_targets(
    execution_weights: pd.DataFrame,
    prices: pd.DataFrame,
    tradability_mask: pd.DataFrame,
    lifetimes: Mapping[str, AssetLifetime],
    *,
    tolerance: float = 1e-12,
) -> None:
    """禁止把 inactive 或无执行价的正权重静默交给模拟器。"""
    executions = execution_weights.dropna(how="all")
    for raw_date, weights in executions.iterrows():
        date = pd.Timestamp(raw_date)  # type: ignore[arg-type]
        for raw_symbol, raw_weight in weights.dropna().items():
            symbol, weight = str(raw_symbol), float(raw_weight)
            if weight <= tolerance:
                continue
            lifetime = lifetimes.get(symbol)
            tradable = (
                symbol in tradability_mask.columns
                and date in tradability_mask.index
                and bool(tradability_mask.at[date, symbol])
            )
            if lifetime is None or not tradable:
                listed = lifetime.listed_date.date().isoformat() if lifetime else "UNKNOWN"
                raise UntradableTargetError(
                    "不可交易正目标: "
                    f"execution_date={pd.Timestamp(date).date()} symbol={symbol} "
                    f"target_weight={weight:.12g} listed_date={listed} "
                    f"price_available={price_available_at(prices, symbol, date)}"
                )


def first_executable_complete_target(
    execution_weights: pd.DataFrame, tradability_mask: pd.DataFrame, *, tolerance: float = 1e-12
) -> pd.Timestamp:
    """完整 target 的第一个合法执行日；零权重 inactive 资产不阻碍 inception。"""
    for raw_date, weights in execution_weights.dropna(how="all").iterrows():
        date = pd.Timestamp(raw_date)  # type: ignore[arg-type]
        positive = weights.fillna(0.0) > tolerance
        symbols = [str(symbol) for symbol in positive.index[positive]]
        values = tradability_mask.loc[date, symbols]  # type: ignore[index]
        if positive.any() and bool(values.all()):  # type: ignore[union-attr]
            return date
    raise UntradableTargetError("没有可形成完整合法目标的执行日")
