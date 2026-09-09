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
    start_date: str, end_date: str, strategy: GlobalDualMomentumConfig, bundle_path: str | Path
) -> dict[str, Any]:
    """生成显式 RQAlpha 配置；bundle 由用户在仓库外维护。"""
    return {
        "base": {
            "start_date": start_date,
            "end_date": end_date,
            "frequency": "1d",
            "accounts": {"STOCK": strategy.initial_cash},
            "data_bundle_path": str(bundle_path),
        },
        "mod": {
            "sys_analyser": {"enabled": True, "output_file": None},
            "sys_simulation": {
                "enabled": True,
                "matching_type": "current_bar",
                "slippage_model": "PriceRatioSlippage",
                "slippage": strategy.slippage,
            },
            "sys_transaction_cost": {
                "stock_commission_multiplier": strategy.fees / 0.0008,
                "cn_stock_min_commission": 0,
                "tax_multiplier": 0,
            },
        },
    }


def build_callbacks(
    strategy: GlobalDualMomentumConfig, universe_path: str | Path
) -> tuple[Callable[[Any], None], Callable[[Any, Any], None]]:
    """构造可交给 rqalpha.run_func 的 init 与月度调仓函数。"""
    universe = load_universe(universe_path)
    source_to_rqalpha = universe["rqalpha_symbol"].to_dict()
    required = set(strategy.risk_symbols) | {strategy.fallback_symbol}
    missing = required.difference(source_to_rqalpha)
    if missing:
        raise ValueError(f"RQAlpha 映射缺少策略资产: {sorted(missing)}")

    def rebalance(context: Any, bar_dict: Any) -> None:
        from rqalpha.api import history_bars, order_target_percent

        del context, bar_dict
        momentum: dict[str, float] = {}
        for symbol in strategy.risk_symbols:
            closes = history_bars(
                source_to_rqalpha[symbol],
                strategy.lookback_trading_days + 1,
                "1d",
                "close",
                skip_suspended=True,
                include_now=False,
            )
            if closes is not None and len(closes) == strategy.lookback_trading_days + 1:
                momentum[symbol] = float(closes[-1] / closes[0] - 1.0)
        selected = select_assets(pd.Series(momentum, dtype=float), strategy)
        target = 1.0 / len(selected)
        for symbol in required:
            order_target_percent(source_to_rqalpha[symbol], target if symbol in selected else 0.0)

    def init(context: Any) -> None:
        from rqalpha.api import scheduler, update_universe

        del context
        update_universe([source_to_rqalpha[symbol] for symbol in required])
        scheduler.run_monthly(rebalance, tradingday=1)

    return init, rebalance


def run_rqalpha(
    strategy: GlobalDualMomentumConfig,
    universe_path: str | Path,
    start_date: str,
    end_date: str,
    bundle_path: str | Path,
) -> dict[str, Any]:
    """在本地已有中国市场 bundle 时运行权威事件驱动验证。"""
    from rqalpha import run_func

    bundle = Path(bundle_path)
    if not bundle.is_dir():
        raise FileNotFoundError(f"RQAlpha bundle 目录不存在: {bundle}")
    init, _ = build_callbacks(strategy, universe_path)
    config = build_rqalpha_config(start_date, end_date, strategy, bundle)
    result = run_func(init=init, config=config)
    if result is None:
        raise RuntimeError("RQAlpha 验证失败；请检查其错误日志")
    return result
