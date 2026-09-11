from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli


@dataclass(frozen=True)
class StaticAllocationConfig:
    symbols: tuple[str, ...]
    weights: tuple[float, ...]
    rebalance_frequency: str
    fees: float
    slippage: float
    initial_cash: float


def load_static_allocation_config(path: str | Path) -> StaticAllocationConfig:
    with Path(path).open("rb") as config_file:
        raw = tomli.load(config_file)["static_strategic_allocation"]
    raw["symbols"] = tuple(raw["symbols"])
    raw["weights"] = tuple(raw["weights"])
    return StaticAllocationConfig(**raw)


def build_execution_weights(prices: pd.DataFrame, config: StaticAllocationConfig) -> pd.DataFrame:
    required = ("510300.SS", "513500.SS", "518880.SS", "511010.SS")
    if config.symbols != required or config.weights != (0.25, 0.25, 0.25, 0.25):
        raise ValueError("S30 requires the frozen four 25% assets")
    if set(config.symbols).difference(prices.columns):
        raise ValueError("S30 requires four available 25% assets")
    common = prices.loc[:, list(config.symbols)].dropna().index
    if common.empty:
        raise ValueError("S30 has no common valid date")
    execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    target = pd.Series(
        dict(zip(config.symbols, config.weights, strict=True)), index=prices.columns
    ).fillna(0.0)
    execution.loc[common[0]] = target
    year_ends = prices.loc[common].groupby(pd.DatetimeIndex(common).to_period("Y")).tail(1).index
    for signal_date in year_ends:
        location = int(prices.index.get_indexer(pd.Index([signal_date]))[0]) + 1
        if location < len(prices.index):
            execution.iloc[location] = target
    return execution
