from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli


@dataclass(frozen=True)
class MultiAssetTrendConfig:
    trend_window: int
    fallback_symbol: str
    risk_symbols: tuple[str, ...]
    fees: float
    slippage: float
    initial_cash: float
    rebalance_frequency: str = "monthly"

    def __post_init__(self) -> None:
        if self.trend_window < 1:
            raise ValueError("trend_window 必须为正整数")
        if self.rebalance_frequency != "monthly":
            raise ValueError("当前基线仅支持 monthly")


def load_trend_config(path: str | Path) -> MultiAssetTrendConfig:
    with Path(path).open("rb") as config_file:
        raw = tomli.load(config_file)["multi_asset_trend"]
    raw["risk_symbols"] = tuple(raw["risk_symbols"])
    return MultiAssetTrendConfig(**raw)


def _validate_prices(prices: pd.DataFrame, config: MultiAssetTrendConfig) -> None:
    required = set(config.risk_symbols) | {config.fallback_symbol}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"价格数据缺少策略资产: {sorted(missing)}")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("价格索引必须是 DatetimeIndex")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("价格日期必须唯一且递增")


def valid_observation_moving_average(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    """逐资产计算最近 window 个有效观测均值，不填补内部缺失值。"""
    result = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    for symbol in prices:
        valid = prices[symbol].dropna()
        result.loc[valid.index, symbol] = valid.rolling(window, min_periods=window).mean()
    return result


def _targets_from_moving_average(
    prices: pd.DataFrame,
    config: MultiAssetTrendConfig,
    moving_average: pd.DataFrame,
) -> pd.DataFrame:
    risk_prices = prices[list(config.risk_symbols)]
    month_periods = pd.DatetimeIndex(prices.index).to_period("M")
    month_ends = prices.groupby(month_periods).tail(1).index
    rows: list[pd.Series] = []
    dates: list[pd.Timestamp] = []
    for signal_date in month_ends:
        eligible = moving_average.loc[signal_date].notna() & risk_prices.loc[signal_date].notna()
        eligible_symbols = eligible[eligible].index
        if len(eligible_symbols) == 0:
            continue
        sleeve = 1.0 / len(eligible_symbols)
        uptrend = (
            risk_prices.loc[signal_date, eligible_symbols]
            > moving_average.loc[signal_date, eligible_symbols]
        )
        target = pd.Series(0.0, index=prices.columns)
        target.loc[uptrend[uptrend].index] = sleeve
        target.loc[config.fallback_symbol] = sleeve * int((~uptrend).sum())
        rows.append(target)
        dates.append(signal_date)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates), columns=prices.columns)


def build_month_end_targets(prices: pd.DataFrame, config: MultiAssetTrendConfig) -> pd.DataFrame:
    """用最近 200 个有效观测，按独立趋势分配等额 sleeve。"""
    _validate_prices(prices, config)
    risk_prices = prices[list(config.risk_symbols)]
    moving_average = valid_observation_moving_average(risk_prices, config.trend_window)
    return _targets_from_moving_average(prices, config, moving_average)


def build_strict_month_end_targets(
    prices: pd.DataFrame, config: MultiAssetTrendConfig
) -> pd.DataFrame:
    """保留 S2 V1 的连续 dataframe 行语义，只用于历史版本复现。"""
    _validate_prices(prices, config)
    risk_prices = prices[list(config.risk_symbols)]
    moving_average = risk_prices.rolling(
        config.trend_window, min_periods=config.trend_window
    ).mean()
    return _targets_from_moving_average(prices, config, moving_average)


def build_execution_weights(prices: pd.DataFrame, month_end_targets: pd.DataFrame) -> pd.DataFrame:
    """将月末信号移至下一观测日，禁止同一收盘价生成并执行信号。"""
    execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    for signal_date, target in month_end_targets.iterrows():
        next_location = int(prices.index.get_indexer(pd.Index([signal_date]))[0]) + 1
        if next_location < len(prices.index):
            execution.iloc[next_location] = target
    return execution


def build_signal_change_execution_weights(
    prices: pd.DataFrame, month_end_targets: pd.DataFrame
) -> pd.DataFrame:
    """仅当策略目标状态发生变化时，在下一观测日提交新目标。"""
    changed = month_end_targets.ne(month_end_targets.shift()).any(axis=1)
    return build_execution_weights(prices, month_end_targets.loc[changed])
