from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli

from tacticore.strategies.china_sector_rotation import (
    build_execution_weights,
    valid_observation_momentum,
)


@dataclass(frozen=True)
class ChinaSectorBreadthConfig:
    momentum_lookback: int
    breadth_threshold: float
    min_eligible_sectors: int
    rebalance_frequency: str
    execution_policy: str
    fallback_symbol: str
    fees: float
    slippage: float
    initial_cash: float

    def __post_init__(self) -> None:
        if self.momentum_lookback < 1 or self.min_eligible_sectors < 1:
            raise ValueError("lookback 与 min_eligible_sectors 必须为正")
        if self.breadth_threshold != 0.50:
            raise ValueError("S3B V1 仅支持预声明的 0.50 majority threshold")
        if self.rebalance_frequency != "monthly" or self.execution_policy != "SIGNAL_CHANGE_ONLY":
            raise ValueError("S3B V1 仅支持 monthly + SIGNAL_CHANGE_ONLY")


def load_sector_breadth_config(path: str | Path) -> ChinaSectorBreadthConfig:
    with Path(path).open("rb") as config_file:
        return ChinaSectorBreadthConfig(**tomli.load(config_file)["china_sector_breadth"])


def sector_breadth_state(
    prices: pd.DataFrame, config: ChinaSectorBreadthConfig, sectors: tuple[str, ...]
) -> pd.DataFrame:
    momentums = valid_observation_momentum(prices.loc[:, list(sectors)], config.momentum_lookback)
    month_ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    rows: list[dict[str, object]] = []
    for date in month_ends:
        current = momentums.loc[date]
        eligible = current.dropna()
        positive = int((eligible > 0).sum())
        count = len(eligible)
        breadth = positive / count if count else float("nan")
        if count < config.min_eligible_sectors:
            regime = "UNAVAILABLE"
        elif breadth > config.breadth_threshold:
            regime = "RISK_ON"
        else:
            regime = "RISK_OFF"
        rows.append(
            {
                "signal_date": date,
                "eligible_sector_count": count,
                "positive_sector_count": positive,
                "negative_sector_count": int((eligible <= 0).sum()),
                "unavailable_sector_count": len(sectors) - count,
                "breadth": breadth,
                "regime": regime,
            }
        )
    return pd.DataFrame(rows).set_index("signal_date")


def build_month_end_targets(
    prices: pd.DataFrame, config: ChinaSectorBreadthConfig, sectors: tuple[str, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    states = sector_breadth_state(prices, config, sectors)
    momentums = valid_observation_momentum(prices.loc[:, list(sectors)], config.momentum_lookback)
    targets = pd.DataFrame(0.0, index=states.index, columns=prices.columns)
    for signal_date in pd.DatetimeIndex(states.index):
        state = states.loc[signal_date]
        if state["regime"] == "RISK_ON":
            eligible = momentums.loc[signal_date].dropna().index
            targets.loc[signal_date, eligible] = 1.0 / len(eligible)
        else:
            targets.loc[signal_date, config.fallback_symbol] = 1.0
    return targets, states


__all__ = [
    "ChinaSectorBreadthConfig",
    "build_execution_weights",
    "build_month_end_targets",
    "load_sector_breadth_config",
    "sector_breadth_state",
]
