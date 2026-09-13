#!/usr/bin/env python3
"""用冻结的 S4C R1 身份生成一条可审计的月末前瞻影子决策。

本模块是**最小 candidate-specific runner**：它只服务 `S4C_R1`，不实现调度器、daemon、
通知、券商或通用候选框架。前瞻决策必须显式提供 `--as-of`，禁止 wall-clock 默认值。
"""

from __future__ import annotations

import csv
import hashlib
import json
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research.experiments.run_s4c_erc_skfolio_transfer import (
    MIN_ELIGIBLE,
    WINDOW,
    SolverFailure,
    aligned_window,
    erc_weights,
)
from research.experiments.verify_s4c_r1_candidate import (
    FROZEN_TARGETS_PATH,
    OBSERVATIONS_PATH,
    RECORD_FIELDS,
    ROOT,
    load_committed_schedule,
    load_manifest,
    sha256_frozen_repository_text,
)
from research.experiments.verify_s4c_r1_candidate import (
    verify_candidate as verify_frozen_candidate,
)
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs, validate_execution_targets

SHADOW_DIR = ROOT / "research/shadow/s4c_r1"
MANIFEST_PATH = SHADOW_DIR / "candidate_manifest.json"
ACTIVATION_PATH = SHADOW_DIR / "activation.json"
VINTAGE_FILES = ("etf_adjusted_close.csv", "trading_calendar.csv", "provenance.json")

MANIFEST_RELATIVE_PATH = "research/shadow/s4c_r1/candidate_manifest.json"
ACTIVATION_RELATIVE_PATH = "research/shadow/s4c_r1/activation.json"
VINTAGE_PARENT_RELATIVE_PATH = "research/shadow/s4c_r1/vintages"
ACTIVATION_PROTOCOL_RELATIVE_PATH = "research/batches/s4c_activation/PROTOCOL.md"
ACTIVATION_DECISION_RECORD_RELATIVE_PATH = (
    "research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md"
)

PROTOCOL_VERSION = "V1"
ACTIVATION_PROTOCOL_VERSION = "V1"
OBSERVATION_SCHEMA_VERSION = "S4C_R1_OBSERVATIONS_V1"
PENDING_EXECUTION_STATUS = "PENDING_NEXT_CANONICAL_OBSERVATION"
ACTIVE_STATUS = "ACTIVE"
ACTIVATION_DECISION_TOKEN = "ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW"
DECISION_RECORD_POLICY = "APPEND_ONLY_ONE_DECISION_PER_SIGNAL_DATE_BEFORE_EXECUTION"
EXECUTION_RECORD_POLICY = "APPEND_ONLY_ONE_EXECUTION_PER_DECISION_AFTER_SIGNAL_DATE"

ACTIVATION_FIELDS = (
    "candidate_id",
    "candidate_version",
    "activation_status",
    "activation_decision_token",
    "activation_decision_timestamp",
    "activation_protocol_version",
    "activation_protocol_path",
    "activation_protocol_sha256",
    "activation_decision_record",
    "activation_decision_record_sha256",
    "candidate_manifest_sha256",
    "candidate_freeze_timestamp",
    "historical_cutoff",
    "first_eligible_prospective_signal",
    "observation_schema_version",
    "decision_record_policy",
    "execution_record_policy",
)

