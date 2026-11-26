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
import fcntl
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
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
WRITER_LOCK_FILENAME = ".writer.lock"
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
# 补遗 2 §2：RECOMMENDATION 的 action / legs 显式允许键；未知键拒绝。
ACTION_ALLOWED_KEYS = frozenset(
    {
        "priority",
        "kind",
        "code",
        "rank",
        "title",
        "reasons",
        "counter_evidence",
        "triggers",
        "invalidation_conditions",
        "risk_impact",
        "fees_cents",
        "fees_assumed",
        "legs",
    }
)
LEG_ALLOWED_KEYS = frozenset({"side", "ts_code", "quantity", "price_milli", "executable"})
# 上游 brief 中存在、但协议明确不投影进 RECOMMENDATION 的展示/派生字段。
ACTION_STRIPPED_UPSTREAM_KEYS = frozenset({"illustrative", "fact_meta"})
LEG_STRIPPED_UPSTREAM_KEYS = frozenset(
    {
        "name",
        "lot_size",
        "lots",
        "gross_cents",
        "fees_cents",
        "net_cents",
        "quote_trade_date",
        "reason",
    }
)
# 补遗 2 §2：SIGNAL 只允许状态/枚举/布尔/标量；不得含腿、份数、价或成交语义。
SIGNAL_ALLOWED_KEYS = frozenset(
    {
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
)
SIGNAL_DECISION_KEYS = frozenset(
    {
        "evidence_complete",
        "no_action_reason_code",
        "no_action_reason_present",
        "suppressed_recommendation_count",
        "trigger_codes",
    }
)
# SIGNAL 不持久化 no_action_reason 自由文本：只留按 status 派生的封闭原因码。
_NO_ACTION_REASON_CODES = {
    "NO_ACTION": "NO_ACTION_REASON_RECORDED_IN_BRIEF",
    "DATA_INSUFFICIENT": "DATA_INSUFFICIENT_REASON_RECORDED_IN_BRIEF",
}
# 封闭触发码枚举：上游目前只有自由文本，没有结构化码；键保留给未来结构化输入。
TRIGGER_CODES = frozenset(
    {
        "ACCOUNT_LIFELINE",
        "CROSS_BORDER_PREMIUM",
        "DECONCENTRATION_GRIND_GUARDS",
        "DECONCENTRATION_MA60_PROTECT",
        "DECONCENTRATION_MONTHLY_WINDOW",
        "DECONCENTRATION_REBOUND",
        "DECONCENTRATION_TACTICAL_TAKE_PROFIT",
        "MARKET_COUNTER_EVIDENCE",
        "POSITION_20D_LOW_BREAK",
        "QUOTE_QUALITY_DEGRADED",
    }
)
OBSERVATION_TRIGGERS_UNPROJECTED = "observation_triggers_text_unprojected"
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,63}$")


def _is_safe_code(value: object) -> bool:
    """状态/估值叶子字符串只允许机器码（枚举、日期、代码、版本号）。

    ASCII 码形判定是**白名单**：中文自由文本（如「减仓三百股，限价一元二角」）、
    空白与标点一律不满足，因此无需枚举坏词。
    """
    return isinstance(value, str) and bool(_SAFE_CODE_RE.match(value))


def _require_safe_code(value: object, *, label: str) -> str:
    if not _is_safe_code(value):
        raise LedgerRefusal(f"{label} 必须是机器码字符串，拒绝自由文本: {value!r}")
    return str(value)


MARKET_REGIME_TIERS = frozenset({"OFFENSIVE", "STRUCTURAL", "DEFENSIVE"})
MARKET_STYLE_TIERS = frozenset({"GROWTH_LEADING", "VALUE_LEADING", "BALANCED"})
CIRCUIT_BREAKER_STATUSES = frozenset({"NORMAL", "L1_WARN", "L2_LOCKED"})
SUB_STRATEGY_STATUSES = frozenset(
    {"ACTIVE", "STOP_ONLY", "REDUCE_ONLY", "LOCKED_PENDING_VALIDATION"}
)
SUB_STRATEGY_KEYS = frozenset({"s_deconcentrate", "s_base_super_etf", "s_stock_swing"})
DECONCENTRATION_PLAN_STATUSES = frozenset({"ACTIVE", "COMPLETED", "CANCELLED", "UNINITIALIZED"})
DECONCENTRATION_PLAN_MODES = frozenset({"STANDARD", "BOTTOM_GRIND_25"})
DOWNSIDE_PROTECT_MODES = frozenset({"MA60", "SUPPORT_FLOOR"})
# FinanceMCP/src/portfolio/deconcentrationPlan.ts:7-14（TrancheTriggerReason，7 值）；
# :122 声明 active_trigger_reason: TrancheTriggerReason | null。
TRANCHE_TRIGGER_REASONS = frozenset(
    {
        "MONTHLY_SCHEDULE",
        "REBOUND_8PCT",
        "BREAKDOWN_MA60",
        "BREAKDOWN_SUPPORT_FLOOR",
        "GRIND_OVERSOLD_RELOAD",
        "GRIND_TACTICAL_TAKE_PROFIT",
        "GRIND_OVERWEIGHT_DRIFT_HARVEST",
    }
)
# FinanceMCP/src/portfolio/dailyReport.ts:182 cost_basis: 'broker_diluted' | 'ledger_average' | null
COST_BASIS_VALUES = frozenset({"broker_diluted", "ledger_average"})
SIGNAL_MARKET_REGIME_KEYS = frozenset(
    {
        "regime",
        "raw_regime",
        "hysteresis_held",
        "crash_override",
        "style",
        "style_spread_20d_pp",
        "target_equity_bps",
        "defensive_cash_bps",
        "target_equity_pct",
        "defensive_cash_pct",
        "pct_above_ma60",
        "amount_vs_ma20",
        "limit_down",
        "hs300_above_ma60",
        "zz500_above_ma60",
        "cyb_above_ma60",
    }
)
# 每个允许键必须恰好归属一个类型组：白名单优先，不再是“命中坏模式才拒”。
SIGNAL_MARKET_REGIME_TYPES: dict[str, tuple[str, frozenset[str] | None]] = {
    "regime": ("enum", MARKET_REGIME_TIERS),
    "raw_regime": ("enum", MARKET_REGIME_TIERS),
    "style": ("enum", MARKET_STYLE_TIERS),
    "hysteresis_held": ("bool", None),
    "crash_override": ("bool", None),
    "hs300_above_ma60": ("bool?", None),
    "zz500_above_ma60": ("bool?", None),
    "cyb_above_ma60": ("bool?", None),
    "style_spread_20d_pp": ("number?", None),
    "target_equity_bps": ("number", None),
    "defensive_cash_bps": ("number", None),
    "target_equity_pct": ("number", None),
    "defensive_cash_pct": ("number", None),
    "pct_above_ma60": ("number?", None),
    "amount_vs_ma20": ("number?", None),
    "limit_down": ("number?", None),
}
SIGNAL_ROUTER_KEYS = frozenset(
    {
        "effective_regime",
        "circuit_breaker_status",
        "locked_until_trade_date",
        "l2_trigger_drawdown_bps",
        "post_breaker_equity_bps",
        "deconcentration_preemptive_active",
        "policy_version",
        "hwm_nav_cents",
        "hwm_date",
        "hwm_drawdown_pct",
        "lifeline_nav_cents",
        "lifeline_buffer_cents",
        "lifeline_buffer_pct",
        "sub_strategies",
    }
)
SIGNAL_ROUTER_TYPES: dict[str, tuple[str, frozenset[str] | None]] = {
    "effective_regime": ("enum", MARKET_REGIME_TIERS),
    "circuit_breaker_status": ("enum", CIRCUIT_BREAKER_STATUSES),
    "deconcentration_preemptive_active": ("bool", None),
    "policy_version": ("code", None),
    "locked_until_trade_date": ("date?", None),
    "hwm_date": ("date", None),
    "l2_trigger_drawdown_bps": ("number", None),
    "post_breaker_equity_bps": ("number", None),
    "hwm_nav_cents": ("number", None),
    "hwm_drawdown_pct": ("number", None),
    "lifeline_nav_cents": ("number", None),
    "lifeline_buffer_cents": ("number", None),
    "lifeline_buffer_pct": ("number", None),
    "sub_strategies": ("sub_strategies", None),
}
SIGNAL_DECONCENTRATION_KEYS = frozenset(
    {
        "plan_present",
        "plan_status",
        "plan_mode",
        "target_keep_bps",
        "target_keep_pct",
        "tactical_slot_bps",
        "tactical_slot_pct",
        "max_grind_weight_pct",
        "drift_harvest_trigger_pct",
        "preemptive_weight_threshold_pct",
        "normal_lifeline_pct",
        "reload_discount_pct",
        "take_profit_pct",
        "rebound_pct",
        "completed_swing_count",
        "live_weight_pct",
        "downside_protect_mode",
        "breakdown_ma60_2d",
        "next_monthly_trigger_date",
        "active_trigger_reason",
    }
)
SIGNAL_DECONCENTRATION_TYPES: dict[str, tuple[str, frozenset[str] | None]] = {
    "plan_present": ("bool", None),
    "breakdown_ma60_2d": ("bool", None),
    "active_trigger_reason": ("enum?", TRANCHE_TRIGGER_REASONS),
    "plan_status": ("enum", DECONCENTRATION_PLAN_STATUSES),
    "plan_mode": ("enum", DECONCENTRATION_PLAN_MODES),
    "downside_protect_mode": ("enum?", DOWNSIDE_PROTECT_MODES),
    "next_monthly_trigger_date": ("date?", None),
    "target_keep_bps": ("number", None),
    "target_keep_pct": ("number", None),
    "tactical_slot_bps": ("number", None),
    "tactical_slot_pct": ("number", None),
    "max_grind_weight_pct": ("number", None),
    "drift_harvest_trigger_pct": ("number", None),
    "preemptive_weight_threshold_pct": ("number", None),
    "normal_lifeline_pct": ("number", None),
    "reload_discount_pct": ("number", None),
    "take_profit_pct": ("number", None),
    "rebound_pct": ("number", None),
    "completed_swing_count": ("number", None),
    "live_weight_pct": ("number?", None),
}
# 补遗 2 §2 + B 复验：SIGNAL 的 data_quality 只允许状态/摘要/缺失字段。
# 任何 quality detail/notes/readiness 列表都不落盘，避免深层自由文本成为份数/价格后门。
SIGNAL_DATA_QUALITY_KEYS = frozenset({"status", "summary_status", "missing_fields"})
# 补遗 2 §2：VALUATION holdings 只保留估值事实。
VALUATION_HOLDING_KEYS = frozenset(
    {
        "ts_code",
        "name",
        "quantity",
        "weight",
        "market_value_cents",
        "price_milli",
        "bar_quality",
        "price_source",
        "latest_bar_date",
        "diluted_cost_per_share",
        "diluted_total_cost_cents",
        "cost_basis",
    }
)
# 补遗 2 §2：concentration 只允许数值/权重（及包含权重的 top_position 结构）。
# FinanceMCP/src/portfolio/dailyReport.ts:629-636：五个数值字段与 top_position 均可为 null；
# top_position = {ts_code: string; name: string; weight: number} | null。
VALUATION_CONCENTRATION_KEYS = frozenset(
    {"hhi", "effective_positions", "equity_weight", "cash_ratio", "top_position"}
)
VALUATION_TOP_POSITION_KEYS = frozenset({"ts_code", "name", "weight"})
CONCENTRATION_NUMBER_KEYS = VALUATION_CONCENTRATION_KEYS.difference({"top_position"})
# `name` 是发行人名称（真实值如「半导体设备ETF 易方达」），只要求字符串，不做码形/语义过滤。
CONCENTRATION_TOP_POSITION_TYPES: dict[str, str] = {
    "ts_code": "code",
    "name": "text",
    "weight": "number",
}
# FinanceMCP/src/portfolio/actionEngine.ts:119-123：
# reconciliation_reminder = {lag_trade_days: number|null, needs_reminder: boolean,
# message_zh: string|null}；账本只落 lag_trade_days/needs_reminder，
# message_zh 识别但丢弃并披露。
VALUATION_RECONCILIATION_KEYS = frozenset({"lag_trade_days", "needs_reminder"})
RECONCILIATION_UPSTREAM_KEYS = frozenset({"lag_trade_days", "needs_reminder", "message_zh"})
RECONCILIATION_TYPES: dict[str, tuple[str, frozenset[str] | None]] = {
    "lag_trade_days": ("int?", None),
    "needs_reminder": ("bool", None),
}
PRINCIPAL_FIELDS = (
    "initial_principal_cents",
    "current_nav_cents",
    "to_principal_gap_cents",
    "to_principal_return_needed_pct",
    "loss_from_principal_pct",
)
PRINCIPAL_TYPES: dict[str, tuple[str, int | None]] = {
    "initial_principal_cents": ("int", 1),
    "current_nav_cents": ("int", 1),
    "to_principal_gap_cents": ("int", None),
    "to_principal_return_needed_pct": ("number", None),
    "loss_from_principal_pct": ("number", None),
}
HOLDING_REQUIRED_FIELDS = (
    "ts_code",
    "quantity",
    "weight",
    "market_value_cents",
    "price_milli",
    "bar_quality",
)
HOLDING_EXPECTED_FIELDS = (
    "name",
    "price_source",
    "latest_bar_date",
    "diluted_cost_per_share",
    "diluted_total_cost_cents",
    "cost_basis",
)
# holdings[] 的逐字段叶类型：白名单只对 holdings[] 生效，不豁免任何其它路径。
# 上游（FinanceMCP/src/portfolio/dailyReport.ts:159-186）：
# `name` 是发行人名称中文标签（真实值「航空航天ETF 天弘」），只要求 str|None；
# 数值字段必须 int / int|float；其余字符串必须是机器码/日期；可选字段允许 null。
HOLDING_TYPES: dict[str, str] = {
    "ts_code": "code",
    "name": "text",
    "quantity": "int",
    "weight": "number",
    "market_value_cents": "int",
    "price_milli": "int",
    "bar_quality": "code",
    "price_source": "code",
    "latest_bar_date": "date?",
    "diluted_cost_per_share": "number?",
    "diluted_total_cost_cents": "int?",
    "cost_basis": "enum?",
}
HOLDING_ENUMS: dict[str, frozenset[str]] = {"cost_basis": COST_BASIS_VALUES}
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


