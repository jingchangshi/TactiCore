#!/usr/bin/env python3
"""V3 账户前瞻台账：只读消费 FinanceMCP 日报与只读账户库的 append-only 事件台账。

协议：`research/batches/v3_prospective_ledger/PROTOCOL_V1.md`（commit `5c76846`）。
本模块只实现协议规定的五类事件（SIGNAL / RECOMMENDATION / CONFIRMED_FILL /
UNEXECUTED_REASON / VALUATION）、幂等键、哈希链、显式缺失与只读输入校验。

它**不**包含策略语义、账户会计、撮合、调度器、数据库写入或通用研究框架：

- 不调用任何可能写入的 FinanceMCP CLI；
- `portfolio.sqlite` 只以 `file:...?mode=ro` + `PRAGMA query_only=ON` 打开；
- 事件只追加到用户私有目录（默认 `~/.local/share/tacticore-v3-prospective-ledger`），
  不写入仓库、不写入生产库。

生产入口全部是人工命令；本模块不注册任何定时器。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sqlite3
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LEDGER_VERSION = "V3_PROSPECTIVE_LEDGER_V1"
PROTOCOL_COMMIT = "5c76846319c29eca78185c69b84393ed49f69bf9"
PROTOCOL_COMMIT_AUTHOR_TIME_UTC = "2026-11-25T09:55:29Z"
PROTOCOL_COMMIT_AUTHOR_TIME_SHANGHAI = "2026-11-25T17:55:29+08:00"
EARLIEST_ELIGIBLE_DAY = "20261126"
EARLIEST_ELIGIBLE_DAY_ISO = "2026-11-26"
CALENDAR_BASIS = (
    "FinanceMCP read-only trade_cal: 20261126 is_open=1; protocol commit "
    "2026-11-25T17:55:29+08:00 is after the 15:00 close, so 2026-11-25 cannot be "
    "the first eligible day. TactiCore data/canonical/trading_calendar.csv ends "
    "2026-08-31 and is not used for 2026-11."
)
LEDGER_ACCOUNT_ID = "real-main"
BRIEF_SCHEMA = "ashare-daily-brief/1.0"
BRIEF_STATUSES = frozenset({"ACTIONABLE", "ILLUSTRATIVE", "NO_ACTION", "DATA_INSUFFICIENT"})
REAL_ACCOUNT_STATUS = "REAL_ACCOUNT_VERIFIED"
CONFIRMED_FILL_SOURCES = frozenset({"broker_statement"})
CONFIRMED_FILL_EVENT_TYPES = frozenset({"TRADE_BUY", "TRADE_SELL"})
REASON_SCHEMA = "v3-prospective-unexecuted-reason/1.0"
REASON_CODES = frozenset(
    {
        "PRICE_INVALIDATED",
        "PREMIUM_BLOCKED",
        "INSUFFICIENT_CASH",
        "MARKET_STATE_CHANGED",
        "BROKER_REJECTED",
        "USER_DEFERRED",
        "OTHER_EXPLICIT",
    }
)
REASON_SCOPES = frozenset({"FULL", "PARTIAL"})
SHANGHAI = timezone(timedelta(hours=8))
ZERO_HASH = "0" * 64
HASH_HEX_LENGTH = 64
EVENT_ID_PREFIX = "V3L-"
BATCH_ID_PREFIX = "BATCH-"
RECORD_FILES = {
    "SIGNAL": "signals.jsonl",
    "RECOMMENDATION": "recommendations.jsonl",
    "CONFIRMED_FILL": "confirmed_fills.jsonl",
    "UNEXECUTED_REASON": "unexecuted_reasons.jsonl",
    "VALUATION": "valuations.jsonl",
}
RECORD_ORDER = {name: index for index, name in enumerate(RECORD_FILES)}
POLICY_BASELINE_FILENAME = "policy_baseline.json"
POLICY_BASELINE_KEYS = frozenset(
    {
        "strategy_id",
        "version",
        "content_hash",
        "production_admission",
        "first_as_of_trade_date",
        "source_sha256",
        "created_at",
    }
)
ENVELOPE_KEYS = frozenset(
    {
        "ledger_version",
        "protocol_commit",
        "record_type",
        "event_id",
        "natural_key",
        "account_id",
        "as_of_trade_date",
        "source",
        "policy",
        "missing_fields",
        "ingest_batch",
        "recorded_at",
        "content_hash",
        "content",
        "prev_event_hash",
        "event_hash",
    }
)
SOURCE_KEYS = frozenset({"kind", "identity", "sha256", "schema_fingerprint"})
POLICY_KEYS = frozenset({"strategy_id", "version", "content_hash", "production_admission"})
BATCH_KEYS = frozenset({"id", "ordinal", "count"})
FORBIDDEN_RECOMMENDATION_KEYS = frozenset(
    {
        "realized_weights",
        "cash_weight",
        "execution_status",
        "execution_date",
        "execution_timestamp",
        "filled_quantity",
        "filled_price_milli",
        "fills",
        "actual_fill",
        "executed_quantity",
        "executed_price_milli",
    }
)
ACTION_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
ACTION_KINDS = frozenset({"REDUCE", "ROTATE", "ADD"})
LEG_SIDES = frozenset({"BUY", "SELL"})
PRINCIPAL_FIELDS = (
    "initial_principal_cents",
    "current_nav_cents",
    "to_principal_gap_cents",
    "to_principal_return_needed_pct",
    "loss_from_principal_pct",
)
HOLDING_REQUIRED_FIELDS = (
    "ts_code",
    "quantity",
    "weight",
    "market_value_cents",
    "price_milli",
    "bar_quality",
    "stance",
)
HOLDING_EXPECTED_FIELDS = (
    "name",
    "price_source",
    "latest_bar_date",
    "diluted_cost_per_share",
    "diluted_total_cost_cents",
    "cost_basis",
)
ACCOUNT_EVENT_COLUMNS = (
    "event_id",
    "account_id",
    "event_type",
    "occurred_on",
    "settled_on",
    "ts_code",
    "quantity",
    "price_milli",
    "gross_cents",
    "fee_cents",
    "tax_cents",
    "cash_delta_cents",
    "ratio_num",
    "ratio_den",
    "reverses_event_id",
    "reversed_by",
    "note",
    "source",
    "recorded_at",
)


class LedgerError(Exception):
    """台账的基础错误类型。"""


class LedgerRefusal(LedgerError):
    """输入或状态不满足协议：拒绝写入，既有 evidence bytes 不变。"""


class LedgerConflict(LedgerRefusal):
    """同一自然键出现不同内容：append-only 协议拒绝覆盖。"""


class LedgerCorruption(LedgerError):
    """既有台账哈希链、schema 或 batch 完整性不成立。"""


def utc_now() -> datetime:
    """生产时钟；测试通过替换本函数注入固定时点。"""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------------------
# Hashing and canonical JSON
# --------------------------------------------------------------------------------------


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _verify_hex64(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != HASH_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise LedgerRefusal(f"{label} 必须是 64 位小写十六进制 SHA-256")
    return value


def content_hash(record_type: str, content: Mapping[str, Any]) -> str:
    return sha256_text(f"{record_type}\n{canonical_json(content)}")


def event_id_for(content_hash_value: str) -> str:
    return EVENT_ID_PREFIX + content_hash_value[:24]


# --------------------------------------------------------------------------------------
# Dates and instants
# --------------------------------------------------------------------------------------


def _require_aware_instant(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise LedgerRefusal(f"{label} 必须是非空 ISO 时间字符串")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise LedgerRefusal(f"{label} 不可解析: {value!r}") from error
    if parsed.tzinfo is None:
        raise LedgerRefusal(f"{label} 必须带时区，不得使用 naive timestamp")
    return parsed


def _shanghai(value: datetime) -> datetime:
    return value.astimezone(SHANGHAI)


def _ymd_of(value: datetime) -> str:
    return _shanghai(value).strftime("%Y%m%d")


def _parse_ymd(value: object, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        raise LedgerRefusal(f"{label} 必须是 YYYYMMDD 形式的日期")
    try:
        date.fromisoformat(_iso_day(value))
    except ValueError as error:
        raise LedgerRefusal(f"{label} 不是合法日期: {value!r}") from error
    return value


def _iso_day(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


def _now_shanghai() -> datetime:
    return _shanghai(utc_now())


# --------------------------------------------------------------------------------------
# Ledger layout and manifest
# --------------------------------------------------------------------------------------


def ledger_root(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    environment = os.environ.get("TACTICORE_V3_LEDGER_ROOT")
    if environment:
        return Path(environment)
    return Path.home() / ".local" / "share" / "tacticore-v3-prospective-ledger"


def _manifest_path(root: Path) -> Path:
    return root / "manifest.json"


def _record_path(root: Path, record_type: str) -> Path:
    return root / RECORD_FILES[record_type]


@dataclass(frozen=True)
class Manifest:
    account_id: str
    earliest_eligible_day: str


def _expected_manifest(now: datetime) -> dict[str, Any]:
    return {
        "ledger_version": LEDGER_VERSION,
        "protocol_commit": PROTOCOL_COMMIT,
        "protocol_commit_author_time_utc": PROTOCOL_COMMIT_AUTHOR_TIME_UTC,
        "protocol_commit_author_time_shanghai": PROTOCOL_COMMIT_AUTHOR_TIME_SHANGHAI,
        "earliest_eligible_day": EARLIEST_ELIGIBLE_DAY,
        "earliest_eligible_day_iso": EARLIEST_ELIGIBLE_DAY_ISO,
        "calendar_basis": CALENDAR_BASIS,
        "account_id": LEDGER_ACCOUNT_ID,
        "record_files": RECORD_FILES,
        "created_at": now.isoformat(),
    }


def init_ledger(root: Path | str | None = None) -> dict[str, Any]:
    """初始化私有台账目录；已有 manifest 或任何事件文件时拒绝。"""
    resolved = ledger_root(root)
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved, 0o700)
    manifest_file = _manifest_path(resolved)
    if manifest_file.exists():
        raise LedgerRefusal(f"台账已初始化，拒绝覆盖: {manifest_file}")
    for name in RECORD_FILES.values():
        target = resolved / name
        if target.exists() and target.stat().st_size:
            raise LedgerRefusal(f"台账目录已有非空 {name}，拒绝初始化")
    now = utc_now()
    payload = _expected_manifest(now)
    temporary = manifest_file.with_name(".manifest.json.tmp")
    temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(manifest_file)
    for name in RECORD_FILES.values():
        target = resolved / name
        target.touch(mode=0o600, exist_ok=True)
        os.chmod(target, 0o600)
    return {"status": "INITIALIZED", "root": str(resolved), **payload}


def load_manifest(root: Path | str | None = None) -> Manifest:
    resolved = ledger_root(root)
    manifest_file = _manifest_path(resolved)
    if not manifest_file.is_file():
        raise LedgerRefusal(f"台账未初始化，缺少 {manifest_file}")
    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LedgerCorruption("manifest.json 不是合法 JSON") from error
    if not isinstance(payload, Mapping):
        raise LedgerCorruption("manifest.json 必须是 JSON object")
    expected = _expected_manifest(utc_now())
    for key, value in expected.items():
        if key == "created_at":
            continue
        if payload.get(key) != value:
            raise LedgerCorruption(
                f"manifest.{key} 与当前协议常量不一致：{payload.get(key)!r} != {value!r}"
            )
    _require_aware_instant(payload.get("created_at"), label="manifest.created_at")
    for name in RECORD_FILES.values():
        if not (resolved / name).is_file():
            raise LedgerCorruption(f"台账缺少事件文件 {name}")
    return Manifest(
        account_id=str(payload["account_id"]),
        earliest_eligible_day=str(payload["earliest_eligible_day"]),
    )


def _policy_baseline_path(root: Path) -> Path:
    return Path(root) / POLICY_BASELINE_FILENAME


def load_policy_baseline(root: Path | str | None = None) -> dict[str, str] | None:
    """读取首次合格 brief 钉住的 policy 身份；缺失是合法状态。"""
    path = _policy_baseline_path(ledger_root(root))
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LedgerCorruption("policy_baseline.json 不是合法 JSON") from error
    if not isinstance(payload, Mapping) or set(payload) != POLICY_BASELINE_KEYS:
        raise LedgerCorruption("policy_baseline.json 字段集合与补遗 1 不一致")
    try:
        for key in ("strategy_id", "version", "production_admission"):
            _require_str(payload[key], label=f"policy_baseline.{key}")
        _verify_hex64(payload["content_hash"], label="policy_baseline.content_hash")
        _parse_ymd(
            payload["first_as_of_trade_date"], label="policy_baseline.first_as_of_trade_date"
        )
        _verify_hex64(payload["source_sha256"], label="policy_baseline.source_sha256")
        _require_aware_instant(payload["created_at"], label="policy_baseline.created_at")
    except LedgerRefusal as error:
        raise LedgerCorruption(f"policy_baseline.json 非法: {error}") from error
    return {key: str(value) for key, value in payload.items()}


def _check_policy_baseline(root: Path, policy: Mapping[str, str]) -> None:
    baseline = load_policy_baseline(root)
    if baseline is None:
        return
    for key in ("strategy_id", "version", "content_hash"):
        if baseline[key] != policy[key]:
            raise LedgerRefusal(
                f"POLICY_RELEASE_CHANGED: {key} {baseline[key]!r} -> {policy[key]!r}；"
                "不得静默换包，须所有者人工裁决"
            )


def _write_policy_baseline(
    root: Path,
    policy: Mapping[str, str],
    *,
    as_of_trade_date: str,
    source_sha256: str,
    created_at: datetime,
) -> dict[str, str]:
    path = _policy_baseline_path(root)
    if path.exists():
        return load_policy_baseline(root) or {}
    payload = {
        "strategy_id": str(policy["strategy_id"]),
        "version": str(policy["version"]),
        "content_hash": str(policy["content_hash"]),
        "production_admission": str(policy["production_admission"]),
        "first_as_of_trade_date": as_of_trade_date,
        "source_sha256": source_sha256,
        "created_at": created_at.isoformat(),
    }
    temporary = path.with_name(".policy_baseline.json.tmp")
    temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return load_policy_baseline(root) or {}


# --------------------------------------------------------------------------------------
# Event reading and validation
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Draft:
    record_type: str
    natural_key: str
    as_of_trade_date: str
    content: dict[str, Any]
    source: dict[str, Any]
    policy: dict[str, str] | None
    missing_fields: tuple[str, ...]

    @property
    def content_hash(self) -> str:
        return content_hash(self.record_type, self.content)


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LedgerRefusal(f"{label} 必须是 JSON object")
    return value


def _require_sequence(value: object, *, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise LedgerRefusal(f"{label} 必须是 JSON array")
    return value


def _require_str(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LedgerRefusal(f"{label} 必须是非空字符串")
    return value


def _require_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise LedgerRefusal(f"{label} 必须是布尔值")
    return value


def _require_int(value: object, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerRefusal(f"{label} 必须是整数")
    if minimum is not None and value < minimum:
        raise LedgerRefusal(f"{label} 必须 >= {minimum}")
    return value


def _require_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LedgerRefusal(f"{label} 必须是数值")
    return float(value)


def _validate_source(source: object) -> Mapping[str, Any]:
    payload = _require_mapping(source, label="event.source")
    if set(payload) != SOURCE_KEYS:
        raise LedgerCorruption("event.source 字段集合与协议不一致")
    _require_str(payload["kind"], label="event.source.kind")
    _require_mapping(payload["identity"], label="event.source.identity")
    _verify_hex64(payload["sha256"], label="event.source.sha256")
    fingerprint = payload["schema_fingerprint"]
    if fingerprint is not None:
        _verify_hex64(fingerprint, label="event.source.schema_fingerprint")
    return payload


def _validate_policy(policy: object, *, required: bool) -> Mapping[str, str] | None:
    if policy is None:
        if required:
            raise LedgerCorruption("brief 派生事件必须携带 policy 身份")
        return None
    payload = _require_mapping(policy, label="event.policy")
    if set(payload) != POLICY_KEYS:
        raise LedgerCorruption("event.policy 字段集合与协议不一致")
    for key in POLICY_KEYS:
        _require_str(payload[key], label=f"event.policy.{key}")
    return {key: str(value) for key, value in payload.items()}


def _validate_batch(batch: object) -> Mapping[str, Any]:
    payload = _require_mapping(batch, label="event.ingest_batch")
    if set(payload) != BATCH_KEYS:
        raise LedgerCorruption("event.ingest_batch 字段集合与协议不一致")
    identifier = _require_str(payload["id"], label="event.ingest_batch.id")
    if not identifier.startswith(BATCH_ID_PREFIX):
        raise LedgerCorruption("event.ingest_batch.id 必须带 BATCH- 前缀")
    ordinal = _require_int(payload["ordinal"], label="event.ingest_batch.ordinal", minimum=0)
    count = _require_int(payload["count"], label="event.ingest_batch.count", minimum=1)
    if ordinal >= count:
        raise LedgerCorruption("event.ingest_batch.ordinal 必须小于 count")
    return payload


def _validate_missing_fields(value: object) -> tuple[str, ...]:
    fields = _require_sequence(value, label="event.missing_fields")
    if any(not isinstance(item, str) or not item for item in fields):
        raise LedgerCorruption("event.missing_fields 必须是非空字符串数组")
    if len(set(fields)) != len(fields):
        raise LedgerCorruption("event.missing_fields 不得重复")
    return tuple(str(item) for item in fields)


def _validate_signal_content(content: Mapping[str, Any], missing: tuple[str, ...]) -> None:
    required = {
        "brief_schema",
        "report_id",
        "status",
        "actionable",
        "generated_at",
        "expected_next_trade_date",
        "account_id_source",
        "account_status",
        "decision",
        "market_regime",
        "router",
        "deconcentration_state",
        "data_quality",
    }
    if set(content) != required:
        raise LedgerCorruption("SIGNAL content 字段集合与协议不一致")
    if content["brief_schema"] != BRIEF_SCHEMA:
        raise LedgerCorruption("SIGNAL brief_schema 与协议不一致")
    _verify_hex64(content["report_id"], label="SIGNAL report_id")
    if content["status"] not in BRIEF_STATUSES:
        raise LedgerCorruption("SIGNAL status 不在协议枚举内")
    _require_bool(content["actionable"], label="SIGNAL actionable")
    if content["actionable"] != (content["status"] == "ACTIONABLE"):
        raise LedgerCorruption("SIGNAL actionable 与 status 不一致")
    _require_aware_instant(content["generated_at"], label="SIGNAL generated_at")
    if content["expected_next_trade_date"] is not None:
        _parse_ymd(content["expected_next_trade_date"], label="SIGNAL expected_next_trade_date")
    decision = _require_mapping(content["decision"], label="SIGNAL decision")
    if set(decision) != {
        "evidence_complete",
        "no_action_reason",
        "observation_triggers",
        "suppressed_recommendation_count",
    }:
        raise LedgerCorruption("SIGNAL decision 字段集合与协议不一致")
    _require_bool(decision["evidence_complete"], label="SIGNAL decision.evidence_complete")
    if content["status"] == "DATA_INSUFFICIENT" and decision["evidence_complete"]:
        raise LedgerCorruption("DATA_INSUFFICIENT SIGNAL 不得声称 evidence_complete")
    if content["status"] != "DATA_INSUFFICIENT" and not decision["evidence_complete"]:
        raise LedgerCorruption("非 DATA_INSUFFICIENT SIGNAL 必须 evidence_complete")
    if decision["no_action_reason"] is not None:
        _require_str(decision["no_action_reason"], label="SIGNAL decision.no_action_reason")
    triggers = _require_sequence(
        decision["observation_triggers"], label="SIGNAL decision.observation_triggers"
    )
    if any(not isinstance(item, str) for item in triggers):
        raise LedgerCorruption("SIGNAL observation_triggers 必须是字符串数组")
    _require_int(
        decision["suppressed_recommendation_count"],
        label="SIGNAL decision.suppressed_recommendation_count",
        minimum=0,
    )
    if content["market_regime"] is not None:
        _require_mapping(content["market_regime"], label="SIGNAL market_regime")
    if content["router"] is not None:
        _require_mapping(content["router"], label="SIGNAL router")
    if content["deconcentration_state"] is not None:
        _require_mapping(content["deconcentration_state"], label="SIGNAL deconcentration_state")
    for name, value in (
        ("v3_cockpit.market_regime", content["market_regime"]),
        ("v3_cockpit.router", content["router"]),
        ("v3_cockpit.deconcentration", content["deconcentration_state"]),
    ):
        if value is None and name not in missing:
            raise LedgerCorruption(f"SIGNAL {name} 为空但未记入 missing_fields")
    data_quality = _require_mapping(content["data_quality"], label="SIGNAL data_quality")
    for key in ("status", "summary_status", "missing_fields"):
        if key not in data_quality and f"data_quality.{key}" not in missing:
            raise LedgerCorruption(f"SIGNAL data_quality.{key} 缺失但未记入 missing_fields")
    complete = decision["evidence_complete"]
    if complete and (content["market_regime"] is None or content["router"] is None):
        raise LedgerCorruption("SIGNAL evidence_complete 但缺少核心 V3 状态")
    if not complete and not missing:
        raise LedgerCorruption("不完整的 SIGNAL 必须显式列出 missing_fields")


def _validate_action(action: object) -> Mapping[str, Any]:
    payload = _require_mapping(action, label="RECOMMENDATION action")
    for key in payload:
        if key in FORBIDDEN_RECOMMENDATION_KEYS:
            raise LedgerRefusal(f"recommendation 不得混入成交字段: {key}")
    priority = _require_str(payload.get("priority"), label="action.priority")
    if priority not in ACTION_PRIORITIES:
        raise LedgerRefusal(f"action.priority 不在协议枚举内: {priority}")
    kind = _require_str(payload.get("kind"), label="action.kind")
    if kind not in ACTION_KINDS:
        raise LedgerRefusal(f"action.kind 不在协议枚举内: {kind}")
    _require_str(payload.get("code"), label="action.code")
    _require_int(payload.get("rank"), label="action.rank", minimum=1)
    _require_str(payload.get("title"), label="action.title")
    for key in (
        "reasons",
        "counter_evidence",
        "triggers",
        "invalidation_conditions",
        "risk_impact",
    ):
        values = _require_sequence(payload.get(key), label=f"action.{key}")
        if any(not isinstance(item, str) for item in values):
            raise LedgerRefusal(f"action.{key} 必须是字符串数组")
    _require_int(payload.get("fees_cents"), label="action.fees_cents", minimum=0)
    _require_bool(payload.get("fees_assumed"), label="action.fees_assumed")
    legs = _require_sequence(payload.get("legs"), label="action.legs")
    if not legs:
        raise LedgerRefusal("action.legs 不得为空：没有腿的动作不是 recommendation")
    for index, raw_leg in enumerate(legs):
        leg = _require_mapping(raw_leg, label=f"action.legs[{index}]")
        for key in leg:
            if key in FORBIDDEN_RECOMMENDATION_KEYS:
                raise LedgerRefusal(f"recommendation leg 不得混入成交字段: {key}")
        side = _require_str(leg.get("side"), label=f"action.legs[{index}].side")
        if side not in LEG_SIDES:
            raise LedgerRefusal(f"action.legs[{index}].side 不在协议枚举内: {side}")
        _require_str(leg.get("ts_code"), label=f"action.legs[{index}].ts_code")
        _require_int(leg.get("quantity"), label=f"action.legs[{index}].quantity", minimum=0)
        _require_int(leg.get("price_milli"), label=f"action.legs[{index}].price_milli", minimum=0)
        _require_bool(leg.get("executable"), label=f"action.legs[{index}].executable")
    return payload


def _validate_recommendation_content(content: Mapping[str, Any]) -> None:
    required = {
        "brief_schema",
        "report_id",
        "status",
        "generated_at",
        "expected_execution_date",
        "action",
    }
    if set(content) != required:
        raise LedgerCorruption("RECOMMENDATION content 字段集合与协议不一致")
    if content["brief_schema"] != BRIEF_SCHEMA:
        raise LedgerCorruption("RECOMMENDATION brief_schema 与协议不一致")
    _verify_hex64(content["report_id"], label="RECOMMENDATION report_id")
    if content["status"] not in BRIEF_STATUSES:
        raise LedgerCorruption("RECOMMENDATION status 不在协议枚举内")
    if content["status"] == "DATA_INSUFFICIENT":
        raise LedgerCorruption("DATA_INSUFFICIENT 不得产生 RECOMMENDATION")
    _require_aware_instant(content["generated_at"], label="RECOMMENDATION generated_at")
    if content["expected_execution_date"] is not None:
        _parse_ymd(
            content["expected_execution_date"], label="RECOMMENDATION expected_execution_date"
        )
    try:
        _validate_action(content["action"])
    except LedgerRefusal as error:
        raise LedgerCorruption(f"RECOMMENDATION action 非法: {error}") from error


def _validate_holding(holding: object, *, index: int, missing: list[str]) -> Mapping[str, Any]:
    source = _require_mapping(holding, label=f"valuation holdings[{index}]")
    payload = dict(source)
    for field in HOLDING_REQUIRED_FIELDS:
        if field not in payload:
            raise LedgerRefusal(f"valuation holdings[{index}].{field} 缺失")
    _require_str(payload["ts_code"], label=f"holdings[{index}].ts_code")
    _require_int(payload["quantity"], label=f"holdings[{index}].quantity", minimum=0)
    _require_number(payload["weight"], label=f"holdings[{index}].weight")
    _require_int(
        payload["market_value_cents"], label=f"holdings[{index}].market_value_cents", minimum=0
    )
    _require_int(payload["price_milli"], label=f"holdings[{index}].price_milli", minimum=0)
    _require_str(payload["bar_quality"], label=f"holdings[{index}].bar_quality")
    _require_str(payload["stance"], label=f"holdings[{index}].stance")
    for field in HOLDING_EXPECTED_FIELDS:
        if payload.get(field) is None:
            missing.append(f"holdings[{index}].{field}")
            payload[field] = None
    return payload


def _validate_valuation_content(content: Mapping[str, Any], missing: tuple[str, ...]) -> None:
    if missing != tuple(sorted(set(missing))):
        raise LedgerCorruption("VALUATION missing_fields 必须排序且去重")
    required = {
        "brief_schema",
        "report_id",
        "status",
        "generated_at",
        "principal",
        "holdings",
        "concentration",
        "reconciliation_reminder",
        "data_quality",
    }
    if set(content) != required:
        raise LedgerCorruption("VALUATION content 字段集合与协议不一致")
    if content["brief_schema"] != BRIEF_SCHEMA:
        raise LedgerCorruption("VALUATION brief_schema 与协议不一致")
    _verify_hex64(content["report_id"], label="VALUATION report_id")
    if content["status"] not in BRIEF_STATUSES:
        raise LedgerCorruption("VALUATION status 不在协议枚举内")
    if content["status"] == "DATA_INSUFFICIENT":
        raise LedgerCorruption("DATA_INSUFFICIENT 不得产生 VALUATION")
    _require_aware_instant(content["generated_at"], label="VALUATION generated_at")
    principal = _require_mapping(content["principal"], label="VALUATION principal")
    for field in PRINCIPAL_FIELDS:
        if field not in principal:
            raise LedgerCorruption(f"VALUATION principal.{field} 缺失")
    _require_int(
        principal["initial_principal_cents"], label="principal.initial_principal_cents", minimum=1
    )
    _require_int(principal["current_nav_cents"], label="principal.current_nav_cents", minimum=1)
    _require_int(principal["to_principal_gap_cents"], label="principal.to_principal_gap_cents")
    _require_number(
        principal["to_principal_return_needed_pct"],
        label="principal.to_principal_return_needed_pct",
    )
    _require_number(principal["loss_from_principal_pct"], label="principal.loss_from_principal_pct")
    holdings = _require_sequence(content["holdings"], label="VALUATION holdings")
    derived_missing: list[str] = []
    for index, holding in enumerate(holdings):
        _validate_holding(holding, index=index, missing=derived_missing)
    if content["concentration"] is not None:
        _require_mapping(content["concentration"], label="VALUATION concentration")
    else:
        derived_missing.append("concentration")
    if content["reconciliation_reminder"] is not None:
        _require_mapping(content["reconciliation_reminder"], label="VALUATION reconciliation")
    else:
        derived_missing.append("v3_cockpit.reconciliation_reminder")
    _require_mapping(content["data_quality"], label="VALUATION data_quality")
    if not set(derived_missing).issubset(set(missing)):
        raise LedgerCorruption("VALUATION missing_fields 未显式覆盖全部缺失字段")


def _validate_fill_content(content: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "account_id",
        "event_id",
        "event_type",
        "occurred_on",
        "settled_on",
        "ts_code",
        "quantity",
        "price_milli",
        "gross_cents",
        "fee_cents",
        "tax_cents",
        "cash_delta_cents",
        "ratio_num",
        "ratio_den",
        "reverses_event_id",
        "reversed_by",
        "note",
        "source",
        "recorded_at",
    }
    if set(content) != required:
        raise LedgerCorruption("CONFIRMED_FILL content 字段集合与协议不一致")
    if content["schema"] != "financemcp.account_event/1.0":
        raise LedgerCorruption("CONFIRMED_FILL schema 与协议不一致")
    _require_str(content["account_id"], label="fill.account_id")
    _require_str(content["event_id"], label="fill.event_id")
    if content["event_type"] not in CONFIRMED_FILL_EVENT_TYPES:
        raise LedgerCorruption("CONFIRMED_FILL event_type 不在协议枚举内")
    _parse_ymd(content["occurred_on"], label="fill.occurred_on")
    if content["settled_on"] is not None:
        _parse_ymd(content["settled_on"], label="fill.settled_on")
    _require_str(content["ts_code"], label="fill.ts_code")
    _require_int(content["quantity"], label="fill.quantity", minimum=1)
    _require_int(content["price_milli"], label="fill.price_milli", minimum=1)
    _require_int(content["gross_cents"], label="fill.gross_cents", minimum=0)
    _require_int(content["fee_cents"], label="fill.fee_cents", minimum=0)
    _require_int(content["tax_cents"], label="fill.tax_cents", minimum=0)
    _require_int(content["cash_delta_cents"], label="fill.cash_delta_cents")
    if content["source"] not in CONFIRMED_FILL_SOURCES:
        raise LedgerCorruption("CONFIRMED_FILL source 必须是券商对账单")
    if content["reversed_by"] is not None:
        raise LedgerCorruption("CONFIRMED_FILL 不得是已撤销成交")
    _require_aware_instant(content["recorded_at"], label="fill.recorded_at")


def _validate_reason_content(content: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "recommendation_event_id",
        "reason_code",
        "scope",
        "reason_note",
        "decided_on",
    }
    if set(content) != required:
        raise LedgerCorruption("UNEXECUTED_REASON content 字段集合与协议不一致")
    if content["schema"] != REASON_SCHEMA:
        raise LedgerCorruption("UNEXECUTED_REASON schema 与协议不一致")
    _require_str(content["recommendation_event_id"], label="reason.recommendation_event_id")
    if content["reason_code"] not in REASON_CODES:
        raise LedgerCorruption("UNEXECUTED_REASON reason_code 不在协议枚举内")
    if content["scope"] not in REASON_SCOPES:
        raise LedgerCorruption("UNEXECUTED_REASON scope 不在协议枚举内")
    note = _require_str(content["reason_note"], label="reason.reason_note").strip()
    if not note:
        raise LedgerCorruption("UNEXECUTED_REASON reason_note 不得为空白")
    _parse_ymd(content["decided_on"], label="reason.decided_on")


def _validate_content(record_type: str, content: object, missing: tuple[str, ...]) -> None:
    payload = _require_mapping(content, label=f"{record_type}.content")
    try:
        if record_type == "SIGNAL":
            _validate_signal_content(payload, missing)
        elif record_type == "RECOMMENDATION":
            _validate_recommendation_content(payload)
        elif record_type == "VALUATION":
            _validate_valuation_content(payload, missing)
        elif record_type == "CONFIRMED_FILL":
            _validate_fill_content(payload)
        elif record_type == "UNEXECUTED_REASON":
            _validate_reason_content(payload)
        else:
            raise LedgerCorruption(f"未知 record_type: {record_type}")
    except LedgerRefusal as error:
        raise LedgerCorruption(f"{record_type} content 非法: {error}") from error


def _validate_event(event: object, *, record_type: str, manifest: Manifest) -> Mapping[str, Any]:
    payload = _require_mapping(event, label=f"{record_type} event")
    if set(payload) != ENVELOPE_KEYS:
        raise LedgerCorruption("事件信封字段集合与协议不一致")
    if payload["record_type"] != record_type:
        raise LedgerCorruption(f"事件 record_type 与文件不一致: {payload['record_type']}")
    if payload["ledger_version"] != LEDGER_VERSION:
        raise LedgerCorruption("事件 ledger_version 与协议不一致")
    if payload["protocol_commit"] != PROTOCOL_COMMIT:
        raise LedgerCorruption("事件 protocol_commit 与协议不一致")
    if payload["account_id"] != manifest.account_id:
        raise LedgerCorruption("事件 account_id 与 manifest 不一致")
    as_of = _parse_ymd(payload["as_of_trade_date"], label="event.as_of_trade_date")
    if as_of < manifest.earliest_eligible_day:
        raise LedgerCorruption("事件早于最早合格日")
    natural_key = _require_str(payload["natural_key"], label="event.natural_key")
    if not natural_key.startswith(f"{record_type}:"):
        raise LedgerCorruption(f"事件 natural_key 必须带 {record_type}: 前缀")
    source = _validate_source(payload["source"])
    expected_source_kind = {
        "SIGNAL": "financemcp_daily_brief",
        "RECOMMENDATION": "financemcp_daily_brief",
        "VALUATION": "financemcp_daily_brief",
        "CONFIRMED_FILL": "financemcp_portfolio_sqlite",
        "UNEXECUTED_REASON": "explicit_operator_input",
    }[record_type]
    if source["kind"] != expected_source_kind:
        raise LedgerCorruption(
            f"{record_type} source.kind 必须是 {expected_source_kind}，实际 {source['kind']!r}"
        )
    missing = _validate_missing_fields(payload["missing_fields"])
    policy_required = record_type in {"RECOMMENDATION", "VALUATION"} or (
        record_type == "SIGNAL"
        and not any(field == "v3_cockpit" or field.startswith("v3_cockpit.") for field in missing)
    )
    _validate_policy(payload["policy"], required=policy_required)
    _validate_batch(payload["ingest_batch"])
    recorded_at = _require_aware_instant(payload["recorded_at"], label="event.recorded_at")
    if _ymd_of(recorded_at) < as_of:
        raise LedgerCorruption("事件 recorded_at 早于 as_of_trade_date")
    declared_hash = _verify_hex64(payload["content_hash"], label="event.content_hash")
    actual_hash = content_hash(
        record_type, _require_mapping(payload["content"], label="event.content")
    )
    if declared_hash != actual_hash:
        raise LedgerCorruption("事件 content_hash 与其 content 不一致")
    if payload["event_id"] != event_id_for(actual_hash):
        raise LedgerCorruption("事件 event_id 与其 content_hash 不一致")
    _validate_content(record_type, payload["content"], missing)
    if (
        record_type == "CONFIRMED_FILL"
        and payload["content"]["account_id"] != payload["account_id"]
    ):
        raise LedgerCorruption("CONFIRMED_FILL content.account_id 与事件 account_id 不一致")
    if not isinstance(natural_key, str) or not natural_key:
        raise LedgerCorruption("事件 natural_key 必须非空")
    _verify_hex64(payload["prev_event_hash"], label="event.prev_event_hash")
    declared_event_hash = _verify_hex64(payload["event_hash"], label="event.event_hash")
    material = {key: value for key, value in payload.items() if key != "event_hash"}
    if sha256_text(canonical_json(material)) != declared_event_hash:
        raise LedgerCorruption("事件 event_hash 与完整行内容不一致")
    return payload


def read_events(
    root: Path | str | None, record_type: str, *, manifest: Manifest | None = None
) -> list[dict[str, Any]]:
    resolved = ledger_root(root)
    active = manifest or load_manifest(resolved)
    path = _record_path(resolved, record_type)
    if not path.is_file():
        raise LedgerCorruption(f"台账缺少 {path.name}")
    raw = path.read_text(encoding="utf-8")
    if raw and not raw.endswith("\n"):
        raise LedgerCorruption(f"{path.name} 存在未完成的半行写入")
    events: list[dict[str, Any]] = []
    previous = ZERO_HASH
    natural_keys: set[str] = set()
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            raise LedgerCorruption(f"{path.name} 第 {line_number} 行为空")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise LedgerCorruption(f"{path.name} 第 {line_number} 行不是合法 JSON") from error
        validated = _validate_event(event, record_type=record_type, manifest=active)
        if validated["prev_event_hash"] != previous:
            raise LedgerCorruption(f"{path.name} 第 {line_number} 行哈希链断裂")
        previous = str(validated["event_hash"])
        key = str(validated["natural_key"])
        if key in natural_keys:
            raise LedgerCorruption(f"{path.name} 出现重复 natural_key: {key}")
        natural_keys.add(key)
        events.append(dict(validated))
    return events


def _read_all_events(
    root: Path | str | None, manifest: Manifest | None = None
) -> dict[str, list[dict[str, Any]]]:
    active = manifest or load_manifest(root)
    return {
        record_type: read_events(root, record_type, manifest=active) for record_type in RECORD_FILES
    }


def _verify_batches(events_by_type: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, int]:
    batches: dict[str, tuple[int, set[int]]] = {}
    for events in events_by_type.values():
        for event in events:
            batch = event["ingest_batch"]
            identifier = str(batch["id"])
            count = int(batch["count"])
            ordinal = int(batch["ordinal"])
            if identifier not in batches:
                batches[identifier] = (count, set())
            existing_count, ordinals = batches[identifier]
            if existing_count != count:
                raise LedgerCorruption(f"batch {identifier} 的 count 不一致")
            if ordinal in ordinals:
                raise LedgerCorruption(f"batch {identifier} 的 ordinal {ordinal} 重复")
            ordinals.add(ordinal)
    for identifier, (count, ordinals) in batches.items():
        if ordinals != set(range(count)):
            raise LedgerCorruption(f"batch {identifier} 不完整: {sorted(ordinals)} / {count}")
    return {identifier: count for identifier, (count, _) in batches.items()}


# --------------------------------------------------------------------------------------
# Append machinery
# --------------------------------------------------------------------------------------


def _sort_drafts(drafts: Sequence[Draft]) -> list[Draft]:
    return sorted(
        drafts,
        key=lambda draft: (
            RECORD_ORDER[draft.record_type],
            draft.as_of_trade_date,
            draft.natural_key,
        ),
    )


def _batch_id(kind: str, source_sha: str, ordered: Sequence[Draft]) -> str:
    material = "\n".join([kind, source_sha, *(draft.content_hash for draft in ordered)])
    return BATCH_ID_PREFIX + sha256_text(material)[:24]


def _append_drafts(
    root: Path | str | None,
    drafts: Sequence[Draft],
    *,
    batch_kind: str,
    batch_source_sha: str,
) -> dict[str, Any]:
    """先完成全部校验，再按固定顺序追加；被拒绝时既有 bytes 不变。"""
    resolved = ledger_root(root)
    manifest = load_manifest(resolved)
    ordered = _sort_drafts(drafts)
    batch_id = _batch_id(batch_kind, batch_source_sha, ordered)
    events_by_type = _read_all_events(resolved, manifest)
    existing_by_key: dict[str, Mapping[str, Any]] = {}
    for events in events_by_type.values():
        for event in events:
            existing_by_key[str(event["natural_key"])] = event
    seen_drafts: dict[str, Draft] = {}
    for draft in ordered:
        _parse_ymd(draft.as_of_trade_date, label="draft.as_of_trade_date")
        _validate_source(draft.source)
        policy_required = draft.record_type in {"RECOMMENDATION", "VALUATION"} or (
            draft.record_type == "SIGNAL"
            and not any(
                field == "v3_cockpit" or field.startswith("v3_cockpit.")
                for field in draft.missing_fields
            )
        )
        _validate_policy(draft.policy, required=policy_required)
        if draft.missing_fields != tuple(sorted(set(draft.missing_fields))):
            raise LedgerCorruption("draft.missing_fields 必须排序且去重")
        _validate_content(draft.record_type, draft.content, draft.missing_fields)
        if draft.natural_key in seen_drafts:
            raise LedgerConflict(f"同一批输入产生重复 natural_key: {draft.natural_key}")
        seen_drafts[draft.natural_key] = draft
        prior = existing_by_key.get(draft.natural_key)
        if prior is not None and prior["content_hash"] != draft.content_hash:
            raise LedgerConflict(
                f"{draft.record_type} natural_key={draft.natural_key} 已存在不同内容；"
                "append-only 协议拒绝覆盖"
            )
    recorded_at = utc_now()
    appended = {record_type: 0 for record_type in RECORD_FILES}
    skipped = {record_type: 0 for record_type in RECORD_FILES}
    count = len(ordered)
    last_hashes = {
        record_type: (events[-1]["event_hash"] if events else ZERO_HASH)
        for record_type, events in events_by_type.items()
    }
    for ordinal, draft in enumerate(ordered):
        if draft.natural_key in existing_by_key:
            skipped[draft.record_type] += 1
            continue
        event = {
            "ledger_version": LEDGER_VERSION,
            "protocol_commit": PROTOCOL_COMMIT,
            "record_type": draft.record_type,
            "event_id": event_id_for(draft.content_hash),
            "natural_key": draft.natural_key,
            "account_id": manifest.account_id,
            "as_of_trade_date": draft.as_of_trade_date,
            "source": draft.source,
            "policy": draft.policy,
            "missing_fields": list(draft.missing_fields),
            "ingest_batch": {"id": batch_id, "ordinal": ordinal, "count": count},
            "recorded_at": recorded_at.isoformat(),
            "content_hash": draft.content_hash,
            "content": draft.content,
            "prev_event_hash": last_hashes[draft.record_type],
        }
        event["event_hash"] = sha256_text(canonical_json(event))
        _validate_event(event, record_type=draft.record_type, manifest=manifest)
        with _record_path(resolved, draft.record_type).open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        last_hashes[draft.record_type] = str(event["event_hash"])
        existing_by_key[draft.natural_key] = event
        appended[draft.record_type] += 1
    total_appended = sum(appended.values())
    return {
        "status": "INGESTED" if total_appended else "IDEMPOTENT_NOOP",
        "batch_id": batch_id,
        "batch_event_count": count,
        "appended": appended,
        "skipped_idempotent": skipped,
        "total_appended": total_appended,
        "recorded_at": recorded_at.isoformat(),
    }


# --------------------------------------------------------------------------------------
# FinanceMCP daily brief ingestion
# --------------------------------------------------------------------------------------


def _read_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LedgerRefusal(f"{label} 不是合法 UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise LedgerRefusal(f"{label} 必须是 JSON object")
    return payload


def _policy_identity(brief: Mapping[str, Any]) -> dict[str, str] | None:
    cockpit = brief.get("v3_cockpit")
    if not isinstance(cockpit, Mapping):
        return None
    release = cockpit.get("policy_release")
    if not isinstance(release, Mapping):
        return None
    identity: dict[str, str] = {}
    for key in POLICY_KEYS:
        value = release.get(key)
        if not isinstance(value, str) or not value:
            raise LedgerRefusal(f"v3_cockpit.policy_release.{key} 缺失")
        identity[key] = value
    return identity


def _validate_brief(brief: Mapping[str, Any], *, account_id: str, now: datetime) -> dict[str, Any]:
    if brief.get("schema") != BRIEF_SCHEMA:
        raise LedgerRefusal(f"brief schema 必须是 {BRIEF_SCHEMA}")
    report_id = _verify_hex64(brief.get("report_id"), label="brief.report_id")
    as_of = _parse_ymd(brief.get("as_of_trade_date"), label="brief.as_of_trade_date")
    if as_of < EARLIEST_ELIGIBLE_DAY:
        raise LedgerRefusal(f"brief as_of={as_of} 早于最早合格日 {EARLIEST_ELIGIBLE_DAY}；不得回填")
    status = brief.get("status")
    if status not in BRIEF_STATUSES:
        raise LedgerRefusal(f"brief.status 不在协议枚举内: {status!r}")
    actionable = _require_bool(brief.get("actionable"), label="brief.actionable")
    if actionable != (status == "ACTIONABLE"):
        raise LedgerRefusal("brief.actionable 与 status 不一致")
    generated_at = _require_aware_instant(brief.get("generated_at"), label="brief.generated_at")
    if _ymd_of(generated_at) != as_of:
        raise LedgerRefusal("brief.generated_at 的上海日历日必须等于 as_of_trade_date")
    now_shanghai = _shanghai(now)
    if now_shanghai.strftime("%Y%m%d") != as_of:
        raise LedgerRefusal(
            "brief 只能在其 as_of 的上海日历日当天追加；当天未运行即永久 MISSED，不得次日补录或回填"
        )
    if now < generated_at:
        raise LedgerRefusal("台账运行时钟早于 brief.generated_at：不得消费尚未生成的日报")
    if brief.get("account_id") != account_id:
        raise LedgerRefusal(f"brief.account_id 必须是 {account_id}")
    if brief.get("account_status") != REAL_ACCOUNT_STATUS:
        raise LedgerRefusal(
            f"brief.account_status 必须是 {REAL_ACCOUNT_STATUS}；拒绝未确认的真实账户之外的数据"
        )
    expected_next = brief.get("expected_next_trade_date")
    if expected_next is not None:
        expected_next = _parse_ymd(expected_next, label="brief.expected_next_trade_date")
        if expected_next <= as_of:
            raise LedgerRefusal("brief.expected_next_trade_date 必须晚于 as_of_trade_date")
    first_section = _require_mapping(brief.get("first_section"), label="brief.first_section")
    for key in ("count", "actions", "no_action_reason", "observation_triggers"):
        if key not in first_section:
            raise LedgerRefusal(f"brief.first_section.{key} 缺失")
    first_actions = _require_sequence(
        first_section.get("actions"), label="brief.first_section.actions"
    )
    first_count = _require_int(
        first_section.get("count"), label="brief.first_section.count", minimum=0
    )
    if first_count != len(first_actions):
        raise LedgerRefusal("brief.first_section.count 与 actions 长度不一致")
    triggers = _require_sequence(
        first_section.get("observation_triggers"),
        label="brief.first_section.observation_triggers",
    )
    if any(not isinstance(item, str) for item in triggers):
        raise LedgerRefusal("brief.first_section.observation_triggers 必须是字符串数组")
    account_id_source = brief.get("account_id_source")
    if account_id_source is not None and (
        not isinstance(account_id_source, str) or not account_id_source
    ):
        raise LedgerRefusal("brief.account_id_source 必须是非空字符串或 null")
    execution_plan = _require_mapping(brief.get("execution_plan"), label="brief.execution_plan")
    actions = _require_sequence(execution_plan.get("actions"), label="brief.execution_plan.actions")
    plan_count = _require_int(
        execution_plan.get("count"), label="brief.execution_plan.count", minimum=0
    )
    if plan_count != len(actions):
        raise LedgerRefusal("brief.execution_plan.count 与 actions 长度不一致")
    for index, action in enumerate(actions):
        try:
            _validate_action(action)
        except LedgerRefusal as error:
            raise LedgerRefusal(f"brief.execution_plan.actions[{index}] 非法: {error}") from error
    if not isinstance(brief.get("holdings"), list):
        raise LedgerRefusal("brief.holdings 必须是 JSON array")
    if not isinstance(brief.get("data_quality"), Mapping):
        raise LedgerRefusal("brief.data_quality 必须是 JSON object")
    concentration = brief.get("concentration")
    if concentration is not None and not isinstance(concentration, Mapping):
        raise LedgerRefusal("brief.concentration 必须是 JSON object 或 null")
    no_action_reason = first_section.get("no_action_reason")
    if status in {"NO_ACTION", "DATA_INSUFFICIENT"}:
        if not isinstance(no_action_reason, str) or not no_action_reason.strip():
            raise LedgerRefusal(f"{status} brief 必须带有非空 no_action_reason")
    elif no_action_reason is not None:
        raise LedgerRefusal(f"{status} brief 的 no_action_reason 必须为 null")
    if status == "NO_ACTION" and actions:
        raise LedgerRefusal("NO_ACTION brief 不得携带执行动作")
    if status == "ACTIONABLE" and not actions:
        raise LedgerRefusal("ACTIONABLE brief 必须至少有一个动作")
    executable_legs = [
        leg for action in actions for leg in action["legs"] if leg.get("executable") is True
    ]
    if status == "ACTIONABLE" and not executable_legs:
        raise LedgerRefusal("ACTIONABLE brief 必须至少有一条 executable leg")
    if status == "ACTIONABLE" and not any(leg.get("quantity", 0) > 0 for leg in executable_legs):
        raise LedgerRefusal("ACTIONABLE brief 的 executable leg 数量必须为正")
    if status != "ACTIONABLE" and executable_legs:
        raise LedgerRefusal(f"{status} brief 不得包含 executable leg")
    cockpit = brief.get("v3_cockpit")
    if status != "DATA_INSUFFICIENT":
        cockpit = _require_mapping(cockpit, label="brief.v3_cockpit")
        for key in ("policy_release", "principal", "market_regime", "router", "deconcentration"):
            if not isinstance(cockpit.get(key), Mapping):
                raise LedgerRefusal(f"brief.v3_cockpit.{key} 缺失")
    elif cockpit is not None and not isinstance(cockpit, Mapping):
        raise LedgerRefusal("brief.v3_cockpit 必须是 JSON object 或 null")
    policy = _policy_identity(brief) if isinstance(cockpit, Mapping) else None
    if status != "DATA_INSUFFICIENT" and policy is None:
        raise LedgerRefusal("非 DATA_INSUFFICIENT brief 必须携带 V3 policy_release 身份")
    return {
        "report_id": report_id,
        "as_of_trade_date": as_of,
        "status": status,
        "generated_at": generated_at,
        "expected_next_trade_date": expected_next,
        "account_id_source": brief.get("account_id_source"),
        "account_status": brief.get("account_status"),
        "first_section": first_section,
        "actions": actions,
        "holdings": brief.get("holdings"),
        "concentration": brief.get("concentration"),
        "data_quality": brief.get("data_quality"),
        "cockpit": cockpit,
        "policy": policy,
    }


def _brief_source_identity(
    brief: Mapping[str, Any], *, path: Path, raw_sha: str, generated_at: str
) -> dict[str, Any]:
    return {
        "kind": "financemcp_daily_brief",
        "identity": {
            "path": str(path),
            "report_id": brief["report_id"],
            "generated_at": generated_at,
            "schema": brief["schema"],
        },
        "sha256": raw_sha,
        "schema_fingerprint": None,
    }


def _signal_content(validated: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    if validated["status"] == "DATA_INSUFFICIENT":
        missing.append("source_data_insufficient")
    first = validated["first_section"]
    if validated["expected_next_trade_date"] is None:
        missing.append("expected_next_trade_date")
    if validated["account_id_source"] is None:
        missing.append("account_id_source")
    triggers = first.get("observation_triggers")
    if triggers is None:
        missing.append("first_section.observation_triggers")
        triggers = []
    cockpit = validated["cockpit"]
    market_regime: Mapping[str, Any] | None = None
    router: Mapping[str, Any] | None = None
    deconcentration_state: Mapping[str, Any] | None = None
    if isinstance(cockpit, Mapping):
        market_regime = (
            cockpit.get("market_regime")
            if isinstance(cockpit.get("market_regime"), Mapping)
            else None
        )
        router = cockpit.get("router") if isinstance(cockpit.get("router"), Mapping) else None
        deconcentration_state = (
            cockpit.get("deconcentration")
            if isinstance(cockpit.get("deconcentration"), Mapping)
            else None
        )
    else:
        missing.extend(["v3_cockpit", "v3_cockpit.policy_release"])
    for name, value in (
        ("v3_cockpit.market_regime", market_regime),
        ("v3_cockpit.router", router),
        ("v3_cockpit.deconcentration", deconcentration_state),
    ):
        if value is None:
            missing.append(name)
    data_quality = copy.deepcopy(dict(validated["data_quality"]))
    for key in ("status", "summary_status", "missing_fields"):
        if key not in data_quality:
            missing.append(f"data_quality.{key}")
    suppressed = len(validated["actions"]) if validated["status"] == "DATA_INSUFFICIENT" else 0
    content = {
        "brief_schema": BRIEF_SCHEMA,
        "report_id": validated["report_id"],
        "status": validated["status"],
        "actionable": validated["status"] == "ACTIONABLE",
        "generated_at": validated["generated_at"].isoformat(),
        "expected_next_trade_date": validated["expected_next_trade_date"],
        "account_id_source": validated["account_id_source"],
        "account_status": validated["account_status"],
        "decision": {
            "evidence_complete": validated["status"] != "DATA_INSUFFICIENT",
            "no_action_reason": first.get("no_action_reason"),
            "observation_triggers": [str(item) for item in triggers],
            "suppressed_recommendation_count": suppressed,
        },
        "market_regime": copy.deepcopy(market_regime) if market_regime is not None else None,
        "router": copy.deepcopy(router) if router is not None else None,
        "deconcentration_state": (
            copy.deepcopy(deconcentration_state) if deconcentration_state is not None else None
        ),
        "data_quality": data_quality,
    }
    return content, sorted(set(missing))


def _recommendation_drafts(
    validated: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    policy: Mapping[str, str],
    account_id: str,
) -> list[Draft]:
    if validated["status"] == "DATA_INSUFFICIENT":
        return []
    drafts: list[Draft] = []
    for action in validated["actions"]:
        content = {
            "brief_schema": BRIEF_SCHEMA,
            "report_id": validated["report_id"],
            "status": validated["status"],
            "generated_at": validated["generated_at"].isoformat(),
            "expected_execution_date": validated["expected_next_trade_date"],
            "action": copy.deepcopy(dict(action)),
        }
        drafts.append(
            Draft(
                record_type="RECOMMENDATION",
                natural_key=(
                    f"RECOMMENDATION:daily_brief:{account_id}:"
                    f"{validated['as_of_trade_date']}:{action['code']}:{action['rank']}"
                ),
                as_of_trade_date=validated["as_of_trade_date"],
                content=content,
                source=copy.deepcopy(dict(source)),
                policy=dict(policy),
                missing_fields=(),
            )
        )
    return drafts


def _valuation_content(validated: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    cockpit = _require_mapping(validated["cockpit"], label="brief.v3_cockpit")
    principal = _require_mapping(cockpit.get("principal"), label="v3_cockpit.principal")
    for field in PRINCIPAL_FIELDS:
        if field not in principal:
            raise LedgerRefusal(f"v3_cockpit.principal.{field} 缺失")
    holdings: list[dict[str, Any]] = []
    for index, holding in enumerate(validated["holdings"]):
        holdings.append(dict(_validate_holding(holding, index=index, missing=missing)))
    concentration = validated.get("concentration")
    if concentration is None:
        missing.append("concentration")
    reconciliation = cockpit.get("reconciliation_reminder")
    if reconciliation is None:
        missing.append("v3_cockpit.reconciliation_reminder")
    content = {
        "brief_schema": BRIEF_SCHEMA,
        "report_id": validated["report_id"],
        "status": validated["status"],
        "generated_at": validated["generated_at"].isoformat(),
        "principal": copy.deepcopy(dict(principal)),
        "holdings": copy.deepcopy(holdings),
        "concentration": copy.deepcopy(concentration) if concentration is not None else None,
        "reconciliation_reminder": (
            copy.deepcopy(reconciliation) if reconciliation is not None else None
        ),
        "data_quality": copy.deepcopy(dict(validated["data_quality"])),
    }
    return content, sorted(set(missing))


def ingest_brief(
    brief_path: Path | str,
    *,
    root: Path | str | None = None,
    account_id: str = LEDGER_ACCOUNT_ID,
) -> dict[str, Any]:
    """读取一份 FinanceMCP compact brief，追加 SIGNAL / RECOMMENDATION / VALUATION。"""
    resolved_root = ledger_root(root)
    manifest = load_manifest(resolved_root)
    if manifest.account_id != account_id:
        raise LedgerRefusal("请求的 account_id 与 manifest 不一致")
    path = Path(brief_path)
    if not path.is_file():
        raise LedgerRefusal(f"brief 文件不存在: {path}")
    raw = path.read_bytes()
    raw_sha = sha256_bytes(raw)
    brief = _read_json_object(raw, label="brief")
    validated = _validate_brief(brief, account_id=account_id, now=utc_now())
    source = _brief_source_identity(
        brief, path=path, raw_sha=raw_sha, generated_at=validated["generated_at"].isoformat()
    )
    policy = validated["policy"]
    drafts: list[Draft] = []
    signal_content, signal_missing = _signal_content(validated)
    signal_policy = dict(policy) if policy is not None else None
    drafts.append(
        Draft(
            record_type="SIGNAL",
            natural_key=f"SIGNAL:daily_brief:{account_id}:{validated['as_of_trade_date']}",
            as_of_trade_date=validated["as_of_trade_date"],
            content=signal_content,
            source=copy.deepcopy(source),
            policy=signal_policy,
            missing_fields=tuple(signal_missing),
        )
    )
    if validated["status"] != "DATA_INSUFFICIENT":
        assert policy is not None
        drafts.extend(
            _recommendation_drafts(validated, source=source, policy=policy, account_id=account_id)
        )
        valuation_content, valuation_missing = _valuation_content(validated)
        drafts.append(
            Draft(
                record_type="VALUATION",
                natural_key=f"VALUATION:daily_brief:{account_id}:{validated['as_of_trade_date']}",
                as_of_trade_date=validated["as_of_trade_date"],
                content=valuation_content,
                source=copy.deepcopy(source),
                policy=dict(policy),
                missing_fields=tuple(valuation_missing),
            )
        )
    if policy is not None:
        _check_policy_baseline(resolved_root, policy)
    result = _append_drafts(
        resolved_root, drafts, batch_kind="daily_brief", batch_source_sha=raw_sha
    )
    if policy is not None:
        _write_policy_baseline(
            resolved_root,
            policy,
            as_of_trade_date=validated["as_of_trade_date"],
            source_sha256=raw_sha,
            created_at=utc_now(),
        )
    return {
        **result,
        "brief": {
            "report_id": validated["report_id"],
            "as_of_trade_date": validated["as_of_trade_date"],
            "status": validated["status"],
            "generated_at": validated["generated_at"].isoformat(),
            "source_sha256": raw_sha,
        },
        "missing_fields": {
            draft.record_type: list(draft.missing_fields)
            for draft in drafts
            if draft.missing_fields
        },
    }


# --------------------------------------------------------------------------------------
# Confirmed fills from the read-only private account database
# --------------------------------------------------------------------------------------


def _open_readonly_sqlite(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise LedgerRefusal(f"只读账户库不存在: {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _account_event_schema_fingerprint(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT name, type, \"notnull\", pk FROM pragma_table_info('account_event') ORDER BY cid"
    ).fetchall()
    if not rows:
        raise LedgerRefusal("account_event 表不存在")
    columns = [dict(row) for row in rows]
    names = {str(column["name"]) for column in columns}
    missing = set(ACCOUNT_EVENT_COLUMNS).difference(names)
    if missing:
        raise LedgerRefusal(f"account_event 缺少协议字段: {sorted(missing)}")
    return sha256_text(canonical_json(columns))


def _require_verified_account(connection: sqlite3.Connection, account_id: str) -> None:
    try:
        row = connection.execute(
            "SELECT value FROM account_meta WHERE key = ?",
            (f"real_account_verified:{account_id}",),
        ).fetchone()
    except sqlite3.DatabaseError as error:
        raise LedgerRefusal("只读账户库缺少 account_meta 表") from error
    if row is None or str(row["value"]) != "1":
        raise LedgerRefusal(f"账户 {account_id} 未经 real_account_verified 确认；拒绝导入成交")


def _reversed_imported_fill_ids(
    connection: sqlite3.Connection, imported: Iterable[str]
) -> list[str]:
    imported_set = set(imported)
    if not imported_set:
        return []
    rows = connection.execute(
        "SELECT event_id FROM account_event WHERE reversed_by IS NOT NULL AND reversed_by != ''"
    ).fetchall()
    return sorted(str(row["event_id"]) for row in rows if str(row["event_id"]) in imported_set)


def _missing_imported_fill_ids(
    connection: sqlite3.Connection, imported: Iterable[str]
) -> list[str]:
    imported_set = set(imported)
    if not imported_set:
        return []
    rows = connection.execute("SELECT event_id FROM account_event").fetchall()
    present = {str(row["event_id"]) for row in rows}
    return sorted(imported_set.difference(present))


def _fill_drafts(
    connection: sqlite3.Connection,
    *,
    account_id: str,
    schema_fingerprint: str,
    db_path: Path,
    now_ymd: str,
) -> tuple[list[Draft], dict[str, int]]:
    skipped = {
        "before_earliest": 0,
        "after_now": 0,
        "not_broker_statement": 0,
        "reversed": 0,
        "other_account": 0,
    }
    rows = connection.execute(
        f"SELECT {', '.join(ACCOUNT_EVENT_COLUMNS)} FROM account_event "
        "WHERE event_type IN ('TRADE_BUY', 'TRADE_SELL') "
        "ORDER BY occurred_on, event_id"
    ).fetchall()
    drafts: list[Draft] = []
    for row in rows:
        record = {column: row[column] for column in ACCOUNT_EVENT_COLUMNS}
        event_source = record.get("source")
        if event_source not in CONFIRMED_FILL_SOURCES:
            skipped["not_broker_statement"] += 1
            continue
        if record.get("reversed_by") not in (None, ""):
            skipped["reversed"] += 1
            continue
        if record.get("account_id") != account_id:
            skipped["other_account"] += 1
            continue
        occurred_on = _parse_ymd(record.get("occurred_on"), label="account_event.occurred_on")
        if occurred_on < EARLIEST_ELIGIBLE_DAY:
            skipped["before_earliest"] += 1
            continue
        if occurred_on > now_ymd:
            skipped["after_now"] += 1
            continue
        record["schema"] = "financemcp.account_event/1.0"
        content = {key: record[key] for key in sorted(record)}
        row_sha = sha256_text(canonical_json(content))
        source = {
            "kind": "financemcp_portfolio_sqlite",
            "identity": {
                "path": str(db_path),
                "table": "account_event",
                "event_id": str(record["event_id"]),
                "db_recorded_at": record["recorded_at"],
            },
            "sha256": row_sha,
            "schema_fingerprint": schema_fingerprint,
        }
        drafts.append(
            Draft(
                record_type="CONFIRMED_FILL",
                natural_key=f"CONFIRMED_FILL:portfolio_sqlite:{account_id}:{record['event_id']}",
                as_of_trade_date=occurred_on,
                content=content,
                source=source,
                policy=None,
                missing_fields=(),
            )
        )
    return drafts, skipped


def ingest_confirmed_fills(
    *,
    portfolio_db: Path | str,
    root: Path | str | None = None,
    account_id: str = LEDGER_ACCOUNT_ID,
) -> dict[str, Any]:
    """只读导入券商对账单确认的成交；绝不把 recommendation 或 synthetic 当成成交。"""
    resolved_root = ledger_root(root)
    manifest = load_manifest(resolved_root)
    if manifest.account_id != account_id:
        raise LedgerRefusal("请求的 account_id 与 manifest 不一致")
    db_path = Path(portfolio_db)
    connection = _open_readonly_sqlite(db_path)
    try:
        _require_verified_account(connection, account_id)
        schema_fingerprint = _account_event_schema_fingerprint(connection)
        imported = [
            str(event["content"]["event_id"])
            for event in read_events(resolved_root, "CONFIRMED_FILL", manifest=manifest)
        ]
        reversed_imported = _reversed_imported_fill_ids(connection, imported)
        if reversed_imported:
            raise LedgerRefusal(
                "SOURCE_REVERSED_AFTER_IMPORT: 已导入成交在源库被撤销 "
                f"{reversed_imported}；建议暂停并人工复核，不得改写既有台账行"
            )
        missing_imported = _missing_imported_fill_ids(connection, imported)
        if missing_imported:
            raise LedgerRefusal(
                "SOURCE_FILL_MISSING_AFTER_IMPORT: 已导入成交在源库消失 "
                f"{missing_imported}；建议暂停并人工复核，不得删除既有台账行"
            )
        drafts, skipped = _fill_drafts(
            connection,
            account_id=account_id,
            schema_fingerprint=schema_fingerprint,
            db_path=db_path,
            now_ymd=_now_shanghai().strftime("%Y%m%d"),
        )
    finally:
        connection.close()
    if not drafts:
        return {
            "status": "NO_NEW_FILLS",
            "appended": {record_type: 0 for record_type in RECORD_FILES},
            "skipped_idempotent": {record_type: 0 for record_type in RECORD_FILES},
            "skipped_rows": skipped,
            "source_schema_fingerprint": schema_fingerprint,
        }
    source_sha = sha256_text(
        canonical_json([draft.content["event_id"] for draft in _sort_drafts(drafts)])
    )
    result = _append_drafts(
        resolved_root, drafts, batch_kind="confirmed_fills", batch_source_sha=source_sha
    )
    return {
        **result,
        "skipped_rows": skipped,
        "source_schema_fingerprint": schema_fingerprint,
        "source_db": str(db_path),
    }


# --------------------------------------------------------------------------------------
# Explicit unexecuted reasons
# --------------------------------------------------------------------------------------


def ingest_unexecuted_reason(
    input_path: Path | str,
    *,
    root: Path | str | None = None,
    account_id: str = LEDGER_ACCOUNT_ID,
) -> dict[str, Any]:
    """追加一条人类显式提供的未执行原因；不推断、不补造。"""
    resolved_root = ledger_root(root)
    manifest = load_manifest(resolved_root)
    if manifest.account_id != account_id:
        raise LedgerRefusal("请求的 account_id 与 manifest 不一致")
    path = Path(input_path)
    if not path.is_file():
        raise LedgerRefusal(f"未执行原因输入不存在: {path}")
    raw = path.read_bytes()
    payload = _read_json_object(raw, label="unexecuted reason")
    if payload.get("schema") != REASON_SCHEMA:
        raise LedgerRefusal(f"unexecuted reason schema 必须是 {REASON_SCHEMA}")
    recommendation_event_id = _require_str(
        payload.get("recommendation_event_id"), label="reason.recommendation_event_id"
    )
    reason_code = _require_str(payload.get("reason_code"), label="reason.reason_code")
    if reason_code not in REASON_CODES:
        raise LedgerRefusal(f"reason.reason_code 不在协议枚举内: {reason_code}")
    scope = _require_str(payload.get("scope"), label="reason.scope")
    if scope not in REASON_SCOPES:
        raise LedgerRefusal(f"reason.scope 不在协议枚举内: {scope}")
    note = _require_str(payload.get("reason_note"), label="reason.reason_note").strip()
    if not note:
        raise LedgerRefusal("reason.reason_note 不得为空白")
    decided_on = _parse_ymd(payload.get("decided_on"), label="reason.decided_on")
    now_ymd = _now_shanghai().strftime("%Y%m%d")
    if decided_on > now_ymd:
        raise LedgerRefusal("reason.decided_on 晚于当前上海日期")
    recommendations = read_events(resolved_root, "RECOMMENDATION", manifest=manifest)
    matching = [event for event in recommendations if event["event_id"] == recommendation_event_id]
    if len(matching) != 1:
        raise LedgerRefusal(
            f"未执行原因必须引用账本中唯一存在的 recommendation: {recommendation_event_id}"
        )
    recommendation = matching[0]
    if decided_on < recommendation["as_of_trade_date"]:
        raise LedgerRefusal("reason.decided_on 不得早于 recommendation.as_of_trade_date")
    content = {
        "schema": REASON_SCHEMA,
        "recommendation_event_id": recommendation_event_id,
        "reason_code": reason_code,
        "scope": scope,
        "reason_note": note,
        "decided_on": decided_on,
    }
    source = {
        "kind": "explicit_operator_input",
        "identity": {
            "path": str(path),
            "recommendation_event_id": recommendation_event_id,
        },
        "sha256": sha256_bytes(raw),
        "schema_fingerprint": None,
    }
    draft = Draft(
        record_type="UNEXECUTED_REASON",
        natural_key=f"UNEXECUTED_REASON:explicit:{account_id}:{recommendation_event_id}",
        as_of_trade_date=decided_on,
        content=content,
        source=source,
        policy=None,
        missing_fields=(),
    )
    result = _append_drafts(
        resolved_root, [draft], batch_kind="unexecuted_reason", batch_source_sha=sha256_bytes(raw)
    )
    return {**result, "recommendation_event_id": recommendation_event_id}


# --------------------------------------------------------------------------------------
# Verification and status
# --------------------------------------------------------------------------------------


def verify_ledger(root: Path | str | None = None) -> dict[str, Any]:
    resolved = ledger_root(root)
    manifest = load_manifest(resolved)
    events_by_type = _read_all_events(resolved, manifest)
    batches = _verify_batches(events_by_type)
    counts = {record_type: len(events) for record_type, events in events_by_type.items()}
    last_hashes: dict[str, str] = {}
    for record_type, events in events_by_type.items():
        last_hashes[record_type] = str(events[-1]["event_hash"]) if events else ZERO_HASH
    return {
        "status": "OK",
        "ledger_version": LEDGER_VERSION,
        "protocol_commit": PROTOCOL_COMMIT,
        "earliest_eligible_day": manifest.earliest_eligible_day,
        "account_id": manifest.account_id,
        "counts": counts,
        "total_events": sum(counts.values()),
        "batches": batches,
        "last_event_hash": last_hashes,
        "policy_baseline": load_policy_baseline(resolved),
    }


def _open_days(calendar_db: Path | str, *, start: str, end: str) -> list[str]:
    connection = _open_readonly_sqlite(Path(calendar_db))
    try:
        rows = connection.execute(
            "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date >= ? AND cal_date <= ? "
            "ORDER BY cal_date",
            (start, end),
        ).fetchall()
    except sqlite3.DatabaseError as error:
        raise LedgerRefusal("交易日历库缺少 trade_cal 表") from error
    finally:
        connection.close()
    days: list[str] = []
    for row in rows:
        value = str(row["cal_date"])
        _parse_ymd(value, label="trade_cal.cal_date")
        days.append(value)
    return days


@dataclass(frozen=True)
class _Recommendation:
    event_id: str
    as_of_trade_date: str
    expected_execution_date: str | None
    action_code: str
    legs: tuple[Mapping[str, Any], ...]


def _recommendations(events: Sequence[Mapping[str, Any]]) -> list[_Recommendation]:
    result: list[_Recommendation] = []
    for event in events:
        content = event["content"]
        action = content["action"]
        result.append(
            _Recommendation(
                event_id=str(event["event_id"]),
                as_of_trade_date=str(event["as_of_trade_date"]),
                expected_execution_date=content["expected_execution_date"],
                action_code=str(action["code"]),
                legs=tuple(action["legs"]),
            )
        )
    return result


def _fill_matches_by_leg(
    recommendation: _Recommendation, fills: Sequence[Mapping[str, Any]]
) -> tuple[dict[int, list[str]], list[str]]:
    """派生视图：按腿匹配同日同码同向的确认成交；不声称执行比例或成交归属。"""
    expected = recommendation.expected_execution_date
    if expected is None:
        return {}, []
    by_leg: dict[int, list[str]] = {}
    all_matched: list[str] = []
    for fill in fills:
        content = fill["content"]
        if str(fill["as_of_trade_date"]) != expected:
            continue
        side = "BUY" if content["event_type"] == "TRADE_BUY" else "SELL"
        for index, leg in enumerate(recommendation.legs):
            if not leg["executable"]:
                continue
            if leg["ts_code"] == content["ts_code"] and leg["side"] == side:
                by_leg.setdefault(index, []).append(str(fill["event_id"]))
                all_matched.append(str(fill["event_id"]))
                break
    normalized = {index: sorted(set(ids)) for index, ids in by_leg.items()}
    return normalized, sorted(set(all_matched))


def status_report(
    root: Path | str | None = None,
    *,
    calendar_db: Path | str | None = None,
) -> dict[str, Any]:
    """只读复核：计数、逾期未执行建议、MISSED 日与暂停建议。"""
    resolved = ledger_root(root)
    manifest = load_manifest(resolved)
    events_by_type = _read_all_events(resolved, manifest)
    _verify_batches(events_by_type)
    counts = {record_type: len(events) for record_type, events in events_by_type.items()}
    signals = events_by_type["SIGNAL"]
    recommendations = _recommendations(events_by_type["RECOMMENDATION"])
    reasons = events_by_type["UNEXECUTED_REASON"]
    fills = events_by_type["CONFIRMED_FILL"]
    reasons_by_recommendation: dict[str, str] = {}
    full_reason_ids: set[str] = set()
    for reason in reasons:
        content = reason["content"]
        reference = str(content["recommendation_event_id"])
        reasons_by_recommendation[reference] = str(reason["event_id"])
        if content["scope"] == "FULL":
            full_reason_ids.add(reference)
    now_ymd = _now_shanghai().strftime("%Y%m%d")
    baseline = load_policy_baseline(resolved)
    review: list[dict[str, Any]] = []
    unresolved: list[str] = []
    warnings: list[str] = []
    matches_by_recommendation: dict[str, list[str]] = {}
    for recommendation in recommendations:
        matched_by_leg, matched = _fill_matches_by_leg(recommendation, fills)
        matches_by_recommendation[recommendation.event_id] = matched
        expected = recommendation.expected_execution_date
        executable_indices = [
            index for index, leg in enumerate(recommendation.legs) if leg["executable"]
        ]
        matched_legs = [index for index in executable_indices if index in matched_by_leg]
        if expected is None:
            match_status = "NO_EXPECTED_DATE"
        elif not executable_indices:
            match_status = "NOT_EXECUTABLE"
        elif expected > now_ymd:
            match_status = "NOT_DUE"
        elif len(matched_legs) == len(executable_indices):
            match_status = "MATCHED"
        elif matched_legs:
            match_status = "PARTIAL"
        else:
            match_status = "UNMATCHED"
        reason_id = reasons_by_recommendation.get(recommendation.event_id)
        if reason_id is not None and recommendation.event_id in full_reason_ids and matched:
            warnings.append(f"REASON_VS_FILL_CONTRADICTION:{recommendation.event_id}")
        if match_status in {"UNMATCHED", "PARTIAL"} and reason_id is None:
            unresolved.append(recommendation.event_id)
        review.append(
            {
                "recommendation_event_id": recommendation.event_id,
                "as_of_trade_date": recommendation.as_of_trade_date,
                "expected_execution_date": expected,
                "action_code": recommendation.action_code,
                "match_status": match_status,
                "matched_fill_event_ids": matched,
                "matched_leg_indices": matched_legs,
                "executable_leg_indices": executable_indices,
                "unexecuted_reason_event_id": reason_id,
            }
        )
    matched_fill_ids = {fill_id for ids in matches_by_recommendation.values() for fill_id in ids}
    unmatched_fills = sorted(
        str(fill["event_id"]) for fill in fills if str(fill["event_id"]) not in matched_fill_ids
    )
    signal_by_day = {str(event["as_of_trade_date"]): event for event in signals}
    for signal in signals:
        day = str(signal["as_of_trade_date"])
        content = signal["content"]
        deconcentration = content["deconcentration_state"] or {}
        legs_today = [
            leg
            for recommendation in recommendations
            if recommendation.as_of_trade_date == day
            for leg in recommendation.legs
        ]
        if int(deconcentration.get("recommended_sell_shares") or 0) > 0 and not any(
            leg["side"] == "SELL" for leg in legs_today
        ):
            warnings.append(f"SIGNAL_ACTION_WITHOUT_RECOMMENDATION:{day}:SELL")
        if int(deconcentration.get("recommended_buy_shares") or 0) > 0 and not any(
            leg["side"] == "BUY" for leg in legs_today
        ):
            warnings.append(f"SIGNAL_ACTION_WITHOUT_RECOMMENDATION:{day}:BUY")
        if content["status"] == "ACTIONABLE" and not any(
            recommendation.as_of_trade_date == day for recommendation in recommendations
        ):
            warnings.append(f"ACTIONABLE_SIGNAL_WITHOUT_RECOMMENDATION:{day}")
        signal_policy = signal.get("policy")
        if baseline is not None and isinstance(signal_policy, Mapping):
            changed = [
                key
                for key in ("strategy_id", "version", "content_hash")
                if str(signal_policy.get(key)) != baseline[key]
            ]
            if changed:
                warnings.append(f"POLICY_RELEASE_CHANGED_SINCE_BASELINE:{day}:{','.join(changed)}")
    missing_days: list[str] | None = None
    consecutive_missing = 0
    open_days_for_age: list[str] = []
    upper = now_ymd
    if calendar_db is not None:
        yesterday = (_now_shanghai() - timedelta(days=1)).strftime("%Y%m%d")
        upper = min(yesterday, now_ymd)
        if upper >= manifest.earliest_eligible_day:
            open_days = _open_days(calendar_db, start=manifest.earliest_eligible_day, end=upper)
            open_days_for_age = open_days
            missing_days = [day for day in open_days if day not in signal_by_day]
            for day in reversed(open_days):
                if day in signal_by_day:
                    break
                consecutive_missing += 1
    expected_by_id = {
        recommendation.event_id: recommendation.expected_execution_date
        for recommendation in recommendations
    }
    stale_unresolved: list[str] = []
    now_date = date.fromisoformat(_iso_day(now_ymd))
    for recommendation_id in unresolved:
        expected = expected_by_id.get(recommendation_id)
        if expected is None:
            continue
        if open_days_for_age:
            # 等待的交易日数：从执行日起到昨日（含端点）的开市日。
            age = len([day for day in open_days_for_age if expected <= day <= upper])
        else:
            age = (now_date - date.fromisoformat(_iso_day(expected))).days
        if age >= 3:
            stale_unresolved.append(recommendation_id)
    pause_reasons: list[str] = []
    if consecutive_missing >= 5:
        pause_reasons.append(f"CONSECUTIVE_MISSED_DAYS:{consecutive_missing}")
    if len(stale_unresolved) >= 3:
        pause_reasons.append(f"STALE_UNRESOLVED_RECOMMENDATIONS:{len(stale_unresolved)}")
    pause_reasons.extend(warnings)
    return {
        "status": "OK",
        "ledger_version": LEDGER_VERSION,
        "protocol_commit": PROTOCOL_COMMIT,
        "earliest_eligible_day": manifest.earliest_eligible_day,
        "account_id": manifest.account_id,
        "counts": counts,
        "policy_baseline": baseline,
        "days": {
            "signal": sorted(signal_by_day),
            "valuation": sorted(
                str(event["as_of_trade_date"]) for event in events_by_type["VALUATION"]
            ),
            "confirmed_fill": sorted(
                str(event["as_of_trade_date"]) for event in events_by_type["CONFIRMED_FILL"]
            ),
            "unexecuted_reason": sorted(
                str(event["as_of_trade_date"]) for event in events_by_type["UNEXECUTED_REASON"]
            ),
            "missed": missing_days,
        },
        "recommendation_review": review,
        "unresolved_recommendation_event_ids": unresolved,
        "stale_unresolved_recommendation_event_ids": stale_unresolved,
        "unmatched_fill_event_ids": unmatched_fills,
        "warnings": sorted(set(warnings)),
        "pause": {
            "recommended": bool(pause_reasons),
            "reasons": sorted(set(pause_reasons)),
            "no_automatic_actions": True,
        },
        "calendar": {
            "checked": calendar_db is not None,
            "note": (
                "MISSED 只统计至昨日；当天日报生成前不判 MISSED"
                if calendar_db is not None
                else "未提供只读交易日历库，无法派生 MISSED 日"
            ),
        },
    }


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _default_portfolio_db() -> Path:
    configured = os.environ.get("ASHARE_PORTFOLIO_DB_PATH")
    if configured:
        return Path(configured)
    return Path.home() / ".local" / "share" / "ashare-private" / "portfolio.sqlite"


def _print(payload: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger-root",
        default=None,
        help=(
            "私有台账目录；默认 TACTICORE_V3_LEDGER_ROOT 或 "
            "~/.local/share/tacticore-v3-prospective-ledger"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="初始化台账目录（仅首次）")
    brief = subparsers.add_parser("ingest-brief", help="追加一份当日 FinanceMCP brief")
    brief.add_argument("--brief", required=True, help="daily-briefs/YYYYMMDD.json 路径")
    fills = subparsers.add_parser("ingest-fills", help="只读导入券商确认成交")
    fills.add_argument("--portfolio-db", default=None, help="portfolio.sqlite 路径")
    reason = subparsers.add_parser("ingest-unexecuted-reason", help="追加显式未执行原因")
    reason.add_argument("--input", required=True, help="原因 JSON 路径")
    subparsers.add_parser("verify", help="只读校验哈希链、schema 与 batch 完整性")
    status = subparsers.add_parser("status", help="只读复核与暂停建议")
    status.add_argument("--calendar-db", default=None, help="只读 FinanceMCP ashare.sqlite")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = ledger_root(args.ledger_root)
    try:
        if args.command == "init":
            _print(init_ledger(root))
        elif args.command == "ingest-brief":
            _print(ingest_brief(args.brief, root=root))
        elif args.command == "ingest-fills":
            _print(
                ingest_confirmed_fills(
                    portfolio_db=args.portfolio_db or _default_portfolio_db(), root=root
                )
            )
        elif args.command == "ingest-unexecuted-reason":
            _print(ingest_unexecuted_reason(args.input, root=root))
        elif args.command == "verify":
            _print(verify_ledger(root))
        elif args.command == "status":
            _print(status_report(root, calendar_db=args.calendar_db))
        else:  # pragma: no cover - argparse enforces the command set
            raise LedgerRefusal(f"未知命令: {args.command}")
    except LedgerConflict as error:
        _print({"status": "CONFLICT", "error": str(error)})
        return 2
    except LedgerRefusal as error:
        _print({"status": "REFUSED", "error": str(error)})
        return 2
    except LedgerCorruption as error:
        _print({"status": "CORRUPT", "error": str(error)})
        return 2
    except (sqlite3.DatabaseError, OSError) as error:
        _print({"status": "ERROR", "error": str(error)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
