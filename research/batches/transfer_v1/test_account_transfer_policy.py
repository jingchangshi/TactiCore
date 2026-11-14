"""离线合成数据测试：不联网、不读真实结果、不运行 RQAlpha bundle。

覆盖任务要求：趋势状态、连续两月确认、15% 上限、10pp 月度上限、
现金约束、偏离带边界、日程 NaN/非交易日、一手与 5,000 元过滤、
指标与裁决。所有价格和持仓均为手工构造，不能作为历史证据。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import account_transfer_policy as policy
import pandas as pd
import pytest
import run_account_transfer as runner

from research.ashare.engines.rqalpha_replay import (
    RQAlphaRunResult,
    apply_min_commission,
    build_frozen_config,
    replay_frozen_schedule,
)
from tacticore.data.tradability import UntradableTargetError

_MAIN_END = pd.Timestamp("2026-08-31")
_LISTED_DATE = pd.Timestamp("2010-01-01")


def _config(
    weights: dict[str, float],
    *,
    main_end: pd.Timestamp = _MAIN_END,
    listed_date: pd.Timestamp = _LISTED_DATE,
    bands: dict[str, float] | None = None,
) -> policy.TransferConfig:
    assets = tuple(
        policy.AssetRule(
            symbol=symbol,
            sleeve="gold" if symbol == "C" else "core",
            base_weight=weight,
            rqalpha_symbol=f"{symbol}.XSHG",
            listed_date=listed_date,
            band=(bands or {}).get(symbol, 0.05),
        )
        for symbol, weight in weights.items()
    )
    return policy.TransferConfig(assets=assets, main_end=main_end)


def _prices(dates: pd.DatetimeIndex, values: dict[str, float | pd.Series]) -> pd.DataFrame:
    columns = {}
    for symbol, value in values.items():
        if isinstance(value, pd.Series):
            series = value.copy()
            series.index = pd.DatetimeIndex(series.index)
            # 去掉重复标签后再对齐；重复索引会让 reindex 直接报错。
            series = series.loc[~series.index.duplicated(keep="last")]
            columns[symbol] = series.reindex(dates).astype(float)
        else:
            columns[symbol] = [float(value)] * len(dates)
    return pd.DataFrame(columns, index=dates)


def _frozen_prices(dates: pd.DatetimeIndex, prices: dict[str, float]) -> pd.DataFrame:
    return _prices(dates, {symbol: prices[symbol] for symbol in policy.FROZEN_CONFIG.symbols})


def _fake_result(
    dates: pd.DatetimeIndex,
    total_value: list[float],
    *,
    positions: pd.DataFrame | None = None,
    trades: pd.DataFrame | None = None,
    events: pd.DataFrame | None = None,
) -> RQAlphaRunResult:
    portfolio = pd.DataFrame({"total_value": total_value, "cash": [0.0] * len(dates)}, index=dates)
    empty_positions = pd.DataFrame(
        columns=["order_book_id", "quantity", "market_value"], index=pd.DatetimeIndex([])
    )
    analyser = {
        "portfolio": portfolio,
        "stock_positions": empty_positions if positions is None else positions,
        "trades": pd.DataFrame() if trades is None else trades,
        "summary": {},
    }
    return RQAlphaRunResult(
        analyser=analyser,
        order_events=pd.DataFrame() if events is None else events,
        replayed_dates=[],
        rqalpha_version="6.3.0",
        fee_mapping_report="stock_min_commission: disabled",
    )


# --------------------------------------------------------------------------------------
# 冻结映射与趋势状态
# --------------------------------------------------------------------------------------


def test_frozen_mapping_matches_owner_decision() -> None:
    base = policy.FROZEN_CONFIG.base_weights
    assert base == pytest.approx(
        {
            "512890.SS": 0.125,
            "515450.SS": 0.125,
            "511360.SS": 0.15,
            "518880.SS": 0.10,
        }
    )
    assert policy.FROZEN_CONFIG.cash_weight == pytest.approx(0.50)
    bands = {asset.symbol: asset.band for asset in policy.FROZEN_CONFIG.assets}
    assert bands["512890.SS"] == bands["515450.SS"] == 0.05
    assert bands["511360.SS"] == 0.05
    assert bands["518880.SS"] == 0.03


def test_trend_classification_is_strict_at_two_percent() -> None:
    assert policy.classify_trend(1.02, 1.0, 0.02) == policy.SIDE_NEUTRAL
    assert policy.classify_trend(1.0200001, 1.0, 0.02) == policy.SIDE_UPPER
    assert policy.classify_trend(0.98, 1.0, 0.02) == policy.SIDE_NEUTRAL
    assert policy.classify_trend(0.9799999, 1.0, 0.02) == policy.SIDE_LOWER


def test_trend_observation_needs_200_valid_consecutive_prices() -> None:
    dates = pd.bdate_range("2020-01-01", periods=200)
    rising = pd.Series([1.0 + i / 199.0 for i in range(200)], index=dates)
    prices = _prices(dates, {"A": rising})
    assert policy.trend_observation(prices, "A", dates[-1]) == policy.SIDE_UPPER
    short = _prices(dates[:199], {"A": rising.iloc[:199]})
    assert policy.trend_observation(short, "A", dates[198]) is None

    missing = rising.copy()
    missing.iloc[100] = float("nan")
    assert policy.trend_observation(_prices(dates, {"A": missing}), "A", dates[-1]) is None

    missing_end = rising.copy()
    missing_end.iloc[-1] = float("nan")
    assert policy.trend_observation(_prices(dates, {"A": missing_end}), "A", dates[-1]) is None
    after = dates[-1] + pd.Timedelta(days=1)
    assert policy.trend_observation(_prices(dates, {"A": rising}), "A", after) is None


def test_two_month_confirmation_and_persistence() -> None:
    tracker = policy.TrendTracker()
    assert tracker.update("A", policy.SIDE_UPPER) is None
    assert tracker.update("A", policy.SIDE_UPPER) == policy.SIDE_UPPER
    assert tracker.update("A", policy.SIDE_NEUTRAL) == policy.SIDE_UPPER
    assert tracker.update("A", policy.SIDE_LOWER) == policy.SIDE_UPPER
    assert tracker.update("A", policy.SIDE_LOWER) == policy.SIDE_LOWER
    assert tracker.update("A", policy.SIDE_UPPER) == policy.SIDE_LOWER
    assert tracker.update("A", policy.SIDE_UPPER) == policy.SIDE_UPPER


def test_missing_data_resets_confirmation_and_is_never_forward_filled() -> None:
    tracker = policy.TrendTracker()
    tracker.update("A", policy.SIDE_UPPER)
    assert tracker.update("A", policy.SIDE_UPPER) == policy.SIDE_UPPER
    assert tracker.update("A", None) is None
    assert tracker.update("A", policy.SIDE_UPPER) is None
    assert tracker.update("A", policy.SIDE_UPPER) == policy.SIDE_UPPER


def test_build_trend_path_marks_missing_month_end_as_no_signal() -> None:
    dates = pd.bdate_range("2020-01-01", periods=260)
    values = pd.Series([1.0 + i / 259.0 for i in range(260)], index=dates)
    decisions = policy.month_end_dates(dates, dates[200], dates[-1])[:3]
    values.loc[decisions[1]] = float("nan")
    signals, confirmed = policy.build_trend_path(
        _prices(dates, {"A": values}), decisions, _config({"A": 0.1})
    )
    assert signals.at[decisions[1], "A"] is None
    assert confirmed.at[decisions[1], "A"] is None


# --------------------------------------------------------------------------------------
# 目标：15% 上限、10pp 月度上限、现金约束
# --------------------------------------------------------------------------------------


def test_upper_target_is_capped_at_fifteen_percent() -> None:
    config = _config({"A": 0.20})
    targets = policy.a2_target_weights(
        {"A": policy.SIDE_UPPER}, {"A": 0.20}, config.base_weights, config
    )
    assert targets["A"] == pytest.approx(0.15)
    lower = policy.a2_target_weights(
        {"A": policy.SIDE_LOWER}, {"A": 0.20}, config.base_weights, config
    )
    assert lower["A"] == pytest.approx(0.15), "15% 上限约束所有新目标"


def test_monthly_change_cap_applies_per_symbol_and_per_sleeve() -> None:
    config = _config({"A": 0.20, "B": 0.20})
    previous = {"A": 0.20, "B": 0.20}
    proposed = {"A": 0.50, "B": 0.40}
    capped = policy.apply_monthly_change_cap(proposed, previous, config)
    assert capped["A"] - previous["A"] == pytest.approx(0.05)
    assert capped["B"] - previous["B"] == pytest.approx(0.05)
    assert sum(capped.values()) - sum(previous.values()) == pytest.approx(0.10)

    config = _config({"A": 0.20})
    capped = policy.apply_monthly_change_cap({"A": 0.50}, {"A": 0.20}, config)
    assert capped["A"] == pytest.approx(0.30)


def test_cash_constraint_scales_upper_increments_proportionally() -> None:
    config = _config({"A": 0.40, "B": 0.40})
    base = {"A": 0.40, "B": 0.40}
    scaled = policy.apply_cash_constraint({"A": 0.60, "B": 0.60}, base, config)
    assert scaled["A"] == pytest.approx(0.50)
    assert scaled["B"] == pytest.approx(0.50)
    assert sum(scaled.values()) == pytest.approx(1.0)

    released = policy.apply_cash_constraint({"A": 0.60, "B": 0.20}, base, config)
    assert released["A"] == pytest.approx(0.60)
    assert released["B"] == pytest.approx(0.20)
    assert sum(released.values()) == pytest.approx(0.80)


def test_a2_target_path_keeps_cash_from_upper_increments() -> None:
    decisions = pd.DatetimeIndex(["2021-01-29", "2021-02-26"])
    confirmed = pd.DataFrame(
        {
            symbol: [None, policy.SIDE_UPPER if symbol == "518880.SS" else None]
            for symbol in policy.FROZEN_CONFIG.symbols
        },
        index=decisions,
    )
    targets = policy.target_path(decisions, policy.FROZEN_CONFIG, confirmed)
    assert targets.loc[decisions[1], "518880.SS"] == pytest.approx(0.11)
    assert targets.loc[decisions[1]].sum() == pytest.approx(0.51)
    cash = policy.FROZEN_CONFIG.cash_weight - 0.01
    assert targets.loc[decisions[1]].sum() + cash == pytest.approx(1.0)


# --------------------------------------------------------------------------------------
# 偏离带、订单过滤与日程
# --------------------------------------------------------------------------------------


def test_deviation_band_boundary_is_strict() -> None:
    assert not policy.band_trigger(0.10, 0.15, 0.05)
    assert policy.band_trigger(0.0999, 0.15, 0.05)
    assert not policy.band_trigger(0.10, 0.13, 0.03)
    assert policy.band_trigger(0.0999, 0.13, 0.03)
    assert not policy.band_trigger(0.125, 0.175, 0.05)


def test_plan_order_one_lot_and_minimum_buy_filters() -> None:
    config = _config({"A": 0.10})
    actual = policy.ActualState(weights={"A": 0.0}, quantities={"A": 0}, equity=100_000.0)
    below_lot = policy.plan_order(
        decision_date=pd.Timestamp("2021-01-29"),
        execution_date=pd.Timestamp("2021-02-01"),
        symbol="A",
        target_weight=0.009,
        actual=actual,
        price=10.0,
        config=config,
        trigger="deviation_band",
        trend_state=None,
    )
    assert not below_lot.submitted
    assert below_lot.reason == "below_one_lot"

    below_min = policy.plan_order(
        decision_date=pd.Timestamp("2021-01-29"),
        execution_date=pd.Timestamp("2021-02-01"),
        symbol="A",
        target_weight=0.049,
        actual=actual,
        price=10.0,
        config=config,
        trigger="deviation_band",
        trend_state=None,
    )
    assert not below_min.submitted
    assert below_min.reason == "below_min_buy"

    exactly_min = policy.plan_order(
        decision_date=pd.Timestamp("2021-01-29"),
        execution_date=pd.Timestamp("2021-02-01"),
        symbol="A",
        target_weight=0.05,
        actual=actual,
        price=10.0,
        config=config,
        trigger="deviation_band",
        trend_state=None,
    )
    assert exactly_min.submitted
    assert exactly_min.side == policy.ORDER_BUY
    assert exactly_min.order_notional == pytest.approx(5_000.0)


def test_sells_are_not_subject_to_minimum_buy_and_can_close() -> None:
    config = _config({"A": 0.10})
    actual = policy.ActualState(weights={"A": 0.05}, quantities={"A": 500}, equity=100_000.0)
    intent = policy.plan_order(
        decision_date=pd.Timestamp("2021-01-29"),
        execution_date=pd.Timestamp("2021-02-01"),
        symbol="A",
        target_weight=0.0,
        actual=actual,
        price=10.0,
        config=config,
        trigger="deviation_band",
        trend_state=None,
    )
    assert intent.submitted
    assert intent.side == policy.ORDER_SELL
    assert intent.order_quantity == 500
    assert intent.reason == "sell_all"


def test_schedule_first_build_filters_bonds_and_keeps_nan_months() -> None:
    dates = pd.bdate_range("2021-01-04", periods=60)
    prices = _frozen_prices(
        dates,
        {
            "512890.SS": 1.0,
            "515450.SS": 2.0,
            # 一手 2 万元高于 15% 目标，用于验证整手过滤。
            "511360.SS": 200.0,
            "518880.SS": 5.0,
        },
    )
    decisions = policy.month_end_dates(dates, dates[0], dates[-1])[:2]
    targets = policy.target_path(decisions, policy.FROZEN_CONFIG)
    schedule, records = policy.build_schedule(
        prices=prices,
        calendar=dates,
        decisions=decisions,
        targets=targets,
        config=policy.FROZEN_CONFIG,
        actual_states=None,
    )
    first_execution = policy.next_trading_day(dates, decisions[0])
    assert first_execution is not None
    row = schedule.loc[first_execution]
    assert not pd.isna(row[("BUY", "512890.SS")])
    assert not pd.isna(row[("BUY", "515450.SS")])
    assert not pd.isna(row[("BUY", "518880.SS")])
    assert pd.isna(row[("BUY", "511360.SS")])
    bond_filters = records.loc[records["symbol"].eq("511360.SS")]
    assert set(bond_filters["reason"]) == {"below_one_lot"}
    later = schedule.index[1:]
    if len(later):
        assert schedule.loc[later].isna().all().all(), "目标已达成时后续月份不得强制交易"


def test_schedule_orders_sells_before_buys() -> None:
    dates = pd.bdate_range("2021-01-04", periods=60)
    prices = _prices(dates, {"A": 10.0, "B": 10.0})
    config = _config({"A": 0.30, "B": 0.30})
    decisions = policy.month_end_dates(dates, dates[0], dates[-1])[:2]
    targets = pd.DataFrame({"A": 0.30, "B": 0.30}, index=decisions)
    state = policy.ActualState(
        weights={"A": 0.50, "B": 0.0}, quantities={"A": 5000, "B": 0}, equity=100_000.0
    )
    schedule, records = policy.build_schedule(
        prices=prices,
        calendar=dates,
        decisions=decisions,
        targets=targets,
        config=config,
        actual_states={decisions[0]: state, decisions[1]: state},
    )
    execution = schedule.index[1]
    present = list(schedule.loc[execution].dropna().index)
    assert present == [("SELL", "A"), ("BUY", "B")]
    assert records.loc[records["symbol"].eq("A"), "side"].iloc[-1] == policy.ORDER_SELL
    assert records.loc[records["symbol"].eq("B"), "side"].iloc[-1] == policy.ORDER_BUY


def test_month_end_rolls_back_from_non_trading_day_and_schedule_stays_nan() -> None:
    dates = pd.bdate_range("2021-01-04", periods=40)
    missing = pd.Timestamp("2021-02-26")
    dates = dates[dates != missing]
    decisions = policy.month_end_dates(dates, dates[0], dates[-1])[:2]
    execution = policy.next_trading_day(dates, decisions[0])
    assert execution in dates
    assert execution > decisions[0]
    prices = _frozen_prices(dates, {symbol: 1.0 for symbol in policy.FROZEN_CONFIG.symbols})
    targets = policy.target_path(decisions, policy.FROZEN_CONFIG)
    zero = policy.ActualState(
        {symbol: 0.0 for symbol in policy.FROZEN_CONFIG.symbols}, {}, 68_826.0
    )
    schedule, _ = policy.build_schedule(
        prices=prices,
        calendar=dates,
        decisions=decisions,
        targets=targets,
        config=policy.FROZEN_CONFIG,
        actual_states={decisions[1]: zero},
    )
    assert all(date in dates for date in schedule.index)
    assert missing not in schedule.index


def test_positive_target_before_listing_is_rejected() -> None:
    dates = pd.bdate_range("2021-01-04", periods=40)
    config = _config({"A": 0.10}, listed_date=dates[0] + pd.Timedelta(days=80))
    prices = _prices(dates, {"A": 10.0})
    decisions = policy.month_end_dates(dates, dates[0], dates[-1])[:1]
    targets = pd.DataFrame({"A": 0.10}, index=decisions)
    with pytest.raises((policy.PolicyError, UntradableTargetError)):
        policy.build_schedule(
            prices=prices,
            calendar=dates,
            decisions=decisions,
            targets=targets,
            config=config,
            actual_states=None,
        )


# --------------------------------------------------------------------------------------
# RQAlpha 原生结果读取、指标与裁决（全部使用假结果）
# --------------------------------------------------------------------------------------


def test_metrics_from_fake_rqalpha_result() -> None:
    dates = pd.bdate_range("2021-01-04", periods=5)
    trades = pd.DataFrame(
        {
            "side": ["BUY", "SELL"],
            "last_quantity": [100, 100],
            "last_price": [10.0, 11.0],
            "commission": [0.5, 0.5],
        }
    )
    events = pd.DataFrame(
        [
            {"event": "ORDER_CREATION_PASS", "order_id": 1, "message": ""},
            {"event": "ORDER_CREATION_REJECT", "order_id": 2, "message": "not enough money"},
            {"event": "ORDER_CREATION_REJECT", "order_id": 3, "message": "0 order quantity"},
        ]
    )
    result = _fake_result(
        dates,
        [100_000.0, 101_000.0, 99_000.0, 102_000.0, 103_000.0],
        trades=trades,
        events=events,
    )
    orders = pd.DataFrame(
        [
            {"submitted": False, "reason": "below_one_lot"},
            {"submitted": False, "reason": "below_min_buy"},
            {"submitted": True, "reason": "buy"},
        ]
    )
    metrics = runner.metrics_from_result(result, orders, "A0")
    assert metrics.cagr == pytest.approx((103_000.0 / 100_000.0) ** (365.25 / 4) - 1.0)
    assert metrics.max_drawdown == pytest.approx(1.0 - 99_000.0 / 101_000.0)
    assert metrics.cvar_observations == 4
    assert metrics.cvar_5pct == pytest.approx(1.0 - 99_000.0 / 101_000.0)
    assert metrics.turnover_total == pytest.approx(2_100.0 / 101_000.0)
    assert metrics.cash_rejections == 1
    assert metrics.lot_rejections == 1
    assert metrics.filtered_below_one_lot == 1
    assert metrics.filtered_below_min_buy == 1


def test_actual_states_from_fake_result_reads_weights_and_quantities() -> None:
    dates = pd.bdate_range("2021-01-04", periods=3)
    decision = dates[-1]
    positions = pd.DataFrame(
        {
            "order_book_id": ["512890.XSHG", "518880.XSHG"],
            "quantity": [1000, 200],
            "market_value": [10_000.0, 5_000.0],
        },
        index=pd.DatetimeIndex([decision, decision]),
    )
    result = _fake_result(dates, [100_000.0, 100_000.0, 100_000.0], positions=positions)
    states = runner.actual_states_from_result(
        result, pd.DatetimeIndex([decision]), policy.FROZEN_CONFIG
    )
    state = states[decision]
    assert state.equity == pytest.approx(100_000.0)
    assert state.weights["512890.SS"] == pytest.approx(0.10)
    assert state.weights["518880.SS"] == pytest.approx(0.05)
    assert state.quantities["512890.SS"] == 1000
    assert state.quantities["518880.SS"] == 200


def _metrics(**overrides: float) -> runner.ArmMetrics:
    values = {
        "cagr": 0.05,
        "max_drawdown": 0.20,
        "cvar_5pct": 0.025,
        "turnover_total": 2.0,
        "cash_rejections": 0,
        "lot_rejections": 0,
        "other_rejections": 0,
    }
    values.update(overrides)
    return runner.ArmMetrics(
        arm="A0",
        cagr=values["cagr"],
        max_drawdown=values["max_drawdown"],
        cvar_5pct=values["cvar_5pct"],
        cvar_observations=100,
        turnover_total=values["turnover_total"],
        turnover_annualized=1.0,
        mean_equity=100_000.0,
        initial_equity=100_000.0,
        ending_equity=105_000.0,
        trade_count=10,
        commission=5.0,
        order_passes=10,
        order_rejections=0,
        cash_rejections=int(values["cash_rejections"]),
        lot_rejections=int(values["lot_rejections"]),
        volume_rejections=0,
        other_rejections=int(values["other_rejections"]),
        filtered_below_one_lot=0,
        filtered_below_min_buy=0,
        filtered_other=0,
    )


def test_adjudication_defaults_to_inconclusive() -> None:
    a0 = _metrics()
    a2 = _metrics(cagr=0.048, max_drawdown=0.17, cvar_5pct=0.02, turnover_total=2.2)
    adjudication = runner.adjudicate(
        a0,
        a2,
        protocol_committed=False,
        min_commission_modelled=False,
        data_gate_passed=True,
        fixed_point_converged=True,
        samples_aligned=True,
    )
    assert adjudication.verdict == "INCONCLUSIVE"
    assert "PROTOCOL_NOT_COMMITTED" in adjudication.blockers
    assert "MIN_COMMISSION_NOT_MODELLED" in adjudication.blockers
    assert adjudication.risk_improvement_mdd == pytest.approx(0.03)


def test_adjudication_rejects_when_threshold_fails_and_gates_pass() -> None:
    a0 = _metrics()
    a2 = _metrics(cagr=0.04, max_drawdown=0.195, cvar_5pct=0.024, turnover_total=2.2)
    adjudication = runner.adjudicate(
        a0,
        a2,
        protocol_committed=True,
        min_commission_modelled=True,
        data_gate_passed=True,
        fixed_point_converged=True,
        samples_aligned=True,
    )
    assert adjudication.verdict == "REJECT"


def test_adjudication_blocks_when_a_whole_positive_sleeve_never_trades() -> None:
    a0 = _metrics()
    a2 = _metrics(cagr=0.04, max_drawdown=0.195, cvar_5pct=0.024, turnover_total=2.2)
    adjudication = runner.adjudicate(
        a0,
        a2,
        protocol_committed=True,
        min_commission_modelled=True,
        data_gate_passed=True,
        fixed_point_converged=True,
        samples_aligned=True,
        allocation_executed=False,
    )
    assert adjudication.verdict == "INCONCLUSIVE"
    assert "ALLOCATION_NOT_EXECUTED" in adjudication.blockers


def test_adjudication_adopts_shadow_only_after_all_gates() -> None:
    a0 = _metrics()
    a2 = _metrics(cagr=0.048, max_drawdown=0.17, cvar_5pct=0.02, turnover_total=2.2)
    adjudication = runner.adjudicate(
        a0,
        a2,
        protocol_committed=True,
        min_commission_modelled=True,
        data_gate_passed=True,
        fixed_point_converged=True,
        samples_aligned=True,
    )
    assert adjudication.verdict == "ADOPT_SHADOW"
    assert adjudication.turnover_ratio == pytest.approx(1.1)


def test_cash_rejection_blocks_adoption() -> None:
    a0 = _metrics()
    a2 = _metrics(
        cagr=0.048,
        max_drawdown=0.17,
        cvar_5pct=0.02,
        turnover_total=2.2,
        cash_rejections=1,
    )
    adjudication = runner.adjudicate(
        a0,
        a2,
        protocol_committed=True,
        min_commission_modelled=True,
        data_gate_passed=True,
        fixed_point_converged=True,
        samples_aligned=True,
    )
    assert adjudication.verdict == "REJECT"
    assert adjudication.checks["zero_cash_and_lot_rejections"] is False


# --------------------------------------------------------------------------------------
# 快照加载边界
# --------------------------------------------------------------------------------------


def test_replay_min_commission_default_is_unchanged() -> None:
    signature = inspect.signature(replay_frozen_schedule)
    assert signature.parameters["min_commission"].default is None
    config, _ = build_frozen_config(
        start=pd.Timestamp("2021-01-01"),
        end=pd.Timestamp("2021-01-31"),
        initial_cash=68_826.0,
        asset_class="ETF",
        bundle_path="/tmp/not-read-by-config",
    )
    assert config["mod"]["sys_transaction_cost"]["stock_min_commission"] == pytest.approx(0.0)
    assert "transaction_cost" not in config["mod"].get("sys_simulation", {})


def test_apply_min_commission_uses_effective_rqalpha_path() -> None:
    config, _ = build_frozen_config(
        start=pd.Timestamp("2021-01-01"),
        end=pd.Timestamp("2021-01-31"),
        initial_cash=68_826.0,
        asset_class="ETF",
        bundle_path="/tmp/not-read-by-config",
    )
    applied = apply_min_commission(config, 5.0)
    assert applied == pytest.approx(5.0)
    transaction_cost = config["mod"]["sys_transaction_cost"]
    assert transaction_cost["stock_min_commission"] == pytest.approx(5.0)
    assert transaction_cost["stock_commission_multiplier"] == pytest.approx(0.3125)
    assert config["mod"]["sys_simulation"]["slippage"] == pytest.approx(0.0005)


def test_apply_min_commission_stops_without_effective_path() -> None:
    with pytest.raises(ValueError, match="sys_transaction_cost"):
        apply_min_commission({"mod": {}}, 5.0)


def test_snapshot_loader_rejects_canonical_directory() -> None:
    with pytest.raises(policy.PolicyError, match="canonical"):
        runner.load_research_snapshot(runner.CANONICAL_DIR / "etf_adjusted_close.csv")


def test_snapshot_loader_reads_synthetic_files(tmp_path: Path) -> None:
    dates = pd.bdate_range("2021-01-04", periods=5)
    frame = _frozen_prices(dates, {symbol: 1.0 for symbol in policy.FROZEN_CONFIG.symbols})
    prices_path = tmp_path / "etf_adjusted_close.csv"
    frame.to_csv(prices_path, index_label="date")
    calendar = pd.DataFrame({"sse_open": [1] * len(dates)}, index=dates)
    calendar.index.name = "date"
    calendar_path = tmp_path / "trading_calendar.csv"
    calendar.to_csv(calendar_path)
    prices, trading_days = runner.load_research_snapshot(prices_path, calendar_path)
    assert list(prices.columns) == list(policy.FROZEN_CONFIG.symbols)
    assert trading_days.equals(dates)


@pytest.mark.parametrize("flag,expected", [([], False), (["--protocol-committed"], True)])
def test_cli_forwards_protocol_claim(monkeypatch, capsys, flag, expected) -> None:
    seen = {}
    monkeypatch.setattr(runner, "load_research_snapshot", lambda *args: (None, None))

    def fake_run_pair(**kwargs):
        seen.update(kwargs)
        raise policy.PolicyError("synthetic stop")

    monkeypatch.setattr(runner, "run_pair", fake_run_pair)
    assert runner.main(["--prices", "synthetic", "--bundle", "synthetic", *flag]) == 1
    assert seen["protocol_committed"] is expected
    assert "INCONCLUSIVE" in capsys.readouterr().out
