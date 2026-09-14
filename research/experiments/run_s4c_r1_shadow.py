#!/usr/bin/env python3
"""用冻结的 S4C R1 身份生成一条可审计的月末前瞻影子决策。

本模块是**最小 candidate-specific runner**：它只服务 `S4C_R1`，不实现调度器、daemon、
通知、券商或通用候选框架。前瞻决策必须显式提供 `--as-of`，禁止 wall-clock 默认值；
canonical vintage 位置与 record 目的地均不可由生产 CLI 覆盖。
"""

from __future__ import annotations

import json
import math
from argparse import ArgumentParser
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research.experiments.prospective_evidence import (
    REQUIRED_VINTAGE_FILES,
    SHANGHAI_TIMEZONE,
    ProspectiveVintage,
    RqalphaExecutionArtifact,
    append_event_row,
    load_calendar,
    load_frozen_universe,
    load_prospective_vintage,
    parse_finite_float,
    parse_iso_date,
    parse_json_list,
    parse_rqalpha_execution_artifact,
    parse_weight_vector,
    read_event_rows,
    require_timezone_aware_instant,
    resolve_canonical_vintage_dir,
    sha256_frozen_repository_text,
    signal_close_instant,
    verify_canonical_vintage_location,
    verify_hex_digest,
    verify_signal_day_seal,
)
from research.experiments.prospective_evidence import (
    build_rqalpha_evidence_identity as build_rqalpha_evidence_identity,
)
from research.experiments.prospective_evidence import sha256_file as sha256_file
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
)
from research.experiments.verify_s4c_r1_candidate import (
    verify_candidate as verify_frozen_candidate,
)
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs, validate_execution_targets
from tacticore.data.tushare import ADJUSTMENT_TYPE, SOURCE

SHADOW_DIR = ROOT / "research/shadow/s4c_r1"
MANIFEST_PATH = SHADOW_DIR / "candidate_manifest.json"
ACTIVATION_PATH = SHADOW_DIR / "activation.json"
VINTAGE_FILES = REQUIRED_VINTAGE_FILES

MANIFEST_RELATIVE_PATH = "research/shadow/s4c_r1/candidate_manifest.json"
ACTIVATION_RELATIVE_PATH = "research/shadow/s4c_r1/activation.json"
OBSERVATIONS_RELATIVE_PATH = "research/shadow/s4c_r1/observations.csv"
VINTAGE_PARENT_RELATIVE_PATH = "research/shadow/s4c_r1/vintages"
ACTIVATION_PROTOCOL_RELATIVE_PATH = "research/batches/s4c_activation/PROTOCOL.md"
ACTIVATION_DECISION_RECORD_RELATIVE_PATH = (
    "research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md"
)

PROTOCOL_VERSION = "V1"
ACTIVATION_PROTOCOL_VERSION = "V1"
OBSERVATION_SCHEMA_VERSION = "S4C_R1_OBSERVATIONS_V1"
PENDING_EXECUTION_STATUS = "PENDING_NEXT_CANONICAL_OBSERVATION"
ALLOWED_EXECUTION_STATUSES = ("EXECUTED",)
MATERIAL_DEVIATION_THRESHOLD = 0.05
ACTIVE_STATUS = "ACTIVE"
ACTIVATION_DECISION_TOKEN = "ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW"
ACTIVATION_DECISION_LINE_PREFIX = "ACTIVATION_DECISION:"
ALLOWED_ACTIVATION_DECISIONS = (
    "ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW",
    "DEFER_S4C_R1_PROSPECTIVE_ACTIVATION",
    "REJECT_S4C_R1_PROSPECTIVE_ACTIVATION",
    "BLOCK_S4C_R1_ACTIVATION_CORRECTNESS",
)
DECISION_RECORD_POLICY = "APPEND_ONLY_ONE_DECISION_PER_SIGNAL_DATE_BEFORE_EXECUTION"
EXECUTION_RECORD_POLICY = "APPEND_ONLY_ONE_EXECUTION_PER_DECISION_AFTER_SIGNAL_DATE"
REGIMES = ("RISK", "FALLBACK")

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


