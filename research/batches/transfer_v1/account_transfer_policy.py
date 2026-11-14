"""ACCOUNT_INVESTABLE_ALLOCATION_TRANSFER_V1: A0/A2 目标与订单规则。

只实现研究规则，不撮合、不记账、不估值；成交、现金、整手、费用和持仓由
RQAlpha 原生承担（`run_account_transfer.py` 调用 `replay_frozen_schedule`）。
规则来源：`PROTOCOL_V1.md` §3.1/§4/§6 与 2026-11-14 冻结资产映射。协议仍是
`DRAFT_NOT_COMMITTED / NO_BACKTEST`，本模块不修改协议、不构成生产批准。

A0/A2 共用月末偏离带：核心/债券严格 >5pp、黄金严格 >3pp 才交易。A2 上侧
`min(1.1w, 15%)`、下侧 `0.9w`；200 日 MA ±2%，连续两个相邻月末确认；单标的
和同袖子月度目标变化 ≤10pp；上侧资金只来自现金。次一交易日执行；先卖后买由
日程列顺序表达，不重排订单。目标不足一手、买入不足 5,000 元只记录为未提交。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from tacticore.data.tradability import (
    AssetLifetime,
    build_tradability_mask,
    validate_execution_targets,
)

SIDE_UPPER = "upper"
SIDE_LOWER = "lower"
SIDE_NEUTRAL = "neutral"
ORDER_SELL = "SELL"
ORDER_BUY = "BUY"

PROTOCOL_STATUS = (
    "FROZEN_PROTOCOL_V1 / DATA_AUDIT_PASS / RUNNER_VALIDATED_PRE_RESULT / "
    "NO_PRODUCTION_AUTHORIZATION"
)
INITIAL_CASH = 68_826.0
MAIN_START = pd.Timestamp("2020-10-01")
MAIN_END = pd.Timestamp("2026-10-31")
MA_WINDOW = 200
TREND_THRESHOLD = 0.02
UPPER_MULTIPLIER = 1.10
LOWER_MULTIPLIER = 0.90
SINGLE_ASSET_CAP = 0.15
MONTHLY_CHANGE_CAP = 0.10
LOT_SIZE = 100
MIN_BUY_NOTIONAL = 5_000.0

CORE_BAND = 0.05
BOND_BAND = 0.05
GOLD_BAND = 0.03


class PolicyError(ValueError):
    """规则输入不完整或不可执行；调用方应输出 NO_BACKTEST / INCONCLUSIVE。"""


@dataclass(frozen=True)
class AssetRule:
    symbol: str
    sleeve: str
    base_weight: float
    rqalpha_symbol: str
    listed_date: pd.Timestamp
    band: float
    delisted_date: pd.Timestamp | None = None


@dataclass(frozen=True)
class TransferConfig:
    """一组版本化的研究参数；默认值是本执行器使用的冻结映射。"""

    assets: tuple[AssetRule, ...]
    initial_cash: float = INITIAL_CASH
    main_start: pd.Timestamp = MAIN_START
    main_end: pd.Timestamp = MAIN_END
    ma_window: int = MA_WINDOW
    trend_threshold: float = TREND_THRESHOLD
    upper_multiplier: float = UPPER_MULTIPLIER
    lower_multiplier: float = LOWER_MULTIPLIER
    single_asset_cap: float = SINGLE_ASSET_CAP
    monthly_change_cap: float = MONTHLY_CHANGE_CAP
    lot_size: int = LOT_SIZE
    min_buy_notional: float = MIN_BUY_NOTIONAL
    tolerance: float = 1e-12

    def __post_init__(self) -> None:
        symbols = [asset.symbol for asset in self.assets]
        if len(set(symbols)) != len(symbols):
            raise ValueError("资产 symbol 必须唯一")
        if any(asset.base_weight < 0 for asset in self.assets):
            raise ValueError("基准权重不得为负")
        if sum(asset.base_weight for asset in self.assets) > 1 + self.tolerance:
            raise ValueError("基准权重之和不得超过 1")
        if self.ma_window < 2:
            raise ValueError("均线窗口至少为 2")
        if not 0 < self.lot_size:
            raise ValueError("整手规模必须为正")
        if self.initial_cash <= 0:
            raise ValueError("初始现金必须为正")
        for asset in self.assets:
            if asset.band <= 0:
                raise ValueError(f"{asset.symbol} 的偏离带必须为正")
            if asset.sleeve not in {"core", "bond", "gold", "overseas", "satellite"}:
                raise ValueError(f"{asset.symbol} 的袖子未知: {asset.sleeve}")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(asset.symbol for asset in self.assets)

    @property
    def base_weights(self) -> dict[str, float]:
        return {asset.symbol: asset.base_weight for asset in self.assets}

    @property
    def cash_weight(self) -> float:
        return 1.0 - sum(self.base_weights.values())

    @property
    def sleeves(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for asset in self.assets:
            grouped.setdefault(asset.sleeve, []).append(asset.symbol)
        return {name: tuple(members) for name, members in grouped.items()}

    @property
    def rule_by_symbol(self) -> dict[str, AssetRule]:
        return {asset.symbol: asset for asset in self.assets}


#: 2026-11-14 研究执行器冻结映射；不是账户现行政策，也不表示协议已提交。
#: 核心 25% = 512890/515450 各 12.5%；债券 20% = 511360/511010 各 10%；
#: 黄金 10% = 518880；海外 0；卫星 0；其余 45% 为现金。
FROZEN_CONFIG = TransferConfig(
    assets=(
        AssetRule("512890.SS", "core", 0.125, "512890.XSHG", pd.Timestamp("2019-01-18"), CORE_BAND),
        AssetRule("515450.SS", "core", 0.125, "515450.XSHG", pd.Timestamp("2020-02-26"), CORE_BAND),
        AssetRule("511360.SS", "bond", 0.10, "511360.XSHG", pd.Timestamp("2020-09-25"), BOND_BAND),
        AssetRule("511010.SS", "bond", 0.10, "511010.XSHG", pd.Timestamp("2013-03-25"), BOND_BAND),
        AssetRule("518880.SS", "gold", 0.10, "518880.XSHG", pd.Timestamp("2013-07-29"), GOLD_BAND),
    )
)


@dataclass
class TrendState:
    confirmed: str | None = None
    pending: str | None = None
    pending_count: int = 0


@dataclass
class TrendTracker:
    """逐标的趋势状态机；缺数据时清空状态，绝不前填。"""

    states: dict[str, TrendState] = field(default_factory=dict)

    def update(self, symbol: str, signal: str | None) -> str | None:
        state = self.states.setdefault(symbol, TrendState())
        if signal is None:
            state.confirmed = None
            state.pending = None
            state.pending_count = 0
            return None
        if signal == SIDE_NEUTRAL:
            state.pending = None
            state.pending_count = 0
            return state.confirmed
        if state.pending == signal:
            state.pending_count += 1
        else:
            state.pending = signal
            state.pending_count = 1
        if state.pending_count >= 2:
            state.confirmed = signal
        return state.confirmed


def classify_trend(close: float, moving_average: float, threshold: float) -> str:
    """严格大于 +2% 为上侧，严格小于 -2% 为下侧，其余中性。"""
    if close > moving_average * (1.0 + threshold):
        return SIDE_UPPER
    if close < moving_average * (1.0 - threshold):
        return SIDE_LOWER
    return SIDE_NEUTRAL


def trend_observation(
    prices: pd.DataFrame,
    symbol: str,
    decision_date: pd.Timestamp,
    *,
    window: int = MA_WINDOW,
    threshold: float = TREND_THRESHOLD,
) -> str | None:
    """不足 200 个有效观测、窗口有缺失或月末缺价时返回 None（不前填）。"""
    if symbol not in prices.columns:
        return None
    date = pd.Timestamp(decision_date).normalize()
    ordered = prices.sort_index()
    if date not in ordered.index:
        return None
    history = ordered.loc[:date, symbol]
    if len(history) < window:
        return None
    sample = pd.to_numeric(history.iloc[-window:], errors="coerce")
    if sample.isna().any() or (sample <= 0).any():
        return None
    return classify_trend(float(sample.iloc[-1]), float(sample.mean()), threshold)


def build_trend_path(
    prices: pd.DataFrame, decisions: Iterable[pd.Timestamp], config: TransferConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (原始信号, 应用确认状态)；缺数据时确认状态为 None。"""
    decisions = pd.DatetimeIndex([pd.Timestamp(date).normalize() for date in decisions])
    signals = pd.DataFrame(index=decisions, columns=list(config.symbols), dtype=object)
    confirmed = pd.DataFrame(index=decisions, columns=list(config.symbols), dtype=object)
    tracker = TrendTracker()
    for date in decisions:
        for symbol in config.symbols:
            signal = trend_observation(
                prices,
                symbol,
                date,
                window=config.ma_window,
                threshold=config.trend_threshold,
            )
            signals.at[date, symbol] = signal
            confirmed.at[date, symbol] = tracker.update(symbol, signal)
    return signals, confirmed


