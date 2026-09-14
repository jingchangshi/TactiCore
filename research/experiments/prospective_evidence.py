#!/usr/bin/env python3
"""S2_R1 / S4C_R1 前瞻证据共享的纯验证原语。

本模块只承担两个活动候选**完全相同**的 evidence-control mechanics：canonical vintage 位置、
冻结 universe 身份、provenance 解析与文件身份、`price_as_of` / `calendar_as_of` 语义、
signal-day temporal seal、append-only 事件表校验与 RQAlpha evidence 身份绑定。

它**不**包含策略语义、target derivation、候选状态机、候选注册表、scheduler、database、
provider abstraction、组合编排或通用研究框架。只服务单一候选的逻辑留在该候选的 runner 中；
若某段抽象不能实质减少重复的正确性逻辑，就不应放在这里。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe

SHANGHAI_TIMEZONE = "Asia/Shanghai"
SIGNAL_CLOSE_HOUR = 15
PRICE_VINTAGE_FILE = "etf_adjusted_close.csv"
CALENDAR_VINTAGE_FILE = "trading_calendar.csv"
PROVENANCE_VINTAGE_FILE = "provenance.json"
REQUIRED_VINTAGE_FILES = (PRICE_VINTAGE_FILE, CALENDAR_VINTAGE_FILE, PROVENANCE_VINTAGE_FILE)
PRICE_ENDPOINTS = ("fund_daily", "fund_adj")
UNIVERSE_RELATIVE_PATH = "config/universe.csv"
CANONICAL_PROVENANCE_RELATIVE_PATH = "data/canonical/provenance.json"
UNIVERSE_FIELDS = ("symbol", "tushare_symbol", "list_date")
HASH_HEX_LENGTH = 64
RQALPHA_EVIDENCE_FRAMEWORK = "rqalpha"
RQALPHA_EVIDENCE_FIELDS = ("framework", "framework_version", "evidence_path", "evidence_sha256")
RQALPHA_ARTIFACT_SCHEMA = "tacticore.rqalpha.execution_artifact.v2"
RQALPHA_ARTIFACT_FIELDS = (
    "schema",
    "candidate_id",
    "signal_date",
    "framework",
    "framework_version",
    "execution_status",
    "execution_timestamp",
    "artifact_generated_at",
    "intended_targets",
    "realized_weights",
    "cash_weight",
    "turnover",
    "portfolio",
    "native_evidence",
    "native",
)
PORTFOLIO_FIELDS = ("portfolio_value", "drawdown")
NATIVE_FIELDS = (
    "execution_status",
    "order_book_values",
    "total_value",
    "cash",
    "turnover",
    "max_drawdown",
    "order_events",
)
NATIVE_ORDER_EVENT_FIELDS = ("order_book_id", "status", "message")
NATIVE_ORDER_EVENT_COLUMNS = ("rqalpha_symbol", "status", "message")
RQALPHA_EXECUTED_STATUS = "EXECUTED"


# --------------------------------------------------------------------------------------
# File identity
# --------------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_frozen_repository_text(path: Path) -> str:
    """Hash frozen repository text consistently across LF and CRLF checkouts."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_hex_digest(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != HASH_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} 必须是 64 位小写十六进制 SHA-256")
    return value


# --------------------------------------------------------------------------------------
# Instant and as-of semantics
# --------------------------------------------------------------------------------------


def require_timezone_aware_instant(value: object, *, label: str) -> pd.Timestamp:
    try:
        instant = pd.Timestamp(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} 不可解析为时间戳: {value!r}") from error
    if pd.isna(instant) or instant.tzinfo is None:
        raise ValueError(f"{label} 必须带时区，不得使用 naive timestamp")
    return instant


def normalize_signal_date(signal_date: object) -> pd.Timestamp:
    day = pd.Timestamp(signal_date)  # type: ignore[arg-type]
    if day.tzinfo is not None:
        day = day.tz_convert(SHANGHAI_TIMEZONE).tz_localize(None)
    return day.normalize()


def parse_iso_date(value: object, *, label: str) -> pd.Timestamp:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} 必须是非空 ISO 日期字符串")
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} 不可解析为日期: {value!r}") from error
    if pd.isna(parsed) or parsed.tzinfo is not None or parsed.normalize() != parsed:
        raise ValueError(f"{label} 必须是 YYYY-MM-DD 形式的日期")
    return parsed


def signal_close_instant(signal_date: object) -> pd.Timestamp:
    """该候选 universe（SSE/SZSE ETF）的 signal_close = signal_date 15:00 Asia/Shanghai。"""
    return normalize_signal_date(signal_date).tz_localize(SHANGHAI_TIMEZONE) + pd.Timedelta(
        hours=SIGNAL_CLOSE_HOUR
    )


def next_canonical_execution_boundary(calendar: pd.DataFrame, signal_date: object) -> pd.Timestamp:
    """只用 decision 时点已合法的交易所日历推导下一个 canonical 交易日起点。

    日历若已覆盖 signal_date 之后已公布的交易日，则取最近的开放日；否则以
    signal_date 次日的 00:00（Asia/Shanghai）为更严格的上界。
    """
    day = normalize_signal_date(signal_date)
    later = calendar.loc[calendar.index > day]
    open_dates = later.index[later.any(axis=1)]
    if len(open_dates):
        boundary_day = pd.Timestamp(open_dates.min()).normalize()
    else:
        boundary_day = day + pd.Timedelta(days=1)
    return boundary_day.tz_localize(SHANGHAI_TIMEZONE)


def verify_signal_day_seal(
    *,
    signal_date: object,
    download_timestamp: object,
    decision_seal_time: object,
    calendar: pd.DataFrame,
) -> pd.Timestamp:
    """强制 signal_close <= download_timestamp <= decision_seal_time < next boundary。"""
    day = normalize_signal_date(signal_date)
    close = signal_close_instant(day)
    download = require_timezone_aware_instant(
        download_timestamp, label="provenance download_timestamp"
    )
    seal = require_timezone_aware_instant(decision_seal_time, label="decision_seal_time")
    if download < close:
        raise ValueError(
            "provenance download_timestamp 不得早于 signal_close：收盘前下载不能支撑月末决策"
        )
    if seal < close:
        raise ValueError("decision_seal_time 不得早于 signal_close")
    if seal < download:
        raise ValueError(
            "decision_seal_time 不得早于 provenance download_timestamp：证据不能在决策之后下载"
        )
    if seal.tz_convert(SHANGHAI_TIMEZONE).date() != day.date():
        raise ValueError(
            "decision_seal_time 的上海本地日历日必须等于 signal_date：拒绝晚到的回填决策"
        )
    boundary = next_canonical_execution_boundary(calendar, day)
    if seal >= boundary:
        raise ValueError(
            "decision_seal_time 不早于 next_canonical_execution_boundary：execution 结果已可观察"
        )
    return seal


