from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli


@dataclass(frozen=True)
class ChinaSectorRotationConfig:
    momentum_lookback: int
    top_k: int
    absolute_momentum_threshold: float
    fallback_symbol: str
    fees: float
    slippage: float
    initial_cash: float
    rebalance_frequency: str
    execution_policy: str

    def __post_init__(self) -> None:
        if self.momentum_lookback < 1 or self.top_k < 1:
            raise ValueError("momentum_lookback 与 top_k 必须为正整数")
        if self.rebalance_frequency != "monthly":
            raise ValueError("S3A V1 仅支持 monthly")
        if self.execution_policy != "SIGNAL_CHANGE_ONLY":
            raise ValueError("S3A V1 仅支持 SIGNAL_CHANGE_ONLY")


def load_sector_rotation_config(path: str | Path) -> ChinaSectorRotationConfig:
    with Path(path).open("rb") as config_file:
        raw = tomli.load(config_file)["china_sector_rotation"]
    return ChinaSectorRotationConfig(**raw)


def valid_observation_momentum(prices: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """按资产自身有效价格计算 trailing lookback-observation 动量，不填补缺失。"""
    result = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    for symbol in prices:
        valid = prices[symbol].dropna()
        result.loc[valid.index, symbol] = valid / valid.shift(lookback) - 1.0
    return result


def _validate_prices(prices: pd.DataFrame, sectors: tuple[str, ...], fallback: str) -> None:
    required = set(sectors) | {fallback}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"价格数据缺少 S3A 资产: {sorted(missing)}")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("价格索引必须是 DatetimeIndex")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("价格日期必须唯一且递增")


def build_month_end_targets(
    prices: pd.DataFrame,
    config: ChinaSectorRotationConfig,
    sector_symbols: tuple[str, ...],
) -> pd.DataFrame:
    """月末以正动量行业前 top_k 的固定 sleeve 构造 target，余量留给防御资产。"""
    _validate_prices(prices, sector_symbols, config.fallback_symbol)
    sector_prices = prices.loc[:, list(sector_symbols)]
    momentums = valid_observation_momentum(sector_prices, config.momentum_lookback)
    month_ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    rows: list[pd.Series] = []
    for signal_date in month_ends:
        available = momentums.loc[signal_date].dropna()
        positive = available.loc[available > config.absolute_momentum_threshold]
        selected = sorted(positive.index, key=lambda symbol: (-positive[symbol], symbol))[
            : config.top_k
        ]
        target = pd.Series(0.0, index=prices.columns)
        sleeve = 1.0 / config.top_k
        target.loc[selected] = sleeve
        target.loc[config.fallback_symbol] = 1.0 - sleeve * len(selected)
        rows.append(target)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(month_ends), columns=prices.columns)


def build_execution_weights(prices: pd.DataFrame, month_end_targets: pd.DataFrame) -> pd.DataFrame:
    """将月末收盘 target 移至下一 canonical observation，禁止 same-close execution。"""
    execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    changed = month_end_targets.ne(month_end_targets.shift()).any(axis=1)
    for signal_date, target in month_end_targets.loc[changed].iterrows():
        location = int(prices.index.get_indexer(pd.Index([signal_date]))[0]) + 1
        if location < len(prices.index):
            execution.iloc[location] = target
    return execution
