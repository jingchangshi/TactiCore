from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import rqalpha.api

from tacticore.engines.rqalpha_adapter import build_rqalpha_config, run_rqalpha
from tacticore.engines.vectorbt_adapter import run_vectorbt
from tacticore.strategies.global_dual_momentum import GlobalDualMomentumConfig


def test_vectorbt_adapter_returns_required_metrics(
    simple_prices: pd.DataFrame, strategy_config: GlobalDualMomentumConfig
) -> None:
    result = run_vectorbt(simple_prices, strategy_config)

    assert set(result.metrics) == {
        "cagr",
        "max_drawdown",
        "sharpe",
        "calmar",
        "turnover",
        "trade_count",
        "average_holding_days",
    }
    assert result.metrics["trade_count"] > 0
    assert result.metrics["turnover"] == 1.0


def test_rqalpha_config_is_daily_stock_account(
    strategy_config: GlobalDualMomentumConfig, tmp_path: Path
) -> None:
    config = build_rqalpha_config("2020-01-01", "2024-12-31", strategy_config, tmp_path / "bundle")

    assert config["base"]["frequency"] == "1d"
    assert config["base"]["accounts"] == {"STOCK": strategy_config.initial_cash}
    assert config["base"]["data_bundle_path"] == str(tmp_path / "bundle")
    assert config["mod"]["sys_simulation"]["slippage"] == strategy_config.slippage
    assert config["mod"]["sys_transaction_cost"]["cn_stock_min_commission"] == 0


def test_rqalpha_run_fails_clearly_without_bundle(
    strategy_config: GlobalDualMomentumConfig, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError, match="bundle 目录不存在"):
        run_rqalpha(
            strategy_config,
            tmp_path / "universe.csv",
            "2020-01-01",
            "2024-12-31",
            tmp_path / "missing-bundle",
        )


def test_rqalpha_callback_uses_prior_bars_and_submits_ranked_targets(
    strategy_config: GlobalDualMomentumConfig, tmp_path: Path, monkeypatch: Any
) -> None:
    universe_file = tmp_path / "universe.csv"
    universe_file.write_text(
        "symbol,rqalpha_symbol,name,asset_class,region,currency,role,data_source,start_date\n"
        "A,A.XSHG,A,equity,China,CNY,tradable,test,2020-01-01\n"
        "B,B.XSHG,B,equity,China,CNY,tradable,test,2020-01-01\n"
        "C,C.XSHG,C,equity,China,CNY,tradable,test,2020-01-01\n"
        "BOND,BOND.XSHG,Bond,bond,China,CNY,tradable,test,2020-01-01\n",
        encoding="utf-8",
    )
    orders: dict[str, float] = {}
    history_calls: list[tuple[str, int, bool]] = []
    scheduled: list[tuple[Any, int]] = []

    def history_bars(
        symbol: str,
        count: int,
        frequency: str,
        field: str,
        *,
        skip_suspended: bool,
        include_now: bool,
    ) -> np.ndarray:
        del frequency, field, skip_suspended
        history_calls.append((symbol, count, include_now))
        end = {"A.XSHG": 1.3, "B.XSHG": 1.2, "C.XSHG": 0.9}[symbol]
        return np.linspace(1.0, end, count)

    class SchedulerStub:
        @staticmethod
        def run_monthly(callback: Any, tradingday: int) -> None:
            scheduled.append((callback, tradingday))

    monkeypatch.setattr(rqalpha.api, "history_bars", history_bars)
    monkeypatch.setattr(
        rqalpha.api, "order_target_percent", lambda symbol, weight: orders.update({symbol: weight})
    )
    monkeypatch.setattr(rqalpha.api, "scheduler", SchedulerStub(), raising=False)
    monkeypatch.setattr(rqalpha.api, "update_universe", lambda symbols: None)

    from tacticore.engines.rqalpha_adapter import build_callbacks

    init, rebalance = build_callbacks(strategy_config, universe_file)
    init(None)
    rebalance(None, None)

    assert scheduled == [(rebalance, 1)]
    assert all(count == 4 and not include_now for _, count, include_now in history_calls)
    assert orders == {"A.XSHG": 0.5, "B.XSHG": 0.5, "C.XSHG": 0.0, "BOND.XSHG": 0.0}