# --------------------------------------------------------------------------------------
# Canonical candidate-specific vintage location
# --------------------------------------------------------------------------------------


def resolve_canonical_vintage_dir(canonical_parent: Path, as_of: object) -> Path:
    return Path(canonical_parent) / normalize_signal_date(as_of).date().isoformat()


def verify_canonical_vintage_location(
    vintage_dir: Path, as_of: object, *, canonical_parent: Path
) -> Path:
    """官方前瞻 vintage 只能来自 <canonical_parent>/<as-of>/，且在任何文件读取之前判定。"""
    expected_parent = Path(canonical_parent).resolve()
    resolved = Path(vintage_dir).resolve()
    if resolved.parent != expected_parent:
        raise ValueError(
            "prospective vintage 必须位于 candidate canonical vintages/<as-of>/ 目录；"
            "任意外部目录不得成为官方前瞻证据"
        )
    if resolved.name != normalize_signal_date(as_of).date().isoformat():
        raise ValueError("vintage 目录名必须等于 --as-of 的 ISO 日期")
    return resolved


# --------------------------------------------------------------------------------------
# Frozen universe identity
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FrozenUniverse:
    """`config/universe.csv` 的机器可验证冻结映射：symbol → tushare_symbol → list date。

    逻辑列名正确并不等于底层标的正确，因此 prospective provenance 必须绑定这份映射，
    而不是只绑定可见的 symbol 集合。
    """

    path: str
    sha256: str
    start_date: str
    symbols: tuple[str, ...]
    tushare_symbols: Mapping[str, str]
    rqalpha_symbols: Mapping[str, str]
    list_dates: Mapping[str, str]

    def identity(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "start_date": self.start_date,
            "symbols": [
                {
                    "symbol": symbol,
                    "tushare_symbol": self.tushare_symbols[symbol],
                    "list_date": self.list_dates[symbol],
                }
                for symbol in self.symbols
            ],
        }


