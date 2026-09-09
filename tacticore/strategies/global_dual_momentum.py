from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli


@dataclass(frozen=True)
class GlobalDualMomentumConfig:
    lookback_trading_days: int
    top_k: int
    absolute_momentum_threshold: float
    fallback_symbol: str
    risk_symbols: tuple[str, ...]
    fees: float
    slippage: float
    initial_cash: float
    rebalance_frequency: str = "monthly"

    def __post_init__(self) -> None:
        if self.lookback_trading_days < 1:
            raise ValueError("lookback_trading_days 必须为正整数")
        if not 1 <= self.top_k <= len(self.risk_symbols):
            raise ValueError("top_k 必须在 1 和 risk_symbols 数量之间")
        if self.rebalance_frequency != "monthly":
            raise ValueError("当前 baseline 仅支持 monthly")


def load_strategy_config(path: str | Path) -> GlobalDualMomentumConfig:
    with Path(path).open("rb") as config_file:
        raw = tomli.load(config_file)["global_dual_momentum"]
    raw["risk_symbols"] = tuple(raw["risk_symbols"])
    return GlobalDualMomentumConfig(**raw)


def select_assets(momentum: pd.Series, config: GlobalDualMomentumConfig) -> list[str]:
    """先做绝对动量过滤，再按相对动量选择；无合格资产时持有防御资产。"""
    eligible = momentum.reindex(config.risk_symbols).dropna()
    eligible = eligible[eligible > config.absolute_momentum_threshold]
    selected = eligible.sort_values(ascending=False, kind="stable").head(config.top_k)
    return selected.index.tolist() if not selected.empty else [config.fallback_symbol]


def build_month_end_targets(prices: pd.DataFrame, config: GlobalDualMomentumConfig) -> pd.DataFrame:
    """用每个自然月最后一个观测日的收盘价计算月度目标权重。"""
    required = set(config.risk_symbols) | {config.fallback_symbol}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"价格数据缺少策略资产: {sorted(missing)}")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("价格索引必须是 DatetimeIndex")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("价格日期必须唯一且递增")

    momentum = prices / prices.shift(config.lookback_trading_days) - 1.0
    month_end_dates = prices.groupby(prices.index.to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=month_end_dates, columns=prices.columns)
    for signal_date in month_end_dates:
        selected = select_assets(momentum.loc[signal_date], config)
        targets.loc[signal_date, selected] = 1.0 / len(selected)
    return targets.loc[momentum.loc[month_end_dates, list(config.risk_symbols)].notna().any(axis=1)]


def build_execution_weights(prices: pd.DataFrame, month_end_targets: pd.DataFrame) -> pd.DataFrame:
    """把月末信号移到下一观测日，避免用同一收盘价生成并执行订单。"""
    execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    for signal_date, target in month_end_targets.iterrows():
        next_location = int(prices.index.get_indexer(pd.Index([signal_date]))[0]) + 1
        if next_location < len(prices.index):
            execution.iloc[next_location] = target
    return execution
