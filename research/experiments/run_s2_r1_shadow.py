#!/usr/bin/env python3
"""用冻结的 S2 R1 身份生成一条可审计的月度前瞻影子决策。"""

from __future__ import annotations

import csv
import hashlib
import json
from argparse import ArgumentParser
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd

from tacticore.data.prices import load_price_csv
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
VINTAGE_FILES = ("etf_adjusted_close.csv", "trading_calendar.csv", "provenance.json")
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
PROTOCOL_VERSION = "V1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_frozen_repository_text(path: Path) -> str:
    """Hash frozen repository text consistently across LF and CRLF checkouts."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    if manifest["candidate_id"] != "S2_R1" or manifest["candidate_version"] != "R1":
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


def validate_month_end_review(vintage_calendar: pd.DataFrame, as_of: pd.Timestamp) -> None:
    """只以已公布交易日历确认月末，不以未来价格推断月末。"""
    month_calendar = vintage_calendar.loc[
        vintage_calendar.index.to_period("M") == as_of.to_period("M")
    ]
    natural_month_end = as_of + pd.offsets.MonthEnd(0)
    if month_calendar.empty or month_calendar.index.max() < natural_month_end:
        raise ValueError("vintage 日历未覆盖完整 signal 月，不能生成月末前瞻 decision")
    open_dates = month_calendar.index[month_calendar.any(axis=1)]
    if open_dates.empty or open_dates.max() != as_of:
        raise ValueError("--as-of 必须是该月最后一个 canonical 交易日")


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


def build_decision_record(
    prices: pd.DataFrame,
    manifest: dict[str, Any],
    *,
    as_of: pd.Timestamp,
    vintage_identifier: str,
    prospective_data_hash: str,
    manifest_hash: str,
    generated_at: str | None = None,
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
    timestamp = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    desired_targets = {symbol: float(weight) for symbol, weight in target.items()}
    return {
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
        "execution_status": "PENDING_NEXT_CANONICAL_OBSERVATION",
        "realized_weights": "",
        "cash_weight": "",
        "target_deviation": "",
        "portfolio_value": "",
        "drawdown": "",
        "turnover": "",
        "execution_evidence": "",
    }


def append_decision_record(record: dict[str, str], path: Path = OBSERVATIONS_PATH) -> None:
    if not path.is_file():
        raise FileNotFoundError("observations.csv 必须先以协议表头创建")
    existing = pd.read_csv(path, dtype=str)
    if tuple(existing.columns) != RECORD_FIELDS:
        raise ValueError("observations.csv schema 与冻结协议不一致")
    if record["signal_date"] in set(existing.get("signal_date", pd.Series(dtype=str)).dropna()):
        raise ValueError("同一 signal_date 的 decision record 已存在，append-only 协议禁止重写")
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECORD_FIELDS)
        writer.writerow(record)


def decision_record_count(path: Path = OBSERVATIONS_PATH) -> int:
    records = pd.read_csv(path, dtype=str)
    if tuple(records.columns) != RECORD_FIELDS:
        raise ValueError("observations.csv schema 与冻结协议不一致")
    return int(records["record_type"].eq("decision").sum())


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--verify-candidate", action="store_true")
    parser.add_argument("--as-of", help="决策时点，YYYY-MM-DD；不得使用 wall-clock 默认值")
    parser.add_argument("--vintage-dir", type=Path)
    parser.add_argument("--record-path", type=Path, default=OBSERVATIONS_PATH)
    args = parser.parse_args()
    manifest = load_manifest()
    verify_candidate(manifest)
    if args.verify_candidate:
        if args.as_of or args.vintage_dir:
            parser.error("--verify-candidate 不能与 --as-of 或 --vintage-dir 同用")
        print(
            "S2_R1 candidate manifest 与冻结历史输入校验通过；"
            f"当前前瞻 decision record 数为 {decision_record_count(args.record_path)}。"
        )
        return
    if not args.as_of or args.vintage_dir is None:
        parser.error("前瞻决策必须同时提供 --as-of 和 --vintage-dir")
    as_of = pd.Timestamp(args.as_of)
    if as_of > pd.Timestamp(manifest["historical_cutoff"]):
        validate_month_end_review(load_calendar(args.vintage_dir / "trading_calendar.csv"), as_of)
        prices, _, vintage_hash = load_prospective_inputs(args.vintage_dir, manifest, as_of=as_of)
        record = build_decision_record(
            prices,
            manifest,
            as_of=as_of,
            vintage_identifier=args.vintage_dir.name,
            prospective_data_hash=vintage_hash,
            manifest_hash=sha256_frozen_repository_text(MANIFEST_PATH),
        )
        if record is None:
            print("as-of 不是合格月末 signal；没有生成或伪造前瞻记录。")
            return
        append_decision_record(record, args.record_path)
        print(f"已追加 S2_R1 前瞻 decision record: {record['signal_date']}")
        return
    raise ValueError("prospective --as-of 必须晚于 historical_cutoff")


if __name__ == "__main__":
    main()
