"""双引擎差异审计的失败先行测试（WP2.2 + WP2.4）。

这些测试要钉住的是**归因**，不是"两个引擎数字相等"：

- `NaN` 与 `0.0` 的目标语义必须被证明不同，否则买入持有会被静默变成买入即卖出；
- 停牌日不得产生正持仓，且必须由**停牌表**而不是价格可得性决定；
- 换手率必须能用公开公式从真实成交还原，否则"差异已解释"是一句空话；
- 一次"什么都没拒"的运行与一次"拒了单"的运行都必须给出可读的计数。

bundle 相关的测试在**没有本地 bundle 时跳过**，不用假数据冒充跑过。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.ashare.data.fee_mapping import (
    ETF_COMMISSION_MIN_CENTS,
    ETF_COMMISSION_RATE,
    map_fees_to_vectorbt,
)
from research.ashare.engines.bundle_source import (
    RQALPHA_NOT_DELISTED,
    open_bundle_source,
    read_bundle_prices,
)
from research.ashare.engines.execution_audit import (
    MATERIAL_RETURN_DIFFERENCE,
    MATERIAL_WEIGHT_DEVIATION,
    _attribute,
    build_lifetimes,
    build_mask,
    material_differences,
)
from research.ashare.engines.rqalpha_replay import build_frozen_config
from tacticore.data.tradability import AssetLifetime, validate_execution_targets

DEFAULT_BUNDLE = Path.home() / ".rqalpha/bundle"

#: 一个确定性的短窗口，bundle 有真实数据（已在开发机上实测）。
WINDOW_START = pd.Timestamp("2026-01-05")
WINDOW_END = pd.Timestamp("2026-01-09")
WINDOW_SYMBOLS = ("510300.XSHG", "510500.XSHG")


def _has_bundle() -> bool:
    return DEFAULT_BUNDLE.is_dir() and (DEFAULT_BUNDLE / "instruments.pk").is_file()


def _bundle_or_skip():
    if not _has_bundle():
        pytest.skip(f"本地 RQAlpha bundle 不存在: {DEFAULT_BUNDLE}（不用假数据冒充跑过）")
    return DEFAULT_BUNDLE


@pytest.fixture(scope="module")
def bundle_window():
    """从**真实 bundle**读一个确定性窗口。整个模块只读一次。"""
    _bundle_or_skip()
    from research.ashare.engines.bundle_source import bundle_calendar

    source = open_bundle_source(DEFAULT_BUNDLE)
    calendar = bundle_calendar(source, WINDOW_START, WINDOW_END)
    series = read_bundle_prices(
        source, list(WINDOW_SYMBOLS), start=WINDOW_START, end=WINDOW_END, calendar=calendar
    )
    return series, calendar


# --------------------------------------------------------------------------------------
# 语义：NaN 与 0.0 不是一回事（本次实测发现，必须钉住）
# --------------------------------------------------------------------------------------


def test_EA01_nan_and_zero_have_different_meanings() -> None:
    """NaN = 不下单保持持仓；0.0 = 清仓。二者混用会让买入持有变成买入即卖出。

    这条测试不跑引擎，只断言**语义约定本身**：schedule 里出现 NaN 的行
    不是执行日，出现 0.0 的行是执行日且目标为空仓。
    """
    dates = pd.date_range("2026-01-05", periods=4, freq="B")
    schedule = pd.DataFrame(float("nan"), index=dates, columns=["A", "B"])
    schedule.loc[dates[0]] = 0.5

    execution_days = [date for date in schedule.index if schedule.loc[date].notna().any()]
    assert execution_days == [dates[0]], "只有第一行有目标，其余 NaN 行不是执行日"

    # 写成 0.0 之后，同样的 schedule 变成"每天都执行"。
    zeroed = schedule.fillna(0.0)
    zero_execution_days = [date for date in zeroed.index if zeroed.loc[date].notna().any()]
    assert zero_execution_days == list(dates), (
        "填 0 之后每天都是执行日——这正是把买入持有静默变成每天清仓的原因"
    )


def test_EA02_a_nan_target_is_never_treated_as_zero_in_the_attribution() -> None:
    """归因逻辑不得把 NaN 目标当成 0 目标，否则非执行日也会被报成偏差。"""
    dates = pd.date_range("2026-01-05", periods=3, freq="B")
    schedule = pd.DataFrame(float("nan"), index=dates, columns=["A"])
    schedule.loc[dates[0]] = 1.0
    actual = pd.DataFrame({"A": [1.0, 0.98, 0.97]}, index=dates)

    differences = material_differences(schedule, pd.DataFrame(), actual)
    assert differences.empty, (
        "非执行日（NaN 目标）不得被报成偏差；出现就说明 NaN 被当成了 0。"
        f"实际: {differences.to_dict('records')}"
    )


def test_EA03_a_positive_target_with_no_actual_position_is_attributed() -> None:
    """目标为正、实际未持仓，必须给出可读归因，不能只报一个数字。"""
    dates = pd.date_range("2026-01-05", periods=2, freq="B")
    schedule = pd.DataFrame(float("nan"), index=dates, columns=["A"])
    schedule.loc[dates[0]] = 0.6
    actual = pd.DataFrame({"A": [0.0, 0.0]}, index=dates)

    differences = material_differences(schedule, pd.DataFrame(), actual)
    assert len(differences) == 1
    row = differences.iloc[0]
    assert row["deviation"] == pytest.approx(0.6)
    assert "round_lot" in row["attribution"] or "拒单" in row["attribution"]


def test_EA03b_both_engines_are_compared_against_the_target() -> None:
    """两个引擎必须**分别**与冻结目标比，不能只比其中一个。

    这条测试是为一个真实发生过的缺陷写的：`material_differences` 收了
    `vectorbt_weights` 参数却从不用它，只拿 RQAlpha 比目标。那样
    VectorBT 自己偏离目标时，差异表是空的——"两引擎一致"的结论
    来自一次漏检，而不是来自一次核对。
    """
    dates = pd.date_range("2026-01-05", periods=1, freq="B")
    schedule = pd.DataFrame(float("nan"), index=dates, columns=["A"])
    schedule.loc[dates[0]] = 0.6
    # 只有 VectorBT 偏离目标，RQAlpha 完全命中。
    vectorbt = pd.DataFrame({"A": [0.0]}, index=dates)
    rqalpha = pd.DataFrame({"A": [0.6]}, index=dates)

    differences = material_differences(schedule, vectorbt, rqalpha)
    assert len(differences) == 1, (
        "VectorBT 偏离了目标就必须出一行；只报 RQAlpha 会让这次偏离被静默漏掉。"
        f"实际: {differences.to_dict('records')}"
    )
    row = differences.iloc[0]
    assert row["engine"] == "vectorbt", f"这一行必须标明是哪个引擎，实际 {row['engine']}"
    assert row["symbol"] == "A"


def test_EA03c_a_clean_engine_side_produces_no_rows() -> None:
    """完全命中目标的一侧不得产生差异行。"""
    dates = pd.date_range("2026-01-05", periods=1, freq="B")
    schedule = pd.DataFrame(float("nan"), index=dates, columns=["A"])
    schedule.loc[dates[0]] = 0.6
    both = pd.DataFrame({"A": [0.6]}, index=dates)

    differences = material_differences(schedule, both, both)
    assert differences.empty, f"命中目标时不得有差异行，实际: {differences.to_dict('records')}"


# --------------------------------------------------------------------------------------
# 可交易性：停牌必须由停牌表决定，不是由价格可得性决定
# --------------------------------------------------------------------------------------


def test_EA04_a_suspended_day_is_not_tradable_even_with_a_price() -> None:
    """停牌日即便有价格也不可交易。

    这条测试是 Phase 1 已修缺陷的回归防线：上游会在停牌日给前收价（非 NaN），
    只看价格可得性会把停牌日判成可交易日。
    """
    dates = pd.date_range("2026-01-05", periods=3, freq="B")
    prices = pd.DataFrame({"A": [10.0, 10.0, 10.0]}, index=dates)
    suspended = pd.DataFrame({"A": [False, True, False]}, index=dates)
    lifetimes = {"A": AssetLifetime(symbol="A", listed_date=dates[0], delisted_date=None)}

    mask = build_mask(prices, suspended, lifetimes)
    assert bool(mask.at[dates[1], "A"]) is False, "停牌日必须不可交易"
    assert bool(mask.at[dates[0], "A"]) is True, "非停牌日必须可交易"
    # 且引擎必须拒绝在这一天放正目标。
    schedule = pd.DataFrame(float("nan"), index=dates, columns=["A"])
    schedule.loc[dates[1]] = 0.5
    with pytest.raises(Exception, match="不可交易正目标"):
        validate_execution_targets(schedule, prices, mask, lifetimes)


def test_EA05_the_unlisted_security_gets_no_positive_target() -> None:
    """未上市证券不得拿到正目标；上市日当天可以。"""
    dates = pd.date_range("2026-01-05", periods=4, freq="B")
    prices = pd.DataFrame({"A": [10.0, 10.0, 10.0, 10.0]}, index=dates)
    suspended = pd.DataFrame(False, index=dates, columns=["A"])
    listed = pd.Timestamp("2026-01-07")
    lifetimes = {"A": AssetLifetime(symbol="A", listed_date=listed, delisted_date=None)}

    mask = build_mask(prices, suspended, lifetimes)
    assert not mask.loc[dates[:2], "A"].any(), "上市日之前必须全部不可交易"
    assert bool(mask.at[listed, "A"]) is True, "上市日当天可交易"


# --------------------------------------------------------------------------------------
# bundle 读取（真实 bundle）
# --------------------------------------------------------------------------------------


def test_EA06_the_real_bundle_is_readable(bundle_window) -> None:
    """真实 bundle 必须能读出非空价格矩阵，且索引是传入的交易日历。"""
    series, calendar = bundle_window
    assert not series.prices.empty
    assert list(series.prices.columns) == list(WINDOW_SYMBOLS)
    assert series.prices.index.equals(calendar)
    assert not series.prices.isna().all().all(), "至少要有一些真实价格"


def test_EA07_bundle_lifetimes_never_use_the_not_delisted_sentinel(bundle_window) -> None:
    """2999-12-31 是 RQAlpha 的哨兵值，不得被当成真实退市日。

    若把它当退市日，`active_at` 会在 2999 年后判 False——现在看不出问题，
    但这是一个把"未退市"错译成"退市"的静默错误。
    """
    series, _ = bundle_window
    assert RQALPHA_NOT_DELISTED == pd.Timestamp("2999-12-31")
    for symbol in series.symbols:
        assert symbol.delisted_date is None or symbol.delisted_date < RQALPHA_NOT_DELISTED


def test_EA08_a_delisted_security_is_refused_at_a_later_as_of() -> None:
    """退市证券在后来的 as-of 必须被拒绝，而不是返回一段空数据。"""
    _bundle_or_skip()
    from research.ashare.engines.bundle_source import bundle_calendar

    source = open_bundle_source(DEFAULT_BUNDLE)
    calendar = bundle_calendar(source, WINDOW_START, WINDOW_END)
    with pytest.raises(KeyError, match="没有有效版本"):
        # 600001.XSHG 于 2009 年退市（已实测确认）。
        read_bundle_prices(
            source, ["600001.XSHG"], start=WINDOW_START, end=WINDOW_END, calendar=calendar
        )


def test_EA09_a_missing_calendar_is_refused_not_guessed() -> None:
    """不提供交易日历必须直接拒绝。日历是 PIT 契约，不能由本模块隐式决定。"""
    _bundle_or_skip()
    source = open_bundle_source(DEFAULT_BUNDLE)
    with pytest.raises(ValueError, match="必须显式提供 calendar"):
        read_bundle_prices(
            source, list(WINDOW_SYMBOLS), start=WINDOW_START, end=WINDOW_END, calendar=None
        )


# --------------------------------------------------------------------------------------
# 双引擎对照（真实 bundle）
# --------------------------------------------------------------------------------------


def test_EA10_both_engines_agree_on_trade_count_for_a_frozen_schedule(bundle_window) -> None:
    """同一份冻结日程，两个引擎的**成交笔数**必须一致。

    成交笔数一致而收益率接近，才说明差异来自费用与撮合口径，而不是来自
    "一边多做了几次交易"。这条是双引擎对照的最低门槛。
    """
    series, calendar = bundle_window
    from research.ashare.engines.execution_audit import audit

    dates = series.prices.index
    schedule = pd.DataFrame(float("nan"), index=dates, columns=series.prices.columns)
    schedule.loc[dates[0]] = 0.5

    result = audit(
        schedule,
        series.prices,
        series.suspended,
        start=WINDOW_START,
        end=WINDOW_END,
        initial_cash=75_776.53,
        bundle_path=DEFAULT_BUNDLE,
        asset_class="ETF",
    )
    comparison = result["comparison"].set_index("item")
    assert float(comparison.at["trade_count", "vectorbt"]) == float(
        comparison.at["trade_count", "rqalpha"]
    ), f"成交笔数不一致: {comparison.to_dict()}"
    assert result["unexplained"] is None, result["unexplained"]
    assert result["insufficient"] is None, result["insufficient"]


def test_EA11_turnover_is_reconstructed_from_real_fills_not_asserted(bundle_window) -> None:
    """换手率必须能用公开公式从真实成交**还原**出来。

    只断言"两个引擎换手率接近"是没有意义的：它们的分母与 /2 都不同。
    这里断言的是 `turnover_attribution` 的重算值等于引擎自报值——
    不一致就抛 AssertionError，因为那说明对口径的理解是错的。
    """
    series, calendar = bundle_window
    from research.ashare.engines.execution_audit import audit

    dates = series.prices.index
    schedule = pd.DataFrame(float("nan"), index=dates, columns=series.prices.columns)
    schedule.loc[dates[0]] = 0.5
    result = audit(
        schedule,
        series.prices,
        series.suspended,
        start=WINDOW_START,
        end=WINDOW_END,
        initial_cash=75_776.53,
        bundle_path=DEFAULT_BUNDLE,
        asset_class="ETF",
    )
    table = result["turnover_attribution"].set_index("item")
    assert float(table.at["rebuilt_turnover", "value"]) == pytest.approx(
        float(table.at["reported_turnover", "value"]), abs=1e-12
    )
    assert float(table.at["trade_notional_sum", "value"]) > 0


def test_EA12_the_rqalpha_config_reuses_the_unmodified_adapter() -> None:
    """RQAlpha 配置必须由**未修改的** `build_rqalpha_config` 生成。

    直接断言换算公式还在：`stock_commission_multiplier == fees / 0.0008`。
    若有人为了让两套账一致而改了适配器，这条会失败。
    """
    _bundle_or_skip()
    config, report = build_frozen_config(
        start=WINDOW_START,
        end=WINDOW_END,
        initial_cash=75_776.53,
        asset_class="ETF",
        bundle_path=DEFAULT_BUNDLE,
    )
    transaction_cost = config["mod"]["sys_transaction_cost"]
    assert transaction_cost["tax_multiplier"] == 0
    assert transaction_cost["stock_min_commission"] == 0
    multiplier = float(transaction_cost["stock_commission_multiplier"])
    assert multiplier == pytest.approx(ETF_COMMISSION_RATE / 0.0008)
    assert multiplier * 0.0008 == pytest.approx(ETF_COMMISSION_RATE)
    # 差异报告必须被带回来，且至少包含印花税这一项。
    assert "tax_multiplier" in report


# --------------------------------------------------------------------------------------
# 归因文本与阈值
# --------------------------------------------------------------------------------------


def test_EA13_every_attribution_names_a_concrete_engine_difference() -> None:
    """每一条归因都必须指向一个具体的引擎差异，不能是"需进一步分析"。"""
    assert "A" in _attribute(0.6, 0.0, "A")
    assert "round_lot" in _attribute(0.6, 0.0, "A")
    assert "拒单" in _attribute(0.6, 0.0, "A") or "volume" in _attribute(0.6, 0.0, "A")
    assert "分母" in _attribute(0.5, 0.6, "A")
    assert "取整" in _attribute(0.5, 0.4, "A")


def test_EA14_the_material_thresholds_are_tight_enough_to_matter() -> None:
    """阈值必须小到能发现问题，又大到不把取整噪声当差异。"""
    assert 0 < MATERIAL_WEIGHT_DEVIATION < 0.05
    assert 0 < MATERIAL_RETURN_DIFFERENCE < 0.05


def test_EA15_the_minimum_commission_does_not_bind_at_this_capital() -> None:
    """该资金量下单笔佣金必须高于最低佣金，否则映射在该区间失效。"""
    single_trade = 75_776.53 * ETF_COMMISSION_RATE
    assert single_trade > ETF_COMMISSION_MIN_CENTS / 100.0, (
        f"单笔佣金 {single_trade:.2f} 元应高于最低佣金 {ETF_COMMISSION_MIN_CENTS / 100.0:.2f} 元"
    )
    mapping = map_fees_to_vectorbt(asset_class="ETF")
    assert "commission_min_cents" in {item.item for item in mapping.unmapped}


def test_EA16_lifetimes_are_shared_between_both_engines(bundle_window) -> None:
    """两个引擎必须用同一套生命周期，否则"一边认为已上市"无法归因。"""
    series, _ = bundle_window
    from research.ashare.engines.execution_audit import _symbols_from_prices

    lifetimes = build_lifetimes(_symbols_from_prices(series.prices))
    assert set(lifetimes) == set(series.prices.columns)
    for symbol, lifetime in lifetimes.items():
        assert lifetime.symbol == symbol


def test_EA17_the_replay_rejects_a_schedule_outside_the_window(bundle_window) -> None:
    """日程超出执行窗口必须被拒绝，不得在无数据窗口里"成功"跑完。"""
    series, _ = bundle_window
    from research.ashare.engines.rqalpha_replay import replay_frozen_schedule

    dates = series.prices.index
    schedule = pd.DataFrame(float("nan"), index=[dates[0]], columns=series.prices.columns)
    schedule.iloc[0] = 0.5
    with pytest.raises(ValueError, match="超出执行窗口"):
        replay_frozen_schedule(
            schedule,
            {symbol: symbol for symbol in schedule.columns},
            start=dates[1],
            end=dates[-1],
            initial_cash=75_776.53,
            bundle_path=DEFAULT_BUNDLE,
            asset_class="ETF",
        )