def _reject_non_finite(value: object) -> None:
    """canonical_json 拒绝 NaN/Infinity（补遗 2 §3）：先递归检查再序列化。"""
    if isinstance(value, float) and not math.isfinite(value):
        raise LedgerRefusal(f"canonical_json 拒绝非有限数值: {value!r}")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_non_finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_non_finite(item)


def canonical_json(value: object) -> str:
    _reject_non_finite(value)
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


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


def content_hash(record_type: str, content: Mapping[str, Any], source_sha256: str) -> str:
    """语义内容哈希：payload **加**源字节 SHA，绑定幂等性（补遗 2 §3 / B D1）。

    同一自然键下源字节任何变化（包括仅多一个换行）都会改变 content_hash，
    从而被判为冲突而不是静默 no-op。
    """
    _verify_hex64(source_sha256, label="content.source_sha256")
    material = {"content": content, "source_sha256": source_sha256}
    return sha256_text(f"{record_type}\n{canonical_json(material)}")


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
    lock_file = resolved / WRITER_LOCK_FILENAME
    lock_file.touch(mode=0o600, exist_ok=True)
    os.chmod(lock_file, 0o600)
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
        return content_hash(self.record_type, self.content, str(self.source["sha256"]))


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
    number = float(value)
    if not math.isfinite(number):
        raise LedgerRefusal(f"{label} 必须是有限数值")
    return number


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
    ordinal = _require_int(payload["ordinal"], label="event.ingest_batch.ordinal", minimum=1)
    count = _require_int(payload["count"], label="event.ingest_batch.count", minimum=1)
    if ordinal > count:
        raise LedgerCorruption("event.ingest_batch.ordinal 必须在 1..count 内")
    return payload


def _validate_missing_fields(value: object) -> tuple[str, ...]:
    fields = _require_sequence(value, label="event.missing_fields")
    if any(not isinstance(item, str) or not item for item in fields):
        raise LedgerCorruption("event.missing_fields 必须是非空字符串数组")
    if len(set(fields)) != len(fields):
        raise LedgerCorruption("event.missing_fields 不得重复")
    return tuple(str(item) for item in fields)


SIGNAL_FORBIDDEN_KEYS = frozenset(
    {
        "legs",
        "quantity",
        "price_milli",
        "fees_cents",
        "gross_cents",
        "net_cents",
        "executable",
        "filled_quantity",
        "filled_price_milli",
        "executed_quantity",
        "executed_price_milli",
        "fills",
        "actual_fill",
        "execution_status",
    }
)


