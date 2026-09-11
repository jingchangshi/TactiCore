from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli

from tacticore.strategies.china_sector_rotation import (
    valid_observation_momentum,
)


@dataclass(frozen=True)
class ChinaSectorSleeveTrendConfig:
    trend_window: int
    absolute_momentum_threshold: float
    rebalance_frequency: str
    execution_policy: str
    fallback_symbol: str
    fees: float
    slippage: float
    initial_cash: float

    def __post_init__(self) -> None:
        if self.trend_window < 1 or self.absolute_momentum_threshold != 0.0:
            raise ValueError("S3C V1 requires 120-observation zero-threshold trend")
        if self.rebalance_frequency != "monthly" or self.execution_policy != "SIGNAL_CHANGE_ONLY":
            raise ValueError("S3C V1 requires monthly SIGNAL_CHANGE_ONLY")


def load_sector_sleeve_trend_config(path: str | Path) -> ChinaSectorSleeveTrendConfig:
    with Path(path).open("rb") as config_file:
        return ChinaSectorSleeveTrendConfig(**tomli.load(config_file)["china_sector_sleeve_trend"])


def sector_trend_states(
    prices: pd.DataFrame, config: ChinaSectorSleeveTrendConfig, sectors: tuple[str, ...]
) -> pd.DataFrame:
    momentums = valid_observation_momentum(prices.loc[:, list(sectors)], config.trend_window)
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    rows = []
    for date in ends:
        row = momentums.loc[date]
        states = {
            symbol: "UNAVAILABLE"
            if pd.isna(value)
            else "POSITIVE"
            if value > 0
            else "NEGATIVE_SIGNAL"
            for symbol, value in row.items()
        }
        rows.append({"signal_date": date, **states})
    return pd.DataFrame(rows).set_index("signal_date")


def build_month_end_targets(
    prices: pd.DataFrame, config: ChinaSectorSleeveTrendConfig, sectors: tuple[str, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    states = sector_trend_states(prices, config, sectors)
    sleeve = 1.0 / len(sectors)
    targets = pd.DataFrame(0.0, index=states.index, columns=prices.columns)
    for date in pd.DatetimeIndex(states.index):
        symbols = [symbol for symbol in sectors if states.at[date, symbol] == "POSITIVE"]
        targets.loc[date, symbols] = sleeve
        targets.loc[date, config.fallback_symbol] = 1.0 - sleeve * len(symbols)
    return targets, states
