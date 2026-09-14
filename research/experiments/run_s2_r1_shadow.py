#!/usr/bin/env python3
"""用冻结的 S2 R1 身份生成一条可审计的月末前瞻影子决策。

本模块是**最小 candidate-specific runner**：它只服务 `S2_R1`，不实现调度器、daemon、
通知、券商或通用候选框架。生产决策路径不暴露 vintage/record 目的地、也不暴露 decision
seal time；这些只能来自 candidate canonical 位置与 runner 的实际运行时钟。
"""

from __future__ import annotations

import json
from argparse import ArgumentParser
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd

from research.experiments.prospective_evidence import (
    REQUIRED_VINTAGE_FILES,
    SHANGHAI_TIMEZONE,
    ProspectiveVintage,
    append_event_row,
    load_calendar,
    load_prospective_vintage,
    parse_finite_float,
    parse_iso_date,
    parse_json_list,
    parse_json_object,
    parse_weight_vector,
    read_event_rows,
    require_timezone_aware_instant,
    resolve_canonical_vintage_dir,
    sha256_frozen_repository_text,
    signal_close_instant,
    verify_canonical_vintage_location,
    verify_hex_digest,
    verify_rqalpha_evidence_identity,
    verify_signal_day_seal,
)
from research.experiments.prospective_evidence import (
    build_rqalpha_evidence_identity as build_rqalpha_evidence_identity,
)
from research.experiments.prospective_evidence import sha256_file as sha256_file
from tacticore.data.prices import load_price_csv
from tacticore.data.tushare import ADJUSTMENT_TYPE, SOURCE
from tacticore.strategies.multi_asset_trend import (
    MultiAssetTrendConfig,
    build_month_end_targets,
    load_trend_config,
    valid_observation_moving_average,
)

ROOT = Path(__file__).resolve().parents[2]
SHADOW_DIR = ROOT / "research/shadow/s2_r1"
MANIFEST_PATH = SHADOW_DIR / "candidate_manifest.json"
OBSERVATIONS_PATH = SHADOW_DIR / "observations.csv"
MANIFEST_RELATIVE_PATH = "research/shadow/s2_r1/candidate_manifest.json"
VINTAGE_PARENT_RELATIVE_PATH = "research/shadow/s2_r1/vintages"
OBSERVATIONS_RELATIVE_PATH = "research/shadow/s2_r1/observations.csv"
CANDIDATE_ID = "S2_R1"
PROTOCOL_VERSION = "V1"
PENDING_EXECUTION_STATUS = "PENDING_NEXT_CANONICAL_OBSERVATION"
ALLOWED_EXECUTION_STATUSES = ("EXECUTED",)
VINTAGE_FILES = REQUIRED_VINTAGE_FILES
TREND_STATES = ("UPTREND", "NEGATIVE_SIGNAL", "UNAVAILABLE")
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
    "eligible_assets",
    "trend_states",
    "target_changed",
    "desired_targets",
    "action_required",
    "execution_date",
    "execution_status",
    "realized_weights",
    "cash_weight",
    "target_deviation",
    "portfolio_value",
    "drawdown",
    "turnover",
    "execution_evidence",
)
# decision 行不得携带任何执行结果；这些列只能由后续 execution 行填充。
EXECUTION_ONLY_FIELDS = (
    "execution_date",
    "realized_weights",
    "cash_weight",
    "target_deviation",
    "portfolio_value",
    "drawdown",
    "turnover",
    "execution_evidence",
)


