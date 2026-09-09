#!/usr/bin/env python3
"""运行 Global Dual Momentum baseline 的 VectorBT 研究 smoke test。"""

from argparse import ArgumentParser
from pathlib import Path

import numpy as np
import pandas as pd

from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe
from tacticore.engines.vectorbt_adapter import run_vectorbt
from tacticore.strategies.global_dual_momentum import load_strategy_config

ROOT = Path(__file__).resolve().parents[2]


def build_demo_prices(symbols: list[str]) -> pd.DataFrame:
    """生成确定性演示价格；仅验证研究管线，不代表真实历史或收益证据。"""
    dates = pd.bdate_range("2014-01-02", "2025-12-31")
    time = np.arange(len(dates), dtype=float)
    values: dict[str, np.ndarray] = {}
    for offset, symbol in enumerate(symbols):
        drift = 0.00008 + offset * 0.000012
        cycle = 0.0008 * np.sin(time / (45.0 + offset * 3.0) + offset)
        shock = -0.018 * np.exp(-(((time - 1650.0 - offset * 4.0) / 75.0) ** 2))
        log_returns = drift + cycle + shock
        values[symbol] = 100.0 * np.exp(np.cumsum(log_returns))
    return pd.DataFrame(values, index=dates)


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, help="date × symbol 的复权收盘价 CSV")
    args = parser.parse_args()

    config = load_strategy_config(ROOT / "config/strategy.toml")
    universe = load_universe(ROOT / "config/universe.csv")
    if args.prices:
        prices = load_price_csv(args.prices)
        data_label = str(args.prices)
    else:
        prices = build_demo_prices(universe["symbol"].tolist())
        data_label = "确定性演示数据（非真实市场研究结论）"

    result = run_vectorbt(prices, config)
    print(f"数据: {data_label}")
    for name, value in result.metrics.items():
        print(f"{name}: {value:.6f}")


if __name__ == "__main__":
    main()