def load_frozen_universe(
    root: Path, *, path: str = UNIVERSE_RELATIVE_PATH, universe: pd.DataFrame | None = None
) -> FrozenUniverse:
    """读取冻结 repository universe 映射及其 normalized SHA-256 与 canonical 起点。"""
    universe_path = Path(root) / path
    frame = load_universe(universe_path) if universe is None else universe
    if frame["symbol"].duplicated().any():
        raise ValueError("frozen universe 的 symbol 必须唯一")
    if frame["tushare_symbol"].duplicated().any():
        raise ValueError("frozen universe 的 tushare_symbol 必须唯一")
    if frame["rqalpha_symbol"].duplicated().any():
        raise ValueError("frozen universe 的 rqalpha_symbol 必须唯一")
    canonical = json.loads(
        (Path(root) / CANONICAL_PROVENANCE_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    start_date = canonical.get("start_date")
    if not isinstance(start_date, str) or not start_date:
        raise ValueError("canonical provenance 缺少冻结 start_date")
    return FrozenUniverse(
        path=path,
        sha256=sha256_frozen_repository_text(universe_path),
        start_date=start_date,
        symbols=tuple(str(value) for value in frame["symbol"]),
        tushare_symbols={
            str(row.symbol): str(row.tushare_symbol) for row in frame.itertuples(index=False)
        },
        rqalpha_symbols={
            str(row.symbol): str(row.rqalpha_symbol) for row in frame.itertuples(index=False)
        },
        list_dates={
            str(row.symbol): pd.Timestamp(row.start_date).strftime("%Y%m%d")
            for row in frame.itertuples(index=False)
        },
    )


def verify_frozen_universe_identity(declared: object, *, frozen: FrozenUniverse) -> None:
    """provenance 里的 universe 身份必须与冻结 repository universe 逐项一致。"""
    entry = _require_mapping(declared, label="provenance universe 身份声明")
    if set(entry) != {"path", "sha256", "start_date", "symbols"}:
        raise ValueError("provenance universe 字段集合与冻结 universe 身份 schema 不一致")
    if entry["path"] != frozen.path:
        raise ValueError(f"provenance universe path 必须是冻结的 {frozen.path}")
    if verify_hex_digest(entry["sha256"], label="provenance universe sha256") != frozen.sha256:
        raise ValueError("provenance universe SHA-256 与冻结 repository universe 不一致")
    if entry["start_date"] != frozen.start_date:
        raise ValueError("provenance universe start_date 与冻结 canonical 起点不一致")
    raw_symbols = entry["symbols"]
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise ValueError("provenance universe 缺少逐标的映射记录")
    declared_mapping: dict[str, tuple[str, str]] = {}
    for raw_record in raw_symbols:
        record = _require_mapping(raw_record, label="provenance universe 标的映射")
        if tuple(sorted(record)) != tuple(sorted(UNIVERSE_FIELDS)):
            raise ValueError("provenance universe 标的映射字段集合与冻结 schema 不一致")
        symbol = record["symbol"]
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("provenance universe 标的映射缺少 symbol")
        if symbol in declared_mapping:
            raise ValueError(f"provenance universe 标的映射重复: {symbol}")
        declared_mapping[symbol] = (str(record["tushare_symbol"]), str(record["list_date"]))
    if set(declared_mapping) != set(frozen.symbols):
        raise ValueError("provenance universe symbol 集合与冻结 universe 不一致")
    for symbol, (tushare_symbol, list_date) in declared_mapping.items():
        if tushare_symbol != frozen.tushare_symbols[symbol]:
            raise ValueError(
                f"provenance universe 的 {symbol} tushare_symbol 与冻结 universe 不一致"
            )
        if list_date != frozen.list_dates[symbol]:
            raise ValueError(f"provenance universe 的 {symbol} list_date 与配置起点不一致")


# --------------------------------------------------------------------------------------
# Vintage provenance authenticity
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VintageProvenance:
    price_as_of: pd.Timestamp
    calendar_as_of: pd.Timestamp
    download_timestamp: pd.Timestamp
    declared_hashes: dict[str, str]


@dataclass(frozen=True)
class ProspectiveVintage:
    prices: pd.DataFrame
    calendar: pd.DataFrame
    raw_calendar: pd.DataFrame
    vintage_hash: str
    provenance: VintageProvenance


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


def load_provenance(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provenance.json 必须是 JSON object")
    return payload


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} 必须是 JSON object")
    return value


def validate_vintage_provenance(
    provenance: Mapping[str, Any],
    *,
    vintage_dir: Path,
    as_of: object,
    expected_source: str,
    expected_adjustment_type: str,
    frozen_universe: FrozenUniverse,
    prices: pd.DataFrame,
    calendar: pd.DataFrame,
) -> VintageProvenance:
    """真正解析 provenance.json，并把它绑定到冻结 universe 身份、实际文件与 as-of 语义。"""
    if not isinstance(provenance, Mapping):
        raise ValueError("provenance.json 必须是 JSON object")
    as_of_day = normalize_signal_date(as_of)
    as_of_token = as_of_day.strftime("%Y%m%d")
    if provenance.get("source") != expected_source:
        raise ValueError("provenance source 与冻结数据契约不一致")
    if provenance.get("end_date") != as_of_token:
        raise ValueError("provenance end_date 必须等于 --as-of")
    if provenance.get("start_date") != frozen_universe.start_date:
        raise ValueError("provenance start_date 必须是冻结 canonical 起点，不得由 CLI 覆盖")
    if provenance.get("adjustment_type") != expected_adjustment_type:
        raise ValueError("provenance adjustment 语义与冻结候选数据契约不一致")
    download_timestamp = require_timezone_aware_instant(
        provenance.get("download_timestamp"), label="provenance download_timestamp"
    )
    verify_frozen_universe_identity(provenance.get("universe"), frozen=frozen_universe)

    raw_symbols = provenance.get("symbols")
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise ValueError("provenance 缺少逐标的 symbols 记录")
    observed_symbols: set[str] = set()
    data_timestamps: list[pd.Timestamp] = []
    for raw_record in raw_symbols:
        record = _require_mapping(raw_record, label="provenance symbol 记录")
        symbol = record.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("provenance symbol 记录缺少 symbol")
        if symbol in observed_symbols:
            raise ValueError(f"provenance symbol 记录重复: {symbol}")
        if symbol not in frozen_universe.tushare_symbols:
            raise ValueError(f"provenance 记录了冻结 universe 之外的 symbol: {symbol}")
        frozen_tushare_symbol = frozen_universe.tushare_symbols[symbol]
        observed_symbols.add(symbol)
        if record.get("tushare_symbol") != frozen_tushare_symbol:
            raise ValueError(f"provenance {symbol} 的 tushare_symbol 与冻结 universe 不一致")
        requests = _require_mapping(
            record.get("request_parameters"), label=f"provenance {symbol} request_parameters"
        )
        for endpoint in PRICE_ENDPOINTS:
            request = _require_mapping(
                requests.get(endpoint), label=f"provenance {symbol} {endpoint} 请求记录"
            )
            if request.get("ts_code") != frozen_tushare_symbol:
                raise ValueError(
                    f"provenance {symbol} 的 {endpoint} request ts_code 与冻结 universe 的 "
                    "tushare_symbol 不一致"
                )
            if request.get("end_date") != as_of_token:
                raise ValueError(
                    f"provenance {symbol} 的 {endpoint} request end_date 必须等于 --as-of"
                )
            if request.get("start_date") != frozen_universe.start_date:
                raise ValueError(
                    f"provenance {symbol} 的 {endpoint} request start_date 必须是冻结 "
                    "canonical 起点"
                )
        metadata = _require_mapping(record.get("metadata"), label=f"provenance {symbol} metadata")
        if metadata.get("list_date") != frozen_universe.list_dates[symbol]:
            raise ValueError(f"provenance {symbol} 的 list_date 与冻结 universe 配置起点不一致")
        try:
            data_timestamp = pd.Timestamp(record.get("data_timestamp")).normalize()
        except (TypeError, ValueError) as error:
            raise ValueError(f"provenance {symbol} 的 data_timestamp 不可解析") from error
        if pd.isna(data_timestamp):
            raise ValueError(f"provenance {symbol} 的 data_timestamp 不可解析")
        if data_timestamp > as_of_day:
            raise ValueError(f"provenance {symbol} 的 data_timestamp 晚于 --as-of")
        data_timestamps.append(data_timestamp)
    if observed_symbols != set(frozen_universe.symbols):
        raise ValueError("provenance symbol 集合与冻结 universe 不一致")

    price_as_of = max(data_timestamps)
    if price_as_of != as_of_day:
        raise ValueError("provenance price_as_of 必须等于 --as-of：as-of 快照必须含该日价格证据")
    if prices.index.max() > as_of_day:
        raise ValueError("prospective vintage 不得包含 as-of 之后的行情")
    calendar_as_of = pd.Timestamp(calendar.index.max()).normalize()
    if calendar_as_of < as_of_day:
        raise ValueError("prospective vintage 的交易日历未覆盖 --as-of")

    declared = _require_mapping(provenance.get("files"), label="provenance files 声明")
    declared_hashes: dict[str, str] = {}
    for name, frame in ((PRICE_VINTAGE_FILE, prices), (CALENDAR_VINTAGE_FILE, calendar)):
        entry = _require_mapping(declared.get(name), label=f"provenance {name} 文件身份声明")
        declared_hash = verify_hex_digest(entry.get("sha256"), label=f"provenance {name} sha256")
        declared_rows = entry.get("rows")
        if not isinstance(declared_rows, int) or isinstance(declared_rows, bool):
            raise ValueError(f"provenance {name} rows 声明必须是整数")
        if declared_rows != len(frame):
            raise ValueError(f"provenance {name} 行数与实际文件不一致")
        if sha256_file(Path(vintage_dir) / name) != declared_hash:
            raise ValueError(f"provenance {name} SHA-256 与实际文件不一致")
        declared_hashes[name] = declared_hash
    return VintageProvenance(
        price_as_of=price_as_of,
        calendar_as_of=calendar_as_of,
        download_timestamp=download_timestamp,
        declared_hashes=declared_hashes,
    )


def verify_overlap_identical(historical: pd.DataFrame, vintage: pd.DataFrame, kind: str) -> None:
    overlap = historical.index.intersection(vintage.index)
    if overlap.empty:
        return
    try:
        pd.testing.assert_frame_equal(historical.loc[overlap], vintage.loc[overlap])
    except AssertionError as error:
        raise ValueError(f"prospective vintage 与 historical {kind} 重叠但内容不同") from error


def compute_vintage_hash(vintage_dir: Path) -> str:
    vintage_path = Path(vintage_dir)
    return hashlib.sha256(
        "".join(
            f"{name}:{sha256_file(vintage_path / name)}\n" for name in REQUIRED_VINTAGE_FILES
        ).encode()
    ).hexdigest()


def load_prospective_vintage(
    vintage_dir: Path,
    *,
    as_of: object,
    historical_cutoff: object,
    historical_prices: pd.DataFrame,
    historical_calendar: pd.DataFrame,
    expected_source: str,
    expected_adjustment_type: str,
    frozen_universe: FrozenUniverse,
) -> ProspectiveVintage:
    """读取并机器验证 candidate-specific vintage，返回截至 as-of 的组合输入。"""
    vintage_path = Path(vintage_dir)
    for name in REQUIRED_VINTAGE_FILES:
        if not (vintage_path / name).is_file():
            raise FileNotFoundError(f"prospective vintage 缺少 {name}")
    prices = load_price_csv(vintage_path / PRICE_VINTAGE_FILE)
    calendar = load_calendar(vintage_path / CALENDAR_VINTAGE_FILE)
    if list(prices.columns) != list(historical_prices.columns):
        raise ValueError("prospective vintage 的价格资产列必须与冻结 historical 基线一致")
    if list(prices.columns) != list(frozen_universe.symbols):
        raise ValueError("prospective vintage 的价格资产列必须等于冻结 universe")
    provenance = validate_vintage_provenance(
        load_provenance(vintage_path / PROVENANCE_VINTAGE_FILE),
        vintage_dir=vintage_path,
        as_of=as_of,
        expected_source=expected_source,
        expected_adjustment_type=expected_adjustment_type,
        frozen_universe=frozen_universe,
        prices=prices,
        calendar=calendar,
    )
    verify_overlap_identical(historical_prices, prices, "价格")
    verify_overlap_identical(historical_calendar, calendar, "日历")
    cutoff = pd.Timestamp(historical_cutoff)
    prospective_prices = prices.loc[prices.index > cutoff]
    prospective_calendar = calendar.loc[calendar.index > cutoff]
    if prospective_prices.empty or prospective_calendar.empty:
        raise ValueError("prospective vintage 没有 historical_cutoff 之后的数据")
    combined_prices = pd.concat([historical_prices, prospective_prices]).sort_index()
    combined_calendar = pd.concat([historical_calendar, prospective_calendar]).sort_index()
    if combined_prices.index.has_duplicates or combined_calendar.index.has_duplicates:
        raise ValueError("prospective vintage 的重叠数据未被安全去重")
    as_of_day = normalize_signal_date(as_of)
    return ProspectiveVintage(
        prices=combined_prices.loc[:as_of_day],
        calendar=combined_calendar.loc[:as_of_day],
        raw_calendar=calendar,
        vintage_hash=compute_vintage_hash(vintage_path),
        provenance=provenance,
    )


# --------------------------------------------------------------------------------------
# Parsed record fields
# --------------------------------------------------------------------------------------


def _decode_json(raw: object, *, label: str) -> Any:
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{label} 必须是非空 JSON 字符串")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} 不是合法 JSON") from error


def parse_json_object(raw: object, *, label: str) -> dict[str, Any]:
    payload = _decode_json(raw, label=label)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} 必须是 JSON object")
    return payload