def _raw_target(rule: AssetRule, side: str | None, config: TransferConfig) -> float:
    if side == SIDE_UPPER:
        return min(rule.base_weight * config.upper_multiplier, config.single_asset_cap)
    if side == SIDE_LOWER:
        # 15% 上限约束所有新目标；基准权重不超过 15% 时该 min 不改变 0.9w。
        return min(rule.base_weight * config.lower_multiplier, config.single_asset_cap)
    return rule.base_weight


def apply_monthly_change_cap(
    proposed: Mapping[str, float],
    previous: Mapping[str, float],
    config: TransferConfig,
) -> dict[str, float]:
    """单标的与同袖子合计的目标变化均不超过 10pp。"""
    capped = {symbol: float(value) for symbol, value in proposed.items()}
    cap = config.monthly_change_cap
    for symbol in capped:
        delta = capped[symbol] - float(previous[symbol])
        capped[symbol] = float(previous[symbol]) + max(-cap, min(cap, delta))
    for members in config.sleeves.values():
        total_delta = sum(capped[symbol] - float(previous[symbol]) for symbol in members)
        if abs(total_delta) > cap + config.tolerance:
            scale = cap / abs(total_delta)
            for symbol in members:
                capped[symbol] = (
                    float(previous[symbol]) + (capped[symbol] - float(previous[symbol])) * scale
                )
    return capped


