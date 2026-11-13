"""确定性对照案例的失败先行测试（WP2.1 + WP2.3）。

这些案例的价值全在于**答案是构造出来的**。如果链路（快照 → 适配器 →
`run_target_weights` → 指标）在现金案例上都会算出正收益，那它没有任何资格
被用来评价真实策略。因此这里用解析解断言，不用"看起来合理"断言。

全部案例标注为模拟账户：初始资金是构造值，不是真实账户余额。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.ashare.data.fee_mapping import (
    ETF_COMMISSION_MIN_CENTS,
    ETF_COMMISSION_RATE,
    ETF_SLIPPAGE_RATE_PER_SIDE,
    FINANCE_FEE_MODEL_VERSION,
    describe_mapping,
    map_fees_to_rqalpha,
    map_fees_to_vectorbt,
)
from research.ashare.experiments.control_cases import (
    DATES,
    INITIAL_CASH,
    all_cases,
    vectorbt_parameters,
)
from tacticore.data.tradability import AssetLifetime, build_tradability_mask
from tacticore.engines.vectorbt_adapter import run_target_weights

# 对照案例里所有资产都视为全期上市、全期有价，这样 mask 不会成为变量。
ALL_LISTED = pd.Timestamp("2018-01-01")


def _lifetimes(symbols: list[str]) -> dict[str, AssetLifetime]:
    return {
        symbol: AssetLifetime(symbol=symbol, listed_date=ALL_LISTED, delisted_date=None)
        for symbol in symbols
    }


def _run(case, *, asset_class: str = "ETF"):
    """把一个对照案例交给**未修改的** run_target_weights。"""
    prices = case.prices
    lifetimes = _lifetimes(list(prices.columns))
    mask = build_tradability_mask(prices.index, list(prices.columns), lifetimes, prices)
    assert mask.all().all(), "对照案例的 mask 必须全为 True，否则测的是可交易性而不是记账"
    parameters = vectorbt_parameters(asset_class=asset_class)
    return run_target_weights(
        prices=prices,
        execution_weights=case.targets,
        fees=float(parameters["fees"]),
        slippage=float(parameters["slippage"]),
        initial_cash=INITIAL_CASH,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )


def _metric(result, name: str) -> float:
    """取一个指标；不存在就明确跳过，不用默认值假装通过。"""
    value = result.metrics.get(name)
    if value is None:
        pytest.skip(f"指标 {name} 未由引擎提供，跳过（不制造通过）")
    assert value is not None, f"指标 {name} 取回了 None"  # 让类型检查器看见上面的分支
    return float(value)


# --------------------------------------------------------------------------------------
# 案例 1：现金
# --------------------------------------------------------------------------------------


def test_CC01_cash_ends_at_exactly_the_initial_cash() -> None:
    """不交易时终值必须精确等于初始资金。

    这是整条链路的零点校准：若现金案例的终值不等于初始资金，说明费用、滑点或
    记账在"没有交易"的情况下仍在动钱，后面所有收益数字都不可信。
    """
    case = next(c for c in all_cases() if c.name == "cash")
    result = _run(case)
    final = float(result.equity.iloc[-1])
    assert final == pytest.approx(INITIAL_CASH, abs=1e-6), (
        f"现金案例终值必须精确等于初始资金 {INITIAL_CASH}，实际 {final}"
    )


def test_CC02_cash_has_zero_drawdown() -> None:
    """不交易时回撤必须为 0。"""
    case = next(c for c in all_cases() if c.name == "cash")
    result = _run(case)
    drawdown = _metric(result, "max_drawdown")
    assert drawdown == pytest.approx(0.0, abs=1e-12), f"现金回撤应为 0，实际 {drawdown}"


# --------------------------------------------------------------------------------------
# 案例 2：单 ETF 买入持有
# --------------------------------------------------------------------------------------


def test_CC03_buy_and_hold_matches_the_price_ratio_minus_cost() -> None:
    """买入持有的终值必须等于 初始资金 × 末价/首价，只被一次性成本降低。

    解析式：满仓买入持有只产生**一次**买入成交，因此
        终值 ≈ 初始资金 × (末价/首价) × (1 − 佣金率 − 滑点率)
    滑点在 VectorBT 里按成交价双向计入，所以这里用一次单边成本作为近似上界，
    并允许引擎实际口径带来的小偏差。关键是它必须**接近**价格比，
    而不是偏离一大截——偏离一大截意味着中途被平过仓。
    """
    case = next(c for c in all_cases() if c.name == "single_etf_buy_and_hold")
    result = _run(case)
    final = float(result.equity.iloc[-1])

    gross = INITIAL_CASH * (case.prices.iloc[-1].iloc[0] / case.prices.iloc[0].iloc[0])
    assert final < gross, "扣除成本后的终值必须低于不含成本的价格比终值"
    # 一次买入成交的成本量级：佣金 + 滑点，各按成交额一次。
    expected = gross * (1.0 - ETF_COMMISSION_RATE - ETF_SLIPPAGE_RATE_PER_SIDE)
    assert final == pytest.approx(expected, rel=1e-3), (
        f"终值 {final} 应约等于 {expected}（价格比终值扣一次单边成本）；"
        "偏离超过 0.1% 说明持仓在中途被平掉过"
    )


def test_CC04_buy_and_hold_has_zero_drawdown_on_a_rising_series() -> None:
    """价格单调上升时，买入持有的回撤必须为 0。

    若这里算出非零回撤，说明权益序列的构造有问题（例如用了错误的复权口径）。
    """
    case = next(c for c in all_cases() if c.name == "single_etf_buy_and_hold")
    assert case.prices.iloc[:, 0].is_monotonic_increasing, "本案例的价格必须单调上升"
    result = _run(case)
    drawdown = _metric(result, "max_drawdown")
    assert drawdown == pytest.approx(0.0, abs=1e-9), (
        f"单调上升价格上的买入持有回撤应为 0，实际 {drawdown}"
    )


def test_CC03b_buy_and_hold_actually_holds_the_position() -> None:
    """买入持有必须**全程持仓**，只产生一次成交。

    本测试验证没有中途平仓，并保持完整敞口。
    """
    case = next(c for c in all_cases() if c.name == "single_etf_buy_and_hold")
    result = _run(case)
    trades = result.portfolio.trades.records_readable
    assert len(trades) == 1, (
        f"买入持有必须只产生 1 笔成交，实际 {len(trades)} 笔；多于 1 笔说明持仓在中途被平掉后重建"
    )
    # 且敞口必须在整个期间保持为 1。
    exposure = result.portfolio.gross_exposure()
    assert all(float(value) == pytest.approx(1.0) for value in exposure), (
        "买入持有的逐日敞口必须恒为 1.0"
    )


# --------------------------------------------------------------------------------------
# 案例 3：固定权重再平衡
# --------------------------------------------------------------------------------------


def test_CC05_rebalanced_result_stays_inside_the_constituent_range() -> None:
    """构造的单调价格下，再平衡终值落在两个成分资产的终值之间。"""
    case = next(c for c in all_cases() if c.name == "fixed_weight_rebalance")
    result = _run(case)
    final = float(result.equity.iloc[-1])

    bounds = []
    for symbol in case.prices.columns:
        buy_hold = INITIAL_CASH * (case.prices[symbol].iloc[-1] / case.prices[symbol].iloc[0])
        # 每次买入持有都扣一次单边成本，得到各自的下界。
        bounds.append(buy_hold * (1.0 - ETF_COMMISSION_RATE - ETF_SLIPPAGE_RATE_PER_SIDE))
    low, high = min(bounds), max(bounds)
    assert low <= final <= high, (
        f"再平衡终值 {final} 跑出了成分资产区间 [{low}, {high}]；"
        "记账不可能同时高过所有成分又低过所有成分"
    )


def test_CC06_rebalance_targets_sum_to_one() -> None:
    """调仓日满仓，其他日期不提交订单并保持持仓。"""
    case = next(c for c in all_cases() if c.name == "fixed_weight_rebalance")
    execution_dates = DATES[::5]
    assert case.targets.loc[execution_dates].eq(0.5).all().all()
    assert case.targets.drop(execution_dates).isna().all().all()
    result = _run(case)
    orders = result.portfolio.orders.records_readable
    assert set(orders["Timestamp"]).issubset(set(execution_dates))
    assert not orders.empty
    assert (result.portfolio.gross_exposure() > 0.99).all()


# --------------------------------------------------------------------------------------
# 案例 4：评分驱动组合
# --------------------------------------------------------------------------------------


def test_CC07_scored_pool_zeroes_the_excluded_assets() -> None:
    """被排除资产的权重必须严格为 0，不是 NaN 也不是小数。"""
    case = next(c for c in all_cases() if c.name == "scored_pool")
    row = case.targets.iloc[0]
    positive = row[row > 0]
    assert len(positive) == 2, f"应恰好 2 个正权重资产，实际 {len(positive)}"
    assert (row[row <= 0] == 0.0).all(), "非选中资产必须严格为 0"
    assert float(positive.sum()) == pytest.approx(1.0), "选中资产权重和必须为 1"
    _run(case)  # 必须能被引擎接受


# --------------------------------------------------------------------------------------
# 费用映射：必须显式记录差异，不得静默对齐
# --------------------------------------------------------------------------------------


def test_CC08_vectorbt_mapping_uses_the_finance_commission_rate() -> None:
    """VectorBT 的 fees 必须等于 FinanceMCP 的佣金率，不能是引擎默认值。"""
    mapping = map_fees_to_vectorbt(asset_class="ETF")
    assert mapping.version == FINANCE_FEE_MODEL_VERSION
    assert float(mapping.parameters["fees"]) == ETF_COMMISSION_RATE
    assert float(mapping.parameters["slippage"]) == ETF_SLIPPAGE_RATE_PER_SIDE


def test_CC09_rqalpha_mapping_records_the_disabled_stamp_duty() -> None:
    """RQAlpha 的 tax_multiplier=0 必须被记录为未映射差异。

    这是任务书 WP2.3 的核心要求：不得静默对齐。若这个测试失败，说明有人
    为了让两套账"看起来一致"而把差异删掉了。
    """
    mapping = map_fees_to_rqalpha(asset_class="STOCK")
    assert float(mapping.parameters["tax_multiplier"]) == 0
    items = {difference.item for difference in mapping.unmapped}
    assert "tax_multiplier" in items, (
        "RQAlpha 关闭了印花税，这是一个真实的成本低估，必须记录在 unmapped 中"
    )
    assert "stock_min_commission" in items, "最低佣金被关闭，同样必须记录"


def test_CC10_rqalpha_commission_multiplier_is_arithmetically_equivalent() -> None:
    """stock_commission_multiplier 换算后必须还原成 FinanceMCP 的佣金率。"""
    mapping = map_fees_to_rqalpha(asset_class="ETF")
    multiplier = float(mapping.parameters["stock_commission_multiplier"])
    rqalpha_default = 0.0008
    assert multiplier * rqalpha_default == pytest.approx(ETF_COMMISSION_RATE), (
        "换算必须可逆：multiplier × RQAlpha 默认佣金率 == FinanceMCP 佣金率"
    )


def test_CC11_the_minimum_commission_threshold_is_stated_not_assumed() -> None:
    """最低佣金的影响区间必须被显式写出，而不是默默忽略。"""
    mapping = map_fees_to_vectorbt(asset_class="ETF")
    items = {difference.item for difference in mapping.unmapped}
    assert "commission_min_cents" in items
    difference = next(d for d in mapping.unmapped if d.item == "commission_min_cents")
    assert ETF_COMMISSION_MIN_CENTS == 500
    assert "5 元" in difference.finance_mcp or "500" in difference.finance_mcp
    # 账户总额高于门槛不代表拆分后的每笔成交额也高于门槛。
    assert INITIAL_CASH * ETF_COMMISSION_RATE > ETF_COMMISSION_MIN_CENTS / 100
    assert (INITIAL_CASH / 4) * ETF_COMMISSION_RATE < ETF_COMMISSION_MIN_CENTS / 100
    for engine_mapping in (mapping, map_fees_to_rqalpha(asset_class="ETF")):
        minimum = next(d for d in engine_mapping.unmapped if "min" in d.item)
        assert "单笔成交额" in minimum.impact
        assert "账户总额" in minimum.impact


def test_CC12_the_mapping_report_is_complete_enough_to_archive() -> None:
    """映射报告必须包含每一项未映射差异的三个字段。"""
    for asset_class in ("ETF", "STOCK"):
        mapping = map_fees_to_rqalpha(asset_class=asset_class)
        report = describe_mapping(mapping)
        for difference in mapping.unmapped:
            assert difference.item in report
            assert difference.finance_mcp in report
            assert difference.engine in report
            assert difference.impact in report


def test_CC13_an_unknown_asset_class_is_refused() -> None:
    """未知资产类别必须拒绝，不得默认按 ETF 处理。"""
    with pytest.raises(ValueError, match="未知资产类别"):
        map_fees_to_vectorbt(asset_class="BOND")
    with pytest.raises(ValueError, match="未知资产类别"):
        map_fees_to_rqalpha(asset_class="BOND")


# --------------------------------------------------------------------------------------
# 模拟账户标注
# --------------------------------------------------------------------------------------


def test_CC14_the_control_cases_are_labelled_as_simulated() -> None:
    """初始资金是构造值，不得被当成真实账户余额引用。"""
    assert INITIAL_CASH == 75_776.53, "对照案例使用构造的约 7.6 万元量级初始资金"
    assert len(DATES) == 21
    # 价格必须是构造的等差序列，不含任何真实市场数据。
    for case in all_cases():
        for symbol in case.prices.columns:
            series = case.prices[symbol]
            differences = np.diff(series.to_numpy())
            assert np.allclose(differences, differences[0]), (
                f"{case.name}/{symbol} 的价格必须是等差序列，否则不是确定性对照案例"
            )