def parse_json_list(raw: object, *, label: str) -> list[Any]:
    payload = _decode_json(raw, label=label)
    if not isinstance(payload, list):
        raise ValueError(f"{label} 必须是 JSON array")
    return payload


def parse_finite_float(raw: object, *, label: str) -> float:
    if isinstance(raw, bool) or raw is None or raw == "":
        raise ValueError(f"{label} 必须是数值")
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} 必须是数值") from error
    if not math.isfinite(value):
        raise ValueError(f"{label} 必须是有限数值")
    return value


def parse_weight_vector(
    raw: object,
    *,
    expected_symbols: Iterable[str],
    label: str,
    require_total_one: bool = True,
) -> dict[str, float]:
    payload = parse_json_object(raw, label=label)
    if set(payload) != set(expected_symbols):
        raise ValueError(f"{label} 必须完整覆盖冻结 universe 的每个标的")
    weights: dict[str, float] = {}
    for symbol, value in payload.items():
        weight = parse_finite_float(value, label=f"{label}.{symbol}")
        if weight < 0.0 or weight > 1.0:
            raise ValueError(f"{label}.{symbol} 必须落在 [0, 1] 区间")
        weights[symbol] = weight
    total = sum(weights.values())
    if require_total_one and abs(total - 1.0) > 1e-6:
        raise ValueError(f"{label} 的权重合计必须为一")
    if not require_total_one and total > 1.0 + 1e-6:
        raise ValueError(f"{label} 的权重合计不得超过一")
    return weights


# --------------------------------------------------------------------------------------
# RQAlpha execution evidence binding
# --------------------------------------------------------------------------------------


