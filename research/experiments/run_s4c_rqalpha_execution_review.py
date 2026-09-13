#!/usr/bin/env python3
# ruff: noqa: E501
"""S4C authoritative execution review: replay frozen ERC targets through RQAlpha only."""

from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
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
from research.experiments.run_s4c_erc_skfolio_transfer import S4CConfig, build_targets
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs
from tacticore.strategies.multi_asset_trend import build_execution_weights, load_trend_config

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = Path.home() / ".rqalpha/bundle"
RETURNS_WINDOW = 60
PRICE_WINDOW = RETURNS_WINDOW + 1
FROZEN_TARGETS = ROOT / "research/results/s4c_pit_corrected_frozen_targets_v1.csv"
BASELINE = ROOT / "research/results/s4c_pit_corrected_comparison_v1.csv"
REPRODUCED_METRICS = ("cagr", "max_drawdown", "sharpe", "calmar", "turnover")
UNEXPLAINED = ("", "UNKNOWN", "UNEXPLAINED_EXECUTION_DIFFERENCE")
ADVANCE = "ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW"
DO_NOT_ADVANCE = "DO_NOT_ADVANCE_S4C_EXECUTION"
BLOCK_REPRODUCTION = "BLOCK_S4C_EXECUTION_REPRODUCTION"
BLOCK_ENVIRONMENT = "BLOCK_S4C_EXECUTION_ENVIRONMENT"


def load_review_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict, S4CConfig, tuple[str, ...]]:
    strategy = load_trend_config(ROOT / "config/strategy.toml")
    config = S4CConfig(
        strategy.fallback_symbol, strategy.fees, strategy.slippage, strategy.initial_cash
    )
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))
    return prices, mask, lifetimes, config, tuple(strategy.risk_symbols)


