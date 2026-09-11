# ruff: noqa: E501
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tomli


@dataclass(frozen=True)
class InverseVolConfig:
    vol_window: int
    min_eligible_assets: int
    rebalance_frequency: str
    fallback_symbol: str
    fees: float
    slippage: float
    initial_cash: float

    def __post_init__(self) -> None:
        if (
            self.vol_window != 60
            or self.min_eligible_assets != 6
            or self.rebalance_frequency != "monthly"
        ):
            raise ValueError("S4A V1 requires 60 returns, six assets, and monthly targets")


def load_inverse_vol_config(path: str | Path) -> InverseVolConfig:
    with Path(path).open("rb") as config_file:
        return InverseVolConfig(**tomli.load(config_file)["inverse_vol_allocation"])


def valid_return_volatility(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    """Trailing standard deviation of each asset's own valid daily returns."""
    result = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    for symbol in prices:
        returns = prices[symbol].dropna().pct_change().dropna()
        result.loc[returns.index, symbol] = returns.rolling(window, min_periods=window).std()
    return result


def build_month_end_targets(
    prices: pd.DataFrame,
    config: InverseVolConfig,
    risk_symbols: tuple[str, ...],
    *,
    equal_weight: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    risk = prices.loc[:, list(risk_symbols)]
    volatility = valid_return_volatility(risk, config.vol_window)
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=ends, columns=prices.columns)
    diagnostics: list[dict[str, object]] = []
    for date in ends:
        current = volatility.loc[date]
        eligible = current.notna() & risk.loc[date].notna() & current.gt(0)
        symbols = list(eligible[eligible].index)
        if len(symbols) < config.min_eligible_assets:
            targets.loc[date, config.fallback_symbol] = 1.0
        elif equal_weight:
            targets.loc[date, symbols] = 1.0 / len(symbols)
        else:
            raw = 1.0 / current.loc[symbols]
            targets.loc[date, symbols] = raw / raw.sum()
        diagnostics.append(
            {
                "signal_date": date,
                "eligible_asset_count": len(symbols),
                "regime": "RISK" if len(symbols) >= config.min_eligible_assets else "FALLBACK",
            }
        )
    return targets, pd.DataFrame(diagnostics).set_index("signal_date")