def verify_rqalpha_evidence_identity(
    raw: object, *, root: Path, expected_framework_version: str
) -> dict[str, str]:
    """execution evidence 必须绑定仓库内冻结的 RQAlpha 原生输出与其 SHA-256。"""
    payload = parse_json_object(raw, label="execution_evidence")
    if set(payload) != set(RQALPHA_EVIDENCE_FIELDS):
        raise ValueError("execution_evidence 字段集合与冻结 RQAlpha evidence schema 不一致")
    if payload["framework"] != RQALPHA_EVIDENCE_FRAMEWORK:
        raise ValueError("execution_evidence 的 framework 必须是 RQAlpha 原生执行")
    if payload["framework_version"] != expected_framework_version:
        raise ValueError("execution_evidence 的 framework_version 与冻结 manifest 不一致")
    raw_path = payload["evidence_path"]
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("execution_evidence 必须包含 RQAlpha evidence relative path")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or not relative.parts or relative.parts[0] != "research":
        raise ValueError("RQAlpha evidence 必须是 research/ 下的仓库相对路径")
    if ".." in relative.parts:
        raise ValueError("RQAlpha evidence 路径不得包含上级目录")
    digest = verify_hex_digest(payload["evidence_sha256"], label="execution_evidence sha256")
    resolved_root = Path(root).resolve()
    resolved = (resolved_root / Path(*relative.parts)).resolve()
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise ValueError("RQAlpha evidence 路径不得越出仓库")
    if not resolved.is_file():
        raise ValueError("RQAlpha evidence 文件不存在")
    if sha256_file(resolved) != digest:
        raise ValueError("RQAlpha evidence SHA-256 与实际文件不一致")
    return {key: str(value) for key, value in payload.items()}


def build_rqalpha_evidence_identity(
    *,
    evidence_path: str,
    root: Path,
    expected_framework_version: str,
) -> str:
    relative = PurePosixPath(evidence_path)
    if relative.is_absolute() or not relative.parts or relative.parts[0] != "research":
        raise ValueError("RQAlpha evidence 必须是 research/ 下的仓库相对路径")
    resolved = Path(root).resolve() / Path(*relative.parts)
    if not resolved.is_file():
        raise ValueError("RQAlpha evidence 文件不存在")
    payload = {
        "framework": RQALPHA_EVIDENCE_FRAMEWORK,
        "framework_version": expected_framework_version,
        "evidence_path": str(relative),
        "evidence_sha256": sha256_file(resolved),
    }
    verify_rqalpha_evidence_identity(
        json.dumps(payload), root=root, expected_framework_version=expected_framework_version
    )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------------------
# Authoritative RQAlpha execution artifact
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RqalphaExecutionArtifact:
    """权威 RQAlpha execution artifact 的确定性解析结果。

    它只保存 native facts 与由 facts 推导出的执行结论；TactiCore 不重新实现撮合、整手、
    现金或成本语义，只把 execution row 变成 `artifact` 的确定性函数。
    """

    candidate_id: str
    signal_date: pd.Timestamp
    execution_date: pd.Timestamp
    execution_timestamp: pd.Timestamp
    artifact_generated_at: pd.Timestamp
    execution_status: str
    intended_targets: dict[str, float]
    realized_weights: dict[str, float]
    cash_weight: float
    turnover: float
    portfolio_value: float
    drawdown: float
    total_absolute_weight_deviation: float
    native_evidence: Mapping[str, str]


def _parse_artifact_instants(record: Mapping[str, Any]) -> tuple[pd.Timestamp, pd.Timestamp]:
    execution_timestamp = require_timezone_aware_instant(
        record.get("execution_timestamp"), label="artifact execution_timestamp"
    )
    artifact_generated_at = require_timezone_aware_instant(
        record.get("artifact_generated_at"), label="artifact artifact_generated_at"
    )
    return execution_timestamp, artifact_generated_at


@dataclass(frozen=True)
class NativeExecutionFacts:
    """由 RQAlpha 原生输出确定性导出的执行事实。"""

    execution_status: str
    realized_weights: dict[str, float]
    cash_weight: float
    portfolio_value: float
    drawdown: float
    turnover: float
    native_evidence: dict[str, str]


def _require_native_frame(analyser: Mapping[str, Any], name: str) -> pd.DataFrame:
    frame = analyser.get(name)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"native RQAlpha analyser 缺少非空 {name}")
    return frame


def _native_order_events(order_events: object, day: pd.Timestamp) -> list[dict[str, str]]:
    """把捕获到的原生 order events 压缩成 native 说明记录。"""
    if not isinstance(order_events, pd.DataFrame):
        raise ValueError("native order events 必须是 DataFrame")
    missing = set(NATIVE_ORDER_EVENT_COLUMNS).difference(order_events.columns)
    if missing:
        raise ValueError(f"native order events 缺少字段: {sorted(missing)}")
    frame = order_events
    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.loc[frame.index.normalize() == day]
    records: list[dict[str, str]] = []
    for row in frame.loc[:, list(NATIVE_ORDER_EVENT_COLUMNS)].itertuples(index=False):
        code = "" if pd.isna(row.rqalpha_symbol) else str(row.rqalpha_symbol)
        if not code:
            raise ValueError("native order event 缺少 rqalpha_symbol")
        records.append(
            {
                "order_book_id": code,
                "status": "" if pd.isna(row.status) else str(row.status),
                "message": "" if pd.isna(row.message) else str(row.message),
            }
        )
    return records


def extract_native_execution_block(
    analyser: Mapping[str, Any], order_events: object, *, execution_date: object
) -> dict[str, Any]:
    """把 RQAlpha 原生 sys_analyser / order events 抽取成 normalized native facts。

    这是唯一的 native 抽取入口：调用方不能提供 weights、cash、turnover、回撤或状态。
    """
    if not isinstance(analyser, Mapping):
        raise ValueError("native RQAlpha analyser 必须是 mapping")
    day = pd.Timestamp(execution_date).normalize()
    portfolio = _require_native_frame(analyser, "portfolio")
    positions = _require_native_frame(analyser, "stock_positions")
    summary = analyser.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("native RQAlpha analyser 缺少 summary")
    if day not in portfolio.index:
        raise ValueError(
            f"native replay 未覆盖请求的 execution 观测日 {day.date().isoformat()}："
            "无法证明该 execution 观测真实发生"
        )
    portfolio_row = portfolio.loc[day]
    total_value = parse_finite_float(
        portfolio_row["total_value"], label="native portfolio total_value"
    )
    cash = parse_finite_float(portfolio_row["cash"], label="native portfolio cash")
    day_positions = positions.loc[positions.index.normalize() == day]
    values: dict[str, float] = {}
    if not day_positions.empty:
        for code, group in day_positions.groupby("order_book_id"):
            values[str(code)] = float(pd.to_numeric(group["market_value"], errors="coerce").sum())
    return {
        "execution_status": RQALPHA_EXECUTED_STATUS,
        "order_book_values": values,
        "total_value": total_value,
        "cash": cash,
        "turnover": parse_finite_float(summary["turnover"], label="native summary turnover"),
        "max_drawdown": -abs(
            parse_finite_float(summary["max_drawdown"], label="native summary max_drawdown")
        ),
        "order_events": _native_order_events(order_events, day),
    }


