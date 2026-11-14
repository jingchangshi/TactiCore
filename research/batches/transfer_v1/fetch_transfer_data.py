#!/usr/bin/env python3
# ruff: noqa: E501
# fmt: off
"""ACCOUNT_INVESTABLE_ALLOCATION_TRANSFER_V1 有界数据下载与审计。

只从环境读取 ``TUSHARE_TOKEN``（不打印、不写盘）；只下载 PROTOCOL_V1.md §4.1 明确列出的
8 个代码的四个接口，区间固定为 2013-01-01..2026-10-31；只写入 data/transfer_v1/ 新快照，
绝不写入 data/canonical/。所有者 2026-11-14 决定：核心 512890+515450 各 12.5%、债券
511360+511010 各约 10%、黄金 518880 10%，因此这 5 只均按 MAIN 做 200 日预热门控。
缺失保持空白，不前向填充、不插值、不置零。

输出 ``ACCOUNT_TRANSFER_DATA_AUDIT_V1`` 的 PASS / NO_BACKTEST 结果。本工具只审计
数据快照与生命周期，不运行回测，不冻结 A0/A2 规则，也不构成生产批准。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import pandas as pd

from tacticore.data.tushare import (
    ADJUSTMENT_TYPE,
    SOURCE,
    TushareDataset,
    _fetch_pages,
    _load_calendar,
    adjust_fund_close,
    write_tushare_dataset,
)

ROOT = Path(__file__).resolve().parents[3]
CANONICAL_DIR = ROOT / "data" / "canonical"
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "transfer_v1"
AUDIT_ID = "ACCOUNT_TRANSFER_DATA_AUDIT_V1"
PROTOCOL_PATH = "research/batches/transfer_v1/PROTOCOL_V1.md"
PROTOCOL_TITLE = "ACCOUNT_INVESTABLE_ALLOCATION_TRANSFER_V1"
START_DATE, END_DATE = "20130101", "20261031"
MAIN_START = "2020-10-01"
WARMUP = 200
BASIC_FIELDS = "ts_code,name,management,fund_type,list_date,delist_date"
DAILY_FIELDS = "ts_code,trade_date,close"
ADJ_FIELDS = "ts_code,trade_date,adj_factor"
CALENDAR_FIELDS = "exchange,cal_date,is_open,pretrade_date"
MISSING_POLICY = "缺失保持空白；不前向填充、不插值、不置零、不猜测。"
SCOPE_NOTES = (
    "只审计 PROTOCOL_V1.md §4.1 点名的 8 个代码；'513100 等 QDII' 其余品种未审计；未执行 RQAlpha lifecycle 交叉验证；未冻结 A0/A2 规则，数据 PASS 不等于协议可回测。",
    "长期敏感性代理未授权；Tushare 不提供 historical revision/vintage 可得时间，本快照不是 PIT vintage。",
    "执行日缺价须停止；信号日缺价按基准目标且清零确认计数；需由 runner 实施，审计不验证可交易性。",
    "PROTOCOL_V1.md 仍为 DRAFT_NOT_COMMITTED / NO_BACKTEST；本结果不改变该状态。",
)


@dataclass(frozen=True)
class AssetSpec:
    tushare_code: str
    symbol: str
    rqalpha_symbol: str
    role: str
    requirement: str
    claim: str | None

    @property
    def exchange(self) -> str:
        return "SSE" if self.tushare_code.endswith(".SH") else "SZSE"


ASSETS = (
    AssetSpec("512890.SH", "512890.SS", "512890.XSHG", "A 股核心（12.5%）", "MAIN", "2019-01-18"),
    AssetSpec("515450.SH", "515450.SS", "515450.XSHG", "A 股核心（12.5%）", "MAIN", "2020-02-26"),
    AssetSpec("511360.SH", "511360.SS", "511360.XSHG", "债券（约 10%）", "MAIN", "2020-09-25"),
    AssetSpec("511880.SH", "511880.SS", "511880.XSHG", "货币 ETF 备选", "ALTERNATE", "2013-04-18"),
    AssetSpec("518880.SH", "518880.SS", "518880.XSHG", "黄金（10%）", "MAIN", "2013-07-29"),
    AssetSpec("159934.SZ", "159934.SZ", "159934.XSHE", "黄金备选", "ALTERNATE", "2013-12-16"),
    AssetSpec("511010.SH", "511010.SS", "511010.XSHG", "债券（约 10%）", "MAIN", "2013-03-25"),
    AssetSpec("513100.SH", "513100.SS", "513100.XSHG", "海外 QDII 代表", "LIFECYCLE", None),
)


class AuditError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}


def _date(value: Any) -> pd.Timestamp:
    text = str(value).strip().removesuffix(".0")
    if re.fullmatch(r"\d{8}", text):
        return pd.to_datetime(text, format="%Y%m%d").normalize()
    return pd.Timestamp(text).normalize()


def _optional(value: Any) -> pd.Timestamp | None:
    text = "" if value is None else str(value).strip()
    return None if text in {"", "0", "00000000", "None", "nan", "NaT"} else _date(text)


def _iso(value: pd.Timestamp | None) -> str | None:
    return None if value is None else pd.Timestamp(value).strftime("%Y-%m-%d")


def _token(value: pd.Timestamp | None) -> str | None:
    return None if value is None else pd.Timestamp(value).strftime("%Y%m%d")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _redact(message: str, token: str | None) -> str:
    return message if not token else message.replace(token, "[REDACTED]").replace(quote(token, safe=""), "[REDACTED]")


def _require(frame: pd.DataFrame, fields: str, endpoint: str) -> pd.DataFrame:
    missing = set(fields.split(",")).difference(frame.columns)
    if missing:
        raise AuditError("ENDPOINT_SCHEMA", f"{endpoint} 缺少字段: {sorted(missing)}")
    return frame.loc[:, fields.split(",")].copy()


def _call(api: Any, endpoint: str, **kwargs: Any) -> pd.DataFrame:
    try:
        frame = getattr(api, endpoint)(**kwargs)
    except Exception as exc:  # noqa: BLE001 - 供应商异常统一转为可审计失败
        raise AuditError("API_ERROR", f"{endpoint} 调用失败: {type(exc).__name__}: {exc}") from exc
    if not isinstance(frame, pd.DataFrame):
        raise AuditError("API_RESPONSE_TYPE", f"{endpoint} 未返回 DataFrame")
    return frame


def _issue(items: list[dict[str, Any]], code: str, message: str, asset: str | None = None) -> None:
    items.append({"code": code, "asset": asset, "message": message})


def _fetch_basic(api: Any) -> pd.DataFrame:
    frames = []
    for status in ("L", "D"):
        frame = _require(_call(api, "fund_basic", market="E", status=status, fields=BASIC_FIELDS),
                         BASIC_FIELDS, "fund_basic")
        frame["request_status"] = status
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _fetch_series(
    api: Any, spec: AssetSpec, endpoint: str, fields: str, page_size: int, start: str, end: str
) -> pd.DataFrame:
    frame = _fetch_pages(api, endpoint, page_size=page_size, fields=fields,
                         parameters={"ts_code": spec.tushare_code, "start_date": start, "end_date": end})
    frame = _require(frame, fields, endpoint)
    if not frame.empty and set(frame["ts_code"].astype(str)).difference({spec.tushare_code}):
        raise AuditError("ENDPOINT_CODE_MISMATCH", f"{endpoint} 返回了非请求代码")
    return frame


def _metadata(basic: pd.DataFrame, spec: AssetSpec) -> dict[str, Any] | None:
    rows = basic.loc[basic["ts_code"].astype(str) == spec.tushare_code]
    if rows.empty:
        return None
    fields = BASIC_FIELDS.split(",")
    records = [
        {field: None if pd.isna(row[field]) else str(row[field]).strip() for field in fields}
        | {"request_status": str(row["request_status"])}
        for _, row in rows.iterrows()
    ]
    selected = next((row for row in records if row["request_status"] == "L"), records[0])
    return {"name": selected["name"], "management": selected["management"],
            "fund_type": selected["fund_type"],
            "list_date": _token(_optional(selected["list_date"])),
            "delist_date": _token(_optional(selected["delist_date"])),
            "statuses": sorted({row["request_status"] for row in records if row["request_status"]}),
            "conflict": len({tuple(row[field] for field in fields) for row in records}) > 1}


def _observations(frame: pd.DataFrame, field: str, endpoint: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["date", "value"])
    try:
        dates = pd.DatetimeIndex(frame["trade_date"].map(_date))
    except (TypeError, ValueError) as exc:
        raise AuditError("INVALID_TRADE_DATE", f"{endpoint} 含无效日期") from exc
    if dates.duplicated().any():
        raise AuditError("DUPLICATE_OBSERVATION", f"{endpoint} 含重复交易日")
    if ((dates < start) | (dates > end)).any():
        raise AuditError("OUT_OF_REQUEST_RANGE", f"{endpoint} 含请求区间外日期")
    values = pd.to_numeric(frame[field], errors="coerce").astype(float)
    return pd.DataFrame({"date": dates, "value": values}).sort_values("date", ignore_index=True)


def _adjust(spec: AssetSpec, daily: pd.DataFrame, adj: pd.DataFrame, blockers: list[dict[str, Any]]) -> pd.Series:
    if daily.empty or adj.empty:
        return pd.Series(dtype=float, name=spec.symbol)
    try:
        return adjust_fund_close(daily, adj).rename(spec.symbol)
    except ValueError as exc:
        _issue(blockers, "ADJUSTMENT_VALIDATION_FAILED", str(exc), spec.tushare_code)
        return pd.Series(dtype=float, name=spec.symbol)


def _audit_asset(
    spec: AssetSpec, meta: dict[str, Any] | None, daily: pd.DataFrame, adj: pd.DataFrame,
    calendar: pd.DataFrame, adjusted: pd.Series, start: pd.Timestamp, end: pd.Timestamp,
    blockers: list[dict[str, Any]], warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    claim: pd.Timestamp | None = _optional(spec.claim)
    list_date: pd.Timestamp | None = _optional(meta["list_date"]) if meta else None
    delist_date: pd.Timestamp | None = _optional(meta["delist_date"]) if meta else None
    record: dict[str, Any] = {
        "tushare_code": spec.tushare_code, "tacticore_symbol": spec.symbol,
        "rqalpha_symbol": spec.rqalpha_symbol, "exchange": spec.exchange,
        "role": spec.role, "requirement": spec.requirement,
        "protocol_claimed_list_date": spec.claim, "metadata": meta,
        "lifecycle": {}, "status": "PASS",
    }
    if meta is None:
        _issue(blockers, "FUND_BASIC_MISSING", "fund_basic 未返回该代码", spec.tushare_code)
    else:
        if meta["conflict"]:
            _issue(blockers, "FUND_BASIC_CONFLICT", "fund_basic 状态间身份字段不一致", spec.tushare_code)
        if list_date is None:
            _issue(blockers, "LIST_DATE_MISSING", "fund_basic 缺少上市日期", spec.tushare_code)
        if claim is not None and list_date is not None and claim != list_date:
            _issue(blockers, "LIST_DATE_CLAIM_MISMATCH",
                     f"协议主张 {_iso(claim)} 与实际 {_iso(list_date)} 不一致", spec.tushare_code)
        if delist_date is not None and list_date is not None and delist_date < list_date:
            _issue(blockers, "LIFECYCLE_DATE_ORDER", "退市日早于上市日", spec.tushare_code)
    daily_obs = _observations(daily, "close", "fund_daily", start, end)
    adj_obs = _observations(adj, "adj_factor", "fund_adj", start, end)
    daily_dates = pd.DatetimeIndex(daily_obs.loc[daily_obs["value"] > 0, "date"])
    adj_dates = pd.DatetimeIndex(adj_obs.loc[adj_obs["value"] > 0, "date"])
    expected = pd.DatetimeIndex([])
    if list_date is not None:
        active_start = max(start, list_date)
        active_end = min(end, delist_date) if delist_date is not None else end
        if active_start <= active_end:
            open_dates = calendar.index[calendar[f"{spec.exchange.lower()}_open"] == 1]
            expected = open_dates[(open_dates >= active_start) & (open_dates <= active_end)]
            record["lifecycle"].update({"active_start": _iso(active_start), "active_end": _iso(active_end)})
        else:
            _issue(blockers, "ASSET_NOT_ACTIVE", "生命周期与请求窗口无交集", spec.tushare_code)
    missing_daily = sorted(set(expected).difference(daily_dates))
    missing_adj = sorted(set(expected).difference(adj_dates))
    outside = sorted({item for item in set(daily_dates).union(adj_dates)
                      if (list_date is not None and item < list_date)
                      or (delist_date is not None and item > delist_date)})
    not_open = sorted(set(daily_dates).union(adj_dates).difference(
        calendar.index[calendar[f"{spec.exchange.lower()}_open"] == 1]))
    # Conservative bound: exactly one absent daily row, with a valid factor, <= 1% of active days.
    position = expected.get_indexer(pd.DatetimeIndex(missing_daily))[0] if len(missing_daily) == 1 else -1
    suspected = (len(missing_daily) == 1 and len(expected) >= 100
                 and 0 < position < len(expected) - 1
                 and expected[position - 1] in daily_dates and expected[position + 1] in daily_dates
                 and missing_daily[0] in adj_dates and missing_daily[0] not in set(daily_obs["date"]))
    if suspected:
        _issue(warnings, "SUSPECTED_SUSPENSION_UNVERIFIED",
               f"疑似停牌，未经核实：{_iso(missing_daily[0])}；缺价保持空白", spec.tushare_code)
    invalid = sorted(set(daily_obs.loc[daily_obs["value"].isna() | (daily_obs["value"] <= 0), "date"])
                     .union(adj_obs.loc[adj_obs["value"].isna() | (adj_obs["value"] <= 0), "date"]))
    checks = (
        ("MISSING_ENDPOINT_DATA", daily.empty, "fund_daily 无数据"),
        ("MISSING_ENDPOINT_DATA", adj.empty, "fund_adj 无数据"),
        ("MISSING_DAILY_OBSERVATIONS", bool(missing_daily and not daily.empty and not suspected), f"缺失 {len(missing_daily)} 个交易日"),
        ("MISSING_ADJ_OBSERVATIONS", bool(missing_adj and not adj.empty), f"缺失 {len(missing_adj)} 个交易日"),
        ("DAILY_WITHOUT_ADJ", bool(set(daily_dates).difference(adj_dates)), "日线缺少复权因子"),
        ("ADJ_WITHOUT_DAILY", bool(set(adj_dates).difference(daily_dates) - (set(missing_daily) if suspected else set())), "复权因子缺少日线"),
        ("OBSERVATION_OUTSIDE_LIFECYCLE", bool(outside), "存在上市前/退市后观测"),
        ("OBSERVATION_ON_NON_TRADING_DAY", bool(not_open), "存在交易所非交易日观测"),
        ("INVALID_OBSERVATION_VALUE", bool(invalid), "存在非正或非数值观测"),
    )
    for code, present, message in checks:
        if present:
            _issue(blockers, code, message, spec.tushare_code)
    valid_dates = pd.DatetimeIndex(sorted(set(adjusted.dropna().index)))
    first_200 = valid_dates[WARMUP - 1] if len(valid_dates) >= WARMUP else None
    main_start = pd.Timestamp(MAIN_START)
    record["lifecycle"].update({
        "metadata_list_date": _iso(list_date), "metadata_delist_date": _iso(delist_date),
        "claim_match": None if spec.claim is None else bool(claim == list_date and claim is not None),
        "expected_open_days": len(expected),
        "missing_daily_dates": [_iso(x) for x in missing_daily],
        "missing_adj_dates": [_iso(x) for x in missing_adj],
        "first_200_valid_observation_date": _iso(first_200),
        "warmup_200_by_main_start": bool(first_200 is not None and first_200 < main_start),
    })
    record["status"] = "NO_BACKTEST" if any(item.get("asset") == spec.tushare_code for item in blockers) else "PASS"
    return record


def _environment(bundle: Path | None) -> dict[str, Any]:
    def version(package: str) -> str | None:
        try:
            return metadata.version(package)
        except metadata.PackageNotFoundError:
            return None

    path = bundle or Path.home() / ".rqalpha" / "bundle" / "instruments.pk"
    return {"python": platform.python_version(), "pandas": pd.__version__,
            "tushare": version("tushare"), "rqalpha": version("rqalpha"),
            "rqalpha_bundle": {"path": str(path), "exists": path.is_file(),
                               "sha256": _sha(path) if path.is_file() else None},
            "rqalpha_lifecycle_cross_check": "NOT_PERFORMED_BY_THIS_TOOL"}


def _prepare(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    canonical = CANONICAL_DIR.resolve()
    if resolved == canonical or canonical in resolved.parents:
        raise AuditError("OUTPUT_IS_CANONICAL", "拒绝写入 data/canonical")
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise AuditError("OUTPUT_DIR_NOT_EMPTY", "目标快照目录非空；拒绝覆盖")
    return resolved


def run_audit(
    api: Any, *, output_dir: str | Path, start_date: str = START_DATE,
    end_date: str = END_DATE, downloaded_at: str | None = None,
    rqalpha_bundle: Path | None = None,
) -> dict[str, Any]:
    """下载并审计；``api`` 可注入假实现用于离线测试。"""
    start, end = _date(start_date), _date(end_date)
    if start > end:
        raise AuditError("INVALID_REQUEST_RANGE", "start_date 晚于 end_date")
    output = _prepare(Path(output_dir))
    generated_at = downloaded_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    basic, calendar = _fetch_basic(api), _load_calendar(api, start_date, end_date)
    environment = _environment(rqalpha_bundle)
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not environment["rqalpha_bundle"]["exists"]:
        _issue(warnings, "RQALPHA_BUNDLE_NOT_FOUND", "未找到 RQAlpha bundle")
    daily_frames, adj_frames, adjusted, records = [], [], {}, []
    for spec in ASSETS:
        daily = pd.DataFrame(columns=DAILY_FIELDS.split(","))
        adj = pd.DataFrame(columns=ADJ_FIELDS.split(","))
        try:
            daily = _fetch_series(api, spec, "fund_daily", DAILY_FIELDS, 5000, start_date, end_date)
            adj = _fetch_series(api, spec, "fund_adj", ADJ_FIELDS, 2000, start_date, end_date)
            series = _adjust(spec, daily, adj, blockers)
            record = _audit_asset(spec, _metadata(basic, spec), daily, adj, calendar,
                                  series, start, end, blockers, warnings)
        except (AuditError, ValueError, TypeError) as exc:
            _issue(blockers, "ASSET_AUDIT_FAILED", type(exc).__name__, spec.tushare_code)
            daily = pd.DataFrame(columns=DAILY_FIELDS.split(","))
            adj = pd.DataFrame(columns=ADJ_FIELDS.split(","))
            series = pd.Series(dtype=float, name=spec.symbol)
            record = {"tushare_code": spec.tushare_code, "requirement": spec.requirement,
                      "status": "NO_BACKTEST", "metadata": None,
                      "lifecycle": {"first_200_valid_observation_date": None}}
        daily_frames.append(daily)
        adj_frames.append(adj)
        adjusted[spec.symbol] = series
        records.append(record)
    prices = pd.concat(adjusted.values(), axis=1).sort_index()
    prices.index.name = "date"
    raw_basic = basic.loc[basic["ts_code"].isin([spec.tushare_code for spec in ASSETS])]
    raw_daily = pd.concat(daily_frames, ignore_index=True)
    raw_adj = pd.concat(adj_frames, ignore_index=True)
    warmups = [r["lifecycle"]["first_200_valid_observation_date"]
               for r in records if r["requirement"] == "MAIN"]
    if any(value is None for value in warmups):
        _issue(blockers, "INSUFFICIENT_WARMUP", "主研究资产不足 200 个有效复权观测")
    elif max(warmups) > MAIN_START:
        _issue(warnings, "MAIN_WINDOW_WARMUP_DELAYED", f"共同 200 日观测最早为 {max(warmups)}")
    main_codes = {s.tushare_code for s in ASSETS if s.requirement == "MAIN"}
    decision = "NO_BACKTEST" if any(b["asset"] is None or b["asset"] in main_codes for b in blockers) else "PASS"
    protocol = {"title": PROTOCOL_TITLE, "path": PROTOCOL_PATH,
                "status": "DRAFT_NOT_COMMITTED / NO_BACKTEST"}
    provenance = {
        "dataset": f"{PROTOCOL_TITLE} 数据审计快照", "audit_id": AUDIT_ID, "source": SOURCE,
        "protocol": protocol, "download_timestamp": generated_at,
        "start_date": start_date, "end_date": end_date, "adjustment_type": ADJUSTMENT_TYPE,
        "token_handling": "TUSHARE_TOKEN 只从环境变量读取；不打印、不写入任何产物。",
        "missing_value_policy": MISSING_POLICY,
        "data_availability": "trade_date 收盘数据只在该交易日收盘后可得；未建立 PIT vintage",
        "endpoints": {
            "fund_basic": {"fields": BASIC_FIELDS, "rows": len(raw_basic), "file": "fund_basic.csv"},
            "fund_daily": {"fields": DAILY_FIELDS, "rows": len(raw_daily), "file": "fund_daily.csv"},
            "fund_adj": {"fields": ADJ_FIELDS, "rows": len(raw_adj), "file": "fund_adj.csv"},
            "trade_cal": {"fields": "exchange,cal_date,is_open", "request_fields": CALENDAR_FIELDS,
                          "rows": len(calendar), "file": "trade_cal.csv",
                          "wide_file": "trading_calendar.csv",
                          "open_days": {"SSE": int(calendar["sse_open"].sum()),
                                        "SZSE": int(calendar["szse_open"].sum())}},
        },
        "code_mapping": [{"tushare": s.tushare_code, "tacticore": s.symbol, "rqalpha": s.rqalpha_symbol,
                          "exchange": s.exchange, "role": s.role, "requirement": s.requirement}
                         for s in ASSETS],
        "symbols": [{"tushare_code": r["tushare_code"], "metadata": r["metadata"]} for r in records],
        "missing_and_lifecycle_audit": {r["tushare_code"]: r["lifecycle"] for r in records},
        "environment": environment, "scope_notes": list(SCOPE_NOTES),
    }
    result = {
        "audit_id": AUDIT_ID, "protocol": protocol, "decision": decision,
        "decision_code": f"{AUDIT_ID}_{decision}",
        "decision_scope": "仅数据完整性/代码映射/生命周期；PASS 不代表协议可回测或生产批准。",
        "generated_at": generated_at,
        "request": {"source": SOURCE, "start_date": start_date, "end_date": end_date,
                    "endpoints": ["fund_basic", "fund_daily", "fund_adj", "trade_cal"]},
        "snapshot_dir": str(output),
        "blockers": sorted(blockers, key=lambda x: (x["code"], x.get("asset") or "")),
        "warnings": sorted(warnings, key=lambda x: (x["code"], x.get("asset") or "")),
        "assets": records,
        "missing_value_policy": MISSING_POLICY, "scope_notes": list(SCOPE_NOTES),
        "overall_protocol_status": "NO_BACKTEST",
    }
    return _write_snapshot(
        output, TushareDataset(prices=prices, calendar=calendar, provenance=provenance),
        raw_basic, raw_daily, raw_adj, _calendar_rows(calendar), provenance, result,
    )


def _calendar_rows(calendar: pd.DataFrame) -> pd.DataFrame:
    dates = pd.DatetimeIndex(calendar.index).strftime("%Y%m%d")
    return pd.concat([pd.DataFrame({"exchange": exchange, "cal_date": dates,
                                    "is_open": calendar[column].astype(int).to_numpy()})
                      for exchange, column in (("SSE", "sse_open"), ("SZSE", "szse_open"))],
                     ignore_index=True)


def _write_snapshot(
    output: Path, dataset: TushareDataset, raw_basic: pd.DataFrame, raw_daily: pd.DataFrame,
    raw_adj: pd.DataFrame, calendar_rows: pd.DataFrame, provenance: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = parent / f".{output.name}.tmp-{uuid4().hex}"
    stage.mkdir()
    try:
        write_tushare_dataset(dataset, stage)
        raw_frames = {"fund_basic.csv": raw_basic, "fund_daily.csv": raw_daily,
                      "fund_adj.csv": raw_adj, "trade_cal.csv": calendar_rows}
        for name, frame in raw_frames.items():
            frame.to_csv(stage / name, index=False, na_rep="", lineterminator="\n")
        provenance_path = stage / "provenance.json"
        stored = json.loads(provenance_path.read_text("utf-8"))
        stored["raw_files"] = {name: {"sha256": _sha(stage / name), "rows": len(frame)}
                               for name, frame in raw_frames.items()}
        stored["audit_result_file"] = "ACCOUNT_TRANSFER_DATA_AUDIT_V1.json"
        provenance_path.write_bytes(_json_bytes(stored))
        result = dict(result, provenance_path=str(output / "provenance.json"),
                      audit_result_path=str(output / "ACCOUNT_TRANSFER_DATA_AUDIT_V1.json"),
                      provenance_sha256=_sha(provenance_path),
                      files={**stored.get("files", {}), **stored["raw_files"]})
        (stage / "ACCOUNT_TRANSFER_DATA_AUDIT_V1.json").write_bytes(_json_bytes(result))
        if output.exists():
            output.rmdir()
        os.replace(stage, output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return result


def _error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"audit_id": AUDIT_ID, "protocol": {"title": PROTOCOL_TITLE, "path": PROTOCOL_PATH},
            "decision": "NO_BACKTEST", "decision_code": f"{AUDIT_ID}_NO_BACKTEST",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "snapshot_dir": None, "provenance_path": None,
            "provenance_sha256": None, "warnings": [], "assets": [],
            "blockers": [{"code": code, "asset": None, "message": message, "details": details or {}}],
            "missing_value_policy": MISSING_POLICY, "scope_notes": list(SCOPE_NOTES),
            "overall_protocol_status": "NO_BACKTEST"}


def main(argv: Sequence[str] | None = None, *, api_factory: Callable[[str], Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None, help="新快照目录")
    parser.add_argument("--rqalpha-bundle", type=Path, default=None, help="RQAlpha bundle 路径（只哈希）")
    args = parser.parse_args(argv)
    token = os.environ.get("TUSHARE_TOKEN")
    result: dict[str, Any]
    if not token:
        result, code = _error("TUSHARE_TOKEN_MISSING", "环境变量 TUSHARE_TOKEN 未设置；未联网"), 1
    else:
        try:
            if api_factory is None:
                import tushare as ts

                api = ts.pro_api(token)
            else:
                api = api_factory(token)
            output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / (
                f"snapshot_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}")
            result = run_audit(api, output_dir=output_dir, rqalpha_bundle=args.rqalpha_bundle)
            code = 0 if result["decision"] == "PASS" else 1
        except AuditError as exc:
            result, code = _error(exc.code, _redact(exc.message, token), exc.details), 1
        except Exception as exc:  # noqa: BLE001 - 不打印 traceback
            result, code = _error("UNEXPECTED_ERROR", _redact(f"{type(exc).__name__}: {exc}", token)), 1
    summary = {key: result.get(key) for key in (
        "audit_id", "decision", "generated_at", "snapshot_dir", "provenance_path",
        "provenance_sha256")}
    summary["blocker_codes"] = [(x["code"], x.get("asset")) for x in result["blockers"]]
    summary["warning_codes"] = [(x["code"], x.get("asset")) for x in result["warnings"]]
    summary["asset_status"] = {x["tushare_code"]: x["status"] for x in result.get("assets", [])}
    print(json.dumps(result if not result.get("assets") else summary, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