def _now_utc_iso() -> str:
    """decision_seal_time 的唯一生产来源：runner 的实际运行时钟。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_hash(path: Path = MANIFEST_PATH) -> str:
    return sha256_frozen_repository_text(path)


def canonical_vintage_dir(root: Path, as_of: object) -> Path:
    return resolve_canonical_vintage_dir(root / VINTAGE_PARENT_RELATIVE_PATH, as_of)


def canonical_observations_path(root: Path = ROOT) -> Path:
    return root / OBSERVATIONS_RELATIVE_PATH


# --------------------------------------------------------------------------------------
# Candidate identity
# --------------------------------------------------------------------------------------


def verify_framework_versions(manifest: dict[str, Any]) -> None:
    for package, expected_version in manifest["framework_versions"].items():
        if version(package) != expected_version:
            raise ValueError(f"candidate manifest 与当前框架版本不一致: {package}")


def verify_candidate(
    manifest: dict[str, Any],
    root: Path = ROOT,
    *,
    verify_framework: bool = True,
) -> None:
    if manifest["candidate_id"] != CANDIDATE_ID or manifest["candidate_version"] != "R1":
        raise ValueError("candidate manifest 不是冻结的 S2_R1")
    cutoff = pd.Timestamp(manifest["historical_cutoff"])
    start = pd.Timestamp(manifest["prospective_start"])
    if start <= cutoff:
        raise ValueError("prospective_start 必须晚于 historical_cutoff")
    config = load_trend_config(root / "config/strategy.toml")
    semantics = manifest["strategy_semantics"]
    expected = {
        "trend_window": config.trend_window,
        "fallback_symbol": config.fallback_symbol,
        "risk_symbols": list(config.risk_symbols),
        "fees": config.fees,
        "slippage": config.slippage,
        "initial_cash": config.initial_cash,
        "rebalance_frequency": config.rebalance_frequency,
    }
    for field, actual in expected.items():
        if semantics[field] != actual:
            raise ValueError(f"candidate manifest 与当前冻结策略不一致: {field}")
    if semantics["execution_policy"] != "SIGNAL_CHANGE_ONLY":
        raise ValueError("candidate manifest 的执行政策不是 SIGNAL_CHANGE_ONLY")
    if not manifest["execution_semantics"]["partial_fill_on_insufficient_cash"]:
        raise ValueError("candidate manifest 未冻结 RQAlpha 原生资金不足部分成交")
    if verify_framework:
        verify_framework_versions(manifest)
    for relative_path, expected_hash in manifest["file_hashes"].items():
        actual_hash = sha256_frozen_repository_text(root / relative_path)
        if actual_hash != expected_hash:
            raise ValueError(f"冻结输入 hash 不一致: {relative_path}")
    provenance = json.loads((root / "data/canonical/provenance.json").read_text(encoding="utf-8"))
    if provenance["end_date"] != cutoff.strftime("%Y%m%d"):
        raise ValueError("canonical provenance 的截止日与 candidate manifest 不一致")


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
    )


def validate_month_end_review(vintage_calendar: pd.DataFrame, as_of: object) -> None:
    """只以已公布交易日历确认月末，不以未来价格推断月末。"""
    as_of_day = pd.Timestamp(as_of).normalize()
    month_calendar = vintage_calendar.loc[
        vintage_calendar.index.to_period("M") == as_of_day.to_period("M")
    ]
    natural_month_end = as_of_day + pd.offsets.MonthEnd(0)
    if month_calendar.empty or month_calendar.index.max() < natural_month_end:
        raise ValueError("vintage 日历未覆盖完整 signal 月，不能生成月末前瞻 decision")
    open_dates = month_calendar.index[month_calendar.any(axis=1)]
    if open_dates.empty or open_dates.max() != as_of_day:
        raise ValueError("--as-of 必须是该月最后一个 canonical 交易日")


def derive_first_eligible_signal(
    manifest: Mapping[str, Any], vintage_calendar: pd.DataFrame
) -> pd.Timestamp | None:
    """由冻结月度语义 + 已公布日历推导 first eligible signal，不改写 manifest。

    日历未覆盖 `prospective_start` 所在月时返回 `None`（该月是否合法由月末校验负责）。
    """
    month = pd.Timestamp(manifest["prospective_start"]).to_period("M")
    month_calendar = vintage_calendar.loc[vintage_calendar.index.to_period("M") == month]
    open_dates = month_calendar.index[month_calendar.any(axis=1)]
    if open_dates.empty:
        return None
    return pd.Timestamp(open_dates.max()).normalize()


# --------------------------------------------------------------------------------------
# Frozen-semantics decision derivation
# --------------------------------------------------------------------------------------


def _trend_states(
    prices: pd.DataFrame, config: MultiAssetTrendConfig, signal_date: pd.Timestamp
) -> tuple[list[str], dict[str, str]]:
    risk_prices = prices[list(config.risk_symbols)]
    averages = valid_observation_moving_average(risk_prices, config.trend_window)
    states: dict[str, str] = {}
    eligible_assets: list[str] = []
    for symbol in config.risk_symbols:
        price = risk_prices.at[signal_date, symbol]
        average = averages.at[signal_date, symbol]
        if pd.isna(price) or pd.isna(average):
            states[symbol] = "UNAVAILABLE"
        elif price > average:
            states[symbol] = "UPTREND"
            eligible_assets.append(symbol)
        else:
            states[symbol] = "NEGATIVE_SIGNAL"
            eligible_assets.append(symbol)
    return eligible_assets, states


def verify_decision_row(
    record: Mapping[str, str],
    *,
    manifest: Mapping[str, Any],
    expected_symbols: Iterable[str],
) -> None:
    """decision 行契约：完整身份、合法时间、完整目标且不含任何执行结果。"""
    if record["record_type"] != "decision":
        raise ValueError("只有 decision 行适用 decision-before-execution 契约")
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
    universe = set(expected_symbols)
    states = parse_json_object(record["trend_states"], label="trend_states")
    if not set(states).issubset(universe):
        raise ValueError("trend_states 引用了冻结 universe 之外的标的")
    if any(state not in TREND_STATES for state in states.values()):
        raise ValueError("trend_states 含未知状态")
    eligible = parse_json_list(record["eligible_assets"], label="eligible_assets")
    if not all(
        isinstance(symbol, str) and states.get(symbol) in {"UPTREND", "NEGATIVE_SIGNAL"}
        for symbol in eligible
    ):
        raise ValueError("eligible_assets 只能引用该 signal 上已评估趋势的标的")
    if record["target_changed"] not in {"true", "false"} or record["action_required"] not in {
        "true",
        "false",
    }:
        raise ValueError("target_changed 与 action_required 必须是 true/false")
    if record["action_required"] != record["target_changed"]:
        raise ValueError("S2 的 action_required 必须与其 target_changed 一致")
    parse_weight_vector(
        record["desired_targets"], expected_symbols=expected_symbols, label="desired_targets"
    )
    if record["execution_status"] != PENDING_EXECUTION_STATUS:
        raise ValueError("decision 行的 execution_status 必须是待执行状态")
    filled = [field for field in EXECUTION_ONLY_FIELDS if record.get(field, "") != ""]
    if filled:
        raise ValueError(f"decision 行不得包含执行结果字段: {filled}")
    seal = require_timezone_aware_instant(
        record["record_generated_at"], label="record_generated_at"
    )
    if seal.tz_convert(SHANGHAI_TIMEZONE).date() != signal_date.date():
        raise ValueError("decision 只允许在其 signal_date 当日封存，不得回填")
    if seal < signal_close_instant(signal_date):
        raise ValueError("record_generated_at 不得早于 signal_close")


def build_decision_record(
    prices: pd.DataFrame,
    manifest: Mapping[str, Any],
    *,
    as_of: pd.Timestamp,
    vintage_identifier: str,
    prospective_data_hash: str,
    manifest_hash: str,
    expected_symbols: Sequence[str] | None = None,
    decision_seal_time: str | None = None,
    root: Path = ROOT,
) -> dict[str, str] | None:
    config = load_trend_config(root / "config/strategy.toml")
    if as_of not in prices.index:
        raise ValueError("as-of 必须是可用的 canonical 价格观测日")
    targets = build_month_end_targets(prices, config)
    if as_of not in targets.index:
        return None
    target = targets.loc[as_of]
    previous = targets.loc[targets.index < as_of]
    target_changed = previous.empty or target.ne(previous.iloc[-1]).any()
    eligible_assets, states = _trend_states(prices, config, as_of)
    timestamp = decision_seal_time or _now_utc_iso()
    desired_targets = {symbol: float(weight) for symbol, weight in target.items()}
    record = {
        "record_type": "decision",
        "candidate_id": manifest["candidate_id"],
        "protocol_version": PROTOCOL_VERSION,
        "record_generated_at": timestamp,
        "data_as_of": as_of.date().isoformat(),
        "vintage_identifier": vintage_identifier,
        "historical_manifest_hash": manifest_hash,
        "prospective_data_hash": prospective_data_hash,
        "signal_date": as_of.date().isoformat(),
        "eligible_assets": json.dumps(eligible_assets, ensure_ascii=False, sort_keys=True),
        "trend_states": json.dumps(states, ensure_ascii=False, sort_keys=True),
        "target_changed": str(bool(target_changed)).lower(),
        "desired_targets": json.dumps(desired_targets, ensure_ascii=False, sort_keys=True),
        "action_required": str(bool(target_changed)).lower(),
        "execution_date": "",
        "execution_status": PENDING_EXECUTION_STATUS,
        "realized_weights": "",
        "cash_weight": "",
        "target_deviation": "",
        "portfolio_value": "",
        "drawdown": "",
        "turnover": "",
        "execution_evidence": "",
    }
    verify_decision_row(
        record,
        manifest=manifest,
        expected_symbols=list(prices.columns) if expected_symbols is None else expected_symbols,
    )
    return record


# --------------------------------------------------------------------------------------
# Append-only record contract
# --------------------------------------------------------------------------------------


def decision_record_count(path: Path = OBSERVATIONS_PATH) -> int:
    return sum(
        1 for row in read_event_rows(path, RECORD_FIELDS) if row["record_type"] == "decision"
    )


def observation_record_count(path: Path = OBSERVATIONS_PATH) -> int:
    return len(read_event_rows(path, RECORD_FIELDS))


def _verify_decision_row_shape(record: Mapping[str, str]) -> None:
    if record["record_type"] != "decision":
        raise ValueError("append_decision_record 只接受 decision 行")
    if record["execution_status"] != PENDING_EXECUTION_STATUS:
        raise ValueError("decision 行的 execution_status 必须是待执行状态")
    filled = [field for field in EXECUTION_ONLY_FIELDS if record.get(field, "") != ""]
    if filled:
        raise ValueError(f"decision 行不得包含执行结果字段: {filled}")


def append_decision_record(record: Mapping[str, str], path: Path = OBSERVATIONS_PATH) -> None:
    _verify_decision_row_shape(record)
    append_event_row(record, path=path, fields=RECORD_FIELDS)


def verify_execution_row(
    record: Mapping[str, str],
    *,
    decision: Mapping[str, str],
    expected_symbols: Iterable[str],
    expected_framework_version: str,
    root: Path = ROOT,
) -> None:
    """execution 行必须**完整**才能 append：不允许空壳，不允许事后补字段。"""
    if record["record_type"] != "execution":
        raise ValueError("只有 execution 行适用 execution completeness 契约")
    if record["candidate_id"] != decision["candidate_id"]:
        raise ValueError("execution 行的 candidate_id 与对应 decision 不一致")
    if record["protocol_version"] != decision["protocol_version"]:
        raise ValueError("execution 行的 protocol_version 与对应 decision 不一致")
    if record["signal_date"] != decision["signal_date"]:
        raise ValueError("execution 行的 signal_date 必须匹配对应 decision")
    signal_date = parse_iso_date(record["signal_date"], label="signal_date")
    execution_date = parse_iso_date(record["execution_date"], label="execution_date")
    if execution_date <= signal_date:
        raise ValueError("execution 日期必须晚于 signal date：决策必须先于执行")
    if record["execution_status"] not in ALLOWED_EXECUTION_STATUSES:
        raise ValueError("execution_status 必须是 RQAlpha 原生执行完成状态")
    realized = parse_weight_vector(
        record["realized_weights"],
        expected_symbols=expected_symbols,
        label="realized_weights",
        require_total_one=False,
    )
    cash = parse_finite_float(record["cash_weight"], label="cash_weight")
    if cash < 0.0:
        raise ValueError("cash_weight 不得为负")
    if abs(sum(realized.values()) + cash - 1.0) > 1e-3:
        raise ValueError("realized_weights 与 cash_weight 合计必须覆盖组合")
    if parse_finite_float(record["target_deviation"], label="target_deviation") < 0.0:
        raise ValueError("target_deviation 不得为负")
    if parse_finite_float(record["portfolio_value"], label="portfolio_value") <= 0.0:
        raise ValueError("portfolio_value 必须为正")
    if parse_finite_float(record["drawdown"], label="drawdown") > 0.0:
        raise ValueError("drawdown 必须为非正值")
    if parse_finite_float(record["turnover"], label="turnover") < 0.0:
        raise ValueError("turnover 不得为负")
    verify_rqalpha_evidence_identity(
        record["execution_evidence"],
        root=root,
        expected_framework_version=expected_framework_version,
    )


def build_execution_record(
    decision: Mapping[str, str],
    *,
    execution_date: object,
    execution_status: str,
    realized_weights: Mapping[str, float],
    cash_weight: float,
    target_deviation: float,
    portfolio_value: float,
    drawdown: float,
    turnover: float,
    execution_evidence: str,
    expected_symbols: Iterable[str],
    expected_framework_version: str,
    root: Path = ROOT,
) -> dict[str, str]:
    """由权威执行输出构造一条完整 execution 行；不完整即拒绝。"""
    record = {field: "" for field in RECORD_FIELDS}
    record.update(
        {
            "record_type": "execution",
            "candidate_id": decision["candidate_id"],
            "protocol_version": decision["protocol_version"],
            "record_generated_at": _now_utc_iso(),
            "data_as_of": decision["data_as_of"],
            "vintage_identifier": decision["vintage_identifier"],
            "historical_manifest_hash": decision["historical_manifest_hash"],
            "prospective_data_hash": decision["prospective_data_hash"],
            "signal_date": decision["signal_date"],
            "eligible_assets": decision["eligible_assets"],
            "trend_states": decision["trend_states"],
            "target_changed": decision["target_changed"],
            "desired_targets": decision["desired_targets"],
            "action_required": decision["action_required"],
            "execution_date": pd.Timestamp(execution_date).date().isoformat(),
            "execution_status": execution_status,
            "realized_weights": json.dumps(
                {symbol: float(weight) for symbol, weight in realized_weights.items()},
                ensure_ascii=False,
                sort_keys=True,
            ),
            "cash_weight": repr(float(cash_weight)),
            "target_deviation": repr(float(target_deviation)),
            "portfolio_value": repr(float(portfolio_value)),
            "drawdown": repr(float(drawdown)),
            "turnover": repr(float(turnover)),
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
    *,
    vintage_dir: Path | None = None,
    manifest: Mapping[str, Any] | None = None,
    root: Path = ROOT,
    decision_seal_time: str | None = None,
    record_path: Path | None = None,
) -> dict[str, str]:
    """唯一写入门：候选完整性 → canonical 位置 → vintage 真实性 → 月末 → temporal seal → append。

    生产 CLI 只使用 canonical vintage 位置与 canonical observation 目标；`vintage_dir` /
    `record_path` / `decision_seal_time` 只供 `tmp_path` fixture 与 dependency injection 使用，
    不对用户暴露。任何非 canonical vintage 目录都在读取任何文件之前被拒绝。
    """
    resolved_manifest = (
        manifest if manifest is not None else load_manifest(root / MANIFEST_RELATIVE_PATH)
    )
    records = Path(record_path) if record_path is not None else canonical_observations_path(root)
    verify_candidate(dict(resolved_manifest), root)
    as_of_day = pd.Timestamp(as_of).normalize()
    cutoff = pd.Timestamp(resolved_manifest["historical_cutoff"]).normalize()
    if as_of_day <= cutoff:
        raise ValueError("prospective --as-of 必须晚于 historical_cutoff")
    vintage_path = (
        Path(vintage_dir) if vintage_dir is not None else canonical_vintage_dir(root, as_of_day)
    )
    # 位置校验必须先于任何 vintage 文件访问：外部目录不得成为官方前瞻证据。
    verify_canonical_vintage_location(
        vintage_path, as_of_day, canonical_parent=root / VINTAGE_PARENT_RELATIVE_PATH
    )
    vintage = load_prospective_inputs(vintage_path, resolved_manifest, as_of=as_of_day, root=root)
    validate_month_end_review(vintage.raw_calendar, as_of_day)
    first_eligible = derive_first_eligible_signal(resolved_manifest, vintage.raw_calendar)
    if first_eligible is not None and as_of_day < first_eligible:
        raise ValueError(
            "prospective --as-of 早于由冻结月度语义推导的 first eligible signal；"
            "该时点不可形成前瞻证据"
        )
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
        manifest_hash=sha256_frozen_repository_text(root / MANIFEST_RELATIVE_PATH),
        decision_seal_time=seal.isoformat(),
        root=root,
    )
    if record is None:
        raise ValueError("as-of 不是合格月末 signal；没有生成或伪造前瞻记录")
    append_decision_record(record, records)
    return record


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--verify-candidate", action="store_true")
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
    if args.verify_candidate or args.verify_no_observations:
        if args.as_of:
            parser.error("只读校验模式不能与 --as-of 同用")
        verify_candidate(manifest)
        lines = [
            "S2_R1 candidate manifest、冻结历史输入与前瞻证据写入路径校验通过；",
            f"observation 行数 = {observation_record_count(OBSERVATIONS_PATH)}，"
            f"decision 行数 = {decision_record_count(OBSERVATIONS_PATH)}。",
            "canonical vintage 位置 = research/shadow/s2_r1/vintages/<as-of>/；"
            "record 目的地固定，不可由 CLI 覆盖。",
        ]
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
    print(f"已追加 S2_R1 前瞻 decision record: {record['signal_date']}（执行证据尚未产生）")


if __name__ == "__main__":
    main()