def build_rqalpha_execution_artifact_from_analyser(
    analyser: Mapping[str, Any],
    order_events: object,
    *,
    root: Path,
    candidate_id: str,
    signal_date: str,
    execution_timestamp: str,
    artifact_generated_at: str,
    framework_version: str,
    intended_targets: Mapping[str, float],
) -> dict[str, Any]:
    """actual RQAlpha output → normalized native facts → v2 artifact payload。"""
    execution_day = (
        require_timezone_aware_instant(execution_timestamp, label="artifact execution_timestamp")
        .tz_convert(SHANGHAI_TIMEZONE)
        .tz_localize(None)
        .normalize()
    )
    native = extract_native_execution_block(analyser, order_events, execution_date=execution_day)
    return build_rqalpha_execution_artifact_payload(
        root=root,
        candidate_id=candidate_id,
        signal_date=signal_date,
        execution_timestamp=execution_timestamp,
        artifact_generated_at=artifact_generated_at,
        framework_version=framework_version,
        intended_targets=intended_targets,
        native=native,
    )


def freeze_prospective_execution_artifact(
    analyser: Mapping[str, Any],
    order_events: object,
    *,
    root: Path,
    decision: Mapping[str, str],
    artifact_relative_path: str,
    execution_timestamp: str,
    artifact_generated_at: str,
    framework_version: str,
) -> str:
    """生产入口：原生 RQAlpha 输出 → 不可覆盖的 v2 artifact → evidence identity。"""
    frozen_universe = load_frozen_universe(root)
    payload = build_rqalpha_execution_artifact_from_analyser(
        analyser,
        order_events,
        root=root,
        candidate_id=decision["candidate_id"],
        signal_date=decision["signal_date"],
        execution_timestamp=execution_timestamp,
        artifact_generated_at=artifact_generated_at,
        framework_version=framework_version,
        intended_targets=parse_weight_vector(
            decision["desired_targets"],
            expected_symbols=frozen_universe.symbols,
            label="decision desired_targets",
        ),
    )
    write_rqalpha_execution_artifact(
        payload,
        path=root / artifact_relative_path,
        frozen_universe=frozen_universe,
        expected_framework_version=framework_version,
    )
    return build_rqalpha_evidence_identity(
        evidence_path=artifact_relative_path,
        root=root,
        expected_framework_version=framework_version,
    )


def derive_native_execution_facts(
    native: object, *, frozen_universe: FrozenUniverse
) -> NativeExecutionFacts:
    """只从 native facts 推导 execution 结论：持仓市值、现金、净值、换手与 native 说明。"""
    record = _require_mapping(native, label="native RQAlpha 输出")
    if set(record) != set(NATIVE_FIELDS):
        raise ValueError("native RQAlpha 输出字段集合与冻结 schema 不一致")
    status = record["execution_status"]
    if not isinstance(status, str) or not status:
        raise ValueError("native RQAlpha 输出缺少 execution_status")
    total_value = parse_finite_float(record["total_value"], label="native total_value")
    if total_value <= 0.0:
        raise ValueError("native total_value 必须为正")
    cash = parse_finite_float(record["cash"], label="native cash")
    if cash < 0.0:
        raise ValueError("native cash 不得为负")
    turnover = parse_finite_float(record["turnover"], label="native turnover")
    if turnover < 0.0:
        raise ValueError("native turnover 不得为负")
    drawdown = parse_finite_float(record["max_drawdown"], label="native max_drawdown")
    if drawdown > 0.0:
        raise ValueError("native max_drawdown 必须为非正值")

    symbol_by_code = {code: symbol for symbol, code in frozen_universe.rqalpha_symbols.items()}
    values = _require_mapping(record["order_book_values"], label="native order_book_values")
    market_values = {symbol: 0.0 for symbol in frozen_universe.symbols}
    for code, raw_value in values.items():
        if code not in symbol_by_code:
            raise ValueError(
                f"native order_book_values 引用了冻结 universe 之外的 rqalpha_symbol: {code}"
            )
        value = parse_finite_float(raw_value, label=f"native order_book_values.{code}")
        if value < 0.0:
            raise ValueError(f"native order_book_values.{code} 不得为负")
        market_values[symbol_by_code[code]] = value
    if abs(sum(market_values.values()) + cash - total_value) > 1e-6 * total_value:
        raise ValueError("native 持仓市值与现金合计必须等于 native total_value")

    raw_events = record["order_events"]
    if not isinstance(raw_events, list):
        raise ValueError("native order_events 必须是 JSON array")
    native_evidence: dict[str, str] = {}
    for raw_event in raw_events:
        event = _require_mapping(raw_event, label="native order event")
        if set(event) != set(NATIVE_ORDER_EVENT_FIELDS):
            raise ValueError("native order event 字段集合与冻结 schema 不一致")
        code = event["order_book_id"]
        if code not in symbol_by_code:
            raise ValueError(f"native order event 引用了冻结 universe 之外: {code}")
        message = str(event["message"])
        status_text = str(event["status"])
        text = message if message else f"native status {status_text}"
        if not text:
            raise ValueError("native order event 必须携带可读的 native 说明")
        native_evidence[symbol_by_code[str(code)]] = text
    return NativeExecutionFacts(
        execution_status=status,
        realized_weights={symbol: value / total_value for symbol, value in market_values.items()},
        cash_weight=cash / total_value,
        portfolio_value=total_value,
        drawdown=drawdown,
        turnover=turnover,
        native_evidence=native_evidence,
    )