# decision 行不得携带任何执行结果；这些列只能由后续 execution 行填充。
EXECUTION_ONLY_FIELDS = (
    "execution_date",
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


def _now_utc_iso() -> str:
    """record 生成时间；只用于记录真实写入时刻，绝不用来推断 research as-of。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------------------
# Candidate / activation integrity
# --------------------------------------------------------------------------------------


def manifest_hash(path: Path = MANIFEST_PATH) -> str:
    return sha256_frozen_repository_text(path)


def load_activation(path: Path = ACTIVATION_PATH) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def verify_activation(
    activation: dict[str, Any],
    manifest: dict[str, Any],
    *,
    manifest_sha256: str | None = None,
    root: Path = ROOT,
) -> None:
    """activation lifecycle artifact 必须与不可变 candidate identity 逐项一致。"""
    missing = [field for field in ACTIVATION_FIELDS if field not in activation]
    if missing:
        raise ValueError(f"activation artifact 缺少字段: {missing}")
    unexpected = [field for field in activation if field not in ACTIVATION_FIELDS]
    if unexpected:
        raise ValueError("activation artifact 字段集合与冻结 schema 不一致")
    if activation["candidate_id"] != manifest["candidate_id"]:
        raise ValueError("activation artifact 的 candidate_id 与 manifest 不一致")
    if activation["candidate_version"] != manifest["candidate_version"]:
        raise ValueError("activation artifact 的 candidate_version 与 manifest 不一致")
    if activation["activation_status"] != ACTIVE_STATUS:
        raise ValueError("activation artifact 的 activation_status 不是 ACTIVE")
    if activation["activation_decision_token"] != ACTIVATION_DECISION_TOKEN:
        raise ValueError("activation artifact 的 activation_decision_token 不是冻结裁决")
    if activation["activation_protocol_version"] != ACTIVATION_PROTOCOL_VERSION:
        raise ValueError("activation artifact 的 protocol version 不是冻结版本")
    if activation["activation_protocol_path"] != ACTIVATION_PROTOCOL_RELATIVE_PATH:
        raise ValueError("activation artifact 的 protocol path 不是冻结协议")
    if activation["decision_record_policy"] != DECISION_RECORD_POLICY:
        raise ValueError("activation artifact 的 decision_record_policy 被改写")
    if activation["execution_record_policy"] != EXECUTION_RECORD_POLICY:
        raise ValueError("activation artifact 的 execution_record_policy 被改写")
    if activation["observation_schema_version"] != OBSERVATION_SCHEMA_VERSION:
        raise ValueError("activation artifact 的 observation schema version 不一致")
    if activation["historical_cutoff"] != manifest["historical_cutoff"]:
        raise ValueError("activation artifact 的 historical_cutoff 与 manifest 不一致")
    if activation["candidate_freeze_timestamp"] != manifest["freeze_timestamp"]:
        raise ValueError("activation artifact 的 candidate freeze timestamp 与 manifest 不一致")
    if (
        activation["first_eligible_prospective_signal"]
        != manifest["first_eligible_prospective_signal"]
    ):
        raise ValueError(
            "activation artifact 的 first_eligible_prospective_signal 与 manifest 不一致"
        )
    expected_manifest_hash = manifest_sha256 or sha256_frozen_repository_text(
        root / MANIFEST_RELATIVE_PATH
    )
    if activation["candidate_manifest_sha256"] != expected_manifest_hash:
        raise ValueError("activation artifact 的 candidate manifest hash 不一致")
    verify_activation_timestamp(activation, manifest)
    verify_activation_evidence(activation, root)


def verify_activation_timestamp(activation: dict[str, Any], manifest: dict[str, Any]) -> None:
    """activation 决策时间必须带时区，且严格晚于候选冻结时刻。"""
    raw = activation["activation_decision_timestamp"]
    try:
        timestamp = pd.Timestamp(raw)
    except (TypeError, ValueError) as error:
        raise ValueError("activation 决策时间不可解析") from error
    if timestamp.tzinfo is None:
        raise ValueError("activation 决策时间必须带时区，不得使用 naive timestamp")
    freeze = pd.Timestamp(manifest["freeze_timestamp"])
    if freeze.tzinfo is None:
        freeze = freeze.tz_localize("UTC")
    if timestamp <= freeze:
        raise ValueError("activation 决策时间必须严格晚于 candidate freeze timestamp")


def verify_activation_evidence(activation: dict[str, Any], root: Path = ROOT) -> None:
    """activation artifact 必须绑定 reviewed protocol 与 activation decision record。"""
    protocol_path = root / activation["activation_protocol_path"]
    if not protocol_path.is_file():
        raise ValueError("activation artifact 引用的预注册协议不存在")
    if sha256_frozen_repository_text(protocol_path) != activation["activation_protocol_sha256"]:
        raise ValueError("activation artifact 的预注册协议 hash 不一致")
    if activation["activation_decision_record"] != ACTIVATION_DECISION_RECORD_RELATIVE_PATH:
        raise ValueError("activation artifact 的 decision record path 不是冻结路径")
    record_path = root / ACTIVATION_DECISION_RECORD_RELATIVE_PATH
    if not record_path.is_file():
        raise ValueError("activation artifact 引用的 activation decision record 不存在")
    if (
        sha256_frozen_repository_text(record_path)
        != activation["activation_decision_record_sha256"]
    ):
        raise ValueError("activation artifact 的 decision record hash 不一致")
    if ACTIVATION_DECISION_TOKEN not in record_path.read_text(encoding="utf-8"):
        raise ValueError("activation decision record 未包含冻结裁决 token")


def verify_candidate_shadow(
    manifest: dict[str, Any],
    root: Path = ROOT,
    *,
    verify_framework: bool = True,
) -> None:
    """复用冻结 verifier，并追加一次“冻结语义仍可重现历史”的抽样再推导。"""
    verify_frozen_candidate(manifest, root, verify_framework=verify_framework)
    verify_semantics_reproduce_frozen_schedule(manifest, root=root)


def verify_semantics_reproduce_frozen_schedule(
    manifest: dict[str, Any],
    root: Path = ROOT,
    *,
    schedule_path: Path = FROZEN_TARGETS_PATH,
) -> None:
    """以冻结语义重推最后一个冻结 signal，必须与 committed 冻结日程逐值一致。"""
    prices = load_price_csv(root / "data/canonical/etf_adjusted_close.csv")
    schedule = load_committed_schedule(schedule_path)
    last_execution = pd.Timestamp(schedule.index[-1])
    month_ends = pd.DatetimeIndex(prices.index).to_period("M")
    signals = prices.groupby(month_ends).tail(1).index
    prior_signals = signals[signals < last_execution]
    if prior_signals.empty:
        raise ValueError("冻结日程缺少可比对的 signal 月份")
    signal_date = pd.Timestamp(prior_signals[-1])
    derived, _ = derive_target(prices, manifest, signal_date)
    expected = schedule.loc[last_execution].astype(float)
    if not derived.reindex(expected.index).round(12).equals(expected.round(12)):
        raise ValueError("冻结语义无法再现 committed 冻结目标日程（candidate 完整性失效）")


def require_activation(
    path: Path = ACTIVATION_PATH,
    manifest: dict[str, Any] | None = None,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    """前瞻写入前的硬门：NOT_ACTIVE 一律拒绝，不得降级继续。"""
    manifest_path = root / "research/shadow/s4c_r1/candidate_manifest.json"
    candidate = manifest if manifest is not None else load_manifest(manifest_path)
    activation = load_activation(path)
    if activation is None:
        raise ValueError(
            "S4C_R1 前瞻影子未激活（无 activation artifact）；拒绝写入任何 prospective record"
        )
    verify_activation(activation, candidate, root=root)
    return activation


def activation_status(path: Path = ACTIVATION_PATH) -> str:
    if not path.is_file():
        return "NOT_ACTIVE"
    return str(load_activation(path).get("activation_status", "UNKNOWN"))  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------
# Vintage loading
# --------------------------------------------------------------------------------------


def load_calendar(path: Path) -> pd.DataFrame:
    calendar = pd.read_csv(path, index_col="date", parse_dates=["date"])
    if (
        calendar.empty
        or calendar.index.has_duplicates
        or not calendar.index.is_monotonic_increasing
    ):
        raise ValueError("交易日历必须非空、唯一且递增")
    if set(calendar.columns) != {"sse_open", "szse_open"}:
        raise ValueError("交易日历必须只包含 sse_open 与 szse_open")
    if not calendar.isin([0, 1]).all().all():
        raise ValueError("交易日历只能包含 0/1")
    return calendar.astype(int)


def _assert_overlaps_identical(historical: pd.DataFrame, vintage: pd.DataFrame, kind: str) -> None:
    overlap = historical.index.intersection(vintage.index)
    if overlap.empty:
        return
    try:
        pd.testing.assert_frame_equal(historical.loc[overlap], vintage.loc[overlap])
    except AssertionError as error:
        raise ValueError(f"prospective vintage 与 historical {kind} 重叠但内容不同") from error


def validate_month_end(
    vintage_calendar: pd.DataFrame,
    as_of: pd.Timestamp,
    manifest: dict[str, Any],
) -> None:
    """月末确认只使用已公布的交易日历，不使用未来价格。"""
    cutoff = pd.Timestamp(manifest["historical_cutoff"])
    first_signal = pd.Timestamp(manifest["first_eligible_prospective_signal"])
    if as_of <= cutoff:
        raise ValueError("prospective --as-of 必须严格晚于 historical_data_cutoff")
    if as_of < first_signal:
        raise ValueError(
            "prospective --as-of 早于 first_eligible_prospective_signal；该时点不可形成前瞻证据"
        )
    month_calendar = vintage_calendar.loc[
        vintage_calendar.index.to_period("M") == as_of.to_period("M")
    ]
    natural_month_end = as_of + pd.offsets.MonthEnd(0)
    if month_calendar.empty or month_calendar.index.max() < natural_month_end:
        raise ValueError("vintage 日历未覆盖完整 signal 月，不能生成月末前瞻 decision")
    open_dates = month_calendar.index[month_calendar.any(axis=1)]
    if open_dates.empty or open_dates.max() != as_of:
        raise ValueError("--as-of 必须是该月最后一个 canonical 交易日")


def verify_canonical_vintage_location(
    vintage_dir: Path, as_of: pd.Timestamp, root: Path = ROOT
) -> None:
    """真实前瞻 vintage 只能位于 candidate-specific 目录，且目录名等于 as-of 日期。"""
    expected_parent = (root / VINTAGE_PARENT_RELATIVE_PATH).resolve()
    resolved = Path(vintage_dir).resolve()
    if resolved.parent != expected_parent:
        raise ValueError(
            "prospective vintage 必须位于 research/shadow/s4c_r1/vintages/<as-of>/；"
            "任意外部目录不得成为官方前瞻证据"
        )
    if resolved.name != pd.Timestamp(as_of).date().isoformat():
        raise ValueError("vintage 目录名必须等于 --as-of 的 ISO 日期")


def load_prospective_inputs(
    vintage_dir: Path,
    manifest: dict[str, Any],
    *,
    as_of: pd.Timestamp,
    root: Path = ROOT,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    for name in VINTAGE_FILES:
        if not (vintage_dir / name).is_file():
            raise FileNotFoundError(f"prospective vintage 缺少 {name}")
    cutoff = pd.Timestamp(manifest["historical_cutoff"])
    historical_prices = load_price_csv(root / "data/canonical/etf_adjusted_close.csv")
    historical_calendar = load_calendar(root / "data/canonical/trading_calendar.csv")
    vintage_prices = load_price_csv(vintage_dir / "etf_adjusted_close.csv")
    vintage_calendar = load_calendar(vintage_dir / "trading_calendar.csv")
    if list(vintage_prices.columns) != list(historical_prices.columns):
        raise ValueError("prospective vintage 的价格资产列必须与冻结 historical 基线一致")
    _assert_overlaps_identical(historical_prices, vintage_prices, "价格")
    _assert_overlaps_identical(historical_calendar, vintage_calendar, "日历")
    if vintage_prices.index.max() > as_of:
        raise ValueError("prospective vintage 不得包含 as-of 之后的行情")
    prospective_prices = vintage_prices.loc[vintage_prices.index > cutoff]
    prospective_calendar = vintage_calendar.loc[vintage_calendar.index > cutoff]
    if prospective_prices.empty or prospective_calendar.empty:
        raise ValueError("prospective vintage 没有 historical_cutoff 之后的数据")
    combined_prices = pd.concat([historical_prices, prospective_prices]).sort_index()
    combined_calendar = pd.concat([historical_calendar, prospective_calendar]).sort_index()
    if combined_prices.index.has_duplicates or combined_calendar.index.has_duplicates:
        raise ValueError("prospective vintage 的重叠数据未被安全去重")
    vintage_hash = hashlib.sha256(
        "".join(f"{name}:{sha256_file(vintage_dir / name)}\n" for name in VINTAGE_FILES).encode()
    ).hexdigest()
    return combined_prices.loc[:as_of], combined_calendar.loc[:as_of], vintage_hash


# --------------------------------------------------------------------------------------
# Frozen-semantics target derivation
# --------------------------------------------------------------------------------------


def _validate_windows(manifest: dict[str, Any]) -> None:
    semantics = manifest["strategy_semantics"]
    if semantics["price_window"] != WINDOW or semantics["returns_window"] != WINDOW - 1:
        raise ValueError("冻结窗口语义与 upstream 实现不一致")
    if semantics["minimum_eligible_assets"] != MIN_ELIGIBLE:
        raise ValueError("冻结 min eligible 语义与 upstream 实现不一致")


def derive_target(
    prices: pd.DataFrame,
    manifest: dict[str, Any],
    signal_date: pd.Timestamp,
) -> tuple[pd.Series, dict[str, object]]:
    """只使用截至 signal_date 可得的冻结语义推导 target；不重算任何历史结论。"""
    _validate_windows(manifest)
    semantics = manifest["strategy_semantics"]
    risk_symbols = tuple(semantics["risk_symbols"])
    fallback = str(semantics["fallback_symbol"])
    if signal_date not in prices.index:
        raise ValueError("signal_date 必须是可用的 canonical 价格观测日")
    risk = prices.loc[:, list(risk_symbols)]
    window = aligned_window(risk, signal_date, WINDOW)
    target = pd.Series(0.0, index=prices.columns, dtype=float)
    if len(window) != WINDOW:
        target[fallback] = 1.0
        return target, {
            "regime": "FALLBACK",
            "eligible_asset_count": 0,
            "maximum_weight": 1.0,
            "effective_number_assets": 1.0,
        }
    returns = window.pct_change(fill_method=None).dropna(how="any")
    if len(returns) != WINDOW - 1 or len(returns.columns) < MIN_ELIGIBLE:
        raise SolverFailure("aligned prices did not yield the requested valid return window")
    weights = erc_weights(returns)
    target.loc[weights.index] = weights
    return target, {
        "regime": "RISK",
        "eligible_asset_count": len(weights),
        "maximum_weight": float(weights.max()),
        "effective_number_assets": float(1.0 / (weights**2).sum()),
    }


def previous_signal_target(
    prices: pd.DataFrame, manifest: dict[str, Any], signal_date: pd.Timestamp
) -> pd.Series | None:
    month_ends = pd.DatetimeIndex(prices.index).to_period("M")
    signals = prices.groupby(month_ends).tail(1).index
    previous = signals[signals < signal_date]
    if previous.empty:
        return None
    target, _ = derive_target(prices, manifest, pd.Timestamp(previous[-1]))
    return target


def verify_target_tradable(
    target: pd.Series,
    prices: pd.DataFrame,
    root: Path = ROOT,
    *,
    signal_date: pd.Timestamp,
) -> None:
    """正目标必须在 signal 时点 active 且价格有限为正（沿用冻结 PIT 契约）。"""
    frame = pd.DataFrame([target], index=pd.DatetimeIndex([signal_date]))
    mask, lifetimes = load_tradability_inputs(prices, str(root / "config/universe.csv"))
    validate_execution_targets(frame, prices, mask, lifetimes)


def build_decision_record(
    prices: pd.DataFrame,
    manifest: dict[str, Any],
    *,
    as_of: pd.Timestamp,
    vintage_identifier: str,
    prospective_data_hash: str,
    historical_manifest_hash: str,
    generated_at: str | None = None,
    root: Path = ROOT,
) -> dict[str, str]:
    target, diagnostics = derive_target(prices, manifest, as_of)
    verify_target_tradable(target, prices, root, signal_date=as_of)
    previous = previous_signal_target(prices, manifest, as_of)
    target_changed = previous is None or not target.round(12).equals(previous.round(12))
    timestamp = generated_at or _now_utc_iso()
    desired_targets = {symbol: float(weight) for symbol, weight in target.items()}
    record = {field: "" for field in RECORD_FIELDS}
    record.update(
        {
            "record_type": "decision",
            "candidate_id": str(manifest["candidate_id"]),
            "protocol_version": PROTOCOL_VERSION,
            "record_generated_at": timestamp,
            "data_as_of": as_of.date().isoformat(),
            "vintage_identifier": vintage_identifier,
            "historical_manifest_hash": historical_manifest_hash,
            "prospective_data_hash": prospective_data_hash,
            "signal_date": as_of.date().isoformat(),
            "eligible_asset_count": str(int(diagnostics["eligible_asset_count"])),
            "regime": str(diagnostics["regime"]),
            "maximum_weight": str(float(diagnostics["maximum_weight"])),
            "effective_number_assets": str(float(diagnostics["effective_number_assets"])),
            "target_changed": str(bool(target_changed)).lower(),
            "desired_targets": json.dumps(desired_targets, ensure_ascii=False, sort_keys=True),
            "action_required": "true",
            "execution_status": PENDING_EXECUTION_STATUS,
        }
    )
    verify_decision_row_is_fixed_before_execution(record)
    verify_record_generation_time(record)
    return record


# --------------------------------------------------------------------------------------
# Append-only record contract
# --------------------------------------------------------------------------------------


def read_observation_rows(path: Path = OBSERVATIONS_PATH) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError("observations.csv 必须先以协议表头创建")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError("observations.csv 缺少协议表头")
    if tuple(rows[0]) != RECORD_FIELDS:
        raise ValueError("observations.csv schema 与冻结协议不一致")
    return [dict(zip(RECORD_FIELDS, row, strict=True)) for row in rows[1:]]


def observation_record_count(path: Path = OBSERVATIONS_PATH) -> int:
    return len(read_observation_rows(path))


def decision_record_count(path: Path = OBSERVATIONS_PATH) -> int:
    return sum(1 for row in read_observation_rows(path) if row["record_type"] == "decision")


def verify_decision_row_is_fixed_before_execution(record: dict[str, str]) -> None:
    if record["record_type"] != "decision":
        raise ValueError("只有 decision 行适用 decision-before-execution 契约")
    if record["execution_status"] != PENDING_EXECUTION_STATUS:
        raise ValueError("decision 行的 execution_status 必须是待执行状态")
    filled = [field for field in EXECUTION_ONLY_FIELDS if record.get(field, "") != ""]
    if filled:
        raise ValueError(f"decision 行不得包含执行结果字段: {filled}")


def verify_record_generation_time(record: dict[str, str]) -> None:
    """decision 只能在其 signal date 当日或之后形成，不得伪造更早的生成时间。"""
    generated = pd.Timestamp(record["record_generated_at"])
    if generated.tzinfo is not None:
        generated = generated.tz_convert("UTC").tz_localize(None)
    signal_date = pd.Timestamp(record["signal_date"])
    if generated.normalize() < signal_date.normalize():
        raise ValueError(
            "record_generated_at 不得早于 signal_date：decision 必须在其 signal 时点形成"
        )


def _append_row(record: dict[str, str], path: Path) -> None:
    if tuple(record.keys()) != RECORD_FIELDS:
        raise ValueError("record 字段集合与冻结 observation schema 不一致")
    existing = read_observation_rows(path)
    for row in existing:
        if (
            row["record_type"] == record["record_type"]
            and row["candidate_id"] == record["candidate_id"]
            and row["signal_date"] == record["signal_date"]
        ):
            raise ValueError(
                "append-only 协议禁止重复写入同一 candidate + signal_date 的 "
                f"{record['record_type']} record"
            )
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=RECORD_FIELDS).writerow(record)


def append_decision_record(record: dict[str, str], path: Path = OBSERVATIONS_PATH) -> None:
    if record["record_type"] != "decision":
        raise ValueError("append_decision_record 只接受 decision 行")
    verify_decision_row_is_fixed_before_execution(record)
    verify_record_generation_time(record)
    _append_row(record, path)


def append_execution_record(record: dict[str, str], path: Path = OBSERVATIONS_PATH) -> None:
    if record["record_type"] != "execution":
        raise ValueError("append_execution_record 只接受 execution 行")
    if not record.get("execution_date", ""):
        raise ValueError("execution 行必须带 execution_date")
    if pd.Timestamp(record["execution_date"]) <= pd.Timestamp(record["signal_date"]):
        raise ValueError("execution 不得早于或等于 signal date：决策必须先于执行")
    decisions = [
        row
        for row in read_observation_rows(path)
        if row["record_type"] == "decision"
        and row["candidate_id"] == record["candidate_id"]
        and row["signal_date"] == record["signal_date"]
    ]
    if len(decisions) != 1:
        raise ValueError("execution 行只能追加在唯一对应的 decision 行之后")
    _append_row(record, path)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def canonical_activation_path(root: Path = ROOT) -> Path:
    return root / ACTIVATION_RELATIVE_PATH


def canonical_observations_path(root: Path = ROOT) -> Path:
    return root / "research/shadow/s4c_r1/observations.csv"


def run_decision(
    as_of: pd.Timestamp,
    vintage_dir: Path,
    *,
    manifest: dict[str, Any] | None = None,
    root: Path = ROOT,
    activation_path: Path | None = None,
    record_path: Path | None = None,
    generated_at: str | None = None,
    enforce_canonical_vintage: bool = True,
) -> dict[str, str]:
    """唯一写入门：候选完整性 → activation → as-of 边界 → vintage → append-only 追加。

    生产 CLI 只使用 canonical 路径；`activation_path` / `record_path` /
    `enforce_canonical_vintage` 仅供 tmp_path 测试的下层 helper 使用，不对用户暴露。
    """
    resolved_manifest = (
        manifest if manifest is not None else load_manifest(root / MANIFEST_RELATIVE_PATH)
    )
    resolved_activation = (
        Path(activation_path) if activation_path is not None else canonical_activation_path(root)
    )
    resolved_records = (
        Path(record_path) if record_path is not None else canonical_observations_path(root)
    )
    vintage_path = Path(vintage_dir)
    verify_candidate_shadow(resolved_manifest, root)
    require_activation(resolved_activation, resolved_manifest, root=root)
    validate_month_end(
        load_calendar(vintage_path / "trading_calendar.csv"), as_of, resolved_manifest
    )
    if enforce_canonical_vintage:
        verify_canonical_vintage_location(vintage_path, as_of, root)
    prices, _, vintage_hash = load_prospective_inputs(
        vintage_path, resolved_manifest, as_of=as_of, root=root
    )
    record = build_decision_record(
        prices,
        resolved_manifest,
        as_of=as_of,
        vintage_identifier=vintage_path.name,
        prospective_data_hash=vintage_hash,
        historical_manifest_hash=sha256_frozen_repository_text(root / MANIFEST_RELATIVE_PATH),
        generated_at=generated_at,
        root=root,
    )
    append_decision_record(record, resolved_records)
    return record


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--verify-candidate", action="store_true")
    parser.add_argument("--verify-activation", action="store_true")
    parser.add_argument("--as-of", help="决策时点 YYYY-MM-DD；不得使用 wall-clock 默认值")
    parser.add_argument("--vintage-dir", type=Path)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    manifest = load_manifest()

    if args.verify_candidate or args.verify_activation:
        if args.as_of or args.vintage_dir:
            parser.error("只读校验模式不能与 --as-of 或 --vintage-dir 同用")
        verify_candidate_shadow(manifest)
        lines = [
            "S4C_R1 candidate manifest、冻结身份输入、PIT 契约与冻结语义再推导校验通过；",
            f"observation 行数 = {observation_record_count(OBSERVATIONS_PATH)}，"
            f"decision 行数 = {decision_record_count(OBSERVATIONS_PATH)}。",
        ]
        if args.verify_activation:
            activation = load_activation(ACTIVATION_PATH)
            if activation is None:
                lines.append(
                    "activation_status = NOT_ACTIVE（无 activation artifact）；"
                    "runner 拒绝写入任何 prospective record。"
                )
            else:
                verify_activation(activation, manifest)
                lines.append(f"activation_status = {activation['activation_status']}（校验通过）。")
        print("\n".join(lines))
        return

    if not args.as_of or args.vintage_dir is None:
        parser.error("前瞻决策必须同时提供 --as-of 与 --vintage-dir")

    record = run_decision(pd.Timestamp(args.as_of), args.vintage_dir)
    print(f"已追加 S4C_R1 前瞻 decision record: {record['signal_date']}（执行证据尚未产生）")


if __name__ == "__main__":
    main()
