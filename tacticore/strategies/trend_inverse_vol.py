# ruff: noqa: E501
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli

from tacticore.strategies.inverse_vol_allocation import valid_return_volatility
from tacticore.strategies.multi_asset_trend import valid_observation_moving_average


@dataclass(frozen=True)
class TrendInverseVolConfig:
    trend_window: int
    vol_window: int
    rebalance_frequency: str
    fallback_symbol: str
    fees: float
    slippage: float
    initial_cash: float

    def __post_init__(self) -> None:
        if (
            self.trend_window != 200
            or self.vol_window != 60
            or self.rebalance_frequency != "monthly"
        ):
            raise ValueError("S27A V1 requires 200-trend, 60-volatility, monthly targets")


def load_trend_inverse_vol_config(path: str | Path) -> TrendInverseVolConfig:
    with Path(path).open("rb") as config_file:
        return TrendInverseVolConfig(**tomli.load(config_file)["trend_inverse_vol"])


def build_month_end_targets(
    prices: pd.DataFrame, config: TrendInverseVolConfig, risk_symbols: tuple[str, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    risk = prices.loc[:, list(risk_symbols)]
    average = valid_observation_moving_average(risk, config.trend_window)
    volatility = valid_return_volatility(risk, config.vol_window)
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=ends, columns=prices.columns)
    rows: list[dict[str, object]] = []
    for date in ends:
        eligible = average.loc[date].notna() & volatility.loc[date].notna() & risk.loc[date].notna()
        positive = eligible & risk.loc[date].gt(average.loc[date]) & volatility.loc[date].gt(0)
        symbols = list(positive[positive].index)
        budget = len(symbols) / len(risk_symbols)
        if symbols:
            raw = 1.0 / volatility.loc[date, symbols]
            targets.loc[date, symbols] = budget * raw / raw.sum()
        targets.loc[date, config.fallback_symbol] = 1.0 - budget
        rows.append(
            {
                "signal_date": date,
                "positive_asset_count": len(symbols),
                "risk_budget": budget,
                "fallback_weight": 1.0 - budget,
            }
        )
    return targets, pd.DataFrame(rows).set_index("signal_date")