def _require_same_weights(
    claimed: Mapping[str, float], derived: Mapping[str, float], *, label: str
) -> None:
    if set(claimed) != set(derived):
        raise ValueError(f"{label} 必须与 native facts 推导结果一致")
    for symbol, value in derived.items():
        if not math.isclose(claimed[symbol], value, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"{label}.{symbol} 与 native facts 推导结果不一致")


def build_rqalpha_execution_artifact_payload(
    *,
    root: Path,
    candidate_id: str,
    signal_date: str,
    execution_timestamp: str,
    artifact_generated_at: str,
    framework_version: str,
    intended_targets: Mapping[str, float],
    native: Mapping[str, Any],
) -> dict[str, Any]:
    """把 RQAlpha 原生输出序列化成 authoritative artifact。

    这是 producer：它只搬运 native facts，所有 execution 结论都由 `native` 推导，
    调用方无法另行提供 realized weights / cash / turnover / status。
    """
    frozen_universe = load_frozen_universe(root)
    facts = derive_native_execution_facts(native, frozen_universe=frozen_universe)
    payload: dict[str, Any] = {
        "schema": RQALPHA_ARTIFACT_SCHEMA,
        "candidate_id": candidate_id,
        "signal_date": signal_date,
        "framework": RQALPHA_EVIDENCE_FRAMEWORK,
        "framework_version": framework_version,
        "execution_status": facts.execution_status,
        "execution_timestamp": execution_timestamp,
        "artifact_generated_at": artifact_generated_at,
        "intended_targets": {
            str(symbol): float(weight) for symbol, weight in intended_targets.items()
        },
        "realized_weights": facts.realized_weights,
        "cash_weight": facts.cash_weight,
        "turnover": facts.turnover,
        "portfolio": {
            "portfolio_value": facts.portfolio_value,
            "drawdown": facts.drawdown,
        },
        "native_evidence": facts.native_evidence,
        "native": dict(native),
    }
    verify_rqalpha_artifact_payload(
        payload, frozen_universe=frozen_universe, expected_framework_version=framework_version
    )
    return payload