def apply_cash_constraint(
    proposed: Mapping[str, float], base: Mapping[str, float], config: TransferConfig
) -> dict[str, float]:
    """上侧增量只能来自现金；不足时按拟增加额等比例缩减，不借款。"""
    targets = {symbol: float(value) for symbol, value in proposed.items()}
    capacity = 1.0 - sum(float(value) for value in base.values())
    capacity += sum(max(0.0, float(base[symbol]) - targets[symbol]) for symbol in targets)
    demand = sum(max(0.0, targets[symbol] - float(base[symbol])) for symbol in targets)
    if demand > capacity + config.tolerance:
        if capacity < -config.tolerance:
            raise PolicyError("基准权重超过 1，无法满足现金约束")
        scale = max(capacity, 0.0) / demand
        for symbol in targets:
            if targets[symbol] > float(base[symbol]):
                targets[symbol] = (
                    float(base[symbol]) + (targets[symbol] - float(base[symbol])) * scale
                )
    if sum(targets.values()) > 1.0 + config.tolerance:
        raise PolicyError("目标权重之和超过 1")
    if any(value < -config.tolerance for value in targets.values()):
        raise PolicyError("目标权重不得为负")
    return targets


def a2_target_weights(
    confirmed: Mapping[str, str | None],
    previous: Mapping[str, float],
    base: Mapping[str, float],
    config: TransferConfig,
) -> dict[str, float]:
    """趋势目标 -> 月度变化上限 -> 现金约束，顺序固定。"""
    proposed = {
        symbol: _raw_target(config.rule_by_symbol[symbol], confirmed.get(symbol), config)
        for symbol in config.symbols
    }
    capped = apply_monthly_change_cap(proposed, previous, config)
    return apply_cash_constraint(capped, base, config)