def _scan_forbidden_keys(value: object, *, label: str, forbidden: frozenset[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in forbidden:
                raise LedgerRefusal(f"{label} 不得包含 {key}（混类或成交语义）")
            _scan_forbidden_keys(item, label=f"{label}.{key}", forbidden=forbidden)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_forbidden_keys(item, label=f"{label}[{index}]", forbidden=forbidden)


def _project_typed_value(
    value: object, *, label: str, kind: str, enum: frozenset[str] | None = None
) -> Any:
    """白名单优先的类型化叶子投影：只接受明确的机器码/枚举/数值/布尔/日期。

    自由文本（含中文「减仓三百股，限价一元二角」）在任何层级都不放行；这里不依赖
    坏词正则，而是要求字符串属于明确枚举或 ASCII 机器码集合。`kind` 末尾的 `?`
    表示该字段允许为 null（上游 `number | null`）。
    """
    nullable = kind.endswith("?")
    base = kind.rstrip("?")
    if value is None:
        if nullable:
            return None
        raise LedgerRefusal(f"{label} 不得为 null")
    if base == "bool":
        if not isinstance(value, bool):
            raise LedgerRefusal(f"{label} 必须是布尔值")
        return value
    if base == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise LedgerRefusal(f"{label} 必须是整数")
        if value < 0:
            raise LedgerRefusal(f"{label} 必须 >= 0")
        return value
    if base == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise LedgerRefusal(f"{label} 必须是数值")
        number = float(value)
        if not math.isfinite(number):
            raise LedgerRefusal(f"{label} 不得是非有限数值")
        return value
    if base == "enum":
        if not isinstance(value, str) or enum is None or value not in enum:
            raise LedgerRefusal(f"{label} 不在封闭枚举内: {value!r}")
        return value
    if base == "text":
        # 发行人名称等中文标签：只要求字符串，不做 ASCII 码形或语义过滤。
        if not isinstance(value, str):
            raise LedgerRefusal(f"{label} 必须是字符串")
        return value
    if base == "code":
        return _require_safe_code(value, label=label)
    if base == "date":
        return _parse_ymd(value, label=label)
    if base == "sub_strategies":
        payload = _require_mapping(value, label=label)
        unknown = set(payload).difference(SUB_STRATEGY_KEYS)
        if unknown:
            raise LedgerRefusal(f"{label} 含未批准子策略键: {sorted(unknown)}")
        return {
            key: _project_typed_value(
                payload[key], label=f"{label}.{key}", kind="enum", enum=SUB_STRATEGY_STATUSES
            )
            for key in sorted(payload)
        }
    raise LedgerRefusal(f"{label} 未知的投影类型: {kind}")


def _project_typed_block(
    block: object,
    *,
    label: str,
    types: Mapping[str, tuple[str, frozenset[str] | None]],
    missing: list[str] | None = None,
    missing_prefix: str | None = None,
) -> dict[str, Any] | None:
    """开类型状态块：键白名单 + 每键显式类型。

    未知顶层键**丢弃并逐个披露**（`<prefix>.<key>_unprojected`）——上游键多于补遗
    允许集是正常的，静默丢弃会让账本无法解释缺失事实。已知键的类型不符属于污染，
    直接拒绝整份输入（不得混同于披露）。
    """
    if block is None:
        return None
    payload = _require_mapping(block, label=label)
    projected: dict[str, Any] = {}
    prefix = missing_prefix or label
    for key in sorted(payload):
        spec = types.get(str(key))
        if spec is None:
            if missing is not None:
                missing.append(f"{prefix}.{key}_unprojected")
            continue
        kind, enum = spec
        projected[str(key)] = _project_typed_value(
            payload[key], label=f"{label}.{key}", kind=kind, enum=enum
        )
    return projected


def _validate_typed_block(
    block: object,
    *,
    label: str,
    types: Mapping[str, tuple[str, frozenset[str] | None]],
) -> Mapping[str, Any] | None:
    if block is None:
        return None
    payload = _require_mapping(block, label=label)
    unknown = set(payload).difference(types)
    if unknown:
        raise LedgerCorruption(f"{label} 含未批准字段: {sorted(unknown)}")
    for key, value in payload.items():
        kind, enum = types[str(key)]
        _project_typed_value(value, label=f"{label}.{key}", kind=kind, enum=enum)
    return payload


DQ_STATUSES = frozenset({"OK", "DEGRADED", "INSUFFICIENT"})
# summary_status 上游是 ResearchSummaryStatus 字符串；台账只要求它是机器码（无自由文本）。
DATA_QUALITY_TYPES: dict[str, tuple[str, frozenset[str] | None]] = {
    "status": ("enum", DQ_STATUSES),
    "summary_status": ("code", None),
    "missing_fields": ("codes", None),
}
# FinanceMCP/src/portfolio/dailyReport.ts:595-608：tiers 的 7 个固定档。
VALUATION_TIER_NAMES = frozenset(
    {
        "market_data",
        "etf_price",
        "etf_share_adjustment",
        "account_identity",
        "account_trade_completeness",
        "research_evidence",
        "trade_plan_executability",
    }
)
VALUATION_DQ_TOP_KEYS = frozenset(
    {
        "status",
        "summary_status",
        "missing_fields",
        "quotes",
        "market_report",
        "screening",
        "tiers",
    }
)
# 上游存在、但按补遗 2 §2 不得落盘的自由文本键：识别并披露，不拒绝。
VALUATION_DQ_DROPPED_KEYS = frozenset({"notes"})
VALUATION_QUOTES_KEYS = frozenset({"ready", "stale", "not_ready", "missing"})
VALUATION_MARKET_REPORT_TYPES: dict[str, tuple[str, frozenset[str] | None]] = {
    "available": ("bool", None),
    "report_id": ("code?", None),
    "as_of_trade_date": ("date?", None),
    "freshness": ("code", None),
}
VALUATION_SCREENING_TYPES: dict[str, tuple[str, frozenset[str] | None]] = {
    "status": ("code", None),
    "missing_tables": ("codes", None),
}
VALUATION_TIER_TYPES: dict[str, tuple[str, frozenset[str] | None]] = {
    "status": ("code", None),
    "as_of": ("date?", None),
    "verified": ("bool", None),
    "ready": ("codes", None),
    "not_ready": ("codes", None),
}
VALUATION_TIER_DROPPED_KEYS = frozenset({"detail"})


def _project_missing_field_codes(value: object, *, label: str) -> list[str]:
    items = _require_sequence(value, label=label)
    return [_require_safe_code(item, label=f"{label}[{index}]") for index, item in enumerate(items)]


def _project_data_quality(
    data_quality: Mapping[str, Any], *, missing: list[str] | None = None
) -> dict[str, Any]:
    """SIGNAL 的 data_quality 只落状态/摘要/缺失字段（补遗 2 §2）。

    其余上游键（`quotes`/`market_report`/`screening`/`tiers`/`notes`）在 SIGNAL 一律
    不落盘，但逐个披露为 `data_quality.<key>_unprojected`；完整质量事实进入 VALUATION。
    """
    payload: dict[str, Any] = {}
    for key in ("status", "summary_status", "missing_fields"):
        if key not in data_quality:
            continue
        kind, enum = DATA_QUALITY_TYPES[key]
        if key == "missing_fields":
            payload[key] = _project_missing_field_codes(
                data_quality[key], label="data_quality.missing_fields"
            )
        else:
            payload[key] = _project_typed_value(
                data_quality[key], label=f"data_quality.{key}", kind=kind, enum=enum
            )
    if missing is not None:
        for key in sorted(data_quality):
            if key not in SIGNAL_DATA_QUALITY_KEYS:
                missing.append(f"data_quality.{key}_unprojected")
    return payload


def _validate_data_quality(data_quality: Mapping[str, Any]) -> None:
    unknown = set(data_quality).difference(SIGNAL_DATA_QUALITY_KEYS)
    if unknown:
        raise LedgerCorruption(f"SIGNAL data_quality 含未批准字段: {sorted(unknown)}")
    for key, value in data_quality.items():
        kind, enum = DATA_QUALITY_TYPES[key]
        if key == "missing_fields":
            _project_missing_field_codes(value, label=f"SIGNAL.data_quality.{key}")
        else:
            _project_typed_value(
                value,
                label=f"SIGNAL.data_quality.{key}",
                kind=kind,
                enum=enum,
            )


def _project_valuation_data_quality(
    data_quality: Mapping[str, Any], *, missing: list[str]
) -> dict[str, Any]:
    """VALUATION 的 data_quality：闭类型键集合 + 显式叶类型。

    - 顶层只允许 `status/summary_status/missing_fields/quotes/market_report/screening/tiers`；
      `notes` 识别后丢弃并披露；其它未知键 = 篡改，拒绝。
    - `quotes`/`market_report`/`screening`/`tiers` 的子键是封闭的，未知子键拒绝。
    - `tiers` 只允许 7 个固定档；每档 `detail` 丢弃并披露，未知键拒绝。
    """
    projected: dict[str, Any] = {}
    for key in sorted(data_quality):
        value = data_quality[key]
        if key in VALUATION_DQ_DROPPED_KEYS:
            missing.append(f"data_quality.{key}_unprojected")
            continue
        if key not in VALUATION_DQ_TOP_KEYS:
            raise LedgerRefusal(f"data_quality 含未批准字段: {key!r}")
        if key == "missing_fields":
            projected[key] = _project_missing_field_codes(
                value, label="data_quality.missing_fields"
            )
        elif key in DATA_QUALITY_TYPES:
            kind, enum = DATA_QUALITY_TYPES[key]
            projected[key] = _project_typed_value(
                value, label=f"data_quality.{key}", kind=kind, enum=enum
            )
        elif key == "quotes":
            quotes = _require_mapping(value, label="data_quality.quotes")
            unknown = set(quotes).difference(VALUATION_QUOTES_KEYS)
            if unknown:
                raise LedgerRefusal(f"data_quality.quotes 含未批准字段: {sorted(unknown)}")
            projected[key] = {
                name: _project_missing_field_codes(
                    quotes[name], label=f"data_quality.quotes.{name}"
                )
                for name in sorted(quotes)
            }
        elif key == "market_report":
            projected[key] = _project_closed_block(
                value,
                label="data_quality.market_report",
                types=VALUATION_MARKET_REPORT_TYPES,
            )
        elif key == "screening":
            projected[key] = _project_closed_block(
                value,
                label="data_quality.screening",
                types=VALUATION_SCREENING_TYPES,
            )
        else:  # tiers
            tiers = _require_mapping(value, label="data_quality.tiers")
            unknown = set(tiers).difference(VALUATION_TIER_NAMES)
            if unknown:
                raise LedgerRefusal(f"data_quality.tiers 含未批准档位: {sorted(unknown)}")
            projected_tiers: dict[str, Any] = {}
            for name in sorted(tiers):
                tier = _require_mapping(tiers[name], label=f"data_quality.tiers.{name}")
                unknown_tier = (
                    set(tier)
                    .difference(VALUATION_TIER_TYPES)
                    .difference(VALUATION_TIER_DROPPED_KEYS)
                )
                if unknown_tier:
                    raise LedgerRefusal(
                        f"data_quality.tiers.{name} 含未批准字段: {sorted(unknown_tier)}"
                    )
                projected_tiers[name] = {}
                for dropped in sorted(VALUATION_TIER_DROPPED_KEYS.intersection(tier)):
                    missing.append(f"data_quality.tiers.{name}.{dropped}_unprojected")
                for field in sorted(set(tier).intersection(VALUATION_TIER_TYPES)):
                    kind, enum = VALUATION_TIER_TYPES[field]
                    if kind == "codes":
                        projected_tiers[name][field] = _project_missing_field_codes(
                            tier[field], label=f"data_quality.tiers.{name}.{field}"
                        )
                    else:
                        projected_tiers[name][field] = _project_typed_value(
                            tier[field],
                            label=f"data_quality.tiers.{name}.{field}",
                            kind=kind,
                            enum=enum,
                        )
            projected[key] = projected_tiers
    return projected


def _project_closed_block(
    block: object, *, label: str, types: Mapping[str, tuple[str, frozenset[str] | None]]
) -> dict[str, Any]:
    payload = _require_mapping(block, label=label)
    unknown = set(payload).difference(types)
    if unknown:
        raise LedgerRefusal(f"{label} 含未批准字段: {sorted(unknown)}")
    projected: dict[str, Any] = {}
    for key in sorted(payload):
        kind, enum = types[str(key)]
        if kind == "codes":
            projected[str(key)] = _project_missing_field_codes(payload[key], label=f"{label}.{key}")
        else:
            projected[str(key)] = _project_typed_value(
                payload[key], label=f"{label}.{key}", kind=kind, enum=enum
            )
    return projected


def _validate_valuation_data_quality(data_quality: Mapping[str, Any]) -> None:
    unknown = set(data_quality).difference(VALUATION_DQ_TOP_KEYS)
    if unknown:
        raise LedgerCorruption(f"VALUATION data_quality 含未批准字段: {sorted(unknown)}")
    for key, value in data_quality.items():
        if key == "missing_fields":
            _project_missing_field_codes(value, label=f"VALUATION.data_quality.{key}")
        elif key in DATA_QUALITY_TYPES:
            kind, enum = DATA_QUALITY_TYPES[key]
            _project_typed_value(value, label=f"VALUATION.data_quality.{key}", kind=kind, enum=enum)
        elif key == "quotes":
            quotes = _require_mapping(value, label="VALUATION data_quality.quotes")
            unknown_quotes = set(quotes).difference(VALUATION_QUOTES_KEYS)
            if unknown_quotes:
                raise LedgerCorruption(
                    f"VALUATION data_quality.quotes 含未批准字段: {sorted(unknown_quotes)}"
                )
            for name, codes in quotes.items():
                _project_missing_field_codes(codes, label=f"VALUATION.data_quality.quotes.{name}")
        elif key == "market_report":
            _validate_closed_block(
                value,
                label="VALUATION data_quality.market_report",
                types=VALUATION_MARKET_REPORT_TYPES,
            )
        elif key == "screening":
            _validate_closed_block(
                value,
                label="VALUATION data_quality.screening",
                types=VALUATION_SCREENING_TYPES,
            )
        else:  # tiers
            tiers = _require_mapping(value, label="VALUATION data_quality.tiers")
            unknown_tiers = set(tiers).difference(VALUATION_TIER_NAMES)
            if unknown_tiers:
                raise LedgerCorruption(
                    f"VALUATION data_quality.tiers 含未批准档位: {sorted(unknown_tiers)}"
                )
            for name, tier in tiers.items():
                payload = _require_mapping(tier, label=f"VALUATION data_quality.tiers.{name}")
                unknown_tier = set(payload).difference(VALUATION_TIER_TYPES)
                if unknown_tier:
                    raise LedgerCorruption(
                        f"VALUATION data_quality.tiers.{name} 含未批准字段: {sorted(unknown_tier)}"
                    )
                for field, item in payload.items():
                    kind, enum = VALUATION_TIER_TYPES[field]
                    if kind == "codes":
                        _project_missing_field_codes(
                            item, label=f"VALUATION.data_quality.tiers.{name}.{field}"
                        )
                    else:
                        _project_typed_value(
                            item,
                            label=f"VALUATION.data_quality.tiers.{name}.{field}",
                            kind=kind,
                            enum=enum,
                        )


def _validate_closed_block(
    block: object, *, label: str, types: Mapping[str, tuple[str, frozenset[str] | None]]
) -> None:
    payload = _require_mapping(block, label=label)
    unknown = set(payload).difference(types)
    if unknown:
        raise LedgerCorruption(f"{label} 含未批准字段: {sorted(unknown)}")
    for key, value in payload.items():
        kind, enum = types[str(key)]
        if kind == "codes":
            _project_missing_field_codes(value, label=f"{label}.{key}")
        else:
            _project_typed_value(value, label=f"{label}.{key}", kind=kind, enum=enum)


def _validate_state_block(
    block: object,
    *,
    label: str,
    types: Mapping[str, tuple[str, frozenset[str] | None]],
) -> Mapping[str, Any] | None:
    return _validate_typed_block(block, label=label, types=types)


def _project_trigger_codes(first_section: Mapping[str, Any]) -> list[str] | None:
    raw = first_section.get("trigger_codes")
    if raw is None:
        return None
    codes = _require_sequence(raw, label="brief.first_section.trigger_codes")
    if not codes:
        # 空数组等同于上游未提供结构化码：省略该键并显式记缺失。
        return None
    projected: list[str] = []
    for index, code in enumerate(codes):
        value = _require_str(code, label=f"brief.first_section.trigger_codes[{index}]")
        if value not in TRIGGER_CODES:
            raise LedgerRefusal(f"trigger_codes 不在封闭枚举内: {value!r}")
        projected.append(value)
    if len(set(projected)) != len(projected):
        raise LedgerRefusal("trigger_codes 不得重复")
    return projected


def _validate_signal_content(content: Mapping[str, Any], missing: tuple[str, ...]) -> None:
    if set(content) != SIGNAL_ALLOWED_KEYS:
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
    if content["account_id_source"] is not None:
        _require_safe_code(content["account_id_source"], label="SIGNAL account_id_source")
    elif "account_id_source" not in missing:
        raise LedgerCorruption("SIGNAL account_id_source 为空但未记入 missing_fields")
    if content["account_status"] != REAL_ACCOUNT_STATUS:
        raise LedgerCorruption("SIGNAL account_status 与协议不一致")
    decision = _require_mapping(content["decision"], label="SIGNAL decision")
    if not set(decision).issubset(SIGNAL_DECISION_KEYS):
        raise LedgerCorruption("SIGNAL decision 含未批准字段")
    for required in (
        "evidence_complete",
        "no_action_reason_code",
        "no_action_reason_present",
        "suppressed_recommendation_count",
    ):
        if required not in decision:
            raise LedgerCorruption(f"SIGNAL decision.{required} 缺失")
    _require_bool(decision["evidence_complete"], label="SIGNAL decision.evidence_complete")
    if content["status"] == "DATA_INSUFFICIENT" and decision["evidence_complete"]:
        raise LedgerCorruption("DATA_INSUFFICIENT SIGNAL 不得声称 evidence_complete")
    if content["status"] != "DATA_INSUFFICIENT" and not decision["evidence_complete"]:
        raise LedgerCorruption("非 DATA_INSUFFICIENT SIGNAL 必须 evidence_complete")
    if decision["no_action_reason_code"] is not None:
        code = decision["no_action_reason_code"]
        if not isinstance(code, str) or code not in _NO_ACTION_REASON_CODES.values():
            raise LedgerCorruption(
                f"SIGNAL decision.no_action_reason_code 不在封闭枚举内: {code!r}"
            )
    _require_bool(
        decision["no_action_reason_present"], label="SIGNAL decision.no_action_reason_present"
    )
    if "trigger_codes" in decision:
        codes = _require_sequence(decision["trigger_codes"], label="SIGNAL trigger_codes")
        if not codes:
            raise LedgerCorruption("SIGNAL trigger_codes 存在时不得为空")
        for code in codes:
            if not isinstance(code, str) or code not in TRIGGER_CODES:
                raise LedgerCorruption(f"SIGNAL trigger_codes 不在封闭枚举内: {code!r}")
        if len(set(codes)) != len(codes):
            raise LedgerCorruption("SIGNAL trigger_codes 不得重复")
        if OBSERVATION_TRIGGERS_UNPROJECTED in missing:
            raise LedgerCorruption("SIGNAL 已有 trigger_codes 却声明文本未投影")
    elif OBSERVATION_TRIGGERS_UNPROJECTED not in missing:
        raise LedgerCorruption(
            "SIGNAL 缺少 trigger_codes 时必须把 "
            f"{OBSERVATION_TRIGGERS_UNPROJECTED} 记入 missing_fields"
        )
    _require_int(
        decision["suppressed_recommendation_count"],
        label="SIGNAL decision.suppressed_recommendation_count",
        minimum=0,
    )
    market_regime = _validate_state_block(
        content["market_regime"],
        label="SIGNAL market_regime",
        types=SIGNAL_MARKET_REGIME_TYPES,
    )
    router = _validate_state_block(
        content["router"], label="SIGNAL router", types=SIGNAL_ROUTER_TYPES
    )
    deconcentration = _validate_state_block(
        content["deconcentration_state"],
        label="SIGNAL deconcentration_state",
        types=SIGNAL_DECONCENTRATION_TYPES,
    )
    for name, value in (
        ("v3_cockpit.market_regime", market_regime),
        ("v3_cockpit.router", router),
        ("v3_cockpit.deconcentration", deconcentration),
    ):
        if value is None and name not in missing:
            raise LedgerCorruption(f"SIGNAL {name} 为空但未记入 missing_fields")
    data_quality = _require_mapping(content["data_quality"], label="SIGNAL data_quality")
    _validate_data_quality(data_quality)
    for key in ("status", "summary_status", "missing_fields"):
        if key not in data_quality and f"data_quality.{key}" not in missing:
            raise LedgerCorruption(f"SIGNAL data_quality.{key} 缺失但未记入 missing_fields")
    _scan_forbidden_keys(content, label="SIGNAL", forbidden=SIGNAL_FORBIDDEN_KEYS)
    complete = decision["evidence_complete"]
    if complete and (market_regime is None or router is None):
        raise LedgerCorruption("SIGNAL evidence_complete 但缺少核心 V3 状态")
    if not complete and not missing:
        raise LedgerCorruption("不完整的 SIGNAL 必须显式列出 missing_fields")


def _project_action(action: object) -> dict[str, Any]:
    """上游 action → RECOMMENDATION action：显式键白名单。

    已知的上游展示/派生键（`illustrative`、`fact_meta`、腿的 `name/lots/...`）被剥离；
    其余未批准键（含所有成交字段）一律拒绝。
    """
    payload = _require_mapping(action, label="RECOMMENDATION action")
    for key in payload:
        if key in FORBIDDEN_RECOMMENDATION_KEYS:
            raise LedgerRefusal(f"recommendation 不得混入成交字段: {key}")
    unknown = set(payload).difference(ACTION_ALLOWED_KEYS).difference(ACTION_STRIPPED_UPSTREAM_KEYS)
    if unknown:
        raise LedgerRefusal(
            f"action 含未批准字段: {sorted(unknown)}；RECOMMENDATION 只允许 "
            f"{sorted(ACTION_ALLOWED_KEYS)}"
        )
    legs_raw = _require_sequence(payload.get("legs"), label="action.legs")
    projected_legs: list[dict[str, Any]] = []
    for index, raw_leg in enumerate(legs_raw):
        leg = _require_mapping(raw_leg, label=f"action.legs[{index}]")
        for key in leg:
            if key in FORBIDDEN_RECOMMENDATION_KEYS:
                raise LedgerRefusal(f"recommendation leg 不得混入成交字段: {key}")
        unknown_leg = set(leg).difference(LEG_ALLOWED_KEYS).difference(LEG_STRIPPED_UPSTREAM_KEYS)
        if unknown_leg:
            raise LedgerRefusal(
                f"action.legs[{index}] 含未批准字段: {sorted(unknown_leg)}；"
                f"腿只允许 {sorted(LEG_ALLOWED_KEYS)}"
            )
        projected_legs.append(
            {key: copy.deepcopy(leg[key]) for key in LEG_ALLOWED_KEYS if key in leg}
        )
    projected = {
        key: copy.deepcopy(payload[key])
        for key in ACTION_ALLOWED_KEYS.difference({"legs"})
        if key in payload
    }
    projected["legs"] = projected_legs
    # 上游 `ActionPlan.priority` 可选；与 cockpit actions_summary 一致回退 P3。
    if projected.get("priority") is None:
        projected["priority"] = "P3"
    return projected


def _validate_action(action: object) -> Mapping[str, Any]:
    payload = _require_mapping(action, label="RECOMMENDATION action")
    unknown = set(payload).difference(ACTION_ALLOWED_KEYS)
    if unknown:
        raise LedgerRefusal(f"action 含未批准字段: {sorted(unknown)}")
    for key in payload:
        if key in FORBIDDEN_RECOMMENDATION_KEYS:
            raise LedgerRefusal(f"recommendation 不得混入成交字段: {key}")
    missing = ACTION_ALLOWED_KEYS.difference(payload)
    if missing:
        raise LedgerRefusal(f"action 缺少必需字段: {sorted(missing)}")
    priority = _require_str(payload["priority"], label="action.priority")
    if priority not in ACTION_PRIORITIES:
        raise LedgerRefusal(f"action.priority 不在协议枚举内: {priority}")
    kind = _require_str(payload["kind"], label="action.kind")
    if kind not in ACTION_KINDS:
        raise LedgerRefusal(f"action.kind 不在协议枚举内: {kind}")
    _require_str(payload["code"], label="action.code")
    _require_int(payload["rank"], label="action.rank", minimum=1)
    _require_str(payload["title"], label="action.title")
    for key in (
        "reasons",
        "counter_evidence",
        "triggers",
        "invalidation_conditions",
        "risk_impact",
    ):
        values = _require_sequence(payload[key], label=f"action.{key}")
        if any(not isinstance(item, str) for item in values):
            raise LedgerRefusal(f"action.{key} 必须是字符串数组")
    if payload["fees_cents"] is not None:
        _require_int(payload["fees_cents"], label="action.fees_cents", minimum=0)
    _require_bool(payload["fees_assumed"], label="action.fees_assumed")
    legs = _require_sequence(payload["legs"], label="action.legs")
    if not legs:
        raise LedgerRefusal("action.legs 不得为空：没有腿的动作不是 recommendation")
    for index, raw_leg in enumerate(legs):
        leg = _require_mapping(raw_leg, label=f"action.legs[{index}]")
        unknown_leg = set(leg).difference(LEG_ALLOWED_KEYS)
        if unknown_leg:
            raise LedgerRefusal(f"action.legs[{index}] 含未批准字段: {sorted(unknown_leg)}")
        for key in leg:
            if key in FORBIDDEN_RECOMMENDATION_KEYS:
                raise LedgerRefusal(f"recommendation leg 不得混入成交字段: {key}")
        if set(leg) != LEG_ALLOWED_KEYS:
            raise LedgerRefusal(
                f"action.legs[{index}] 缺少必需字段: {sorted(LEG_ALLOWED_KEYS.difference(leg))}"
            )
        side = _require_str(leg["side"], label=f"action.legs[{index}].side")
        if side not in LEG_SIDES:
            raise LedgerRefusal(f"action.legs[{index}].side 不在协议枚举内: {side}")
        _require_str(leg["ts_code"], label=f"action.legs[{index}].ts_code")
        executable = _require_bool(leg["executable"], label=f"action.legs[{index}].executable")
        for field in ("quantity", "price_milli"):
            value = leg[field]
            if value is None:
                if executable:
                    raise LedgerRefusal(
                        f"action.legs[{index}].{field} 不得为 null：executable leg 必须有数值"
                    )
                continue
            _require_int(value, label=f"action.legs[{index}].{field}", minimum=0)
    return payload


def _validate_recommendation_content(content: Mapping[str, Any], missing: tuple[str, ...]) -> None:
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
    elif "expected_execution_date" not in missing:
        raise LedgerCorruption("RECOMMENDATION expected_execution_date 为空但未记入 missing_fields")
    try:
        _validate_action(content["action"])
    except LedgerRefusal as error:
        raise LedgerCorruption(f"RECOMMENDATION action 非法: {error}") from error


def _project_holding(holding: object, *, index: int, missing: list[str]) -> dict[str, Any]:
    """上游 holding → VALUATION 估值事实白名单；`stance`/理由/研究块一律移除。

    白名单**只对 holdings[] 生效**：这里逐字段显式类型化，未知键不读取；
    非字符串/错误类型一律置 null 并记缺失，而不是原样落盘。
    """
    source = _require_mapping(holding, label=f"valuation holdings[{index}]")
    for field in HOLDING_REQUIRED_FIELDS:
        if field not in source:
            raise LedgerRefusal(f"valuation holdings[{index}].{field} 缺失")
    _require_str(source["ts_code"], label=f"holdings[{index}].ts_code")
    _require_int(source["quantity"], label=f"holdings[{index}].quantity", minimum=0)
    _require_number(source["weight"], label=f"holdings[{index}].weight")
    _require_int(
        source["market_value_cents"], label=f"holdings[{index}].market_value_cents", minimum=0
    )
    _require_int(source["price_milli"], label=f"holdings[{index}].price_milli", minimum=0)
    _require_str(source["bar_quality"], label=f"holdings[{index}].bar_quality")
    payload: dict[str, Any] = {}
    for field in sorted(VALUATION_HOLDING_KEYS):
        if field not in source or source[field] is None:
            payload[field] = None
            continue
        value = source[field]
        kind = HOLDING_TYPES[field]
        if field in HOLDING_REQUIRED_FIELDS:
            payload[field] = _project_holding_leaf(
                value, label=f"holdings[{index}].{field}", kind=kind, field=field
            )
            continue
        try:
            payload[field] = _project_holding_leaf(
                value, label=f"holdings[{index}].{field}", kind=kind, field=field
            )
        except LedgerRefusal:
            payload[field] = None
            missing.append(f"holdings[{index}].{field}_type_invalid")
    for field in HOLDING_EXPECTED_FIELDS:
        if payload.get(field) is None:
            missing.append(f"holdings[{index}].{field}")
    return payload


def _project_holding_leaf(value: object, *, label: str, kind: str, field: str) -> Any:
    enum = HOLDING_ENUMS.get(field)
    return _project_typed_value(value, label=label, kind=kind, enum=enum)


def _validate_holding(holding: object, *, index: int, missing: list[str]) -> Mapping[str, Any]:
    source = _require_mapping(holding, label=f"valuation holdings[{index}]")
    if set(source) != VALUATION_HOLDING_KEYS:
        raise LedgerCorruption(
            f"valuation holdings[{index}] 字段集合与补遗 2 不一致: "
            f"{sorted(set(source).symmetric_difference(VALUATION_HOLDING_KEYS))}"
        )
    for field in HOLDING_REQUIRED_FIELDS:
        if source[field] is None:
            raise LedgerCorruption(f"valuation holdings[{index}].{field} 不得为 null")
    for field, kind in HOLDING_TYPES.items():
        value = source[field]
        if value is None:
            continue
        try:
            _project_holding_leaf(value, label=f"holdings[{index}].{field}", kind=kind, field=field)
        except LedgerRefusal as error:
            raise LedgerCorruption(f"VALUATION {error}") from error
    for field in HOLDING_EXPECTED_FIELDS:
        if source[field] is None:
            missing.append(f"holdings[{index}].{field}")
    return source


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
    _validate_principal(principal)
    holdings = _require_sequence(content["holdings"], label="VALUATION holdings")
    derived_missing: list[str] = []
    for index, holding in enumerate(holdings):
        _validate_holding(holding, index=index, missing=derived_missing)
    _validate_concentration(content["concentration"])
    if content["concentration"] is None:
        derived_missing.append("concentration")
    _validate_reconciliation(content["reconciliation_reminder"])
    if content["reconciliation_reminder"] is None:
        derived_missing.append("v3_cockpit.reconciliation_reminder")
    _validate_valuation_data_quality(
        _require_mapping(content["data_quality"], label="VALUATION data_quality")
    )
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
        # 协议 §4：只有 `reversed_by IS NULL` 才可导入；空串不是 NULL。
        raise LedgerCorruption("CONFIRMED_FILL 不得是已撤销/带撤销标记的成交")
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
            _validate_recommendation_content(payload, missing)
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
    status = payload["content"].get("status") if isinstance(payload["content"], Mapping) else None
    policy_required = record_type in {"RECOMMENDATION", "VALUATION"} or (
        record_type == "SIGNAL" and status != "DATA_INSUFFICIENT"
    )
    _validate_policy(payload["policy"], required=policy_required)
    _validate_batch(payload["ingest_batch"])
    recorded_at = _require_aware_instant(payload["recorded_at"], label="event.recorded_at")
    if _ymd_of(recorded_at) < as_of:
        raise LedgerCorruption("事件 recorded_at 早于 as_of_trade_date")
    declared_hash = _verify_hex64(payload["content_hash"], label="event.content_hash")
    source_sha = _verify_hex64(source["sha256"], label="event.source.sha256")
    actual_hash = content_hash(
        record_type,
        _require_mapping(payload["content"], label="event.content"),
        source_sha,
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
            event = json.loads(line, parse_constant=_reject_json_constant)
        except json.JSONDecodeError as error:
            raise LedgerCorruption(f"{path.name} 第 {line_number} 行不是合法 JSON") from error
        except LedgerRefusal as error:
            raise LedgerCorruption(f"{path.name} 第 {line_number} 行非法: {error}") from error
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
    """跨五文件按批分组：拒绝缺序号/重复序号/count 不一致/重复自然键（补遗 2 §3）。"""
    batches: dict[str, tuple[int, set[int]]] = {}
    natural_keys: set[str] = set()
    for events in events_by_type.values():
        for event in events:
            key = str(event["natural_key"])
            if key in natural_keys:
                raise LedgerCorruption(f"跨文件出现重复 natural_key: {key}")
            natural_keys.add(key)
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
        if ordinals != set(range(1, count + 1)):
            raise LedgerCorruption(
                f"batch {identifier} 不完整: {sorted(ordinals)} / 1..{count}；"
                "部分批已停写，拒绝重放、截断或静默修复"
            )
    return {identifier: count for identifier, (count, _) in batches.items()}


# --------------------------------------------------------------------------------------
# Append machinery
# --------------------------------------------------------------------------------------


@contextmanager
def _writer_lock(root: Path, *, create: bool = True) -> Generator[None, None, None]:
    """单写者排他锁；覆盖 verify、整批预检、全部 append 与最后一次 fsync。

    `create=False` 时（只读 `verify` 路径）若锁文件不存在则不加锁，绝不向账本目录
    新增文件；`init` 会预先创建该锁文件，正常账本两条路径都加锁。
    """
    path = root / WRITER_LOCK_FILENAME
    if not create and not path.exists():
        yield
        return
    flags = os.O_RDWR | (os.O_CREAT if create else 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        if create:
            os.chmod(path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


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


def _append_line(path: Path, payload: Mapping[str, Any]) -> None:
    """一行一次 append + flush + fsync；测试用此函数注入 I/O 故障。"""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(payload) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _apply_policy_gate(
    root: Path,
    *,
    policy: Mapping[str, str] | None,
    existing_signals: Sequence[Mapping[str, Any]],
) -> None:
    """补遗 1 §1：baseline 在首个非不足日钉住，之后不得静默改变。

    - `DATA_INSUFFICIENT` 日的 SIGNAL 没有 policy 身份，不构成"已有证据"；
    - 只有**已钉住**了携带 policy 身份的 SIGNAL 而 baseline 缺失时才拒绝（不得静默重建）；
    - 首个非不足日之前只写不足日 SIGNAL 是合法状态，不会被拒。
    """
    if policy is None:
        return
    policy_signals = [signal for signal in existing_signals if signal.get("policy")]
    if load_policy_baseline(root) is None and policy_signals:
        raise LedgerRefusal(
            "POLICY_BASELINE_MISSING_WITH_EVIDENCE: 已有 SIGNAL 但 policy_baseline 缺失；"
            "不得静默重建，须所有者人工复核"
        )
    _check_policy_baseline(root, policy)


def _append_drafts(
    root: Path | str | None,
    drafts: Sequence[Draft],
    *,
    batch_kind: str,
    batch_source_sha: str,
    policy: Mapping[str, str] | None = None,
    policy_source_sha256: str | None = None,
    policy_as_of_trade_date: str | None = None,
    precheck: Callable[[Mapping[str, list[dict[str, Any]]]], None] | None = None,
    clock_precheck: Callable[[datetime], None] | None = None,
) -> dict[str, Any]:
    """单写者锁内 verify 全账 → 整批预检 → 实际时钟校钟 → 追加；预检拒绝字节不变。

    - 同自然键 + 同 `content_hash` → 幂等 no-op，不新增行；
    - 同自然键 + 不同 `content_hash` → 整批拒绝，既有字节不变；
    - 只为新行分配批 ID 与 `ordinal=1..count`；
    - `clock_precheck` 在锁内、真正追加前以**实际时钟**重校窗口（等锁到次日即拒绝）；
    - I/O/崩溃：既有前缀不变，可能留下不完整新尾；停止写入并报错，`verify` 拒绝重放。
    """
    resolved = ledger_root(root)
    with _writer_lock(resolved):
        manifest = load_manifest(resolved)
        events_by_type = _read_all_events(resolved, manifest)
        _verify_batches(events_by_type)
        # 任何 append 前的**完整**全账 verify：含 policy_baseline 与 SIGNAL 一致性。
        # 只有 _verify_batches 不够：坏 baseline 之后仍可追加（B 反例 8）。
        _verify_policy_baseline_consistency(resolved, events_by_type)
        if precheck is not None:
            precheck(events_by_type)
        _apply_policy_gate(resolved, policy=policy, existing_signals=events_by_type["SIGNAL"])
        ordered = _sort_drafts(drafts)
        existing_by_key: dict[str, Mapping[str, Any]] = {}
        for events in events_by_type.values():
            for event in events:
                existing_by_key[str(event["natural_key"])] = event
        seen_drafts: dict[str, Draft] = {}
        new_drafts: list[Draft] = []
        skipped = {record_type: 0 for record_type in RECORD_FILES}
        for draft in ordered:
            _parse_ymd(draft.as_of_trade_date, label="draft.as_of_trade_date")
            _validate_source(draft.source)
            draft_status = (
                draft.content.get("status") if isinstance(draft.content, Mapping) else None
            )
            policy_required = draft.record_type in {"RECOMMENDATION", "VALUATION"} or (
                draft.record_type == "SIGNAL" and draft_status != "DATA_INSUFFICIENT"
            )
            _validate_policy(draft.policy, required=policy_required)
            if draft.missing_fields != tuple(sorted(set(draft.missing_fields))):
                raise LedgerCorruption("draft.missing_fields 必须排序且去重")
            _validate_content(draft.record_type, draft.content, draft.missing_fields)
            if draft.natural_key in seen_drafts:
                raise LedgerConflict(f"同一批输入产生重复 natural_key: {draft.natural_key}")
            seen_drafts[draft.natural_key] = draft
            prior = existing_by_key.get(draft.natural_key)
            if prior is not None:
                if prior["content_hash"] != draft.content_hash:
                    raise LedgerConflict(
                        f"{draft.record_type} natural_key={draft.natural_key} 已存在不同内容；"
                        "append-only 协议拒绝覆盖"
                    )
                skipped[draft.record_type] += 1
                continue
            new_drafts.append(draft)
        batch_id = _batch_id(batch_kind, batch_source_sha, new_drafts)
        recorded_at = utc_now()
        if clock_precheck is not None:
            clock_precheck(recorded_at)
        appended = {record_type: 0 for record_type in RECORD_FILES}
        last_hashes = {
            record_type: (events[-1]["event_hash"] if events else ZERO_HASH)
            for record_type, events in events_by_type.items()
        }
        count = len(new_drafts)
        for ordinal, draft in enumerate(new_drafts, start=1):
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
            try:
                _append_line(_record_path(resolved, draft.record_type), event)
            except OSError as error:
                raise LedgerRefusal(
                    f"APPEND_IO_FAILURE: 批 {batch_id} 在 ordinal {ordinal}/{count} 写入失败"
                    f"（{error}）；既有前缀不变但可能留下不完整新尾，停止写入；"
                    "运行 verify 复核，不得截断或重试补行"
                ) from error
            last_hashes[draft.record_type] = str(event["event_hash"])
            appended[draft.record_type] += 1
        if policy is not None and count:
            if policy_source_sha256 is None or policy_as_of_trade_date is None:
                raise LedgerCorruption("写入 policy_baseline 缺少来源 SHA 或 as_of")
            _write_policy_baseline(
                resolved,
                policy,
                as_of_trade_date=policy_as_of_trade_date,
                source_sha256=policy_source_sha256,
                created_at=recorded_at,
            )
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


def _reject_json_constant(value: str) -> Any:
    """`json.loads` 对 NaN/Infinity 的钩子：一律拒绝，不静默接受非有限数。"""
    raise LedgerRefusal(f"输入 JSON 含非有限数值常量 {value}，拒绝")


def _reject_non_finite_tree(value: object, *, path: str = "$") -> None:
    """解码后全树检查：`1e999` 这类溢出 digit 会被 Python 解成 +Inf，必须拒绝。

    `parse_constant` 只覆盖字面 NaN/Infinity/-Infinity；`1e999` 走普通 float 解析，
    因此必须在整棵树（含未投影字段）上做有限性检查（B 终判 #8）。
    """
    if isinstance(value, float) and not math.isfinite(value):
        raise LedgerRefusal(f"输入 JSON 在 {path} 处含非有限数值，拒绝")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_non_finite_tree(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_non_finite_tree(item, path=f"{path}[{index}]")


def _read_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LedgerRefusal(f"{label} 不是合法 UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise LedgerRefusal(f"{label} 必须是 JSON object")
    _reject_non_finite_tree(payload, path=label)
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


def _validate_close_window(
    *,
    as_of: str,
    generated_at: datetime,
    now: datetime,
    open_days: Sequence[str] | None,
) -> None:
    """补遗 2 §1：只接受已确认开市日，且必须为 D 15:00 <= generated_at <= now < D+1 00:00。

    - `open_days` 为 None 表示受信交易日历不可用/未知：整次拒绝。
    - `open_days` 为空表示日历确认当日休市：整次拒绝。
    - 比较真实瞬间；不使用 UTC 日期字符串或“同一上海日历日”作为充分条件。
    """
    if open_days is None:
        raise LedgerRefusal(
            "交易日历未知：无法确认 as_of_trade_date 是开市日；整次拒绝（不写任何 event）"
        )
    if as_of not in set(open_days):
        raise LedgerRefusal(f"as_of_trade_date={as_of} 不是受信交易日历中的开市日；整次拒绝")
    day = date.fromisoformat(_iso_day(as_of))
    close = datetime.combine(day, time(15, 0, 0), tzinfo=SHANGHAI)
    next_midnight = datetime.combine(day + timedelta(days=1), time(0, 0, 0), tzinfo=SHANGHAI)
    if _shanghai(generated_at) < close:
        raise LedgerRefusal(
            f"brief.generated_at 上海时间 {_shanghai(generated_at).isoformat()} 早于 "
            f"{as_of} 15:00:00 收盘窗口；不得消费盘中生成的日报"
        )
    if not (_shanghai(generated_at) <= _shanghai(now) < next_midnight):
        raise LedgerRefusal(
            f"台账运行时钟上海时间 {_shanghai(now).isoformat()} 不在 "
            f"[{_shanghai(generated_at).isoformat()}, {next_midnight.isoformat()}) 窗口内；"
            "跨午夜不得补录，过期即 MISSED"
        )


def _validate_brief(
    brief: Mapping[str, Any],
    *,
    account_id: str,
    now: datetime,
    calendar_db: Path | str | None = None,
) -> dict[str, Any]:
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
    if now.tzinfo is None:
        raise LedgerRefusal("台账运行时钟必须是带时区的时间")
    _validate_close_window(
        as_of=as_of,
        generated_at=generated_at,
        now=now,
        open_days=_calendar_open_days(calendar_db, as_of),
    )
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
    trigger_codes = _project_trigger_codes(first_section)
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
            _validate_action(_project_action(action))
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
    if status == "ACTIONABLE" and not any(
        (leg.get("quantity") or 0) > 0 for leg in executable_legs
    ):
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
    # 补遗 1 §1：不足日不得读取/绑定 policy 身份；validate 仍原样记录供审计。
    policy = (
        _policy_identity(brief)
        if status != "DATA_INSUFFICIENT" and isinstance(cockpit, Mapping)
        else None
    )
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
        "trigger_codes": trigger_codes,
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
    trigger_codes = validated.get("trigger_codes")
    if trigger_codes is None:
        missing.append(OBSERVATION_TRIGGERS_UNPROJECTED)
    cockpit = validated["cockpit"]
    market_regime: Mapping[str, Any] | None = None
    router: Mapping[str, Any] | None = None
    deconcentration_state: Mapping[str, Any] | None = None
    if isinstance(cockpit, Mapping):
        market_regime = _project_typed_block(
            cockpit.get("market_regime"),
            label="v3_cockpit.market_regime",
            types=SIGNAL_MARKET_REGIME_TYPES,
            missing=missing,
            missing_prefix="market_regime",
        )
        router = _project_typed_block(
            cockpit.get("router"),
            label="v3_cockpit.router",
            types=SIGNAL_ROUTER_TYPES,
            missing=missing,
            missing_prefix="router",
        )
        deconcentration_state = _project_typed_block(
            cockpit.get("deconcentration"),
            label="v3_cockpit.deconcentration",
            types=SIGNAL_DECONCENTRATION_TYPES,
            missing=missing,
            missing_prefix="deconcentration",
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
    data_quality = _project_data_quality(validated["data_quality"], missing=missing)
    for key in ("status", "summary_status", "missing_fields"):
        if key not in data_quality:
            missing.append(f"data_quality.{key}")
    suppressed = len(validated["actions"]) if validated["status"] == "DATA_INSUFFICIENT" else 0
    # B 建议：no_action_reason 不再持久化任何自由文本，只保留状态原因码与缺失标志，
    # 从根上消除「文本夹带份数/价格」的后门（关键词枚举不可靠）。
    no_action_reason_code = _NO_ACTION_REASON_CODES.get(validated["status"])
    no_action_reason_present = first.get("no_action_reason") is not None
    if no_action_reason_present and no_action_reason_code is None:
        missing.append("decision.no_action_reason_unclassified")
    decision: dict[str, Any] = {
        "evidence_complete": validated["status"] != "DATA_INSUFFICIENT",
        "no_action_reason_code": no_action_reason_code,
        "no_action_reason_present": no_action_reason_present,
        "suppressed_recommendation_count": suppressed,
    }
    if trigger_codes is not None:
        decision["trigger_codes"] = list(trigger_codes)
    content = {
        "brief_schema": BRIEF_SCHEMA,
        "report_id": validated["report_id"],
        "status": validated["status"],
        "actionable": validated["status"] == "ACTIONABLE",
        "generated_at": validated["generated_at"].isoformat(),
        "expected_next_trade_date": validated["expected_next_trade_date"],
        "account_id_source": validated["account_id_source"],
        "account_status": validated["account_status"],
        "decision": decision,
        "market_regime": market_regime,
        "router": router,
        "deconcentration_state": deconcentration_state,
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
    expected_execution = validated["expected_next_trade_date"]
    missing: tuple[str, ...] = (
        () if expected_execution is not None else ("expected_execution_date",)
    )
    for action in validated["actions"]:
        projected_action = _project_action(action)
        content = {
            "brief_schema": BRIEF_SCHEMA,
            "report_id": validated["report_id"],
            "status": validated["status"],
            "generated_at": validated["generated_at"].isoformat(),
            "expected_execution_date": expected_execution,
            "action": projected_action,
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
                missing_fields=missing,
            )
        )
    return drafts


def _project_concentration(concentration: object, *, missing: list[str]) -> dict[str, Any] | None:
    """concentration：键白名单 + 显式叶类型，未知键丢弃并逐个披露。

    上游类型（dailyReport.ts:629-636）五个数值字段与 top_position 均可为 null；
    top_position 只允许 `ts_code/name/weight` 三个标量键，出现其它键即拒绝
    （防止 `{"legs":[...]}` 被吞成空对象）。`disclosure` 等未知键 → `_unprojected`。
    """
    if concentration is None:
        return None
    payload = _require_mapping(concentration, label="brief.concentration")
    projected: dict[str, Any] = {}
    for key in sorted(payload):
        value = payload[key]
        if key in CONCENTRATION_NUMBER_KEYS:
            if value is None:
                projected[key] = None
                missing.append(f"concentration.{key}")
            else:
                projected[key] = _project_typed_value(
                    value, label=f"concentration.{key}", kind="number"
                )
        elif key == "top_position":
            if value is None:
                projected[key] = None
                missing.append("concentration.top_position")
                continue
            top = _require_mapping(value, label="concentration.top_position")
            unknown_top = set(top).difference(CONCENTRATION_TOP_POSITION_TYPES)
            if unknown_top:
                raise LedgerRefusal(
                    f"concentration.top_position 含未批准字段: {sorted(unknown_top)}"
                )
            projected[key] = {
                name: _project_typed_value(
                    top[name], label=f"concentration.top_position.{name}", kind=kind
                )
                for name, kind in sorted(CONCENTRATION_TOP_POSITION_TYPES.items())
                if name in top
            }
        else:
            missing.append(f"concentration.{key}_unprojected")
    return projected


def _validate_concentration(concentration: object) -> None:
    if concentration is None:
        return
    payload = _require_mapping(concentration, label="VALUATION concentration")
    unknown = set(payload).difference(VALUATION_CONCENTRATION_KEYS)
    if unknown:
        raise LedgerCorruption(f"VALUATION concentration 含未批准字段: {sorted(unknown)}")
    for key, value in payload.items():
        if key == "top_position":
            if value is None:
                # 上游允许 null（无持仓/空账户），合法。
                continue
            if not isinstance(value, Mapping):
                raise LedgerCorruption(
                    "VALUATION concentration.top_position 必须是 JSON object 或 null"
                )
            unknown_top = set(value).difference(VALUATION_TOP_POSITION_KEYS)
            if unknown_top:
                raise LedgerCorruption(
                    f"VALUATION concentration.top_position 含未批准字段: {sorted(unknown_top)}"
                )
            _validate_concentration_top(value)
        elif key in CONCENTRATION_NUMBER_KEYS:
            _project_typed_value(value, label=f"concentration.{key}", kind="number?")
        else:
            raise LedgerCorruption(f"VALUATION concentration.{key} 必须是数值")


def _validate_concentration_top(top: Mapping[str, Any]) -> None:
    for name, kind in CONCENTRATION_TOP_POSITION_TYPES.items():
        if name in top:
            _project_typed_value(top[name], label=f"concentration.top_position.{name}", kind=kind)


def _project_reconciliation(reminder: object, *, missing: list[str]) -> dict[str, Any] | None:
    """reconciliation：只落 lag_trade_days/needs_reminder；message_zh 识别但披露不落盘。"""
    if reminder is None:
        return None
    payload = _require_mapping(reminder, label="v3_cockpit.reconciliation_reminder")
    projected: dict[str, Any] = {}
    for key in sorted(payload):
        value = payload[key]
        if key == "message_zh":
            # 上游 string|null；可能含「需核对 5 个交易日内 3 笔成交」叙述 → 不落盘，披露。
            missing.append("reconciliation_reminder.message_zh_unprojected")
            continue
        spec = RECONCILIATION_TYPES.get(str(key))
        if spec is None:
            missing.append(f"reconciliation_reminder.{key}_unprojected")
            continue
        kind, enum = spec
        projected[str(key)] = _project_typed_value(
            value, label=f"reconciliation_reminder.{key}", kind=kind, enum=enum
        )
    return projected


def _validate_reconciliation(reminder: object) -> None:
    if reminder is None:
        return
    payload = _require_mapping(reminder, label="VALUATION reconciliation_reminder")
    unknown = set(payload).difference(RECONCILIATION_TYPES)
    if unknown:
        raise LedgerCorruption(f"VALUATION reconciliation_reminder 含未批准字段: {sorted(unknown)}")
    for key, value in payload.items():
        kind, enum = RECONCILIATION_TYPES[str(key)]
        _project_typed_value(value, label=f"reconciliation_reminder.{key}", kind=kind, enum=enum)


def _project_principal(principal: Mapping[str, Any]) -> dict[str, Any]:
    """principal 只允许协议列出的五个数值字段；未知键（如 proposed_exit）拒绝。"""
    unknown = set(principal).difference(PRINCIPAL_FIELDS)
    if unknown:
        raise LedgerRefusal(f"v3_cockpit.principal 含未批准字段: {sorted(unknown)}")
    projected: dict[str, Any] = {}
    for field, (kind, minimum) in PRINCIPAL_TYPES.items():
        if field not in principal:
            raise LedgerRefusal(f"v3_cockpit.principal.{field} 缺失")
        value = principal[field]
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise LedgerRefusal(f"v3_cockpit.principal.{field} 必须是整数")
            if minimum is not None and value < minimum:
                raise LedgerRefusal(f"v3_cockpit.principal.{field} 必须 >= {minimum}")
            projected[field] = value
        else:
            projected[field] = _project_typed_value(
                value, label=f"v3_cockpit.principal.{field}", kind="number"
            )
    return projected


def _validate_principal(principal: Mapping[str, Any]) -> None:
    unknown = set(principal).difference(PRINCIPAL_FIELDS)
    if unknown:
        raise LedgerCorruption(f"VALUATION principal 含未批准字段: {sorted(unknown)}")
    for field, (kind, minimum) in PRINCIPAL_TYPES.items():
        if field not in principal:
            raise LedgerCorruption(f"VALUATION principal.{field} 缺失")
        value = principal[field]
        if kind == "int":
            _require_int(value, label=f"principal.{field}", minimum=minimum)
        else:
            _project_typed_value(value, label=f"principal.{field}", kind="number")


def _valuation_content(validated: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    cockpit = _require_mapping(validated["cockpit"], label="brief.v3_cockpit")
    principal = _require_mapping(cockpit.get("principal"), label="v3_cockpit.principal")
    projected_principal = _project_principal(principal)
    holdings: list[dict[str, Any]] = []
    for index, holding in enumerate(validated["holdings"]):
        holdings.append(_project_holding(holding, index=index, missing=missing))
    concentration = validated.get("concentration")
    if concentration is None:
        missing.append("concentration")
    reconciliation = cockpit.get("reconciliation_reminder")
    if reconciliation is None:
        missing.append("v3_cockpit.reconciliation_reminder")
    projected_concentration = _project_concentration(concentration, missing=missing)
    projected_reconciliation = _project_reconciliation(reconciliation, missing=missing)
    content = {
        "brief_schema": BRIEF_SCHEMA,
        "report_id": validated["report_id"],
        "status": validated["status"],
        "generated_at": validated["generated_at"].isoformat(),
        "principal": projected_principal,
        "holdings": copy.deepcopy(holdings),
        "concentration": (
            copy.deepcopy(projected_concentration) if projected_concentration is not None else None
        ),
        "reconciliation_reminder": (
            copy.deepcopy(projected_reconciliation)
            if projected_reconciliation is not None
            else None
        ),
        "data_quality": _project_valuation_data_quality(
            _require_mapping(validated["data_quality"], label="brief.data_quality"),
            missing=missing,
        ),
    }
    return content, sorted(set(missing))


def ingest_brief(
    brief_path: Path | str,
    *,
    root: Path | str | None = None,
    account_id: str = LEDGER_ACCOUNT_ID,
    calendar_db: Path | str | None = None,
) -> dict[str, Any]:
    """读取一份 FinanceMCP compact brief，追加 SIGNAL / RECOMMENDATION / VALUATION。

    `calendar_db` 是受信交易日历（只读 `trade_cal`）；缺省或未知时整次拒绝，
    这是补遗 2 §1 的收盘窗口硬门槛。
    """
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
    validated = _validate_brief(
        brief, account_id=account_id, now=utc_now(), calendar_db=calendar_db
    )
    source = _brief_source_identity(
        brief, path=path, raw_sha=raw_sha, generated_at=validated["generated_at"].isoformat()
    )
    policy = validated["policy"]
    if validated["status"] == "DATA_INSUFFICIENT":
        # 补遗 1 §1：baseline 只在**首个非不足日**钉住；不足日即使 cockpit 带
        # policy_release 也不得提前绑定，SIGNAL 的 policy 身份置空并显式记缺失。
        policy = None
    drafts: list[Draft] = []
    signal_content, signal_missing = _signal_content(validated)
    if policy is None and validated["status"] == "DATA_INSUFFICIENT":
        signal_missing = sorted({*signal_missing, "v3_cockpit.policy_release"})
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

    def _locked_clock_recheck(moment: datetime) -> None:
        """锁内、真正追加前用实际时钟重校窗口（等待锁到次日即整批拒绝）。"""
        _validate_close_window(
            as_of=validated["as_of_trade_date"],
            generated_at=validated["generated_at"],
            now=moment,
            open_days=_calendar_open_days(calendar_db, validated["as_of_trade_date"]),
        )

    result = _append_drafts(
        resolved_root,
        drafts,
        batch_kind="daily_brief",
        batch_source_sha=raw_sha,
        policy=dict(policy) if policy is not None else None,
        policy_source_sha256=raw_sha,
        policy_as_of_trade_date=validated["as_of_trade_date"],
        clock_precheck=_locked_clock_recheck,
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


def _reversed_imported_fill_ids(
    connection: sqlite3.Connection, imported: Iterable[str]
) -> list[str]:
    """撤销复核只针对**已导入** fill；源行现在 `reversed_by` 非 NULL（含空串）即视为已撤销。"""
    imported_set = set(imported)
    if not imported_set:
        return []
    rows = connection.execute(
        "SELECT event_id FROM account_event WHERE reversed_by IS NOT NULL"
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
        if record.get("reversed_by") is not None:
            # 协议 §4：只有 `reversed_by IS NULL` 才导入；空串不是 NULL，按正常筛选排除，
            # 不判 CORRUPT、不阻断整批。
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
        # 源行 SHA 只覆盖 account_event 原生 19 列；不掺入合成 schema 键。
        native_row = {column: record[column] for column in ACCOUNT_EVENT_COLUMNS}
        row_sha = sha256_text(canonical_json(native_row))
        content = {key: record[key] for key in sorted(record)}
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
        schema_fingerprint = _account_event_schema_fingerprint(connection)
        drafts, skipped = _fill_drafts(
            connection,
            account_id=account_id,
            schema_fingerprint=schema_fingerprint,
            db_path=db_path,
            now_ymd=_now_shanghai().strftime("%Y%m%d"),
        )

        def _source_precheck(
            events_by_type: Mapping[str, list[dict[str, Any]]],
        ) -> None:
            """锁内复核：已导入成交在源库不得被撤销或消失（只读查询）。"""
            imported = [
                str(event["content"]["event_id"]) for event in events_by_type["CONFIRMED_FILL"]
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

        if not drafts:
            _source_precheck(_read_all_events(resolved_root, manifest))
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
            resolved_root,
            drafts,
            batch_kind="confirmed_fills",
            batch_source_sha=source_sha,
            precheck=_source_precheck,
        )
    finally:
        connection.close()
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


def _verify_policy_baseline_consistency(
    root: Path, events_by_type: Mapping[str, Sequence[Mapping[str, Any]]]
) -> Mapping[str, str] | None:
    """全账 verify 的一部分：baseline 与每条携带 policy 的 SIGNAL 必须一致。"""
    baseline = load_policy_baseline(root)
    if baseline is None:
        return None
    for signal in events_by_type["SIGNAL"]:
        policy = signal["policy"]
        if policy is None:
            continue
        for key in ("strategy_id", "version", "content_hash"):
            if str(policy.get(key)) != baseline[key]:
                raise LedgerCorruption(
                    f"SIGNAL {signal['as_of_trade_date']} policy.{key} 与 policy_baseline 不一致"
                )
    return baseline


def verify_ledger(root: Path | str | None = None) -> dict[str, Any]:
    resolved = ledger_root(root)
    manifest = load_manifest(resolved)
    with _writer_lock(resolved, create=False):
        events_by_type = _read_all_events(resolved, manifest)
        batches = _verify_batches(events_by_type)
        baseline = _verify_policy_baseline_consistency(resolved, events_by_type)
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
        "policy_baseline": baseline,
    }


def _default_calendar_db() -> Path | None:
    configured = os.environ.get("TACTICORE_V3_LEDGER_CALENDAR_DB")
    if configured:
        return Path(configured)
    return None


def _calendar_open_days(calendar_db: Path | str | None, day: str) -> list[str] | None:
    """只读取信交易日历，确认 `day` 是开市日。

    返回 `[day]`（开市）、`[]`（日历明确休市/未知日期）、`None`（日历不可用/未配置）。
    调用方对 `None`/`[]` 一律整次拒绝（补遗 2 §1）。
    """
    resolved = Path(calendar_db) if calendar_db is not None else _default_calendar_db()
    if resolved is None:
        return None
    if not resolved.is_file():
        raise LedgerRefusal(f"受信交易日历库不存在: {resolved}")
    connection = _open_readonly_sqlite(resolved)
    try:
        rows = connection.execute(
            "SELECT cal_date, is_open FROM trade_cal WHERE cal_date = ?", (day,)
        ).fetchall()
    except sqlite3.DatabaseError as error:
        raise LedgerRefusal("交易日历库缺少 trade_cal 表") from error
    finally:
        connection.close()
    if not rows:
        return []
    return [day] if int(rows[0]["is_open"] or 0) == 1 else []


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


def _fill_coincidences_by_leg(
    recommendation: _Recommendation, fills: Sequence[Mapping[str, Any]]
) -> tuple[dict[int, list[str]], list[str]]:
    """派生视图：仅按同日同码同向找出**候选重合**，绝不声称成交归属或执行（补遗 2 §2）。

    结果只能提示人工复核；不把成交自动匹配给 recommendation，也不据此解除 UNRESOLVED。
    """
    expected = recommendation.expected_execution_date
    if expected is None:
        return {}, []
    by_leg: dict[int, list[str]] = {}
    all_coincident: list[str] = []
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
                all_coincident.append(str(fill["event_id"]))
                break
    normalized = {index: sorted(set(ids)) for index, ids in by_leg.items()}
    return normalized, sorted(set(all_coincident))


def status_report(
    root: Path | str | None = None,
    *,
    calendar_db: Path | str | None = None,
) -> dict[str, Any]:
    """只读复核：计数、逾期未执行建议、MISSED 日与暂停建议。"""
    resolved = ledger_root(root)
    manifest = load_manifest(resolved)
    with _writer_lock(resolved, create=False):
        events_by_type = _read_all_events(resolved, manifest)
        _verify_batches(events_by_type)
        baseline = _verify_policy_baseline_consistency(resolved, events_by_type)
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
    review: list[dict[str, Any]] = []
    unresolved: list[str] = []
    warnings: list[str] = []
    if baseline is None and signals:
        warnings.append("POLICY_BASELINE_MISSING_WITH_SIGNALS")
    matches_by_recommendation: dict[str, list[str]] = {}
    for recommendation in recommendations:
        coincident_by_leg, coincident = _fill_coincidences_by_leg(recommendation, fills)
        matches_by_recommendation[recommendation.event_id] = coincident
        expected = recommendation.expected_execution_date
        executable_indices = [
            index for index, leg in enumerate(recommendation.legs) if leg["executable"]
        ]
        coincident_legs = [index for index in executable_indices if index in coincident_by_leg]
        # 补遗 2 §2：同日同码同向只是"候选重合"，不自动判 MATCHED，也不是执行证明。
        if expected is None:
            match_status = "NO_EXPECTED_DATE"
        elif not executable_indices:
            match_status = "NOT_EXECUTABLE"
        elif expected > now_ymd:
            match_status = "NOT_DUE"
        elif coincident_legs:
            match_status = "COINCIDENT_FILLS_UNATTRIBUTED"
        else:
            match_status = "NO_COINCIDENT_FILL"
        reason_id = reasons_by_recommendation.get(recommendation.event_id)
        if reason_id is not None and recommendation.event_id in full_reason_ids and coincident:
            warnings.append(f"REASON_VS_FILL_CONTRADICTION:{recommendation.event_id}")
        # 任何未给出显式原因的已到期建议都留在 UNRESOLVED；重合成交不解除它。
        if match_status in {"COINCIDENT_FILLS_UNATTRIBUTED", "NO_COINCIDENT_FILL"} and (
            reason_id is None
        ):
            unresolved.append(recommendation.event_id)
        review.append(
            {
                "recommendation_event_id": recommendation.event_id,
                "as_of_trade_date": recommendation.as_of_trade_date,
                "expected_execution_date": expected,
                "action_code": recommendation.action_code,
                "match_status": match_status,
                "coincident_fill_event_ids": coincident,
                "coincident_leg_indices": coincident_legs,
                "executable_leg_indices": executable_indices,
                "unexecuted_reason_event_id": reason_id,
                "attribution": "NOT_ATTRIBUTED",
            }
        )
    coincident_fill_ids = {fill_id for ids in matches_by_recommendation.values() for fill_id in ids}
    unattributed_fills = sorted(
        str(fill["event_id"]) for fill in fills if str(fill["event_id"]) not in coincident_fill_ids
    )
    signal_by_day = {str(event["as_of_trade_date"]): event for event in signals}
    for signal in signals:
        day = str(signal["as_of_trade_date"])
        content = signal["content"]
        # 补遗 2：SIGNAL 不再携带份数/价格，状态一致性只核对动作与建议数量。
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
            # 执行日之后已过去的交易日数；执行日当天不计。
            age = len([day for day in open_days_for_age if expected < day <= upper])
        else:
            age = max(0, (now_date - date.fromisoformat(_iso_day(expected))).days - 1)
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
        "unattributed_fill_event_ids": unattributed_fills,
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
    brief.add_argument(
        "--calendar-db",
        default=None,
        help=(
            "受信只读交易日历（ashare.sqlite 的 trade_cal）；缺省 "
            "TACTICORE_V3_LEDGER_CALENDAR_DB；未知即拒绝整次运行"
        ),
    )
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
            _print(ingest_brief(args.brief, root=root, calendar_db=args.calendar_db))
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
