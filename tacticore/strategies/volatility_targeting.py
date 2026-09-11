from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import tomli


@dataclass(frozen=True)
class VolatilityTargetingConfig:
    symbols: tuple[str, ...]
    base_weights: tuple[float, ...]
    vol_window: int
    target_volatility: float
    max_scale: float
    min_scale: float
    rebalance_frequency: str
    fees: float
    slippage: float
    initial_cash: float


def load_volatility_targeting_config(path: str | Path) -> VolatilityTargetingConfig:
    with Path(path).open("rb") as file:
        raw = tomli.load(file)["volatility_targeting"]
    raw["symbols"] = tuple(raw["symbols"])
    raw["base_weights"] = tuple(raw["base_weights"])
    return VolatilityTargetingConfig(**raw)


def build_month_end_targets(
    prices: pd.DataFrame, config: VolatilityTargetingConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(config.symbols) != 4 or config.base_weights != (0.25, 0.25, 0.25, 0.25):
        raise ValueError("S10A requires the frozen 25/25/25/25 base allocation")
    base = prices.loc[:, list(config.symbols)]
    aligned_returns = base.pct_change(fill_method=None).dropna(how="any")
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=ends, columns=prices.columns)
    diagnostics: list[dict[str, object]] = []
    bond = config.symbols[-1]
    for date in ends:
        returns = aligned_returns.loc[:date].tail(config.vol_window)
        if len(returns) != config.vol_window:
            realized = float("nan")
            scale = config.min_scale
        else:
            portfolio_returns = returns.mul(config.base_weights, axis=1).sum(axis=1)
            realized = float(portfolio_returns.std(ddof=1) * np.sqrt(252))
            scale = min(config.max_scale, config.target_volatility / realized)
            scale = max(config.min_scale, scale)
        target = pd.Series(0.0, index=prices.columns)
        target.loc[list(config.symbols)] = np.array(config.base_weights) * scale
        target.loc[bond] += 1.0 - scale
        targets.loc[date] = target
        diagnostics.append(
            {
                "signal_date": date,
                "realized_vol": realized,
                "scale": scale,
                "risk_reduction": 1 - scale,
                "bond_weight": target[bond],
            }
        )
    return targets, pd.DataFrame(diagnostics).set_index("signal_date")
