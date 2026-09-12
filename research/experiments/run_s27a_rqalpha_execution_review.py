#!/usr/bin/env python3
# ruff: noqa: E501
"""将冻结 S27A 目标日程交给 RQAlpha 原生执行，不在回调中重算信号。"""

import hashlib
from pathlib import Path

import pandas as pd

from research.experiments.run_s2_rqalpha_validation import (
    MATERIAL_DEVIATION,
    actual_weight_table,
    build_symbol_mapping,
    material_difference_table,
    parse_native_results,
    run_rqalpha_frozen_targets,
    target_tracking_table,
    user_effort_table,
)
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.multi_asset_trend import build_execution_weights, load_trend_config
from tacticore.strategies.trend_inverse_vol import (
    build_month_end_targets,
    load_trend_inverse_vol_config,
)

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = Path.home() / ".rqalpha/bundle"


def build_frozen_schedule(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    trend = load_trend_config(ROOT / "config/strategy.toml")
    targets, diagnostics = build_month_end_targets(prices, config, trend.risk_symbols)
    execution = build_execution_weights(prices, targets).dropna(how="all")
    symbols = [*trend.risk_symbols, config.fallback_symbol]
    schedule = execution.loc[:, symbols].copy()
    schedule.index.name = "execution_date"
    if schedule.index.has_duplicates or not schedule.index.is_monotonic_increasing:
        raise ValueError("S27A 冻结目标日期必须唯一并严格递增")
    if (schedule < 0).any().any() or not schedule.sum(axis=1).round(12).eq(1.0).all():
        raise ValueError("S27A 冻结权重必须非负且总和为一")
    return schedule, diagnostics


def schedule_execution(prices: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    execution.loc[schedule.index, schedule.columns] = schedule
    return execution


def vectorbt_reproduction(prices: pd.DataFrame, schedule: pd.DataFrame):
    config = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    # Batch 02 S27A 的权威基线从首个 execution date 计量，而非此前一日。
    start = schedule.index[0]
    tradability_mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))
    return run_target_weights(
        prices,
        schedule_execution(prices, schedule),
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=start,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    ), start


def decision(
    native: pd.Series,
    replayed: list[pd.Timestamp],
    schedule: pd.DataFrame,
    differences: pd.DataFrame,
) -> str:
    if replayed != list(schedule.index):
        return "BLOCK_S27A_EXECUTION_REPRODUCTION"
    unexplained = (
        differences.get("native_evidence", pd.Series(dtype=str))
        .eq("UNEXPLAINED_EXECUTION_DIFFERENCE")
        .any()
    )
    integrity = not unexplained
    tracking = (
        native.average_execution_date_total_absolute_weight_deviation <= 0.03
        and native.materially_off_target_execution_dates <= 0.10 * len(schedule)
    )
    cash = native.cash_rejection_events == 0 and native.average_cash_ratio <= 0.02
    economics = (
        native.cagr > 0
        and native.cagr >= native.vectorbt_cagr - 0.02
        and native.max_drawdown >= native.vectorbt_max_drawdown - 0.05
    )
    return (
        "ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW"
        if integrity and tracking and cash and economics
        else "DO_NOT_ADVANCE_S27A_EXECUTION"
    )


def main() -> None:
    import rqalpha

    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    schedule, diagnostics = build_frozen_schedule(prices)
    serialized = schedule.reset_index().to_csv(
        index=False, float_format="%.17g", lineterminator="\n"
    )
    output = ROOT / "research/results"
    schedule_path = output / "s27a_v1_frozen_targets.csv"
    schedule_path.write_text(serialized)
    vectorbt, start = vectorbt_reproduction(prices, schedule)
    expected = pd.read_csv(ROOT / "research/results/s27a_trend_inverse_vol_comparison_v1.csv")
    baseline = expected.loc[expected.series.eq("S27A_TREND_INVERSE_VOL_V1")].iloc[0]
    if not all(
        abs(float(vectorbt.metrics[key]) - float(baseline[key])) < 1e-12
        for key in ("cagr", "max_drawdown", "sharpe")
    ):
        print("decision=BLOCK_S27A_EXECUTION_REPRODUCTION")
        return
    mapping = build_symbol_mapping(ROOT / "config/universe.csv", list(schedule.columns))
    frozen = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    analyser, events, replayed = run_rqalpha_frozen_targets(
        schedule,
        mapping,
        frozen,
        str(start.date()),
        str(prices.index[-1].date()),
        BUNDLE,
        partial_fill_on_insufficient_cash=True,
    )
    reverse = {value: key for key, value in mapping.items()}
    actual = actual_weight_table(analyser, reverse, list(schedule.columns))
    monthly = diagnostics.index
    tracking = target_tracking_table(schedule, monthly, actual)
    differences = material_difference_table(schedule, actual, analyser, events, reverse)
    native = parse_native_results(analyser, events).iloc[0].copy()
    execution_rows = tracking.loc[tracking.observation_type.str.contains("execution")]
    native["rqalpha_version"] = rqalpha.__version__
    native["vectorbt_cagr"] = vectorbt.metrics["cagr"]
    native["vectorbt_max_drawdown"] = vectorbt.metrics["max_drawdown"]
    native["vectorbt_sharpe"] = vectorbt.metrics["sharpe"]
    native["frozen_target_count"] = len(schedule)
    native["frozen_target_sha256"] = hashlib.sha256(serialized.encode()).hexdigest()
    native["average_execution_date_total_absolute_weight_deviation"] = (
        execution_rows.total_absolute_weight_deviation.mean()
    )
    native["materially_off_target_execution_dates"] = int(
        execution_rows.materially_off_target.sum()
    )
    native["material_deviation_threshold"] = MATERIAL_DEVIATION
    outcome = decision(native, replayed, schedule, differences)
    effort = user_effort_table(schedule, monthly, analyser, events, tracking)
    pd.DataFrame([native]).to_csv(output / "s27a_rqalpha_execution_summary_v1.csv", index=False)
    tracking.to_csv(output / "s27a_rqalpha_target_tracking_v1.csv", index=False)
    differences.to_csv(output / "s27a_rqalpha_material_differences_v1.csv", index=False)
    effort.to_csv(output / "s27a_rqalpha_user_effort_v1.csv", index=False)
    print(f"decision={outcome}\n{pd.DataFrame([native]).to_csv(index=False)}")


if __name__ == "__main__":
    main()
