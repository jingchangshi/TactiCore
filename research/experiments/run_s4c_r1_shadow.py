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

PROTOCOL_VERSION = "V1"
ACTIVATION_PROTOCOL_VERSION = "V1"
OBSERVATION_SCHEMA_VERSION = "S4C_R1_OBSERVATIONS_V1"
PENDING_EXECUTION_STATUS = "PENDING_NEXT_CANONICAL_OBSERVATION"
ACTIVE_STATUS = "ACTIVE"

ACTIVATION_FIELDS = (
    "candidate_id",
    "candidate_version",
    "activation_status",
    "activation_decision_timestamp",
    "activation_protocol_version",
    "candidate_manifest_sha256",
    "historical_cutoff",
    "first_eligible_prospective_signal",
    "observation_schema_version",
    "decision_record_policy",
    "execution_record_policy",
    "activation_decision_record",
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
    if tuple(activation.keys()) != ACTIVATION_FIELDS:
        raise ValueError("activation artifact 字段集合与冻结 schema 不一致")
    if activation["candidate_id"] != manifest["candidate_id"]:
        raise ValueError("activation artifact 的 candidate_id 与 manifest 不一致")
    if activation["candidate_version"] != manifest["candidate_version"]:
        raise ValueError("activation artifact 的 candidate_version 与 manifest 不一致")
    if activation["activation_status"] != ACTIVE_STATUS:
        raise ValueError("activation artifact 的 activation_status 不是 ACTIVE")
    if activation["activation_protocol_version"] != ACTIVATION_PROTOCOL_VERSION:
        raise ValueError("activation artifact 的 protocol version 不是冻结版本")
    if activation["observation_schema_version"] != OBSERVATION_SCHEMA_VERSION:
        raise ValueError("activation artifact 的 observation schema version 不一致")
    if activation["historical_cutoff"] != manifest["historical_cutoff"]:
        raise ValueError("activation artifact 的 historical_cutoff 与 manifest 不一致")
    if (
        activation["first_eligible_prospective_signal"]
        != manifest["first_eligible_prospective_signal"]
    ):
        raise ValueError(
            "activation artifact 的 first_eligible_prospective_signal 与 manifest 不一致"
        )
    expected_manifest_hash = manifest_sha256 or sha256_frozen_repository_text(
        root / "research/shadow/s4c_r1/candidate_manifest.json"
    )
    if activation["candidate_manifest_sha256"] != expected_manifest_hash:
        raise ValueError("activation artifact 的 candidate manifest hash 不一致")
    # activation 决策时间必须可解析；是否晚于 wall-clock 不属于证据契约，
    # 因为它会让协议依赖运行机器的时钟（reproducibility 由 decision record 保证）。
    pd.Timestamp(activation["activation_decision_timestamp"])


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


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--verify-candidate", action="store_true")
    parser.add_argument("--verify-activation", action="store_true")
    parser.add_argument("--as-of", help="决策时点 YYYY-MM-DD；不得使用 wall-clock 默认值")
    parser.add_argument("--vintage-dir", type=Path)
    parser.add_argument("--activation-path", type=Path, default=ACTIVATION_PATH)
    parser.add_argument("--record-path", type=Path, default=OBSERVATIONS_PATH)
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
            f"observation 行数 = {observation_record_count(args.record_path)}，"
            f"decision 行数 = {decision_record_count(args.record_path)}。",
        ]
        if args.verify_activation:
            activation = load_activation(args.activation_path)
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

    verify_candidate_shadow(manifest)
    require_activation(args.activation_path, manifest)
    as_of = pd.Timestamp(args.as_of)
    vintage_calendar = load_calendar(args.vintage_dir / "trading_calendar.csv")
    validate_month_end(vintage_calendar, as_of, manifest)
    prices, _, vintage_hash = load_prospective_inputs(args.vintage_dir, manifest, as_of=as_of)
    record = build_decision_record(
        prices,
        manifest,
        as_of=as_of,
        vintage_identifier=args.vintage_dir.name,
        prospective_data_hash=vintage_hash,
        historical_manifest_hash=manifest_hash(),
    )
    append_decision_record(record, args.record_path)
    print(f"已追加 S4C_R1 前瞻 decision record: {record['signal_date']}（执行证据尚未产生）")


if __name__ == "__main__":
    main()
