#!/usr/bin/env python3
"""只读校验冻结的 S4C_R1 候选身份、前瞻边界与 append-only 记录契约。

本模块**不**重算历史绩效、**不**生成前瞻记录、**不**激活前瞻影子。
"""

from __future__ import annotations

import csv
import hashlib
import json
from argparse import ArgumentParser
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd

from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs, validate_execution_targets
from tacticore.strategies.multi_asset_trend import load_trend_config

ROOT = Path(__file__).resolve().parents[2]
SHADOW_DIR = ROOT / "research/shadow/s4c_r1"
MANIFEST_PATH = SHADOW_DIR / "candidate_manifest.json"
OBSERVATIONS_PATH = SHADOW_DIR / "observations.csv"
FROZEN_TARGETS_PATH = ROOT / "research/results/s4c_pit_corrected_frozen_targets_v1.csv"
PROTOCOL_VERSION = "V1"
CANDIDATE_ID = "S4C_R1"
FROZEN_TARGET_SHA256 = "f7bf398d7f8a016933cbe287bfa1cac98b3cccf175d40ef99092b95db1227e47"
FROZEN_TARGET_ROWS = 161
FROZEN_FIRST_DATE = pd.Timestamp("2013-04-01")
FROZEN_LAST_DATE = pd.Timestamp("2026-08-03")
MINIMUM_ELIGIBLE_ASSETS = 6
RETURNS_WINDOW = 60

# 逐字冻结的经济语义：manifest 自身不得偏离这些字面值。
FROZEN_STRATEGY_CONTRACT: tuple[tuple[str, object], ...] = (
    ("canonical_strategy", "equal risk contribution / risk budgeting"),
    ("upstream_implementation", "skfolio.optimization.RiskBudgeting"),
    ("upstream_version", "1.0.6"),
    ("risk_measure", "RiskMeasure.VARIANCE"),
    ("risk_budgets", "equal (library default risk budget)"),
    ("min_weights", 0.0),
    ("max_weights", 1.0),
    ("long_only", True),
    ("fully_invested", True),
    ("leverage", "none"),
    ("minimum_eligible_assets", MINIMUM_ELIGIBLE_ASSETS),
    ("price_window", 61),
    ("returns_window", RETURNS_WINDOW),
    (
        "returns_definition",
        "aligned_window 上 pct_change(fill_method=None).dropna(how='any')，60 条有效对齐日收益",
    ),
    ("signal_timing", "月末 canonical 观测日收盘后估计"),
    ("execution_timing", "不得早于信号日后的下一 canonical 观测日"),
    ("target_submission_policy", "MONTHLY_TARGET_SUBMISSION"),
    ("strategy_inception", "2013-04-01"),
)

# 逐字冻结的权威执行语义：不得由 manifest 单方面改写。
FROZEN_EXECUTION_CONTRACT: tuple[tuple[str, object], ...] = (
    ("authority", "RQAlpha 6.3.x native execution"),
    ("order_api", "order_target_portfolio"),
    ("partial_fill_on_insufficient_cash", True),
    ("matching_type", "current_bar"),
    ("volume_limit", True),
    ("volume_percent", 0.25),
    ("replay_input", "committed frozen target schedule only"),
    ("recomputation_inside_replay", "none"),
)

