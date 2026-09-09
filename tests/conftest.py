from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from tacticore.strategies.global_dual_momentum import GlobalDualMomentumConfig


@pytest.fixture
def strategy_config() -> GlobalDualMomentumConfig:
    return GlobalDualMomentumConfig(
        lookback_trading_days=3,
        top_k=2,
        absolute_momentum_threshold=0.0,
        fallback_symbol="BOND",
        risk_symbols=("A", "B", "C"),
        fees=0.0,
        slippage=0.0,
        initial_cash=100_000.0,
    )


@pytest.fixture
def simple_prices() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-22", "2024-02-09")
    step = np.arange(len(dates), dtype=float)
    return pd.DataFrame(
        {
            "A": 100.0 + step * 3.0,
            "B": 100.0 + step * 2.0,
            "C": 100.0 - step,
            "BOND": 100.0 + step * 0.1,
        },
        index=dates,
    )


@pytest.fixture
def one_asset_config(strategy_config: GlobalDualMomentumConfig) -> GlobalDualMomentumConfig:
    return replace(strategy_config, top_k=1)