def build_frozen_schedule(
    prices: pd.DataFrame,
    risk_symbols: tuple[str, ...],
    mask: pd.DataFrame,
    lifetimes: dict,
    config: S4CConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Rebuild the frozen 60-return ERC target schedule from already-frozen semantics."""
    targets, _equal, _inverse, diagnostics = build_targets(
        prices, risk_symbols, config, price_window=PRICE_WINDOW
    )
    schedule, start = freeze_pit_legal_schedule(
        prices, build_execution_weights(prices, targets), mask, lifetimes
    )
    return schedule, diagnostics, start


def load_committed_schedule(path: Path = FROZEN_TARGETS) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"缺少冻结目标文件: {path}")
    frame = pd.read_csv(path, parse_dates=["execution_date"])
    frame = frame.set_index("execution_date")
    frame.index.name = "execution_date"
    return frame


def assert_committed_matches(serialized: str, path: Path = FROZEN_TARGETS) -> str:
    """Fail closed when the committed target artifact differs from frozen semantics."""
    if not path.is_file():
        raise FileNotFoundError(f"缺少冻结目标文件: {path}")
    committed = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if committed != serialized:
        raise ValueError("冻结目标文件与当前冻结语义不一致")
    return sha256(committed.encode()).hexdigest()


def reproduces(metrics: dict[str, float], expected: pd.Series) -> bool:
    return all(
        abs(float(metrics[key]) - float(expected[key])) < 1e-12 for key in REPRODUCED_METRICS
    )


def execution_decision(
    native: pd.Series,
    replayed: list[pd.Timestamp],
    schedule: pd.DataFrame,
    differences: pd.DataFrame,
) -> str:
    """Apply the preregistered S4C execution gates mechanically."""
    if replayed != list(schedule.index):
        return BLOCK_REPRODUCTION
    explained = not (
        differences.get("native_evidence", pd.Series(dtype=str)).isin(UNEXPLAINED).any()
    )
    tracking = (
        bool(native.all_frozen_dates_processed)
        and int(native.extra_replayed_dates) == 0
        and native.average_execution_date_total_absolute_weight_deviation <= 0.03
        and native.materially_off_target_execution_dates <= 0.10 * len(schedule)
    )
    cash = native.cash_rejection_events == 0 and native.average_cash_ratio <= 0.02
    economics = (
        native.cagr > 0
        and native.cagr >= native.vectorbt_cagr - 0.02
        and native.max_drawdown >= native.vectorbt_max_drawdown - 0.05
    )
    return ADVANCE if explained and tracking and cash and economics else DO_NOT_ADVANCE


def run_native_replay(
    prices: pd.DataFrame,
    schedule: pd.DataFrame,
    config: S4CConfig,
    start: pd.Timestamp,
    bundle: Path,
):
    if not bundle.is_dir():
        raise FileNotFoundError(f"RQAlpha bundle 目录不存在: {bundle}")
    mapping = build_symbol_mapping(ROOT / "config/universe.csv", list(schedule.columns))
    signal_index = prices.index.get_loc(schedule.index[0]) - 1
    analyser, events, replayed = run_rqalpha_frozen_targets(
        schedule,
        mapping,
        config,
        str(prices.index[signal_index].date()),
        str(prices.index[-1].date()),
        bundle,
        partial_fill_on_insufficient_cash=True,
    )
    reverse = {value: key for key, value in mapping.items()}
    actual = actual_weight_table(analyser, reverse, list(schedule.columns))
    tracking = target_tracking_table(schedule, schedule.index, actual)
    execution_rows = tracking.loc[tracking.observation_type.str.contains("execution")]
    differences = material_difference_table(schedule, actual, analyser, events, reverse)
    native = parse_native_results(analyser, events).iloc[0].copy()
    native["all_frozen_dates_processed"] = replayed == list(schedule.index)
    native["extra_replayed_dates"] = len(set(replayed).difference(schedule.index))
    native["average_execution_date_total_absolute_weight_deviation"] = float(
        execution_rows.total_absolute_weight_deviation.mean()
    )
    native["maximum_execution_date_total_absolute_weight_deviation"] = float(
        execution_rows.total_absolute_weight_deviation.max()
    )
    native["materially_off_target_execution_dates"] = int(
        execution_rows.materially_off_target.sum()
    )
    effort = user_effort_table(schedule, schedule.index, analyser, events, tracking)
    return native, tracking, differences, effort, replayed


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-targets", action="store_true")
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/results")
    args = parser.parse_args()

    prices, mask, lifetimes, config, risk_symbols = load_review_inputs()
    schedule, _diagnostics, start = build_frozen_schedule(
        prices, risk_symbols, mask, lifetimes, config
    )
    target_sha256, serialized = schedule_sha256(schedule)
    print(
        f"frozen_targets={len(schedule)} first={schedule.index[0].date()} "
        f"last={schedule.index[-1].date()} sha256={target_sha256}"
    )
    if args.freeze_targets:
        FROZEN_TARGETS.write_text(serialized, encoding="utf-8", newline="")
        print(f"wrote={FROZEN_TARGETS}")
        return

    committed_sha256 = assert_committed_matches(serialized)
    result = replay_vectorbt(
        prices,
        schedule,
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )
    expected = pd.read_csv(BASELINE).iloc[0]
    reproduction = pd.DataFrame(
        [
            {
                **result.metrics,
                "schedule_sha256": committed_sha256,
                "reproduced": reproduces(result.metrics, expected),
            }
        ]
    )
    reproduction.to_csv(
        args.output_dir / "s4c_rqalpha_execution_vectorbt_reproduction_v1.csv", index=False
    )
    if not bool(reproduction.reproduced.iloc[0]):
        print(f"decision={BLOCK_REPRODUCTION}")
        print(reproduction.to_csv(index=False))
        return

    import rqalpha

    try:
        native, tracking, differences, effort, replayed = run_native_replay(
            prices, schedule, config, start, args.bundle
        )
    except FileNotFoundError as error:
        print(f"decision={BLOCK_ENVIRONMENT}\nreason={error}")
        return
    native["rqalpha_version"] = rqalpha.__version__
    native["frozen_target_count"] = len(schedule)
    native["frozen_target_sha256"] = committed_sha256
    native["vectorbt_cagr"] = result.metrics["cagr"]
    native["vectorbt_max_drawdown"] = result.metrics["max_drawdown"]
    native["vectorbt_sharpe"] = result.metrics["sharpe"]
    native["vectorbt_calmar"] = result.metrics["calmar"]
    native["vectorbt_turnover"] = result.metrics["turnover"]
    outcome = execution_decision(native, replayed, schedule, differences)
    summary = pd.DataFrame([native])
    for name, frame in (
        ("s4c_rqalpha_execution_summary_v1.csv", summary),
        ("s4c_rqalpha_execution_target_tracking_v1.csv", tracking),
        ("s4c_rqalpha_execution_material_differences_v1.csv", differences),
        ("s4c_rqalpha_execution_user_effort_v1.csv", effort),
    ):
        frame.to_csv(args.output_dir / name, index=False)
    print(f"decision={outcome}\n{summary.to_csv(index=False)}")


if __name__ == "__main__":
    main()
