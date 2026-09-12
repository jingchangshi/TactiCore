from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import rqalpha.api

from tacticore.data.tradability import AssetLifetime, build_tradability_mask
from tacticore.engines.rqalpha_adapter import build_rqalpha_config, run_rqalpha
from tacticore.engines.vectorbt_adapter import run_vectorbt
from tacticore.strategies.global_dual_momentum import GlobalDualMomentumConfig


def test_vectorbt_adapter_returns_required_metrics(
    simple_prices: pd.DataFrame, strategy_config: GlobalDualMomentumConfig
) -> None:
    lifetimes = {symbol: AssetLifetime(symbol, simple_prices.index[0]) for symbol in simple_prices}
    result = run_vectorbt(
        simple_prices,
        strategy_config,
        tradability_mask=build_tradability_mask(
            simple_prices.index, list(simple_prices), lifetimes, simple_prices
        ),
        lifetimes=lifetimes,
    )

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
    config = build_rqalpha_config(
        "2020-01-01",
        "2024-12-31",
        initial_cash=strategy_config.initial_cash,
        fees=strategy_config.fees,
        slippage=strategy_config.slippage,
        bundle_path=tmp_path / "bundle",
        rqalpha_major_version=5,
    )

    assert config["base"]["frequency"] == "1d"
    assert config["base"]["accounts"] == {"STOCK": strategy_config.initial_cash}
    assert config["base"]["data_bundle_path"] == str(tmp_path / "bundle")
    assert config["mod"]["sys_simulation"]["slippage"] == strategy_config.slippage
    assert config["mod"]["sys_simulation"]["volume_limit"] is True
    assert config["mod"]["sys_simulation"]["volume_percent"] == 0.25
    assert config["mod"]["sys_transaction_cost"]["cn_stock_min_commission"] == 0


def test_rqalpha_6_config_enables_native_insufficient_cash_handling(
    strategy_config: GlobalDualMomentumConfig, tmp_path: Path
) -> None:
    config = build_rqalpha_config(
        "2020-01-01",
        "2024-12-31",
        initial_cash=strategy_config.initial_cash,
        fees=strategy_config.fees,
        slippage=strategy_config.slippage,
        bundle_path=tmp_path / "bundle",
        rqalpha_major_version=6,
        partial_fill_on_insufficient_cash=True,
    )

    assert config["base"]["partial_fill_on_insufficient_cash"] is True
    assert config["base"]["capital_gain_tax_rate"] == 0
    assert config["mod"]["sys_transaction_cost"]["stock_min_commission"] == 0
    assert "cn_stock_min_commission" not in config["mod"]["sys_transaction_cost"]


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
        "symbol,tushare_symbol,rqalpha_symbol,name,asset_class,region,currency,role,"
        "data_source,start_date\n"
        "A,A.SH,A.XSHG,A,equity,China,CNY,tradable,test,2020-01-01\n"
        "B,B.SH,B.XSHG,B,equity,China,CNY,tradable,test,2020-01-01\n"
        "C,C.SH,C.XSHG,C,equity,China,CNY,tradable,test,2020-01-01\n"
        "BOND,BOND.SH,BOND.XSHG,Bond,bond,China,CNY,tradable,test,2020-01-01\n",
        encoding="utf-8",
    )
    orders: dict[str, float] = {}
    order_calls: list[tuple[str, float]] = []
    history_calls: list[tuple[str, int, bool, str]] = []
    scheduled: list[tuple[Any, int]] = []

    def history_bars(
        symbol: str,
        count: int,
        frequency: str,
        field: str,
        *,
        skip_suspended: bool,
        include_now: bool,
        adjust_type: str,
    ) -> np.ndarray:
        del frequency, field, skip_suspended
        history_calls.append((symbol, count, include_now, adjust_type))
        end = {"A.XSHG": 1.3, "B.XSHG": 1.2, "C.XSHG": 0.9}[symbol]
        return np.linspace(1.0, end, count)

    class SchedulerStub:
        @staticmethod
        def run_monthly(callback: Any, tradingday: int) -> None:
            scheduled.append((callback, tradingday))

    class InstrumentStub:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def active_at(self, now: pd.Timestamp) -> bool:
            return now >= pd.Timestamp("2020-01-01") and self.symbol != "C.XSHG"

    monkeypatch.setattr(rqalpha.api, "history_bars", history_bars)
    monkeypatch.setattr(rqalpha.api, "instruments", InstrumentStub)

    def record_order(symbol: str, weight: float) -> None:
        order_calls.append((symbol, weight))
        orders[symbol] = weight

    monkeypatch.setattr(rqalpha.api, "order_target_percent", record_order)
    monkeypatch.setattr(rqalpha.api, "scheduler", SchedulerStub(), raising=False)
    monkeypatch.setattr(rqalpha.api, "update_universe", lambda symbols: None)

    from tacticore.engines.rqalpha_adapter import build_callbacks

    target_records: list[dict[str, Any]] = []
    init, rebalance = build_callbacks(strategy_config, universe_file, target_records)
    init(None)
    rebalance(type("Context", (), {"now": pd.Timestamp("2021-01-04")})(), None)

    assert scheduled == [(rebalance, 1)]
    assert all(
        count == 4 and not include_now and adjust_type == "pre"
        for _, count, include_now, adjust_type in history_calls
    )
    assert {symbol for symbol, *_ in history_calls} == {"A.XSHG", "B.XSHG"}
    assert orders == {"A.XSHG": 0.5, "B.XSHG": 0.5, "BOND.XSHG": 0.0}
    assert order_calls == [("BOND.XSHG", 0.0), ("A.XSHG", 0.5), ("B.XSHG", 0.5)]
    assert target_records == [
        {
            "rebalance_date": pd.Timestamp("2021-01-04"),
            "targets": {"A": 0.5, "B": 0.5},
        }
    ]
