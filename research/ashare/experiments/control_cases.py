"""确定性对照案例（WP2.1）。

目的：在把任何"策略表现"当成研究发现之前，先用**答案已知**的案例校准整条链路
（快照 → 适配器 → `run_target_weights` → 指标）。一个在现金案例上都会算出正收益的
执行栈，不可能被信任去评价真实策略。

四个案例，答案都由构造方式决定，不由模拟器决定：

1. **现金**：目标权重恒 0。终值必须等于初始资金，回撤必须为 0。
2. **单 ETF 买入持有**：第一日满仓、之后不动。终值必须等于
   `初始资金 × 末价/首价`，误差只来自滑点与佣金。
3. **固定权重多资产低频再平衡**：两资产各 50%，按固定间隔再平衡。
   用构造价格和订单记录验证非调仓日保持持仓。
4. **股票池评分驱动组合**：按给定分数取前 N 名等权。用于验证
   `validate_execution_targets` 的拦截，不验证收益。

全部案例都标注为**模拟账户**：初始资金取任务书提到的约 7.6 万元量级，
但这是构造出来的输入，不是真实账户余额。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.ashare.data.fee_mapping import map_fees_to_vectorbt

#: 初始资金。取任务书提到的约 7.6 万元量级，但是**构造值**，不是真实账户余额。
INITIAL_CASH = 75_776.53

#: 基准日。仅为让构造的价格有确定答案，与任何真实市场日期无关。
DATES = pd.date_range("2026-01-05", periods=21, freq="B")


@dataclass(frozen=True)
class ControlCase:
    """一个对照案例的定义与期望。"""

    name: str
    description: str
    prices: pd.DataFrame
    targets: pd.DataFrame
    expected_final_equity: float | None
    expected_max_drawdown: float | None
    tolerance: float
    #: 该案例证明的是哪一条链路属性。
    proves: str


def _flat(rows: list[tuple[str, list[float]]]) -> pd.DataFrame:
    return pd.DataFrame({symbol: values for symbol, values in rows}, index=DATES)


def case_cash() -> ControlCase:
    """案例 1：现金。终值 = 初始资金，回撤 = 0。"""
    prices = _flat(
        [
            ("600000.SH", list(np.linspace(10.0, 12.0, len(DATES)))),
            ("510300.SH", list(np.linspace(4.0, 4.8, len(DATES)))),
        ]
    )
    targets = pd.DataFrame(0.0, index=DATES, columns=prices.columns)
    return ControlCase(
        name="cash",
        description="目标权重恒 0，不产生任何交易",
        prices=prices,
        targets=targets,
        expected_final_equity=INITIAL_CASH,
        expected_max_drawdown=0.0,
        tolerance=1e-6,
        proves="无交易时不产生费用、不产生权益变动；费用链路不会凭空扣钱",
    )


def case_single_etf_buy_and_hold() -> ControlCase:
    """案例 2：单 ETF 买入持有。终值 = 初始资金 × 末价/首价，扣除一次性成本。

    此案例每天提交 1.0 的目标；未提交目标应使用 NaN，0.0 则是清仓指令。
    单资产满仓时每天重申目标不会改变买入持有的经济敞口。
    """
    closes = list(np.linspace(4.000, 4.800, len(DATES)))
    prices = _flat([("510300.SH", closes)])
    targets = pd.DataFrame(1.0, index=DATES, columns=prices.columns)
    return ControlCase(
        name="single_etf_buy_and_hold",
        description="全期满仓 510300.SH，目标权重每日恒为 1.0",
        prices=prices,
        targets=targets,
        expected_final_equity=INITIAL_CASH * (closes[-1] / closes[0]),
        expected_max_drawdown=0.0,
        tolerance=1e-6,
        proves="买入持有的收益必须等于价格比；成本只应从终值中扣除，不应产生额外漂移",
    )


def case_fixed_weight_rebalance() -> ControlCase:
    """案例 3：两资产各 50%，每 5 个交易日再平衡。"""
    # 单资产买入持有区间仅适用于此处构造的单调价格，不是一般再平衡定理。
    up = list(np.linspace(10.0, 12.0, len(DATES)))
    down = list(np.linspace(20.0, 18.0, len(DATES)))
    prices = _flat([("600000.SH", up), ("600001.SH", down)])
    targets = pd.DataFrame(float("nan"), index=DATES, columns=prices.columns)
    for position in range(0, len(DATES), 5):
        targets.iloc[position] = 0.5
    return ControlCase(
        name="fixed_weight_rebalance",
        description="600000.SH 与 600001.SH 各 50%，每 5 个交易日再平衡",
        prices=prices,
        targets=targets,
        # 再平衡结果必须落在两个单资产买入持有构成的区间内。区间在测试里算。
        expected_final_equity=None,
        expected_max_drawdown=None,
        tolerance=1e-9,
        proves="非调仓日保持持仓；调仓日重新提交两资产各 50% 的目标",
    )


def case_scored_pool() -> ControlCase:
    """案例 4：按评分取前 2 名等权。用于验证目标合法性拦截。"""
    prices = _flat(
        [
            ("600000.SH", list(np.linspace(10.0, 11.0, len(DATES)))),
            ("600001.SH", list(np.linspace(20.0, 22.0, len(DATES)))),
            ("600002.SH", list(np.linspace(30.0, 29.0, len(DATES)))),
        ]
    )
    scores = {"600000.SH": 0.9, "600001.SH": 0.8, "600002.SH": 0.1}
    # 用 (score, symbol) 元组排序：dict.get 的签名允许返回 None，
    # 排序键必须是可比较的标量，否则类型上就是错的。
    selected = [
        symbol for symbol, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ][:2]
    targets = pd.DataFrame(0.0, index=DATES, columns=prices.columns)
    targets.iloc[0] = [
        1.0 / len(selected) if symbol in selected else 0.0 for symbol in prices.columns
    ]
    return ControlCase(
        name="scored_pool",
        description=f"按评分取前 2 名等权: {selected}",
        prices=prices,
        targets=targets,
        expected_final_equity=None,
        expected_max_drawdown=None,
        tolerance=1e-9,
        proves="评分驱动的目标权重能进入引擎；被排除资产的权重必须严格为 0",
    )


def all_cases() -> list[ControlCase]:
    return [
        case_cash(),
        case_single_etf_buy_and_hold(),
        case_fixed_weight_rebalance(),
        case_scored_pool(),
    ]


def vectorbt_parameters(*, asset_class: str = "ETF") -> dict[str, float]:
    """从 FinanceMCP 费用模型取引擎参数，保证对照案例与真实研究用同一套费用。"""
    mapping = map_fees_to_vectorbt(asset_class=asset_class)
    return dict(mapping.parameters)


__all__ = [
    "ControlCase",
    "DATES",
    "INITIAL_CASH",
    "all_cases",
    "case_cash",
    "case_fixed_weight_rebalance",
    "case_scored_pool",
    "case_single_etf_buy_and_hold",
    "vectorbt_parameters",
]