RECORD_FIELDS = (
    "record_type",
    "candidate_id",
    "protocol_version",
    "record_generated_at",
    "data_as_of",
    "vintage_identifier",
    "historical_manifest_hash",
    "prospective_data_hash",
    "signal_date",
    "eligible_asset_count",
    "regime",
    "maximum_weight",
    "effective_number_assets",
    "target_changed",
    "desired_targets",
    "action_required",
    "execution_date",
    "execution_status",
    "realized_weights",
    "cash_weight",
    "portfolio_total_absolute_weight_deviation",
    "material_portfolio_tracking_date",
    "material_asset_differences",
    "turnover",
    "execution_evidence",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_frozen_repository_text(path: Path) -> str:
    """Hash frozen repository text consistently across LF and CRLF checkouts."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_committed_schedule(path: Path = FROZEN_TARGETS_PATH) -> pd.DataFrame:
    schedule = pd.read_csv(path, index_col="execution_date", parse_dates=["execution_date"])
    schedule.index.name = "execution_date"
    return schedule


def observation_row_count(path: Path = OBSERVATIONS_PATH) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError("observations.csv 缺少协议表头")
    if tuple(rows[0]) != RECORD_FIELDS:
        raise ValueError("observations.csv schema 与冻结协议不一致")
    return len(rows) - 1


def verify_framework_versions(manifest: dict[str, Any]) -> None:
    for package, expected_version in manifest["framework_versions"].items():
        if version(package) != expected_version:
            raise ValueError(f"candidate manifest 与当前框架版本不一致: {package}")


def verify_prospective_boundary(manifest: dict[str, Any]) -> None:
    cutoff = pd.Timestamp(manifest["historical_cutoff"])
    freeze_moment = pd.Timestamp(manifest["freeze_timestamp"])
    if freeze_moment.tzinfo is not None:
        freeze_moment = freeze_moment.tz_convert("UTC").tz_localize(None)
    first_signal = pd.Timestamp(manifest["first_eligible_prospective_signal"])
    if first_signal <= cutoff:
        raise ValueError("first_eligible_prospective_signal 必须晚于 historical_cutoff")
    if first_signal <= freeze_moment.normalize():
        raise ValueError("前瞻 signal 必须严格晚于候选冻结日：禁止回溯前瞻证据")
    if first_signal != first_signal + pd.offsets.MonthEnd(0):
        raise ValueError("first_eligible_prospective_signal 必须是自然月末")


def verify_strategy_semantics(manifest: dict[str, Any], root: Path = ROOT) -> None:
    semantics = manifest["strategy_semantics"]
    config = load_trend_config(root / "config/strategy.toml")
    expected = {
        "fallback_symbol": config.fallback_symbol,
        "risk_symbols": list(config.risk_symbols),
        "fees": config.fees,
        "slippage": config.slippage,
        "initial_cash": config.initial_cash,
    }
    for field, actual in expected.items():
        if semantics[field] != actual:
            raise ValueError(f"candidate manifest 与当前冻结策略不一致: {field}")
    for field, frozen_value in FROZEN_STRATEGY_CONTRACT:
        if semantics.get(field) != frozen_value:
            raise ValueError(f"S4C 冻结经济语义被改写: {field}")


def verify_execution_semantics(manifest: dict[str, Any]) -> None:
    execution = manifest["execution_semantics"]
    for field, frozen_value in FROZEN_EXECUTION_CONTRACT:
        if execution.get(field) != frozen_value:
            raise ValueError(f"S4C 冻结执行语义被改写: {field}")


def verify_frozen_targets(
    manifest: dict[str, Any],
    root: Path = ROOT,
    target_path: Path = FROZEN_TARGETS_PATH,
) -> str:
    actual_hash = sha256_frozen_repository_text(target_path)
    if actual_hash != FROZEN_TARGET_SHA256:
        raise ValueError(f"冻结目标 SHA-256 与 RL-040 / Protocol V2 不一致: {actual_hash}")
    schedule = load_committed_schedule(target_path)
    if len(schedule) != FROZEN_TARGET_ROWS:
        raise ValueError("冻结目标行数与记录不符")
    if schedule.index[0] != FROZEN_FIRST_DATE or schedule.index[-1] != FROZEN_LAST_DATE:
        raise ValueError("冻结目标首末执行日与记录不符")
    if schedule.index.has_duplicates or not schedule.index.is_monotonic_increasing:
        raise ValueError("冻结目标日期必须唯一且严格递增")
    if not schedule.ge(0).all().all():
        raise ValueError("冻结目标权重不得为负")
    if not schedule.sum(axis=1).round(12).eq(1.0).all():
        raise ValueError("冻结目标每行权重合计必须为一")
    prices = load_price_csv(root / "data/canonical/etf_adjusted_close.csv")
    mask, lifetimes = load_tradability_inputs(prices, str(root / "config/universe.csv"))
    validate_execution_targets(schedule, prices, mask, lifetimes)
    return actual_hash


def verify_candidate(
    manifest: dict[str, Any],
    root: Path = ROOT,
    *,
    verify_framework: bool = True,
) -> None:
    if manifest["candidate_id"] != CANDIDATE_ID or manifest["candidate_version"] != "R1":
        raise ValueError("candidate manifest 不是冻结的 S4C_R1")
    if manifest["prospective_activation"] != "NOT_ACTIVE":
        raise ValueError("本 Goal 不授权激活 S4C R1 前瞻影子")
    verify_prospective_boundary(manifest)
    verify_strategy_semantics(manifest, root)
    verify_execution_semantics(manifest)
    if verify_framework:
        verify_framework_versions(manifest)
    for relative_path, expected_hash in manifest["frozen_identity_artifacts"].items():
        actual_hash = sha256_frozen_repository_text(root / relative_path)
        if actual_hash != expected_hash:
            raise ValueError(f"冻结身份 hash 不一致: {relative_path}")
    provenance = json.loads((root / "data/canonical/provenance.json").read_text(encoding="utf-8"))
    if provenance["end_date"] != pd.Timestamp(manifest["historical_cutoff"]).strftime("%Y%m%d"):
        raise ValueError("canonical provenance 的截止日与 candidate manifest 不一致")
    verify_frozen_targets(manifest, root)


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--verify-candidate", action="store_true")
    args = parser.parse_args()
    if not args.verify_candidate:
        parser.error("本 Goal 只提供 --verify-candidate；前瞻决策协议尚未激活")
    manifest = load_manifest()
    verify_candidate(manifest)
    rows = observation_row_count()
    if rows != 0:
        raise ValueError("S4C R1 尚未激活前瞻影子，observations.csv 不得含任何记录")
    print(
        "S4C_R1 candidate manifest、冻结历史输入、PIT 契约与 append-only 契约校验通过；"
        f"当前前瞻 observation 行数为 {rows}；prospective_activation="
        f"{manifest['prospective_activation']}。"
    )


if __name__ == "__main__":
    main()
