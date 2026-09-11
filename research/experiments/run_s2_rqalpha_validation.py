#!/usr/bin/env python3
"""将冻结的 S2 V2B 目标变更日程交给 RQAlpha 原生执行与记账。"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

import pandas as pd

from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe
from tacticore.engines.rqalpha_adapter import build_rqalpha_config
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.multi_asset_trend import (
    MultiAssetTrendConfig,
    build_month_end_targets,
    build_signal_change_execution_weights,
    load_trend_config,
)

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = Path.home() / ".rqalpha/bundle"
MATERIAL_DEVIATION = 0.05


def build_frozen_target_schedule(
    prices: pd.DataFrame, config: MultiAssetTrendConfig
) -> pd.DataFrame:
    """调用既有 S2 实现，冻结仅含目标变化执行日的输入日程。"""
    monthly_targets = build_month_end_targets(prices, config)
    schedule = build_signal_change_execution_weights(prices, monthly_targets).dropna(how="all")
    symbols = [*config.risk_symbols, config.fallback_symbol]
    schedule = schedule.loc[:, symbols].copy()
    schedule.index.name = "execution_date"
    if schedule.index.has_duplicates or not schedule.index.is_monotonic_increasing:
        raise ValueError("冻结目标日期必须唯一且递增")
    if not schedule.sum(axis=1).round(12).eq(1.0).all():
        raise ValueError("冻结目标权重必须合计为 100%")
    return schedule


def build_symbol_mapping(universe_path: Path, symbols: list[str]) -> dict[str, str]:
    mapping = load_universe(universe_path)["rqalpha_symbol"].to_dict()
    missing = set(symbols).difference(mapping)
    if missing:
        raise ValueError(f"RQAlpha 映射缺少 S2 资产: {sorted(missing)}")
    return {symbol: mapping[symbol] for symbol in symbols}


def target_for_replay(
    schedule: pd.DataFrame, mapping: dict[str, str], now: pd.Timestamp
) -> dict[str, float] | None:
    """仅在冻结执行日返回正权重目标；其他日期不下单。"""
    execution_date = now.normalize()
    if execution_date not in schedule.index:
        return None
    row = schedule.loc[execution_date]
    return {mapping[symbol]: float(weight) for symbol, weight in row.items() if weight > 0}


def build_callbacks(
    schedule: pd.DataFrame,
    mapping: dict[str, str],
    order_events: list[dict[str, Any]],
    replayed_dates: list[pd.Timestamp],
) -> tuple[Any, Any]:
    """构造冻结目标回放回调，并仅记录 analyser 缺失的原生订单事件。"""

    def capture(event_name: str) -> Any:
        def handler(context: Any, event: Any) -> None:
            order = getattr(event, "order", None)
            order_events.append(
                {
                    "event": event_name,
                    "date": pd.Timestamp(context.now).normalize(),
                    "order_id": getattr(order, "order_id", None),
                    "rqalpha_symbol": getattr(
                        order, "order_book_id", getattr(event, "order_book_id", None)
                    ),
                    "status": getattr(getattr(order, "status", None), "name", "REJECTED"),
                    "quantity": getattr(order, "quantity", None),
                    "filled_quantity": getattr(order, "filled_quantity", None),
                    "message": getattr(order, "message", getattr(event, "reason", "")),
                }
            )

        return handler

    def init(context: Any) -> None:
        from rqalpha.api import subscribe_event, update_universe
        from rqalpha.core.events import EVENT

        del context
        update_universe(list(mapping.values()))
        for event_name in (
            "ORDER_CREATION_PASS",
            "ORDER_CREATION_REJECT",
            "ORDER_CANCELLATION_PASS",
            "ORDER_CANCELLATION_REJECT",
            "ORDER_UNSOLICITED_UPDATE",
        ):
            subscribe_event(getattr(EVENT, event_name), capture(event_name))

    def handle_bar(context: Any, bar_dict: Any) -> None:
        from rqalpha.api import order_target_portfolio

        del bar_dict
        execution_date = pd.Timestamp(context.now).normalize()
        target = target_for_replay(schedule, mapping, execution_date)
        if target is None:
            return
        replayed_dates.append(execution_date)
        order_target_portfolio(target)

    return init, handle_bar


def run_rqalpha_frozen_targets(
    schedule: pd.DataFrame,
    mapping: dict[str, str],
    config: MultiAssetTrendConfig,
    start_date: str,
    end_date: str,
    bundle: Path,
    *,
    partial_fill_on_insufficient_cash: bool = False,
) -> tuple[dict[str, Any], pd.DataFrame, list[pd.Timestamp]]:
    from rqalpha import __version__ as rqalpha_version
    from rqalpha import run_func

    if not bundle.is_dir():
        raise FileNotFoundError(f"RQAlpha bundle 目录不存在: {bundle}")
    events: list[dict[str, Any]] = []
    replayed_dates: list[pd.Timestamp] = []
    init, handle_bar = build_callbacks(schedule, mapping, events, replayed_dates)
    rq_config = build_rqalpha_config(
        start_date,
        end_date,
        initial_cash=config.initial_cash,
        fees=config.fees,
        slippage=config.slippage,
        bundle_path=bundle,
        rqalpha_major_version=int(rqalpha_version.split(".", 1)[0]),
        partial_fill_on_insufficient_cash=partial_fill_on_insufficient_cash,
    )
    result = run_func(init=init, handle_bar=handle_bar, config=rq_config)
    if result is None:
        raise RuntimeError("RQAlpha 冻结目标验证失败")
    return result["sys_analyser"], pd.DataFrame(events), replayed_dates


def parse_native_results(analyser: dict[str, Any], order_events: pd.DataFrame) -> pd.DataFrame:
    """将 sys_analyser 原生汇总压缩为单行决策证据。"""
    summary = analyser["summary"]
    trades = analyser["trades"]
    account = analyser["stock_account"]
    passed = order_events.loc[order_events["event"].eq("ORDER_CREATION_PASS")]
    failed = order_events.loc[
        order_events["event"].eq("ORDER_CREATION_REJECT")
        | (
            order_events["event"].eq("ORDER_UNSOLICITED_UPDATE")
            & order_events["status"].isin(["REJECTED", "CANCELLED"])
        )
    ]
    rejected_for_cash = failed.loc[
        failed["status"].eq("REJECTED")
        & failed["message"].str.contains("not enough money", na=False)
    ]
    cancelled_for_cash = order_events.loc[
        order_events["event"].eq("ORDER_UNSOLICITED_UPDATE")
        & order_events["status"].eq("CANCELLED")
        & order_events["message"].str.contains("not enough money", na=False)
    ]
    transaction_cost = float(trades.get("transaction_cost", pd.Series(dtype=float)).sum())
    return pd.DataFrame(
        [
            {
                "total_return": float(summary["total_returns"]),
                "cagr": float(summary["annualized_returns"]),
                "max_drawdown": -abs(float(summary["max_drawdown"])),
                "sharpe": float(summary["sharpe"]),
                "transaction_cost": transaction_cost,
                "native_order_count": int(passed["order_id"].nunique()),
                "native_failed_order_events": len(failed),
                "cash_failure_events": int(
                    failed["message"].str.contains("not enough money", na=False).sum()
                ),
                "cash_rejection_events": len(rejected_for_cash),
                "cash_residual_cancellation_events": len(cancelled_for_cash),
                "volume_limited_events": int(
                    failed["message"].str.contains("current bar volume", na=False).sum()
                ),
                "trade_count": len(trades),
                "ending_cash": float(summary["cash"]),
                "minimum_cash": float(account["cash"].min()),
                "average_cash_ratio": float(
                    (analyser["portfolio"]["cash"] / analyser["portfolio"]["total_value"]).mean()
                ),
                "turnover": float(summary["turnover"]),
            }
        ]
    )


def actual_weight_table(
    analyser: dict[str, Any], reverse_mapping: dict[str, str], symbols: list[str]
) -> pd.DataFrame:
    positions = analyser["stock_positions"]
    portfolio = analyser["portfolio"]
    weights = pd.DataFrame(0.0, index=portfolio.index, columns=symbols)
    if not positions.empty:
        local = positions.assign(symbol=positions["order_book_id"].map(reverse_mapping))
        market_values = local.pivot_table(
            index=local.index, columns="symbol", values="market_value", aggfunc="sum"
        ).fillna(0.0)
        weights.loc[market_values.index, market_values.columns] = market_values.div(
            portfolio.loc[market_values.index, "total_value"], axis=0
        )
    weights["cash"] = portfolio["cash"] / portfolio["total_value"]
    return weights


def target_tracking_table(
    schedule: pd.DataFrame,
    monthly_reviews: pd.DatetimeIndex,
    actual_weights: pd.DataFrame,
) -> pd.DataFrame:
    dates = schedule.index.union(monthly_reviews).intersection(actual_weights.index)
    dates = dates[dates >= schedule.index[0]]
    intended = schedule.reindex(dates, method="ffill")
    actual = actual_weights.loc[dates, schedule.columns]
    cash = actual_weights.loc[dates, "cash"]
    total_deviation = intended.sub(actual).abs().sum(axis=1) + cash.abs()
    rows = pd.DataFrame(
        {
            "observation_type": [
                "execution+review"
                if date in schedule.index and date in monthly_reviews
                else "execution"
                if date in schedule.index
                else "monthly_review"
                for date in dates
            ],
            "total_absolute_weight_deviation": total_deviation,
            "maximum_asset_weight_deviation": intended.sub(actual).abs().max(axis=1),
            "cash_residual": cash,
            "materially_off_target": total_deviation.gt(MATERIAL_DEVIATION),
            "intended_positions": intended.apply(_format_positions, axis=1),
            "actual_positions": actual.apply(_format_positions, axis=1),
        },
        index=dates,
    )
    rows.index.name = "date"
    return rows.reset_index()


def _format_positions(row: pd.Series) -> str:
    return ";".join(f"{symbol}:{weight:.4f}" for symbol, weight in row.items() if weight > 0.0001)


def material_difference_table(
    schedule: pd.DataFrame,
    actual_weights: pd.DataFrame,
    analyser: dict[str, Any],
    order_events: pd.DataFrame,
    reverse_mapping: dict[str, str],
) -> pd.DataFrame:
    event_rows = order_events.copy()
    event_rows["symbol"] = event_rows["rqalpha_symbol"].map(reverse_mapping)
    records = []
    for date, intended in schedule.iterrows():
        actual = actual_weights.loc[date, schedule.columns]
        for symbol in schedule.columns[intended.sub(actual).abs().gt(MATERIAL_DEVIATION)]:
            native = event_rows.loc[
                (event_rows["date"].eq(date)) & (event_rows["symbol"].eq(symbol))
            ]
            final = native.iloc[-1] if not native.empty else None
            trades = analyser["trades"]
            fills = (
                trades.loc[trades["order_id"].eq(final["order_id"])]
                if final is not None and pd.notna(final["order_id"]) and not trades.empty
                else pd.DataFrame()
            )
            status = final["status"] if final is not None else "NO_ORDER_RECORDED"
            evidence = final["message"] if final is not None else ""
            if not fills.empty and status == "ACTIVE":
                filled = int(fills["last_quantity"].sum())
                ordered = int(final["quantity"])
                status = "FILLED" if filled == ordered else "PARTIALLY_FILLED"
                evidence = f"sys_analyser 成交数量 {filled}/{ordered}"
            records.append(
                {
                    "date": date.date().isoformat(),
                    "symbol": symbol,
                    "intended_weight": intended[symbol],
                    "realized_weight": actual[symbol],
                    "native_status": status,
                    "native_evidence": evidence or "UNEXPLAINED_EXECUTION_DIFFERENCE",
                }
            )
    return pd.DataFrame(records)


def user_effort_table(
    schedule: pd.DataFrame,
    monthly_reviews: pd.DatetimeIndex,
    analyser: dict[str, Any],
    order_events: pd.DataFrame,
    tracking: pd.DataFrame,
) -> pd.DataFrame:
    trades = analyser["trades"]
    passed = order_events.loc[order_events["event"].eq("ORDER_CREATION_PASS")]
    elapsed_years = (analyser["portfolio"].index[-1] - schedule.index[0]).days / 365.25
    review_rows = tracking.loc[tracking["observation_type"].str.contains("review")]
    execution_rows = tracking.loc[tracking["observation_type"].str.contains("execution")]
    return pd.DataFrame(
        [
            {
                "monthly_reviews": int((monthly_reviews >= schedule.index[0]).sum()),
                "target_change_months": len(schedule),
                "months_with_submitted_orders": passed["date"].dt.to_period("M").nunique(),
                "months_with_actual_fills": pd.DatetimeIndex(trades.index).to_period("M").nunique(),
                "unique_instruments_traded": trades["order_book_id"].nunique(),
                "trade_records": len(trades),
                "materially_unreached_execution_dates": int(
                    execution_rows["materially_off_target"].sum()
                ),
                "materially_unreached_review_months": int(
                    review_rows["materially_off_target"].sum()
                ),
                "annualized_target_change_months": len(schedule) / elapsed_years,
                "annualized_fill_months": (
                    pd.DatetimeIndex(trades.index).to_period("M").nunique() / elapsed_years
                ),
                "annualized_materially_unreached_review_months": int(
                    review_rows["materially_off_target"].sum()
                )
                / elapsed_years,
            }
        ]
    )


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/results")
    parser.add_argument("--output-prefix")
    parser.add_argument("--partial-fill-on-insufficient-cash", action="store_true")
    args = parser.parse_args()
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    config = load_trend_config(ROOT / "config/strategy.toml")
    schedule = build_frozen_target_schedule(prices, config)
    mapping = build_symbol_mapping(ROOT / "config/universe.csv", list(schedule.columns))
    start = prices.index[prices.index.get_loc(schedule.index[0]) - 1]
    analyser, order_events, replayed = run_rqalpha_frozen_targets(
        schedule,
        mapping,
        config,
        str(start.date()),
        str(prices.index[-1].date()),
        args.bundle,
        partial_fill_on_insufficient_cash=args.partial_fill_on_insufficient_cash,
    )
    if replayed != list(schedule.index):
        raise RuntimeError("RQAlpha 实际回放日期与冻结目标日程不一致")

    reverse_mapping = {rqalpha: local for local, rqalpha in mapping.items()}
    actual_weights = actual_weight_table(analyser, reverse_mapping, list(schedule.columns))
    monthly_reviews = build_month_end_targets(prices, config).index
    tracking = target_tracking_table(schedule, monthly_reviews, actual_weights)
    native = parse_native_results(analyser, order_events)
    differences = material_difference_table(
        schedule, actual_weights, analyser, order_events, reverse_mapping
    )
    effort = user_effort_table(schedule, monthly_reviews, analyser, order_events, tracking)
    vectorbt = run_target_weights(
        prices,
        build_signal_change_execution_weights(prices, build_month_end_targets(prices, config)),
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=start,
    )
    native.insert(0, "engine", "RQAlpha")
    from rqalpha import __version__ as rqalpha_version

    native.insert(1, "rqalpha_version", rqalpha_version)
    native.insert(
        2,
        "partial_fill_on_insufficient_cash",
        args.partial_fill_on_insufficient_cash,
    )
    native["vectorbt_total_return"] = float(
        vectorbt.equity.iloc[-1] / vectorbt.equity.loc[start] - 1
    )
    native["vectorbt_cagr"] = vectorbt.metrics["cagr"]
    native["vectorbt_max_drawdown"] = vectorbt.metrics["max_drawdown"]
    native["vectorbt_sharpe"] = vectorbt.metrics["sharpe"]
    native["mean_total_absolute_weight_deviation"] = tracking[
        "total_absolute_weight_deviation"
    ].mean()
    native["maximum_total_absolute_weight_deviation"] = tracking[
        "total_absolute_weight_deviation"
    ].max()
    native["material_deviation_threshold"] = MATERIAL_DEVIATION
    execution_tracking = tracking.loc[tracking["observation_type"].str.contains("execution")]
    review_tracking = tracking.loc[tracking["observation_type"].str.contains("review")]
    native["material_execution_dates"] = int(execution_tracking["materially_off_target"].sum())
    native["material_review_months"] = int(review_tracking["materially_off_target"].sum())
    native["cash_above_material_threshold_review_months"] = int(
        review_tracking["cash_residual"].gt(MATERIAL_DEVIATION).sum()
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.output_prefix:
        outputs = {
            f"{args.output_prefix}_summary.csv": native,
            f"{args.output_prefix}_target_tracking.csv": tracking,
            f"{args.output_prefix}_material_differences.csv": differences,
            f"{args.output_prefix}_user_effort.csv": effort,
        }
    else:
        outputs = {
            "s2_v2_frozen_targets.csv": schedule.reset_index(),
            "s2_rqalpha_native_summary.csv": native,
            "s2_rqalpha_target_tracking.csv": tracking,
            "s2_rqalpha_material_differences.csv": differences,
            "s2_rqalpha_user_effort.csv": effort,
        }
    for filename, frame in outputs.items():
        frame.to_csv(
            args.output_dir / filename, index=False, float_format="%.8f", lineterminator="\n"
        )
    print(native.to_string(index=False))
    print(effort.to_string(index=False))


if __name__ == "__main__":
    main()
