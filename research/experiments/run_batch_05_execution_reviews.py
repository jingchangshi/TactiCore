#!/usr/bin/env python3
"""Batch 05: replay PIT-corrected S27A/S10A frozen targets in RQAlpha only."""
# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.experiments.frozen_target_replay import (
    freeze_pit_legal_schedule,
    replay_vectorbt,
    schedule_sha256,
)
from research.experiments.run_s2_rqalpha_validation import (
    actual_weight_table,
    build_symbol_mapping,
    material_difference_table,
    parse_native_results,
    run_rqalpha_frozen_targets,
    target_tracking_table,
    user_effort_table,
)
from research.experiments.run_s10a_robustness import RobustnessSpec
from research.experiments.run_s10a_robustness import build_targets as s10_targets
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs
from tacticore.strategies.multi_asset_trend import build_execution_weights, load_trend_config
from tacticore.strategies.trend_inverse_vol import (
    build_month_end_targets as s27_targets,
)
from tacticore.strategies.trend_inverse_vol import (
    load_trend_inverse_vol_config,
)
from tacticore.strategies.volatility_targeting import load_volatility_targeting_config

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = Path.home() / ".rqalpha/bundle"
METRICS = ("cagr", "max_drawdown", "sharpe", "calmar", "turnover")


def _batch4_row(filename: str) -> pd.Series:
    return pd.read_csv(ROOT / "research/results" / filename).iloc[0]


def _reproduces(result_metrics: dict[str, float], expected: pd.Series) -> bool:
    return all(abs(float(result_metrics[key]) - float(expected[key])) < 1e-12 for key in METRICS)


def _execution_decision(
    native: pd.Series,
    replayed: list[pd.Timestamp],
    schedule: pd.DataFrame,
    differences: pd.DataFrame,
    label: str,
) -> str:
    if replayed != list(schedule.index):
        return f"BLOCK_{label}_EXECUTION_REPRODUCTION"
    explained = (
        not differences.get("native_evidence", pd.Series(dtype=str))
        .isin(["", "UNKNOWN", "UNEXPLAINED_EXECUTION_DIFFERENCE"])
        .any()
    )
    tracking = (
        native.average_execution_date_total_absolute_weight_deviation <= 0.03
        and native.materially_off_target_execution_dates <= 0.10 * len(schedule)
    )
    economics = (
        native.cash_rejection_events == 0
        and native.average_cash_ratio <= 0.02
        and native.cagr > 0
        and native.cagr >= native.vectorbt_cagr - 0.02
        and native.max_drawdown >= native.vectorbt_max_drawdown - 0.05
    )
    if not (explained and tracking and economics):
        return f"DO_NOT_ADVANCE_{label}_EXECUTION"
    return f"ADVANCE_{label}_TO_CANDIDATE_FREEZE_REVIEW"


def _run_review(
    label: str,
    prices: pd.DataFrame,
    schedule: pd.DataFrame,
    frozen_config: object,
    mapping: dict[str, str],
    expected: pd.Series,
    monthly_reviews: pd.DatetimeIndex,
    tradability_mask: pd.DataFrame,
    lifetimes: dict,
    bundle: Path,
) -> tuple[str, dict[str, pd.DataFrame]]:
    result = replay_vectorbt(
        prices,
        schedule,
        fees=float(frozen_config.fees),
        slippage=float(frozen_config.slippage),
        initial_cash=float(frozen_config.initial_cash),
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )
    sha256, serialized = schedule_sha256(schedule)
    frozen = schedule.reset_index()
    if not _reproduces(result.metrics, expected):
        return f"BLOCK_{label}_EXECUTION_REPRODUCTION", {
            "frozen_targets": frozen,
            "vectorbt_reproduction": pd.DataFrame([{**result.metrics, "schedule_sha256": sha256}]),
        }
    analyser, events, replayed = run_rqalpha_frozen_targets(
        schedule,
        mapping,
        frozen_config,  # only account parameters are consumed by the approved replay helper
        str(prices.index[prices.index.get_loc(schedule.index[0]) - 1].date()),
        str(prices.index[-1].date()),
        bundle,
        partial_fill_on_insufficient_cash=True,
    )
    reverse = {value: key for key, value in mapping.items()}
    actual = actual_weight_table(analyser, reverse, list(schedule.columns))
    tracking = target_tracking_table(schedule, monthly_reviews, actual)
    differences = material_difference_table(schedule, actual, analyser, events, reverse)
    native = parse_native_results(analyser, events).iloc[0].copy()
    execution = tracking.loc[tracking.observation_type.str.contains("execution")]
    native["frozen_target_count"] = len(schedule)
    native["frozen_target_sha256"] = sha256
    native["all_frozen_dates_processed"] = replayed == list(schedule.index)
    native["extra_replayed_dates"] = len(set(replayed).difference(schedule.index))
    native["average_execution_date_total_absolute_weight_deviation"] = float(
        execution.total_absolute_weight_deviation.mean()
    )
    native["maximum_execution_date_total_absolute_weight_deviation"] = float(
        execution.total_absolute_weight_deviation.max()
    )
    native["materially_off_target_execution_dates"] = int(execution.materially_off_target.sum())
    native["vectorbt_cagr"] = result.metrics["cagr"]
    native["vectorbt_max_drawdown"] = result.metrics["max_drawdown"]
    native["vectorbt_sharpe"] = result.metrics["sharpe"]
    native["vectorbt_calmar"] = result.metrics["calmar"]
    native["vectorbt_turnover"] = result.metrics["turnover"]
    outcome = _execution_decision(native, replayed, schedule, differences, label)
    return outcome, {
        "frozen_targets": frozen,
        "vectorbt_reproduction": pd.DataFrame([{**result.metrics, "schedule_sha256": sha256}]),
        "summary": pd.DataFrame([native]),
        "target_tracking": tracking,
        "material_differences": differences,
        "user_effort": user_effort_table(schedule, monthly_reviews, analyser, events, tracking),
        "serialized": pd.DataFrame({"sha256": [sha256], "bytes": [len(serialized)]}),
    }