def _now_utc_iso() -> str:
    """decision_seal_time 的唯一生产来源：runner 的实际运行时钟。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def manifest_hash(path: Path = MANIFEST_PATH) -> str:
    return sha256_frozen_repository_text(path)


def canonical_observations_path(root: Path = ROOT) -> Path:
    return root / OBSERVATIONS_RELATIVE_PATH


def canonical_activation_path(root: Path = ROOT) -> Path:
    return root / ACTIVATION_RELATIVE_PATH


def canonical_vintage_dir(root: Path, as_of: object) -> Path:
    return resolve_canonical_vintage_dir(root / VINTAGE_PARENT_RELATIVE_PATH, as_of)


# --------------------------------------------------------------------------------------
# Candidate / activation integrity
# --------------------------------------------------------------------------------------


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


def parse_activation_decision(text: str) -> str:
    """解析 activation decision record 的机器可读裁决行。

    只接受唯一一条 `ACTIVATION_DECISION: <verdict>` 行；正文其他位置提到 ACTIVATE
    token（例如备选方案目录）不构成授权。
    """
    verdicts = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.strip().startswith(ACTIVATION_DECISION_LINE_PREFIX)
    ]
    if len(verdicts) != 1:
        raise ValueError("activation decision record 必须恰好包含一条 ACTIVATION_DECISION 行")
    decision = verdicts[0]
    if decision not in ALLOWED_ACTIVATION_DECISIONS:
        raise ValueError(f"activation decision record 的裁决不是允许值: {decision}")
    if decision != ACTIVATION_DECISION_TOKEN:
        raise ValueError("activation decision record 选择的裁决不是 ACTIVATE")
    return decision


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
    parse_activation_decision(record_path.read_text(encoding="utf-8"))


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
    manifest_path = root / MANIFEST_RELATIVE_PATH
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


def load_prospective_inputs(
    vintage_dir: Path,
    manifest: Mapping[str, Any],
    *,
    as_of: object,
    root: Path = ROOT,
) -> ProspectiveVintage:
    """读取并经机器验证的 candidate-specific vintage；只使用冻结 historical + 该 vintage。"""
    return load_prospective_vintage(
        vintage_dir,
        as_of=as_of,
        historical_cutoff=pd.Timestamp(manifest["historical_cutoff"]),
        historical_prices=load_price_csv(root / "data/canonical/etf_adjusted_close.csv"),
        historical_calendar=load_calendar(root / "data/canonical/trading_calendar.csv"),
        expected_source=SOURCE,
        expected_adjustment_type=ADJUSTMENT_TYPE,
        frozen_universe=load_frozen_universe(root),
    )


def validate_month_end(
    vintage_calendar: pd.DataFrame,
    as_of: object,
    manifest: Mapping[str, Any],
) -> None:
    """月末确认只使用已公布的交易日历，不使用未来价格。"""
    as_of_day = pd.Timestamp(as_of).normalize()
    cutoff = pd.Timestamp(manifest["historical_cutoff"]).normalize()
    first_signal = pd.Timestamp(manifest["first_eligible_prospective_signal"]).normalize()
    if as_of_day <= cutoff:
        raise ValueError("prospective --as-of 必须严格晚于 historical_data_cutoff")
    if as_of_day < first_signal:
        raise ValueError(
            "prospective --as-of 早于 first_eligible_prospective_signal；该时点不可形成前瞻证据"
        )
    month_calendar = vintage_calendar.loc[
        vintage_calendar.index.to_period("M") == as_of_day.to_period("M")
    ]
    natural_month_end = as_of_day + pd.offsets.MonthEnd(0)
    if month_calendar.empty or month_calendar.index.max() < natural_month_end:
        raise ValueError("vintage 日历未覆盖完整 signal 月，不能生成月末前瞻 decision")
    open_dates = month_calendar.index[month_calendar.any(axis=1)]
    if open_dates.empty or open_dates.max() != as_of_day:
        raise ValueError("--as-of 必须是该月最后一个 canonical 交易日")


# --------------------------------------------------------------------------------------
# Frozen-semantics target derivation
# --------------------------------------------------------------------------------------


def _validate_windows(manifest: Mapping[str, Any]) -> None:
    semantics = manifest["strategy_semantics"]
    if semantics["price_window"] != WINDOW or semantics["returns_window"] != WINDOW - 1:
        raise ValueError("冻结窗口语义与 upstream 实现不一致")
    if semantics["minimum_eligible_assets"] != MIN_ELIGIBLE:
        raise ValueError("冻结 min eligible 语义与 upstream 实现不一致")


def derive_target(
    prices: pd.DataFrame,
    manifest: Mapping[str, Any],
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
    prices: pd.DataFrame, manifest: Mapping[str, Any], signal_date: pd.Timestamp
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


# --------------------------------------------------------------------------------------
# Decision row contract
# --------------------------------------------------------------------------------------


def verify_decision_row_is_fixed_before_execution(record: Mapping[str, str]) -> None:
    if record["record_type"] != "decision":
        raise ValueError("只有 decision 行适用 decision-before-execution 契约")
    if record["execution_status"] != PENDING_EXECUTION_STATUS:
        raise ValueError("decision 行的 execution_status 必须是待执行状态")
    filled = [field for field in EXECUTION_ONLY_FIELDS if record.get(field, "") != ""]
    if filled:
        raise ValueError(f"decision 行不得包含执行结果字段: {filled}")


def verify_record_generation_time(record: Mapping[str, str]) -> None:
    """decision 只能在其 signal date 收盘后、且当日封存，不得回填更早或更晚的时间。"""
    seal = require_timezone_aware_instant(
        record["record_generated_at"], label="record_generated_at"
    )
    signal_date = parse_iso_date(record["signal_date"], label="signal_date")
    if seal.tz_convert(SHANGHAI_TIMEZONE).date() != signal_date.date():
        raise ValueError("record_generated_at 的上海本地日历日必须等于 signal_date")
    if seal < signal_close_instant(signal_date):
        raise ValueError("record_generated_at 不得早于 signal_close")


def verify_decision_row(
    record: Mapping[str, str],
    *,
    manifest: Mapping[str, Any],
    expected_symbols: Iterable[str],
) -> None:
    """decision 行契约：完整身份、合法时间、完整目标且不含任何执行结果。"""
    verify_decision_row_is_fixed_before_execution(record)
    if record["candidate_id"] != manifest["candidate_id"]:
        raise ValueError("decision 行的 candidate_id 与冻结 manifest 不一致")
    if record["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("decision 行的 protocol_version 与冻结协议不一致")
    signal_date = parse_iso_date(record["signal_date"], label="signal_date")
    if parse_iso_date(record["data_as_of"], label="data_as_of") != signal_date:
        raise ValueError("decision 行的 data_as_of 必须等于 signal_date")
    if record["vintage_identifier"] != signal_date.date().isoformat():
        raise ValueError("decision 行的 vintage_identifier 必须是 canonical vintage 目录名")
    verify_hex_digest(record["historical_manifest_hash"], label="historical_manifest_hash")
    verify_hex_digest(record["prospective_data_hash"], label="prospective_data_hash")
    if parse_finite_float(record["eligible_asset_count"], label="eligible_asset_count") < 0.0:
        raise ValueError("eligible_asset_count 不得为负")
    if record["regime"] not in REGIMES:
        raise ValueError("regime 必须是冻结的 RISK/FALLBACK 之一")
    maximum_weight = parse_finite_float(record["maximum_weight"], label="maximum_weight")
    if not 0.0 <= maximum_weight <= 1.0:
        raise ValueError("maximum_weight 必须落在 [0, 1]")
    if parse_finite_float(record["effective_number_assets"], label="effective_number_assets") < 1.0:
        raise ValueError("effective_number_assets 不得小于一")
    if record["target_changed"] not in {"true", "false"}:
        raise ValueError("target_changed 必须是 true/false")
    if record["action_required"] != "true":
        raise ValueError("S4C 采用 MONTHLY_TARGET_SUBMISSION，action_required 必须为 true")
    parse_weight_vector(
        record["desired_targets"], expected_symbols=expected_symbols, label="desired_targets"
    )
    verify_record_generation_time(record)


def build_decision_record(
    prices: pd.DataFrame,
    manifest: Mapping[str, Any],
    *,
    as_of: pd.Timestamp,
    vintage_identifier: str,
    prospective_data_hash: str,
    historical_manifest_hash: str,
    expected_symbols: Sequence[str] | None = None,
    decision_seal_time: str | None = None,
    root: Path = ROOT,
) -> dict[str, str]:
    target, diagnostics = derive_target(prices, manifest, as_of)
    verify_target_tradable(target, prices, root, signal_date=as_of)
    previous = previous_signal_target(prices, manifest, as_of)
    target_changed = previous is None or not target.round(12).equals(previous.round(12))
    timestamp = decision_seal_time or _now_utc_iso()
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
            "maximum_weight": repr(float(diagnostics["maximum_weight"])),
            "effective_number_assets": repr(float(diagnostics["effective_number_assets"])),
            "target_changed": str(bool(target_changed)).lower(),
            "desired_targets": json.dumps(desired_targets, ensure_ascii=False, sort_keys=True),
            "action_required": "true",
            "execution_status": PENDING_EXECUTION_STATUS,
        }
    )
    verify_decision_row(
        record,
        manifest=manifest,
        expected_symbols=list(prices.columns) if expected_symbols is None else expected_symbols,
    )
    return record


# --------------------------------------------------------------------------------------
# Append-only record contract
# --------------------------------------------------------------------------------------


def read_observation_rows(path: Path = OBSERVATIONS_PATH) -> list[dict[str, str]]:
    return read_event_rows(path, RECORD_FIELDS)


def observation_record_count(path: Path = OBSERVATIONS_PATH) -> int:
    return len(read_event_rows(path, RECORD_FIELDS))


def decision_record_count(path: Path = OBSERVATIONS_PATH) -> int:
    return sum(
        1 for row in read_event_rows(path, RECORD_FIELDS) if row["record_type"] == "decision"
    )


def append_decision_record(record: Mapping[str, str], path: Path = OBSERVATIONS_PATH) -> None:
    if record["record_type"] != "decision":
        raise ValueError("append_decision_record 只接受 decision 行")
    verify_decision_row_is_fixed_before_execution(record)
    verify_record_generation_time(record)
    append_event_row(record, path=path, fields=RECORD_FIELDS)


def verify_material_asset_differences(
    raw: object, *, realized_symbols: Iterable[str]
) -> list[dict[str, Any]]:
    differences = parse_json_list(raw, label="material_asset_differences")
    for entry in differences:
        if not isinstance(entry, Mapping):
            raise ValueError("material_asset_differences 的每个元素必须是 JSON object")
        symbol = entry.get("symbol")
        if not isinstance(symbol, str) or symbol not in set(realized_symbols):
            raise ValueError("material_asset_differences 引用了未知 symbol")
        intended = parse_finite_float(
            entry.get("intended"), label="material_asset_differences.intended"
        )
        realized = parse_finite_float(
            entry.get("realized"), label="material_asset_differences.realized"
        )
        if abs(intended - realized) <= MATERIAL_DEVIATION_THRESHOLD:
            raise ValueError("material_asset_differences 只能记录超过 5pp 的单资产差异")
        native_evidence = entry.get("native_evidence")
        if not isinstance(native_evidence, str) or not native_evidence:
            raise ValueError("material_asset_differences 必须携带 native_evidence")
    return list(differences)


def _material_asset_differences(artifact: RqalphaExecutionArtifact) -> list[dict[str, Any]]:
    """由 artifact 的 intended vs realized weights 推导 5pp 单资产差异，不接受调用方清单。"""
    differences: list[dict[str, Any]] = []
    for symbol in sorted(artifact.intended_targets):
        intended = float(artifact.intended_targets[symbol])
        realized = float(artifact.realized_weights[symbol])
        if abs(intended - realized) <= MATERIAL_DEVIATION_THRESHOLD:
            continue
        evidence = artifact.native_evidence.get(symbol)
        if not isinstance(evidence, str) or not evidence:
            raise ValueError(f"material_asset_differences.{symbol} 缺少 artifact native_evidence")
        differences.append(
            {
                "symbol": symbol,
                "intended": intended,
                "realized": realized,
                "native_evidence": evidence,
            }
        )
    return differences


def _require_artifact_value(actual: float, expected: float, *, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{label} 必须等于 RQAlpha execution artifact 的确定性解析结果")


def verify_execution_row(
    record: Mapping[str, str],
    *,
    decision: Mapping[str, str],
    expected_symbols: Iterable[str],
    expected_framework_version: str,
    root: Path = ROOT,
) -> None:
    """execution 行必须**完整**且逐值等于 SHA-bound artifact 的确定性解析结果。"""
    if record["record_type"] != "execution":
        raise ValueError("只有 execution 行适用 execution completeness 契约")
    if record["candidate_id"] != decision["candidate_id"]:
        raise ValueError("execution 行的 candidate_id 与对应 decision 不一致")
    if record["protocol_version"] != decision["protocol_version"]:
        raise ValueError("execution 行的 protocol_version 与对应 decision 不一致")
    if record["signal_date"] != decision["signal_date"]:
        raise ValueError("execution 行的 signal_date 必须匹配对应 decision")
    if record["execution_status"] not in ALLOWED_EXECUTION_STATUSES:
        raise ValueError("execution_status 必须是 RQAlpha 原生执行完成状态")
    signal_date = parse_iso_date(record["signal_date"], label="signal_date")
    execution_date = parse_iso_date(record["execution_date"], label="execution_date")
    if execution_date <= signal_date:
        raise ValueError("execution 日期必须晚于 signal date：决策必须先于执行")
    artifact = parse_rqalpha_execution_artifact(
        record["execution_evidence"],
        root=root,
        decision=decision,
        expected_symbols=expected_symbols,
        expected_framework_version=expected_framework_version,
        record_generated_at=record["record_generated_at"],
    )
    if record["execution_status"] != artifact.execution_status:
        raise ValueError("execution_status 必须等于 RQAlpha execution artifact 的 native 状态")
    if execution_date != artifact.execution_date:
        raise ValueError("execution_date 必须等于 artifact execution_timestamp 的上海本地日历日")
    realized = parse_weight_vector(
        record["realized_weights"],
        expected_symbols=expected_symbols,
        label="realized_weights",
        require_total_one=False,
    )
    if realized != artifact.realized_weights:
        raise ValueError("realized_weights 必须等于 RQAlpha execution artifact 的 native 权重")
    cash = parse_finite_float(record["cash_weight"], label="cash_weight")
    if cash < 0.0:
        raise ValueError("cash_weight 不得为负")
    if abs(sum(realized.values()) + cash - 1.0) > 1e-3:
        raise ValueError("realized_weights 与 cash_weight 合计必须覆盖组合")
    _require_artifact_value(
        parse_finite_float(record["cash_weight"], label="cash_weight"),
        artifact.cash_weight,
        label="cash_weight",
    )
    deviation = parse_finite_float(
        record["portfolio_total_absolute_weight_deviation"],
        label="portfolio_total_absolute_weight_deviation",
    )
    if deviation < 0.0:
        raise ValueError("portfolio_total_absolute_weight_deviation 不得为负")
    _require_artifact_value(
        deviation,
        artifact.total_absolute_weight_deviation,
        label="portfolio_total_absolute_weight_deviation",
    )
    if record["material_portfolio_tracking_date"] not in {"true", "false"}:
        raise ValueError("material_portfolio_tracking_date 必须是 true/false")
    expected_material = str(deviation > MATERIAL_DEVIATION_THRESHOLD).lower()
    if record["material_portfolio_tracking_date"] != expected_material:
        raise ValueError("material_portfolio_tracking_date 必须与 5pp 组合层判据一致")
    declared_differences = verify_material_asset_differences(
        record["material_asset_differences"], realized_symbols=realized
    )
    expected_differences = _material_asset_differences(artifact)
    if len(declared_differences) != len(expected_differences):
        raise ValueError("material_asset_differences 必须等于 artifact 推导出的 5pp 差异清单")
    for declared, expected in zip(declared_differences, expected_differences, strict=True):
        if declared.get("symbol") != expected["symbol"]:
            raise ValueError("material_asset_differences 必须等于 artifact 推导出的 5pp 差异清单")
        if declared.get("native_evidence") != expected["native_evidence"]:
            raise ValueError("material_asset_differences 必须携带 artifact 的 native 说明")
        _require_artifact_value(
            parse_finite_float(
                declared.get("intended"), label="material_asset_differences.intended"
            ),
            float(expected["intended"]),
            label="material_asset_differences.intended",
        )
        _require_artifact_value(
            parse_finite_float(
                declared.get("realized"), label="material_asset_differences.realized"
            ),
            float(expected["realized"]),
            label="material_asset_differences.realized",
        )
    _require_artifact_value(
        parse_finite_float(record["turnover"], label="turnover"),
        artifact.turnover,
        label="turnover",
    )


def build_execution_record(
    decision: Mapping[str, str],
    *,
    execution_evidence: str,
    expected_symbols: Iterable[str],
    expected_framework_version: str,
    root: Path = ROOT,
) -> dict[str, str]:
    """由 SHA-bound 权威 artifact 派生 execution 行；调用方不得再单独提供指标。"""
    record_generated_at = _now_utc_iso()
    artifact = parse_rqalpha_execution_artifact(
        execution_evidence,
        root=root,
        decision=decision,
        expected_symbols=expected_symbols,
        expected_framework_version=expected_framework_version,
        record_generated_at=record_generated_at,
    )
    material = artifact.total_absolute_weight_deviation > MATERIAL_DEVIATION_THRESHOLD
    record = {field: "" for field in RECORD_FIELDS}
    record.update(
        {
            "record_type": "execution",
            "candidate_id": decision["candidate_id"],
            "protocol_version": decision["protocol_version"],
            "record_generated_at": record_generated_at,
            "data_as_of": decision["data_as_of"],
            "vintage_identifier": decision["vintage_identifier"],
            "historical_manifest_hash": decision["historical_manifest_hash"],
            "prospective_data_hash": decision["prospective_data_hash"],
            "signal_date": decision["signal_date"],
            "eligible_asset_count": decision["eligible_asset_count"],
            "regime": decision["regime"],
            "maximum_weight": decision["maximum_weight"],
            "effective_number_assets": decision["effective_number_assets"],
            "target_changed": decision["target_changed"],
            "desired_targets": decision["desired_targets"],
            "action_required": decision["action_required"],
            "execution_date": artifact.execution_date.date().isoformat(),
            "execution_status": artifact.execution_status,
            "realized_weights": json.dumps(
                artifact.realized_weights, ensure_ascii=False, sort_keys=True
            ),
            "cash_weight": repr(artifact.cash_weight),
            "portfolio_total_absolute_weight_deviation": repr(
                artifact.total_absolute_weight_deviation
            ),
            "material_portfolio_tracking_date": str(material).lower(),
            "material_asset_differences": json.dumps(
                _material_asset_differences(artifact), ensure_ascii=False, sort_keys=True
            ),
            "turnover": repr(artifact.turnover),
            "execution_evidence": execution_evidence,
        }
    )
    verify_execution_row(
        record,
        decision=decision,
        expected_symbols=expected_symbols,
        expected_framework_version=expected_framework_version,
        root=root,
    )
    return record


def append_execution_record(
    record: Mapping[str, str],
    path: Path = OBSERVATIONS_PATH,
    *,
    expected_symbols: Iterable[str] | None = None,
    expected_framework_version: str | None = None,
    root: Path = ROOT,
) -> None:
    if record["record_type"] != "execution":
        raise ValueError("append_execution_record 只接受 execution 行")
    rows = read_event_rows(path, RECORD_FIELDS)
    decisions = [
        row
        for row in rows
        if row["record_type"] == "decision"
        and row["candidate_id"] == record["candidate_id"]
        and row["signal_date"] == record["signal_date"]
    ]
    if len(decisions) != 1:
        raise ValueError("execution 行只能追加在唯一对应的 decision 行之后")
    manifest = load_manifest(root / MANIFEST_RELATIVE_PATH)
    symbols = (
        list(load_price_csv(root / "data/canonical/etf_adjusted_close.csv").columns)
        if expected_symbols is None
        else list(expected_symbols)
    )
    verify_execution_row(
        record,
        decision=decisions[0],
        expected_symbols=symbols,
        expected_framework_version=(
            str(manifest["framework_versions"]["rqalpha"])
            if expected_framework_version is None
            else expected_framework_version
        ),
        root=root,
    )
    append_event_row(record, path=path, fields=RECORD_FIELDS)


# --------------------------------------------------------------------------------------
# Production write gate
# --------------------------------------------------------------------------------------


def run_decision(
    as_of: object,
    vintage_dir: Path | None = None,
    *,
    manifest: Mapping[str, Any] | None = None,
    root: Path = ROOT,
    activation_path: Path | None = None,
    record_path: Path | None = None,
    decision_seal_time: str | None = None,
) -> dict[str, str]:
    """唯一写入门：候选完整性 → activation → as-of 边界 → canonical 位置 → vintage 真实性
    → temporal seal → append。

    生产 CLI 只使用 canonical 路径与 runner 的实际运行时钟；`vintage_dir` /
    `activation_path` / `record_path` / `decision_seal_time` 只供 `tmp_path` fixture 与
    dependency injection 使用，不对用户暴露。任何非 canonical vintage 目录都在读取任何
    文件之前被拒绝。
    """
    resolved_manifest = (
        manifest if manifest is not None else load_manifest(root / MANIFEST_RELATIVE_PATH)
    )
    resolved_activation = (
        Path(activation_path) if activation_path is not None else canonical_activation_path(root)
    )
    records = Path(record_path) if record_path is not None else canonical_observations_path(root)
    verify_candidate_shadow(dict(resolved_manifest), root)
    require_activation(resolved_activation, dict(resolved_manifest), root=root)
    as_of_day = pd.Timestamp(as_of).normalize()
    # 候选级前瞻边界必须在读取该 as-of 的任何 vintage 文件之前 fail closed。
    cutoff = pd.Timestamp(resolved_manifest["historical_cutoff"]).normalize()
    first_signal = pd.Timestamp(resolved_manifest["first_eligible_prospective_signal"]).normalize()
    if as_of_day <= cutoff:
        raise ValueError("prospective --as-of 必须严格晚于 historical_data_cutoff")
    if as_of_day < first_signal:
        raise ValueError(
            "prospective --as-of 早于 first_eligible_prospective_signal；该时点不可形成前瞻证据"
        )
    vintage_path = (
        Path(vintage_dir) if vintage_dir is not None else canonical_vintage_dir(root, as_of_day)
    )
    # 位置校验必须先于任何 vintage 文件访问：外部目录不得成为官方前瞻证据。
    verify_canonical_vintage_location(
        vintage_path, as_of_day, canonical_parent=root / VINTAGE_PARENT_RELATIVE_PATH
    )
    vintage = load_prospective_inputs(vintage_path, resolved_manifest, as_of=as_of_day, root=root)
    validate_month_end(vintage.raw_calendar, as_of_day, resolved_manifest)
    seal = require_timezone_aware_instant(
        decision_seal_time if decision_seal_time is not None else _now_utc_iso(),
        label="decision_seal_time",
    )
    verify_signal_day_seal(
        signal_date=as_of_day,
        download_timestamp=vintage.provenance.download_timestamp,
        decision_seal_time=seal,
        calendar=vintage.raw_calendar,
    )
    record = build_decision_record(
        vintage.prices,
        resolved_manifest,
        as_of=as_of_day,
        vintage_identifier=vintage_path.name,
        prospective_data_hash=vintage.vintage_hash,
        historical_manifest_hash=sha256_frozen_repository_text(root / MANIFEST_RELATIVE_PATH),
        decision_seal_time=seal.isoformat(),
        root=root,
    )
    append_decision_record(record, records)
    return record


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--verify-candidate", action="store_true")
    parser.add_argument("--verify-activation", action="store_true")
    parser.add_argument(
        "--verify-no-observations",
        action="store_true",
        help="stage-specific：在首个真实 cycle 之前确认 observations.csv 仍为 0 行",
    )
    parser.add_argument("--as-of", help="决策时点 YYYY-MM-DD；不得使用 wall-clock 默认值")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    manifest = load_manifest()

    if args.verify_candidate or args.verify_activation or args.verify_no_observations:
        if args.as_of:
            parser.error("只读校验模式不能与 --as-of 同用")
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
        if args.verify_no_observations:
            count = observation_record_count(OBSERVATIONS_PATH)
            if count != 0:
                raise ValueError("首个真实前瞻 cycle 之前 observations.csv 必须仍为 0 行")
            lines.append("observations.csv 仍为表头（首个真实前瞻 cycle 之前）。")
        print("\n".join(lines))
        return

    if not args.as_of:
        parser.error("前瞻决策必须显式提供 --as-of")

    record = run_decision(pd.Timestamp(args.as_of))
    print(f"已追加 S4C_R1 前瞻 decision record: {record['signal_date']}（执行证据尚未产生）")


if __name__ == "__main__":
    main()
