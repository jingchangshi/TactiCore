from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from tacticore.data.universe import load_universe
from tacticore.strategies.global_dual_momentum import (
    GlobalDualMomentumConfig,
    select_assets,
)


def build_rqalpha_config(
    start_date: str,
    end_date: str,
    *,
    initial_cash: float,
    fees: float,
    slippage: float,
    bundle_path: str | Path,
    rqalpha_major_version: int,
    partial_fill_on_insufficient_cash: bool = False,
) -> dict[str, Any]:
    """生成显式 RQAlpha 配置；bundle 由用户在仓库外维护。"""
    base: dict[str, Any] = {
        "start_date": start_date,
        "end_date": end_date,
        "frequency": "1d",
        "accounts": {"STOCK": initial_cash},
        "data_bundle_path": str(bundle_path),
    }
    transaction_cost: dict[str, Any] = {
        "stock_commission_multiplier": fees / 0.0008,
        "tax_multiplier": 0,
    }
    if rqalpha_major_version >= 6:
        base.update(
            {
                "capital_gain_tax_rate": 0,
                "partial_fill_on_insufficient_cash": partial_fill_on_insufficient_cash,
            }
        )
        transaction_cost["stock_min_commission"] = 0
    else:
        if partial_fill_on_insufficient_cash:
            raise ValueError("RQAlpha 6.3.0 之前不支持资金不足时原生部分成交")
        transaction_cost["cn_stock_min_commission"] = 0

    return {
        "base": base,
        "extra": {"log_level": "error"},
        "mod": {
            "sys_analyser": {"enabled": True, "output_file": None},
            "sys_simulation": {
                "enabled": True,
                "matching_type": "current_bar",
                "volume_limit": True,
                "volume_percent": 0.25,
                "slippage_model": "PriceRatioSlippage",
                "slippage": slippage,
            },
            "sys_transaction_cost": transaction_cost,
        },
    }


def build_callbacks(
    strategy: GlobalDualMomentumConfig,
    universe_path: str | Path,
    target_recorder: list[dict[str, Any]] | None = None,
) -> tuple[Callable[[Any], None], Callable[[Any, Any], None]]:
    """构造可交给 rqalpha.run_func 的 init 与月度调仓函数。"""
    universe = load_universe(universe_path)
    source_to_rqalpha = universe["rqalpha_symbol"].to_dict()
    required_symbols = tuple(dict.fromkeys((*strategy.risk_symbols, strategy.fallback_symbol)))
    missing = set(required_symbols).difference(source_to_rqalpha)
    if missing:
        raise ValueError(f"RQAlpha 映射缺少策略资产: {sorted(missing)}")

    def rebalance(context: Any, bar_dict: Any) -> None:
        from rqalpha.api import history_bars, instruments, order_target_percent

        del bar_dict
        listed_symbols = {
            symbol
            for symbol in required_symbols
            if instruments(source_to_rqalpha[symbol]).active_at(context.now)
        }
        momentum: dict[str, float] = {}
        for symbol in strategy.risk_symbols:
            if symbol not in listed_symbols:
                continue
            closes = history_bars(
                source_to_rqalpha[symbol],
                strategy.lookback_trading_days + 1,
                "1d",
                "close",
                skip_suspended=True,
                include_now=False,
                adjust_type="pre",
            )
            if closes is not None and len(closes) == strategy.lookback_trading_days + 1:
                momentum[symbol] = float(closes[-1] / closes[0] - 1.0)
        selected = select_assets(pd.Series(momentum, dtype=float), strategy)
        selected = [symbol for symbol in selected if symbol in listed_symbols]
        if not selected:
            return
        target = 1.0 / len(selected)
        if target_recorder is not None:
            target_recorder.append(
                {
                    "rebalance_date": pd.Timestamp(context.now).normalize(),
                    "targets": {symbol: target for symbol in selected},
                }
            )
        order_symbols = [
            symbol
            for symbol in required_symbols
            if symbol in listed_symbols and symbol not in selected
        ] + selected
        for symbol in order_symbols:
            order_target_percent(source_to_rqalpha[symbol], target if symbol in selected else 0.0)

    def init(context: Any) -> None:
        from rqalpha.api import scheduler, update_universe

        del context
        update_universe([source_to_rqalpha[symbol] for symbol in required_symbols])
        scheduler.run_monthly(rebalance, tradingday=1)

    return init, rebalance


def run_rqalpha(
    strategy: GlobalDualMomentumConfig,
    universe_path: str | Path,
    start_date: str,
    end_date: str,
    bundle_path: str | Path,
    target_recorder: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """在本地已有中国市场 bundle 时运行权威事件驱动验证。"""
    from rqalpha import run_func

    bundle = Path(bundle_path)
    if not bundle.is_dir():
        raise FileNotFoundError(f"RQAlpha bundle 目录不存在: {bundle}")
    init, _ = build_callbacks(strategy, universe_path, target_recorder)
    from rqalpha import __version__ as rqalpha_version

    config = build_rqalpha_config(
        start_date,
        end_date,
        initial_cash=strategy.initial_cash,
        fees=strategy.fees,
        slippage=strategy.slippage,
        bundle_path=bundle,
        rqalpha_major_version=int(rqalpha_version.split(".", 1)[0]),
    )
    result = run_func(init=init, config=config)
    if result is None:
        raise RuntimeError("RQAlpha 验证失败；请检查其错误日志")
    return result
