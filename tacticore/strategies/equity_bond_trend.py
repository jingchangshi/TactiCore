# ruff: noqa: E501
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli

from tacticore.strategies.china_sector_rotation import valid_observation_momentum


@dataclass(frozen=True)
class EquityBondTrendConfig:
    trend_window: int
    rebalance_frequency: str
    execution_policy: str
    equity_symbol: str
    bond_symbol: str
    fees: float
    slippage: float
    initial_cash: float

    def __post_init__(self) -> None:
        if (
            self.trend_window != 200
            or self.rebalance_frequency != "monthly"
            or self.execution_policy != "SIGNAL_CHANGE_ONLY"
        ):
            raise ValueError("S8A V1 requires 200-observation monthly signal changes")


def load_equity_bond_trend_config(path: str | Path) -> EquityBondTrendConfig:
    with Path(path).open("rb") as config_file:
        return EquityBondTrendConfig(**tomli.load(config_file)["equity_bond_trend"])


def build_month_end_targets(
    prices: pd.DataFrame, config: EquityBondTrendConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    subset = prices[[config.equity_symbol]]
    momentum = valid_observation_momentum(subset, config.trend_window)[config.equity_symbol]
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=ends, columns=prices.columns)
    states: list[dict[str, object]] = []
    for date in ends:
        value = momentum.loc[date]
        state = "EQUITY" if pd.notna(value) and value > 0 else "BOND"
        targets.loc[date, config.equity_symbol if state == "EQUITY" else config.bond_symbol] = 1.0
        states.append({"signal_date": date, "regime": state})
    return targets, pd.DataFrame(states).set_index("signal_date")