def main() -> None:
    import rqalpha

    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))
    trend = load_trend_config(ROOT / "config/strategy.toml")
    s27 = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    s27_execution = build_execution_weights(prices, s27_targets(prices, s27, trend.risk_symbols)[0])
    s27_schedule, _ = freeze_pit_legal_schedule(prices, s27_execution, mask, lifetimes)
    s27_outcome, s27_outputs = _run_review(
        "S27A",
        prices,
        s27_schedule,
        s27,
        build_symbol_mapping(ROOT / "config/universe.csv", list(s27_schedule.columns)),
        _batch4_row("s27a_pit_corrected_summary_v1.csv"),
        prices.groupby(prices.index.to_period("M")).tail(1).index,
        mask,
        lifetimes,
        BUNDLE,
    )
    s10 = load_volatility_targeting_config(ROOT / "config/s10a_vol_targeting.toml")
    s10_spec = RobustnessSpec(
        s10.symbols,
        s10.base_weights,
        s10.vol_window,
        s10.target_volatility,
        s10.max_scale,
        s10.min_scale,
        s10.fees,
        s10.slippage,
        s10.initial_cash,
    )
    s10_monthly, s10_diagnostics = s10_targets(prices, s10_spec)
    s10_execution = build_execution_weights(prices, s10_monthly)
    s10_schedule, _ = freeze_pit_legal_schedule(prices, s10_execution, mask, lifetimes)
    s10_outcome, s10_outputs = _run_review(
        "S10A",
        prices,
        s10_schedule,
        s10_spec,
        build_symbol_mapping(ROOT / "config/universe.csv", list(s10_schedule.columns)),
        _batch4_row("s10a_corrected_robustness_summary_v1.csv"),
        s10_diagnostics.index,
        mask,
        lifetimes,
        BUNDLE,
    )
    if "summary" in s10_outputs:
        frozen_diagnostics = s10_diagnostics.loc[s10_schedule.index]
        s10_outputs["summary"]["months_scale_lt_1"] = int(frozen_diagnostics.scale.lt(1).sum())
        s10_outputs["summary"]["average_frozen_scale"] = float(frozen_diagnostics.scale.mean())
        s10_outputs["summary"]["average_implemented_risky_exposure"] = float(
            s10_schedule.loc[:, list(s10.symbols[:-1])].sum(axis=1).mean()
        )
        s10_outputs["summary"]["average_implemented_bond_exposure"] = float(
            s10_schedule[s10.symbols[-1]].mean()
        )
    output = ROOT / "research/results"
    for prefix, outputs in (("s27a", s27_outputs), ("s10a", s10_outputs)):
        for name, frame in outputs.items():
            if name != "serialized":
                frame.to_csv(output / f"{prefix}_pit_corrected_{name}_v1.csv", index=False)
    print(f"rqalpha={rqalpha.__version__} s27={s27_outcome} s10={s10_outcome}")


if __name__ == "__main__":
    main()