def target_path(
    decisions: Iterable[pd.Timestamp],
    config: TransferConfig,
    confirmed: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """逐月目标；A0 传 ``confirmed=None``，A2 传已确认状态表。"""
    decisions = pd.DatetimeIndex([pd.Timestamp(date).normalize() for date in decisions])
    base = config.base_weights
    previous = dict(base)
    rows: list[dict[str, float]] = []
    for date in decisions:
        if confirmed is None:
            targets = dict(base)
        else:
            if date not in confirmed.index:
                raise PolicyError(f"趋势状态缺少决策日: {date.date()}")
            targets = a2_target_weights(confirmed.loc[date].to_dict(), previous, base, config)
        rows.append(targets)
        previous = targets
    return pd.DataFrame(rows, index=decisions, columns=list(config.symbols), dtype=float)


def band_trigger(actual: float, target: float, band: float, tolerance: float = 1e-12) -> bool:
    """偏离严格大于带宽才触发；等于边界不触发。"""
    return abs(float(actual) - float(target)) > float(band) + tolerance


def month_end_dates(
    calendar: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DatetimeIndex:
    """窗口内每个自然月的最后一个交易日；月末非交易日自动前移。"""
    trading = pd.DatetimeIndex(pd.to_datetime(calendar)).normalize().unique().sort_values()
    within = trading[(trading >= pd.Timestamp(start)) & (trading <= pd.Timestamp(end))]
    if within.empty:
        return pd.DatetimeIndex([])
    frame = pd.DataFrame({"date": within})
    frame["month"] = pd.DatetimeIndex(within).to_period("M")
    return pd.DatetimeIndex(frame.groupby("month")["date"].max().sort_values().to_numpy())


def next_trading_day(calendar: pd.DatetimeIndex, date: pd.Timestamp) -> pd.Timestamp | None:
    trading = pd.DatetimeIndex(pd.to_datetime(calendar)).normalize().unique().sort_values()
    position = int(trading.searchsorted(pd.Timestamp(date).normalize(), side="right"))
    return pd.Timestamp(trading[position]) if position < len(trading) else None


def decision_execution_pairs(
    calendar: pd.DatetimeIndex, decisions: Iterable[pd.Timestamp], config: TransferConfig
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """决策日 -> 次一交易日；没有下一交易日或超出窗口的月份不执行。"""
    trading = pd.DatetimeIndex(pd.to_datetime(calendar)).normalize().unique().sort_values()
    pairs: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    seen: set[pd.Timestamp] = set()
    for raw in decisions:
        decision = pd.Timestamp(raw).normalize()
        if decision not in trading:
            raise PolicyError(f"决策日不是交易日: {decision.date()}")
        execution = next_trading_day(trading, decision)
        if execution is None or execution > config.main_end:
            continue
        if execution in seen:
            raise PolicyError(f"两个决策日映射到同一个执行日: {execution.date()}")
        seen.add(execution)
        pairs.append((decision, execution))
    return pairs


@dataclass(frozen=True)
class ActualState:
    """决策日收盘的 RQAlpha 原生持仓快照。"""

    weights: Mapping[str, float]
    quantities: Mapping[str, int]
    equity: float


@dataclass(frozen=True)
class OrderIntent:
    decision_date: pd.Timestamp
    execution_date: pd.Timestamp
    symbol: str
    side: str | None
    target_weight: float
    actual_weight: float
    equity: float
    price: float | None
    current_quantity: int
    target_quantity: int
    order_quantity: int
    order_notional: float
    submitted: bool
    reason: str
    trigger: str
    trend_state: str | None
    passive_overweight: bool
    cap_forced_sale: bool


def plan_order(
    *,
    decision_date: pd.Timestamp,
    execution_date: pd.Timestamp,
    symbol: str,
    target_weight: float,
    actual: ActualState,
    price: float,
    config: TransferConfig,
    trigger: str,
    trend_state: str | None,
) -> OrderIntent:
    """按一手与最低买入额过滤；卖出无最低额，整手卖出允许清仓。"""
    actual_weight = float(actual.weights.get(symbol, 0.0))
    lot = config.lot_size
    target_quantity = int(math.floor(target_weight * actual.equity / price / lot)) * lot
    if symbol in actual.quantities:
        current_quantity = int(actual.quantities[symbol])
    else:
        current_quantity = int(math.floor(actual_weight * actual.equity / price / lot)) * lot
    side: str | None = None
    order_quantity = 0
    notional = 0.0
    submitted = False
    reason = "target_equals_holding"
    if target_quantity > current_quantity:
        side = ORDER_BUY
        order_quantity = target_quantity - current_quantity
        if order_quantity < lot or order_quantity % lot:
            if (order_quantity // lot) * lot == 0:
                reason = "below_one_lot"
            else:
                reason = "odd_lot_buy"
            order_quantity = 0
        else:
            notional = order_quantity * price
            if notional < config.min_buy_notional - config.tolerance:
                reason = "below_min_buy"
                order_quantity = 0
            else:
                submitted, reason = True, "buy"
    elif target_quantity < current_quantity:
        side = ORDER_SELL
        order_quantity = current_quantity - target_quantity
        notional = order_quantity * price
        submitted = True
        reason = "sell_all" if target_quantity == 0 else "sell"
    elif target_quantity == 0:
        reason = "below_one_lot"
    passive_overweight = (
        actual_weight > config.single_asset_cap + config.tolerance
        and target_weight <= config.single_asset_cap + config.tolerance
    )
    return OrderIntent(
        decision_date=pd.Timestamp(decision_date).normalize(),
        execution_date=pd.Timestamp(execution_date).normalize(),
        symbol=symbol,
        side=side,
        target_weight=float(target_weight),
        actual_weight=actual_weight,
        equity=float(actual.equity),
        price=float(price),
        current_quantity=current_quantity,
        target_quantity=target_quantity,
        order_quantity=order_quantity,
        order_notional=float(notional),
        submitted=submitted,
        reason=reason,
        trigger=trigger,
        trend_state=trend_state,
        passive_overweight=passive_overweight,
        cap_forced_sale=False,
    )


def _price_at(prices: pd.DataFrame, date: pd.Timestamp, symbol: str) -> float | None:
    if symbol not in prices.columns or date not in prices.index:
        return None
    value = float(prices.at[date, symbol])
    return value if np.isfinite(value) and value > 0 else None


def _schedule_columns(config: TransferConfig) -> pd.MultiIndex:
    sell = [(ORDER_SELL, symbol) for symbol in config.symbols]
    buy = [(ORDER_BUY, symbol) for symbol in config.symbols]
    return pd.MultiIndex.from_tuples(sell + buy, names=["side", "symbol"])


def build_schedule(
    *,
    prices: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    decisions: pd.DatetimeIndex,
    targets: pd.DataFrame,
    config: TransferConfig,
    actual_states: Mapping[pd.Timestamp, ActualState] | None = None,
    trend_sides: pd.DataFrame | None = None,
    arm: str = "A0",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """生成冻结目标日程与逐笔订单意图。

    日程列按 ``("SELL", symbol)`` 在前、``("BUY", symbol)`` 在后排列，
    因此现有 `replay_frozen_schedule` 的逐列 `order_target_percent` 调用
    天然先卖后买。没有订单的月份保留整行 NaN（“今天不下单”）。

    ``actual_states=None`` 时，首个决策日按初始现金、后续月份假定目标已达成，
    用于第一次校准回放；真实运行必须传入上一轮回放得到的原生持仓快照。
    """
    pairs = decision_execution_pairs(calendar, decisions, config)
    columns = _schedule_columns(config)
    schedule = pd.DataFrame(
        np.nan, index=pd.DatetimeIndex([execution for _, execution in pairs]), columns=columns
    )
    target_frame = pd.DataFrame(
        np.nan, index=schedule.index, columns=list(config.symbols), dtype=float
    )
    if not pairs:
        return schedule, pd.DataFrame()

    lifetimes = {
        asset.symbol: AssetLifetime(
            asset.symbol, pd.Timestamp(asset.listed_date), asset.delisted_date
        )
        for asset in config.assets
    }
    mask = build_tradability_mask(
        pd.DatetimeIndex(prices.index), list(config.symbols), lifetimes, prices
    )
    records: list[dict[str, Any]] = []
    rules = config.rule_by_symbol
    first_decision = min(decisions)
    for decision, execution in pairs:
        if decision not in targets.index:
            raise PolicyError(f"目标表缺少决策日: {decision.date()}")
        target_row = targets.loc[decision]
        if decision == first_decision:
            actual = ActualState(
                weights={symbol: 0.0 for symbol in config.symbols},
                quantities={symbol: 0 for symbol in config.symbols},
                equity=config.initial_cash,
            )
            trigger = "first_build"
        elif actual_states is None:
            actual = ActualState(
                weights={symbol: float(target_row[symbol]) for symbol in config.symbols},
                quantities={},
                equity=config.initial_cash,
            )
            trigger = "deviation_band"
        else:
            state = actual_states.get(decision)
            if state is None:
                raise PolicyError(f"缺少决策日实际持仓快照: {decision.date()}")
            actual = state
            trigger = "deviation_band"
        for symbol in config.symbols:
            rule = rules[symbol]
            target_weight = float(target_row[symbol])
            actual_weight = float(actual.weights.get(symbol, 0.0))
            if not band_trigger(actual_weight, target_weight, rule.band, config.tolerance):
                continue
            price = _price_at(prices, execution, symbol)
            tradable = execution in mask.index and bool(mask.at[execution, symbol])
            if price is None or not tradable:
                # 正目标无法执行时必须停止；卖不掉则保留持仓并记录，不能假装卖出。
                if target_weight > actual_weight + config.tolerance:
                    raise PolicyError(f"正目标缺少可执行价格/生命周期: {execution.date()} {symbol}")
                records.append(
                    {
                        "arm": arm,
                        "decision_date": decision,
                        "execution_date": execution,
                        "symbol": symbol,
                        "side": ORDER_SELL,
                        "target_weight": target_weight,
                        "actual_weight": actual_weight,
                        "equity": float(actual.equity),
                        "price": np.nan,
                        "current_quantity": int(actual.quantities.get(symbol, 0)),
                        "target_quantity": np.nan,
                        "order_quantity": 0,
                        "order_notional": 0.0,
                        "submitted": False,
                        "reason": (
                            "no_execution_price" if price is None else "untradable_sell_blocked"
                        ),
                        "trigger": trigger,
                        "trend_state": (
                            None if trend_sides is None else trend_sides.at[decision, symbol]
                        ),
                        "passive_overweight": actual_weight > config.single_asset_cap,
                        "cap_forced_sale": False,
                    }
                )
                continue
            trend_state = None if trend_sides is None else trend_sides.at[decision, symbol]
            intent = plan_order(
                decision_date=decision,
                execution_date=execution,
                symbol=symbol,
                target_weight=target_weight,
                actual=actual,
                price=price,
                config=config,
                trigger=trigger,
                trend_state=trend_state,
            )
            records.append({"arm": arm, **intent.__dict__})
            if not intent.submitted:
                continue
            column = (ORDER_SELL if intent.side == ORDER_SELL else ORDER_BUY, symbol)
            schedule.at[execution, column] = target_weight
            target_frame.at[execution, symbol] = target_weight

    validate_execution_targets(target_frame, prices, mask, lifetimes, tolerance=config.tolerance)
    return schedule, pd.DataFrame(records)