def verify_rqalpha_artifact_payload(
    payload: object,
    *,
    frozen_universe: FrozenUniverse,
    expected_framework_version: str,
) -> None:
    """artifact 自身必须自洽：每个 execution 结论都要能被 native facts 重新推导。"""
    record = _require_mapping(payload, label="RQAlpha execution artifact")
    if set(record) != set(RQALPHA_ARTIFACT_FIELDS):
        raise ValueError("RQAlpha execution artifact 字段集合与冻结 schema 不一致")
    if record["schema"] != RQALPHA_ARTIFACT_SCHEMA:
        raise ValueError("RQAlpha execution artifact schema 版本与冻结契约不一致")
    if record["framework"] != RQALPHA_EVIDENCE_FRAMEWORK:
        raise ValueError("RQAlpha execution artifact 的 framework 必须是 RQAlpha 原生执行")
    if record["framework_version"] != expected_framework_version:
        raise ValueError("RQAlpha execution artifact 的 framework_version 与冻结 manifest 不一致")
    if not isinstance(record["candidate_id"], str) or not record["candidate_id"]:
        raise ValueError("RQAlpha execution artifact 缺少 candidate_id")
    if not isinstance(record["execution_status"], str) or not record["execution_status"]:
        raise ValueError("RQAlpha execution artifact 缺少 execution_status")
    parse_iso_date(record["signal_date"], label="artifact signal_date")
    _parse_artifact_instants(record)
    parse_weight_vector(
        json.dumps(record["intended_targets"], ensure_ascii=False),
        expected_symbols=frozen_universe.symbols,
        label="artifact intended_targets",
    )
    facts = derive_native_execution_facts(record["native"], frozen_universe=frozen_universe)
    if record["execution_status"] != facts.execution_status:
        raise ValueError("artifact execution_status 必须等于 native RQAlpha 输出的状态")
    claimed_realized = parse_weight_vector(
        json.dumps(record["realized_weights"], ensure_ascii=False),
        expected_symbols=frozen_universe.symbols,
        label="artifact realized_weights",
        require_total_one=False,
    )
    _require_same_weights(
        claimed_realized, facts.realized_weights, label="artifact realized_weights"
    )
    cash_weight = parse_finite_float(record["cash_weight"], label="artifact cash_weight")
    if not math.isclose(cash_weight, facts.cash_weight, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("artifact cash_weight 与 native 持仓/现金推导结果不一致")
    if abs(sum(claimed_realized.values()) + cash_weight - 1.0) > 1e-3:
        raise ValueError("artifact realized_weights 与 cash_weight 合计必须覆盖组合")
    turnover = parse_finite_float(record["turnover"], label="artifact turnover")
    if not math.isclose(turnover, facts.turnover, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("artifact turnover 与 native 汇总推导结果不一致")
    portfolio = _require_mapping(record["portfolio"], label="artifact portfolio")
    if set(portfolio) != set(PORTFOLIO_FIELDS):
        raise ValueError("artifact portfolio 字段集合与冻结 schema 不一致")
    portfolio_value = parse_finite_float(
        portfolio["portfolio_value"], label="artifact portfolio_value"
    )
    if not math.isclose(portfolio_value, facts.portfolio_value, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("artifact portfolio_value 与 native total_value 不一致")
    drawdown = parse_finite_float(portfolio["drawdown"], label="artifact drawdown")
    if not math.isclose(drawdown, facts.drawdown, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("artifact drawdown 与 native max_drawdown 不一致")
    claimed_evidence = _require_mapping(record["native_evidence"], label="artifact native_evidence")
    if set(claimed_evidence) != set(facts.native_evidence):
        raise ValueError("artifact native_evidence 必须完全由 native order events 推导")
    for symbol, text in facts.native_evidence.items():
        if claimed_evidence[symbol] != text:
            raise ValueError(
                f"artifact native_evidence.{symbol} 与 native order events 推导结果不一致"
            )


def write_rqalpha_execution_artifact(
    payload: Mapping[str, Any],
    *,
    path: Path,
    frozen_universe: FrozenUniverse,
    expected_framework_version: str,
) -> Path:
    """冻结一份 authoritative execution artifact；既有 evidence 不可覆盖。"""
    destination = Path(path)
    verify_rqalpha_artifact_payload(
        payload,
        frozen_universe=frozen_universe,
        expected_framework_version=expected_framework_version,
    )
    if destination.exists():
        raise ValueError("RQAlpha execution artifact 已存在，拒绝覆盖既有 evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def parse_rqalpha_execution_artifact(
    execution_evidence: object,
    *,
    root: Path,
    decision: Mapping[str, str],
    frozen_universe: FrozenUniverse,
    expected_framework_version: str,
    record_generated_at: object,
) -> RqalphaExecutionArtifact:
    """把 SHA-bound execution artifact 解析成 deterministic execution 结论。

    时间链必须成立：decision seal < execution_timestamp <= artifact_generated_at
    <= execution record_generated_at，且 execution_timestamp 不得早于 execution_close。
    """
    identity = verify_rqalpha_evidence_identity(
        execution_evidence, root=root, expected_framework_version=expected_framework_version
    )
    artifact_path = Path(root).resolve() / PurePosixPath(identity["evidence_path"])
    record = _require_mapping(
        json.loads(artifact_path.read_text(encoding="utf-8")), label="RQAlpha execution artifact"
    )
    verify_rqalpha_artifact_payload(
        record,
        frozen_universe=frozen_universe,
        expected_framework_version=expected_framework_version,
    )
    if record["candidate_id"] != decision["candidate_id"]:
        raise ValueError("RQAlpha execution artifact 的 candidate_id 与对应 decision 不一致")
    if record["signal_date"] != decision["signal_date"]:
        raise ValueError("RQAlpha execution artifact 的 signal_date 与对应 decision 不一致")
    execution_timestamp, artifact_generated_at = _parse_artifact_instants(record)
    decision_seal = require_timezone_aware_instant(
        decision["record_generated_at"], label="decision record_generated_at"
    )
    record_seal = require_timezone_aware_instant(
        record_generated_at, label="execution record_generated_at"
    )
    execution_date = execution_timestamp.tz_convert(SHANGHAI_TIMEZONE).tz_localize(None).normalize()
    execution_close = signal_close_instant(execution_date)
    if execution_timestamp < execution_close:
        raise ValueError(
            "artifact execution_timestamp 不得早于 execution_close："
            "execution 观测在该日收盘前并不存在"
        )
    if artifact_generated_at < execution_timestamp:
        raise ValueError("artifact artifact_generated_at 不得早于 execution_timestamp")
    if artifact_generated_at > record_seal:
        raise ValueError(
            "artifact artifact_generated_at 晚于 execution record_generated_at："
            "不得用尚未产生的观测构造 execution 行"
        )
    if execution_timestamp <= decision_seal:
        raise ValueError("execution_timestamp 必须严格晚于 decision seal：决策必须先于执行")
    signal_date = parse_iso_date(decision["signal_date"], label="signal_date")
    if execution_date <= signal_date:
        raise ValueError("execution_date 必须晚于 signal_date：决策必须先于执行")
    intended = parse_weight_vector(
        json.dumps(record["intended_targets"], ensure_ascii=False),
        expected_symbols=frozen_universe.symbols,
        label="artifact intended_targets",
    )
    decision_targets = parse_weight_vector(
        decision["desired_targets"],
        expected_symbols=frozen_universe.symbols,
        label="desired_targets",
    )
    if set(intended) != set(decision_targets) or any(
        abs(intended[symbol] - decision_targets[symbol]) > 1e-9 for symbol in intended
    ):
        raise ValueError("artifact intended_targets 必须等于 decision 冻结的 desired_targets")
    realized = parse_weight_vector(
        json.dumps(record["realized_weights"], ensure_ascii=False),
        expected_symbols=frozen_universe.symbols,
        label="artifact realized_weights",
        require_total_one=False,
    )
    cash_weight = parse_finite_float(record["cash_weight"], label="artifact cash_weight")
    portfolio = _require_mapping(record["portfolio"], label="artifact portfolio")
    return RqalphaExecutionArtifact(
        candidate_id=str(record["candidate_id"]),
        signal_date=signal_date,
        execution_date=execution_date,
        execution_timestamp=execution_timestamp,
        artifact_generated_at=artifact_generated_at,
        execution_status=str(record["execution_status"]),
        intended_targets=intended,
        realized_weights=realized,
        cash_weight=cash_weight,
        turnover=parse_finite_float(record["turnover"], label="artifact turnover"),
        portfolio_value=parse_finite_float(
            portfolio["portfolio_value"], label="artifact portfolio_value"
        ),
        drawdown=parse_finite_float(portfolio["drawdown"], label="artifact drawdown"),
        total_absolute_weight_deviation=sum(
            abs(intended[symbol] - realized[symbol]) for symbol in intended
        )
        + abs(cash_weight),
        native_evidence={
            str(symbol): str(text)
            for symbol, text in _require_mapping(
                record["native_evidence"], label="artifact native_evidence"
            ).items()
        },
    )


# --------------------------------------------------------------------------------------
# Append-only event table
# --------------------------------------------------------------------------------------


def read_event_rows(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    field_names = tuple(fields)
    if not Path(path).is_file():
        raise FileNotFoundError("observations.csv 必须先以协议表头创建")
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError("observations.csv 缺少协议表头")
    if tuple(rows[0]) != field_names:
        raise ValueError("observations.csv schema 与冻结协议不一致")
    return [dict(zip(field_names, row, strict=True)) for row in rows[1:]]


def verify_no_duplicate_event(rows: Iterable[Mapping[str, str]], record: Mapping[str, str]) -> None:
    for row in rows:
        if (
            row["record_type"] == record["record_type"]
            and row["candidate_id"] == record["candidate_id"]
            and row["signal_date"] == record["signal_date"]
        ):
            raise ValueError(
                "append-only 协议禁止重复写入同一 candidate + signal_date 的 "
                f"{record['record_type']} record"
            )


def append_event_row(record: Mapping[str, str], *, path: Path, fields: Sequence[str]) -> None:
    """单一追加点：schema 与重复校验完成后才打开文件，失败不改变 evidence bytes。"""
    field_names = tuple(fields)
    if tuple(record.keys()) != field_names:
        raise ValueError("record 字段集合与冻结 observation schema 不一致")
    existing = read_event_rows(path, field_names)
    verify_no_duplicate_event(existing, record)
    with Path(path).open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=list(field_names)).writerow(dict(record))
