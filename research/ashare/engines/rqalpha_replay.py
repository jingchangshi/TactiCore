"""把一个**已冻结**的目标权重日程交给 RQAlpha 原生执行（WP2.2）。

设计约束（任务书）：不得新增第三套撮合或组合会计引擎，也不能修改
`tacticore/engines/rqalpha_adapter.py`。因此本模块只做三件事：

1. 用**未修改的** `build_rqalpha_config` 生成配置，费用口径由
   `research/ashare/data/fee_mapping.py` 显式映射并记录差异；
2. 提供"消费冻结日程"的回调：每个交易日把当日目标交给
   `order_target_portfolio`，**不在这里生成任何信号**——信号在上游冻结；
3. 订阅订单事件，把原生撮合结果原样收回来，供 WP2.4 做差异审计。

为什么不用 `tacticore/engines/rqalpha_adapter.py` 的 `build_callbacks`：
那个回调内部调 `select_assets` 自己算动量，是**策略**而不是**回放**。
回放一个已冻结日程时如果重新算信号，就分不清"目标不同"与"执行不同"。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from research.ashare.data.fee_mapping import map_fees_to_rqalpha

#: 参与"原生订单事件"记录的 RQAlpha 事件名。缺一个就少一类归因线索。
RECORDED_EVENTS = (
    "ORDER_CREATION_PASS",
    "ORDER_CREATION_REJECT",
    "ORDER_CANCELLATION_PASS",
    "ORDER_CANCELLATION_REJECT",
    "ORDER_UNSOLICITED_UPDATE",
)


@dataclass(frozen=True)
class RQAlphaRunResult:
    """一次冻结日程回放的完整证据。

    `analyser` 是 RQAlpha 原生的 `sys_analyser` 结果（未加工）；
    `order_events` 是订阅到的原生订单事件；`replayed_dates` 是**实际**下单的日期。
    三者必须与 `schedule` 对得上，否则这次回放不能作为证据使用。
    `min_commission` 是显式覆盖的最低佣金；None 表示沿用适配器默认值。
    """

    analyser: dict[str, Any]
    order_events: pd.DataFrame
    replayed_dates: list[pd.Timestamp]
    rqalpha_version: str
    fee_mapping_report: str
    min_commission: float | None = None


def build_frozen_config(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    initial_cash: float,
    asset_class: str,
    bundle_path: str | Path,
    partial_fill_on_insufficient_cash: bool = False,
) -> tuple[dict[str, Any], str]:
    """用**未修改的** `build_rqalpha_config` 生成配置，并返回差异报告。

    费用从 `fees-2.0.0` 映射，不直接写字面量：写死数字会让
    "研究用的费率"与"FinanceMCP 的费率"在某天悄悄分叉，而分叉那天不会有任何报错。
    """
    from rqalpha import __version__ as rqalpha_version

    from tacticore.engines.rqalpha_adapter import build_rqalpha_config

    mapping = map_fees_to_rqalpha(asset_class=asset_class)
    fees = float(mapping.parameters["fees"])
    slippage = float(mapping.parameters["slippage"])
    config = build_rqalpha_config(
        str(pd.Timestamp(start).date()),
        str(pd.Timestamp(end).date()),
        initial_cash=initial_cash,
        fees=fees,
        slippage=slippage,
        bundle_path=bundle_path,
        rqalpha_major_version=int(rqalpha_version.split(".", 1)[0]),
        partial_fill_on_insufficient_cash=partial_fill_on_insufficient_cash,
    )
    report = (
        f"asset_class={asset_class} fees={fees} slippage={slippage} "
        f"version={mapping.version} unmapped={len(mapping.unmapped)} 项\n"
        + "\n".join(f"  - {item.item}: {item.impact}" for item in mapping.unmapped)
    )
    return config, report


def build_replay_callbacks(
    schedule: pd.DataFrame,
    mapping: dict[str, str],
    order_events: list[dict[str, Any]],
    replayed_dates: list[pd.Timestamp],
) -> tuple[Any, Any]:
    """构造"消费冻结日程"的 init / handle_bar。

    `mapping` 是 `本地 symbol -> rqalpha order_book_id`。目标里出现映射表中
    没有的证券时**直接抛错**：静默跳过会让"目标 60%"被执行成"目标 0%"，
    而这条信息只会以收益偏差的形式出现，永远查不到原因。
    """

    def capture(event_name: str) -> Any:
        def handler(context: Any, event: Any) -> None:
            order = getattr(event, "order", None)
            order_events.append(
                {
                    "event": event_name,
                    "date": pd.Timestamp(context.now).normalize(),
                    "order_id": getattr(order, "order_id", None),
                    "order_book_id": getattr(order, "order_book_id", None),
                    "side": getattr(getattr(order, "side", None), "name", None),
                    "status": getattr(getattr(order, "status", None), "name", None),
                    "quantity": getattr(order, "quantity", None),
                    "filled_quantity": getattr(order, "filled_quantity", None),
                    "unfilled_quantity": getattr(order, "unfilled_quantity", None),
                    "avg_price": getattr(order, "avg_price", None),
                    "message": str(getattr(order, "message", getattr(event, "reason", "")) or ""),
                }
            )

        return handler

    def init(context: Any) -> None:
        from rqalpha.api import subscribe_event, update_universe
        from rqalpha.core.events import EVENT

        del context
        update_universe(list(mapping.values()))
        for event_name in RECORDED_EVENTS:
            subscribe_event(getattr(EVENT, event_name), capture(event_name))

    def handle_bar(context: Any, bar_dict: Any) -> None:
        from rqalpha.api import order_target_percent

        del bar_dict
        execution_date = pd.Timestamp(context.now).normalize()
        if execution_date not in schedule.index:
            # 日程里没有这一天：不下单，保持现有持仓。
            # 这与 VectorBT 侧 `execution_weights` 留 NaN 的语义一致。
            return
        row = schedule.loc[execution_date]
        # **必须逐证券下单，不能用 `order_target_portfolio`。**
        # 实测确认：`order_target_portfolio({'A': 0.5})` 把 A 调到 50%，
        # 并**把没提到的 B 隐式调到 0**，剩下的进现金。
        # 也就是说"字典里没有这个键"被 RQAlpha 解释成"目标为 0"，
        # 而不是"这个证券今天不管"。于是 NaN（今天没目标）会被静默变成
        # "今天把它平掉"——一次查不到原因的平仓。
        # `order_target_percent` 只动被点名的证券，与 VectorBT 的 NaN 语义一致。
        for symbol, weight in row.items():
            if symbol not in mapping:
                # `row.items()` 的键是 Hashable 但不保证可排序，所以不能直接
                # `sorted(missing)`；先把缺失项收集起来再转成 str 列表。
                raise KeyError(f"冻结日程中的证券没有 RQAlpha 映射: {[str(symbol)]}")
            if pd.isna(weight):
                # 今天没有目标：不下单，保持现有持仓。
                continue
            replayed_dates.append(execution_date)
            order_target_percent(mapping[symbol], float(weight))

    return init, handle_bar


def apply_min_commission(config: dict[str, Any], value: float) -> float:
    """写入 RQAlpha 6.3 实际读取的 `sys_transaction_cost.stock_min_commission`。

    冻结适配器固定写 0；本函数只在调用方显式要求时覆盖，并核对
    ETF 佣金倍率 0.3125（万 2.5）与单边滑点 5bp 未被静默改动。
    """
    transaction_cost = config.get("mod", {}).get("sys_transaction_cost")
    if not isinstance(transaction_cost, dict) or "stock_min_commission" not in transaction_cost:
        raise ValueError("RQAlpha config 缺少 mod.sys_transaction_cost.stock_min_commission")
    transaction_cost["stock_min_commission"] = float(value)
    multiplier = float(transaction_cost.get("stock_commission_multiplier", float("nan")))
    if abs(multiplier - 0.3125) > 1e-12:
        raise ValueError(f"ETF 佣金倍率不是 2.5bp 映射值: {multiplier} != 0.3125")
    slippage = float(config.get("mod", {}).get("sys_simulation", {}).get("slippage", float("nan")))
    if abs(slippage - 0.0005) > 1e-12:
        raise ValueError(f"ETF 滑点不是单边 5bp: {slippage} != 0.0005")
    return float(value)


def replay_frozen_schedule(
    schedule: pd.DataFrame,
    mapping: dict[str, str],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    initial_cash: float,
    bundle_path: str | Path,
    asset_class: str = "ETF",
    partial_fill_on_insufficient_cash: bool = False,
    min_commission: float | None = None,
) -> RQAlphaRunResult:
    """把一个已冻结的目标日程交给 RQAlpha 原生执行，并原样收回证据。

    `schedule` 的索引是**候选执行日**，可以包含 NaN 行（"这一天不下单"）。
    真正会下单的日期 = 至少有一个非 NaN 权重的日期；这个集合必须与日程的
    执行日完全一致，否则说明有执行日被跳过，回测净值对应的就不是冻结目标。

    `min_commission=None` 保持既有行为（适配器的 0，即不建模最低佣金）；
    显式传入时覆盖为指定金额（本研究的 ETF 值为 5 元）。
    """
    from rqalpha import __version__ as rqalpha_version
    from rqalpha import run_func

    if not Path(bundle_path).is_dir():
        raise FileNotFoundError(f"RQAlpha bundle 目录不存在: {bundle_path}")
    if schedule.empty:
        raise ValueError("冻结日程为空；没有可回放的目标")
    if schedule.index.has_duplicates or not schedule.index.is_monotonic_increasing:
        raise ValueError("冻结日程的日期必须唯一且递增")
    if (schedule < 0).any().any():
        raise ValueError("冻结日程不得包含负权重")
    # 全 NaN 的日程等于"什么都不做"，此时跑一次 RQAlpha 只会得到一条现金直线，
    # 把它当成执行证据是误导。
    if schedule.notna().to_numpy().sum() == 0:
        raise ValueError("冻结日程全为 NaN；没有任何执行日")

    # 目标必须在 bundle 覆盖的区间内，否则 run_func 会在一个没有数据的窗口里
    # "成功"跑完并给出全是 NaN 的结论。
    schedule_start, schedule_end = schedule.index[0], schedule.index[-1]
    window_start, window_end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if schedule_start < window_start or schedule_end > window_end:
        raise ValueError(
            f"冻结日程 [{schedule_start.date()}, {schedule_end.date()}] 超出执行窗口 "
            f"[{window_start.date()}, {window_end.date()}]"
        )

    config, report = build_frozen_config(
        start=window_start,
        end=window_end,
        initial_cash=initial_cash,
        asset_class=asset_class,
        bundle_path=bundle_path,
        partial_fill_on_insufficient_cash=partial_fill_on_insufficient_cash,
    )
    applied_min_commission: float | None = None
    if min_commission is not None:
        applied_min_commission = apply_min_commission(config, min_commission)
        report += (
            f"\nreplay_override: sys_transaction_cost.stock_min_commission="
            f"{applied_min_commission} 元；佣金 2.5bp、滑点单边 5bp 已核对"
        )
    order_events: list[dict[str, Any]] = []
    replayed_dates: list[pd.Timestamp] = []
    init, handle_bar = build_replay_callbacks(schedule, mapping, order_events, replayed_dates)
    result = run_func(init=init, handle_bar=handle_bar, config=config)
    if result is None:
        raise RuntimeError("RQAlpha 冻结目标回放失败；请检查其错误日志")
    if "sys_analyser" not in result:
        raise RuntimeError(f"RQAlpha 结果缺少 sys_analyser，实际键: {sorted(result)}")

    # 实际下单日期必须与日程的**执行日**一致。不一致说明有执行日被跳过
    # （例如 bundle 当日无数据），此时回测净值对应的不是冻结目标，不得作为证据。
    # 执行日 = 至少有一个非 NaN 权重的日期；全 NaN 行是"不下单"，不是执行日。
    execution_days = [
        pd.Timestamp(date) for date in schedule.index if schedule.loc[date].notna().any()
    ]
    observed_dates = list(dict.fromkeys(replayed_dates))
    if observed_dates != execution_days:
        missing = sorted(set(execution_days) - set(observed_dates))
        extra = sorted(set(observed_dates) - set(execution_days))
        raise RuntimeError(
            "RQAlpha 实际回放日期与冻结日程的执行日不一致: "
            f"应有 {len(execution_days)} 天，实际 {len(observed_dates)} 天"
            f"（缺少 {missing[:5]}，多出 {extra[:5]}）"
        )
    return RQAlphaRunResult(
        analyser=result["sys_analyser"],
        order_events=pd.DataFrame(order_events),
        replayed_dates=list(replayed_dates),
        rqalpha_version=rqalpha_version,
        fee_mapping_report=report,
        min_commission=applied_min_commission,
    )


def actual_weights(
    result: RQAlphaRunResult,
    *,
    local_symbols: list[str],
    reverse_mapping: dict[str, str],
) -> pd.DataFrame:
    """从原生结果还原**逐日实际成交权重**与现金权重。

    `stock_positions` 是 RQAlpha 的持仓表，`portfolio` 是逐日组合快照。
    实际权重 = 持仓市值 / 总资产；现金单独一列，不混进证券权重里。
    """
    positions = result.analyser["stock_positions"]
    portfolio = result.analyser["portfolio"]
    weights = pd.DataFrame(0.0, index=portfolio.index, columns=local_symbols, dtype=float)
    if not positions.empty:
        local = positions.assign(symbol=positions["order_book_id"].map(reverse_mapping))
        unmapped = local.loc[local["symbol"].isna(), "order_book_id"].unique()
        if len(unmapped):
            raise KeyError(f"原生持仓中有未映射的 order_book_id: {sorted(map(str, unmapped))}")
        market_values = local.pivot_table(
            index=local.index, columns="symbol", values="market_value", aggfunc="sum"
        ).fillna(0.0)
        weights.loc[market_values.index, market_values.columns] = market_values.div(
            portfolio.loc[market_values.index, "total_value"], axis=0
        )
    weights["cash"] = portfolio["cash"] / portfolio["total_value"]
    return weights


def native_summary(result: RQAlphaRunResult) -> dict[str, float | int]:
    """压缩 RQAlpha 原生汇总指标，供 WP2.4 与 VectorBT 侧对照。

    只取 `sys_analyser` 自己算出的数字，不做二次加工：二次加工的地方越多，
    "两个引擎差异"与"我自己算错了"就越难分开。
    """
    analyser = result.analyser
    summary = analyser["summary"]
    trades = analyser["trades"]
    account = analyser["stock_account"]
    events = result.order_events
    # 空事件表也必须能走完整条路径：一次"什么都没拒"的运行与一次"拒了单"的运行
    # 都要给出 0 或真实计数，不能因为没有事件就跳过统计。
    empty = events.empty
    passed = events.loc[events["event"].eq("ORDER_CREATION_PASS")] if not empty else events
    rejected = events.loc[events["event"].eq("ORDER_CREATION_REJECT")] if not empty else events
    cash_rejections = (
        rejected.loc[rejected["message"].str.contains("not enough money", na=False)]
        if not rejected.empty
        else rejected
    )
    volume_limited = (
        rejected.loc[rejected["message"].str.contains("current bar volume", na=False)]
        if not rejected.empty
        else rejected
    )
    return {
        "total_return": float(summary["total_returns"]),
        "annualized_return": float(summary["annualized_returns"]),
        "max_drawdown": -abs(float(summary["max_drawdown"])),
        "sharpe": float(summary["sharpe"]),
        "turnover": float(summary["turnover"]),
        "trade_count": int(len(trades)),
        "order_creation_passed": int(passed["order_id"].nunique()) if not passed.empty else 0,
        "order_creation_rejected": int(len(rejected)),
        "cash_rejection_events": int(len(cash_rejections)),
        "volume_limited_events": int(len(volume_limited)),
        "transaction_cost": float(trades["transaction_cost"].sum()) if not trades.empty else 0.0,
        "ending_cash": float(summary["cash"]),
        "minimum_cash": float(account["cash"].min()),
    }


__all__ = [
    "RECORDED_EVENTS",
    "RQAlphaRunResult",
    "actual_weights",
    "apply_min_commission",
    "build_frozen_config",
    "build_replay_callbacks",
    "native_summary",
    "replay_frozen_schedule",
]
