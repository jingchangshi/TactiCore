"""S4C R1 前瞻影子 runner 的 activation、边界与 append-only 契约测试。

全部使用 fixtures / `tmp_path` / synthetic data；不修改系统时间，不运行真实 future observation。
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

from research.experiments import run_s4c_r1_shadow as shadow
from research.experiments import verify_s4c_r1_candidate as candidate
from tacticore.data.prices import load_price_csv

ROOT = Path(__file__).resolve().parents[1]
AS_OF = pd.Timestamp("2026-09-30")
# COMMIT A 之前冻结的 candidate_manifest.json（CRLF 归一化）SHA-256。
FROZEN_MANIFEST_SHA256 = "09469df0ec06d741bee2f176fd1f8334154edafe84afef5b01d889222f6cd908"
GENERATED_AT = "2026-09-30T16:00:00+00:00"
ACTIVATION_TIMESTAMP = "2026-09-14T02:00:00+00:00"


def _write_header(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=shadow.RECORD_FIELDS).writeheader()
    return path


def _write_vintage(
    parent: Path,
    name: str,
    *,
    overlap_multiplier: float = 1.0,
    beyond_as_of: bool = False,
) -> Path:
    historical_prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    historical_calendar = shadow.load_calendar(ROOT / "data/canonical/trading_calendar.csv")
    overlap_date = historical_prices.index[-1]
    future_dates = pd.bdate_range("2026-09-01", "2026-09-30")
    if beyond_as_of:
        future_dates = future_dates.append(pd.DatetimeIndex([pd.Timestamp("2026-10-01")]))
    prospective_prices = pd.DataFrame(
        [historical_prices.iloc[-1].to_numpy()] * len(future_dates),
        index=future_dates,
        columns=historical_prices.columns,
    )
    drift = 1.0 + 0.001 * pd.Series(range(len(future_dates)), index=future_dates).to_numpy()
    prospective_prices = prospective_prices.mul(drift, axis=0)
    prices = pd.concat(
        [historical_prices.loc[[overlap_date]] * overlap_multiplier, prospective_prices]
    )
    calendar = pd.concat(
        [
            historical_calendar.loc[[overlap_date]],
            pd.DataFrame(1, index=future_dates, columns=["sse_open", "szse_open"]).astype(int),
        ]
    )
    vintage = parent / name
    vintage.mkdir(parents=True, exist_ok=True)
    prices.to_csv(vintage / "etf_adjusted_close.csv", index_label="date")
    calendar.to_csv(vintage / "trading_calendar.csv", index_label="date")
    (vintage / "provenance.json").write_text(json.dumps({"vintage": name}), encoding="utf-8")
    return vintage


def _fake_repo(tmp_path: Path) -> Path:
    """最小 canonical repo 布局，用于验证生产资料路径约束。"""
    root = tmp_path / "repo"
    (root / "research/shadow/s4c_r1").mkdir(parents=True, exist_ok=True)
    (root / "research/batches/s4c_activation").mkdir(parents=True, exist_ok=True)
    (root / "research/results").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "data/canonical").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / shadow.MANIFEST_RELATIVE_PATH, root / shadow.MANIFEST_RELATIVE_PATH)
    shutil.copyfile(
        ROOT / shadow.ACTIVATION_PROTOCOL_RELATIVE_PATH,
        root / shadow.ACTIVATION_PROTOCOL_RELATIVE_PATH,
    )
    shutil.copyfile(ROOT / "config/universe.csv", root / "config/universe.csv")
    for name in ("etf_adjusted_close.csv", "trading_calendar.csv", "provenance.json"):
        shutil.copyfile(ROOT / "data/canonical" / name, root / "data/canonical" / name)
    (root / shadow.ACTIVATION_DECISION_RECORD_RELATIVE_PATH).write_text(
        "# S4C R1 activation decision (fixture)\n\n"
        f"{shadow.ACTIVATION_DECISION_LINE_PREFIX} {shadow.ACTIVATION_DECISION_TOKEN}\n",
        encoding="utf-8",
    )
    _write_header(root / "research/shadow/s4c_r1/observations.csv")
    return root


def _activation_payload(root: Path) -> dict[str, str]:
    return {
        "candidate_id": "S4C_R1",
        "candidate_version": "R1",
        "activation_status": "ACTIVE",
        "activation_decision_token": shadow.ACTIVATION_DECISION_TOKEN,
        "activation_decision_timestamp": ACTIVATION_TIMESTAMP,
        "activation_protocol_version": "V1",
        "activation_protocol_path": shadow.ACTIVATION_PROTOCOL_RELATIVE_PATH,
        "activation_protocol_sha256": shadow.sha256_frozen_repository_text(
            root / shadow.ACTIVATION_PROTOCOL_RELATIVE_PATH
        ),
        "activation_decision_record": shadow.ACTIVATION_DECISION_RECORD_RELATIVE_PATH,
        "activation_decision_record_sha256": shadow.sha256_frozen_repository_text(
            root / shadow.ACTIVATION_DECISION_RECORD_RELATIVE_PATH
        ),
        "candidate_manifest_sha256": FROZEN_MANIFEST_SHA256,
        "candidate_freeze_timestamp": "2026-09-13T13:28:15Z",
        "historical_cutoff": "2026-08-31",
        "first_eligible_prospective_signal": "2026-09-30",
        "observation_schema_version": "S4C_R1_OBSERVATIONS_V1",
        "decision_record_policy": shadow.DECISION_RECORD_POLICY,
        "execution_record_policy": shadow.EXECUTION_RECORD_POLICY,
    }


def _write_activation(root: Path, **overrides: str) -> Path:
    payload = _activation_payload(root)
    payload.update(overrides)
    path = shadow.canonical_activation_path(root)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def candidate_verification_stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """写入门测试隔离候选完整性校验；该步在真实仓库上单独覆盖。"""
    monkeypatch.setattr(shadow, "verify_candidate_shadow", lambda *args, **kwargs: None)


@pytest.fixture
def frozen_record_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 record 生成时间可确定，避免测试依赖运行机器时钟。"""
    monkeypatch.setattr(shadow, "_now_utc_iso", lambda: GENERATED_AT)


# --- candidate identity ------------------------------------------------------------------


def test_candidate_manifest_is_unchanged_by_activation_work() -> None:
    manifest = shadow.load_manifest()

    assert manifest["candidate_id"] == "S4C_R1"
    assert manifest["prospective_activation"] == "NOT_ACTIVE"
    assert manifest["historical_cutoff"] == "2026-08-31"
    assert manifest["freeze_timestamp"] == "2026-09-13T13:28:15Z"
    assert manifest["first_eligible_prospective_signal"] == "2026-09-30"
    assert shadow.manifest_hash() == FROZEN_MANIFEST_SHA256


def test_frozen_semantics_still_reproduce_the_committed_schedule() -> None:
    shadow.verify_semantics_reproduce_frozen_schedule(shadow.load_manifest())


def test_framework_version_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = shadow.load_manifest()

    def frozen_version_except_numpy(package: str) -> str:
        if package == "numpy":
            return "0.0.0"
        return manifest["framework_versions"][package]

    monkeypatch.setattr(candidate, "version", frozen_version_except_numpy)

    with pytest.raises(ValueError, match="当前框架版本不一致: numpy"):
        shadow.verify_candidate_shadow(manifest)


# --- activation lifecycle artifact -------------------------------------------------------


def test_runner_refuses_to_write_without_an_activation_artifact(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    missing = root / shadow.ACTIVATION_RELATIVE_PATH

    assert shadow.activation_status(missing) == "NOT_ACTIVE"
    with pytest.raises(ValueError, match="未激活"):
        shadow.require_activation(missing, shadow.load_manifest(), root=root)


def test_activation_requires_the_correct_candidate_id(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    activation = shadow.load_activation(_write_activation(root, candidate_id="S4C_R2"))

    with pytest.raises(ValueError, match="candidate_id"):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


def test_activation_artifact_manifest_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    activation = shadow.load_activation(_write_activation(root, candidate_manifest_sha256="0" * 64))

    with pytest.raises(ValueError, match="manifest hash 不一致"):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("historical_cutoff", "2026-09-30", "historical_cutoff"),
        ("first_eligible_prospective_signal", "2026-09-29", "first_eligible_prospective_signal"),
        ("observation_schema_version", "S4C_R1_OBSERVATIONS_V2", "observation schema version"),
        ("activation_protocol_version", "V2", "protocol version"),
        ("activation_status", "NOT_ACTIVE", "activation_status"),
        ("activation_decision_token", "DEFER_S4C_R1_PROSPECTIVE_ACTIVATION", "decision_token"),
        ("candidate_freeze_timestamp", "2026-09-12T00:00:00Z", "freeze timestamp"),
        ("candidate_version", "R2", "candidate_version"),
        ("decision_record_policy", "APPEND_ANY_TIME", "decision_record_policy"),
        ("execution_record_policy", "INLINE_UPDATE", "execution_record_policy"),
        ("activation_protocol_path", "docs/goal.md", "protocol path"),
        ("activation_protocol_sha256", "0" * 64, "协议 hash 不一致"),
        ("activation_decision_record", "research/results/OTHER.md", "decision record path"),
        ("activation_decision_record_sha256", "0" * 64, "decision record hash 不一致"),
    ],
)
def test_every_frozen_activation_field_is_machine_verified(
    tmp_path: Path, field: str, value: str, match: str
) -> None:
    root = _fake_repo(tmp_path)
    activation = shadow.load_activation(_write_activation(root, **{field: value}))

    with pytest.raises(ValueError, match=match):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


def test_activation_schema_drift_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    payload = _activation_payload(root)
    payload["activation_commit"] = "self-referential"

    with pytest.raises(ValueError, match="字段集合与冻结 schema 不一致"):
        shadow.verify_activation(payload, shadow.load_manifest(), root=root)


def test_naive_activation_timestamp_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    activation = shadow.load_activation(
        _write_activation(root, activation_decision_timestamp="2026-09-14T02:00:00")
    )

    with pytest.raises(ValueError, match="必须带时区"):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


@pytest.mark.parametrize(
    "timestamp",
    ["2026-09-13T13:28:15Z", "2026-09-01T00:00:00+00:00"],
)
def test_activation_timestamp_at_or_before_freeze_is_rejected(
    tmp_path: Path, timestamp: str
) -> None:
    root = _fake_repo(tmp_path)
    activation = shadow.load_activation(
        _write_activation(root, activation_decision_timestamp=timestamp)
    )

    with pytest.raises(ValueError, match="严格晚于 candidate freeze timestamp"):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


def test_activation_evidence_must_exist_in_the_repository(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    activation = shadow.load_activation(_write_activation(root))
    (root / shadow.ACTIVATION_DECISION_RECORD_RELATIVE_PATH).unlink()

    with pytest.raises(ValueError, match="decision record 不存在"):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


def test_activation_decision_record_selecting_defer_is_rejected(tmp_path: Path) -> None:
    """正文提到 ACTIVATE token 不构成授权：只有被选中的裁决行有效。"""
    root = _fake_repo(tmp_path)
    record = root / shadow.ACTIVATION_DECISION_RECORD_RELATIVE_PATH
    record.write_text(
        "# S4C R1 activation decision\n\n"
        f"{shadow.ACTIVATION_DECISION_LINE_PREFIX} DEFER_S4C_R1_PROSPECTIVE_ACTIVATION\n\n"
        f"Allowed verdicts include {shadow.ACTIVATION_DECISION_TOKEN}.\n",
        encoding="utf-8",
    )
    activation = shadow.load_activation(
        _write_activation(
            root,
            activation_decision_record_sha256=shadow.sha256_frozen_repository_text(record),
        )
    )

    with pytest.raises(ValueError, match="选择的裁决不是 ACTIVATE"):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


def test_activation_decision_record_without_a_verdict_line_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    record = root / shadow.ACTIVATION_DECISION_RECORD_RELATIVE_PATH
    record.write_text(
        f"# S4C R1 activation decision\n\nProse mention only: {shadow.ACTIVATION_DECISION_TOKEN}\n",
        encoding="utf-8",
    )
    activation = shadow.load_activation(
        _write_activation(
            root,
            activation_decision_record_sha256=shadow.sha256_frozen_repository_text(record),
        )
    )

    with pytest.raises(ValueError, match="恰好包含一条 ACTIVATION_DECISION 行"):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


@pytest.mark.parametrize(
    "verdict",
    [
        "REJECT_S4C_R1_PROSPECTIVE_ACTIVATION",
        "BLOCK_S4C_R1_ACTIVATION_CORRECTNESS",
        "TOTALLY_NOT_A_VERDICT",
    ],
)
def test_non_activate_verdict_lines_are_parsed_and_rejected(tmp_path: Path, verdict: str) -> None:
    root = _fake_repo(tmp_path)
    record = root / shadow.ACTIVATION_DECISION_RECORD_RELATIVE_PATH
    record.write_text(
        f"# decision\n\n{shadow.ACTIVATION_DECISION_LINE_PREFIX} {verdict}\n", encoding="utf-8"
    )
    activation = shadow.load_activation(
        _write_activation(
            root,
            activation_decision_record_sha256=shadow.sha256_frozen_repository_text(record),
        )
    )

    with pytest.raises(ValueError, match="选择的裁决不是 ACTIVATE|不是允许值"):
        shadow.verify_activation(activation, shadow.load_manifest(), root=root)


# --- historical / prospective boundary ---------------------------------------------------


def test_historical_cutoff_cannot_be_prospective(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, "2026-09-30")

    with pytest.raises(ValueError, match="严格晚于 historical_data_cutoff"):
        shadow.validate_month_end(
            shadow.load_calendar(vintage / "trading_calendar.csv"),
            pd.Timestamp("2026-08-31"),
            manifest,
        )


@pytest.mark.parametrize("as_of", ["2026-09-01", "2026-09-13", "2026-09-29"])
def test_pre_eligible_signal_is_rejected(tmp_path: Path, as_of: str) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, "2026-09-30")

    with pytest.raises(ValueError, match="first_eligible_prospective_signal"):
        shadow.validate_month_end(
            shadow.load_calendar(vintage / "trading_calendar.csv"),
            pd.Timestamp(as_of),
            manifest,
        )


def test_first_eligible_signal_is_accepted_by_pure_validation(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, "2026-09-30")

    shadow.validate_month_end(
        shadow.load_calendar(vintage / "trading_calendar.csv"), AS_OF, manifest
    )

    prices, _, _ = shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)
    target, diagnostics = shadow.derive_target(prices, manifest, AS_OF)

    assert diagnostics["regime"] in {"RISK", "FALLBACK"}
    assert float(target.sum()) == pytest.approx(1.0)


def test_incomplete_signal_month_cannot_fabricate_a_month_end_decision(
    tmp_path: Path,
) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, "2026-09-30")
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv").loc[:"2026-09-29"]

    with pytest.raises(ValueError, match="未覆盖完整 signal 月"):
        shadow.validate_month_end(calendar, AS_OF, manifest)


def test_as_of_must_be_the_last_canonical_trading_day(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, "2026-09-30")
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv")
    calendar.loc[pd.Timestamp("2026-09-30")] = 0

    with pytest.raises(ValueError, match="最后一个 canonical 交易日"):
        shadow.validate_month_end(calendar, AS_OF, manifest)


def test_vintage_after_as_of_is_rejected_instead_of_leaking(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, "2026-09-30", beyond_as_of=True)

    with pytest.raises(ValueError, match="as-of 之后"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_vintage_cannot_overwrite_different_historical_data(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, "2026-09-30", overlap_multiplier=1.01)

    with pytest.raises(ValueError, match="重叠但内容不同"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


# --- canonical candidate-specific vintage location ---------------------------------------


def test_canonical_vintage_location_passes_pure_validation(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    vintage = _write_vintage(root / shadow.VINTAGE_PARENT_RELATIVE_PATH, "2026-09-30")

    shadow.verify_canonical_vintage_location(vintage, AS_OF, root)


def test_external_vintage_directory_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    external = _write_vintage(tmp_path / "elsewhere", "2026-09-30")

    with pytest.raises(ValueError, match="vintages"):
        shadow.verify_canonical_vintage_location(external, AS_OF, root)


def test_wrong_vintage_basename_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    vintage = _write_vintage(root / shadow.VINTAGE_PARENT_RELATIVE_PATH, "2026-10-30")

    with pytest.raises(ValueError, match="目录名必须等于 --as-of"):
        shadow.verify_canonical_vintage_location(vintage, AS_OF, root)


# --- decision / execution separation -----------------------------------------------------


def _decision_record(root: Path) -> dict[str, str]:
    manifest = shadow.load_manifest(root / shadow.MANIFEST_RELATIVE_PATH)
    vintage = _write_vintage(root / shadow.VINTAGE_PARENT_RELATIVE_PATH, "2026-09-30")
    prices, _, vintage_hash = shadow.load_prospective_inputs(
        vintage, manifest, as_of=AS_OF, root=root
    )
    return shadow.build_decision_record(
        prices,
        manifest,
        as_of=AS_OF,
        vintage_identifier=vintage.name,
        prospective_data_hash=vintage_hash,
        historical_manifest_hash=FROZEN_MANIFEST_SHA256,
        generated_at=GENERATED_AT,
        root=root,
    )


def test_decision_record_carries_no_execution_evidence(tmp_path: Path) -> None:
    record = _decision_record(_fake_repo(tmp_path))

    assert record["record_type"] == "decision"
    assert record["signal_date"] == "2026-09-30"
    assert record["data_as_of"] == "2026-09-30"
    assert record["candidate_id"] == "S4C_R1"
    assert record["protocol_version"] == "V1"
    assert record["execution_status"] == shadow.PENDING_EXECUTION_STATUS
    assert record["action_required"] == "true"
    assert json.loads(record["desired_targets"])
    for field in shadow.EXECUTION_ONLY_FIELDS:
        assert record[field] == ""


def test_decision_record_with_execution_evidence_is_rejected(tmp_path: Path) -> None:
    record = _decision_record(_fake_repo(tmp_path))
    record["execution_date"] = "2026-10-09"

    with pytest.raises(ValueError, match="不得包含执行结果字段"):
        shadow.verify_decision_row_is_fixed_before_execution(record)


def test_decision_generated_before_the_signal_date_is_rejected(tmp_path: Path) -> None:
    record = _decision_record(_fake_repo(tmp_path))
    record["record_generated_at"] = "2026-09-13T16:00:00+00:00"

    with pytest.raises(ValueError, match="不得早于 signal_date"):
        shadow.verify_record_generation_time(record)


def test_execution_must_follow_the_decision(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(_fake_repo(tmp_path))
    shadow.append_decision_record(record, path)

    execution = dict.fromkeys(shadow.RECORD_FIELDS, "")
    execution.update(
        {
            "record_type": "execution",
            "candidate_id": "S4C_R1",
            "signal_date": "2026-09-30",
            "execution_date": "2026-09-30",
            "execution_status": "EXECUTED",
        }
    )
    with pytest.raises(ValueError, match="决策必须先于执行"):
        shadow.append_execution_record(execution, path)

    execution["execution_date"] = "2026-10-09"
    shadow.append_execution_record(execution, path)
    assert shadow.observation_record_count(path) == 2


def test_execution_without_a_decision_is_rejected(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    execution = dict.fromkeys(shadow.RECORD_FIELDS, "")
    execution.update(
        {
            "record_type": "execution",
            "candidate_id": "S4C_R1",
            "signal_date": "2026-09-30",
            "execution_date": "2026-10-09",
        }
    )

    with pytest.raises(ValueError, match="只能追加在唯一对应的 decision 行之后"):
        shadow.append_execution_record(execution, path)


# --- append-only and idempotency ---------------------------------------------------------


def test_duplicate_decision_is_rejected(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(_fake_repo(tmp_path))

    shadow.append_decision_record(record, path)
    with pytest.raises(ValueError, match="append-only"):
        shadow.append_decision_record(record, path)

    assert shadow.decision_record_count(path) == 1


def test_duplicate_execution_is_rejected(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(_fake_repo(tmp_path))
    shadow.append_decision_record(record, path)

    execution = dict.fromkeys(shadow.RECORD_FIELDS, "")
    execution.update(
        {
            "record_type": "execution",
            "candidate_id": "S4C_R1",
            "signal_date": "2026-09-30",
            "execution_date": "2026-10-09",
        }
    )
    shadow.append_execution_record(execution, path)

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_execution_record(execution, path)

    assert shadow.observation_record_count(path) == 2


def test_append_only_preserves_the_existing_decision_row(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(_fake_repo(tmp_path))
    shadow.append_decision_record(record, path)
    before = path.read_text(encoding="utf-8").splitlines()

    execution = dict.fromkeys(shadow.RECORD_FIELDS, "")
    execution.update(
        {
            "record_type": "execution",
            "candidate_id": "S4C_R1",
            "signal_date": "2026-09-30",
            "execution_date": "2026-10-09",
        }
    )
    shadow.append_execution_record(execution, path)

    after = path.read_text(encoding="utf-8").splitlines()
    assert after[: len(before)] == before
    assert len(after) == len(before) + 1


def test_rejected_duplicate_append_leaves_the_file_bytes_unchanged(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(_fake_repo(tmp_path))
    shadow.append_decision_record(record, path)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_decision_record(record, path)

    assert path.read_bytes() == before


def test_observation_schema_drift_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "observations.csv"
    path.write_text("record_type,candidate_id\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="schema 与冻结协议不一致"):
        shadow.read_observation_rows(path)


def test_frozen_observation_scaffold_is_still_header_only() -> None:
    rows = candidate.OBSERVATIONS_PATH.read_text(encoding="utf-8").splitlines()

    assert rows == [",".join(candidate.RECORD_FIELDS)]
    assert shadow.observation_record_count(candidate.OBSERVATIONS_PATH) == 0


# --- CLI write authorization -------------------------------------------------------------


def test_production_cli_cannot_substitute_lifecycle_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for option in ("--activation-path", "--record-path"):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_s4c_r1_shadow",
                "--as-of",
                "2026-09-30",
                "--vintage-dir",
                str(tmp_path),
                option,
                str(tmp_path / "override.json"),
            ],
        )
        with pytest.raises(SystemExit):
            shadow.main()


def test_explicit_as_of_is_required(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["run_s4c_r1_shadow", "--vintage-dir", str(tmp_path)])

    with pytest.raises(SystemExit):
        shadow.main()


def test_runner_refuses_to_write_when_not_active(
    tmp_path: Path, candidate_verification_stubbed: None, frozen_record_time: None
) -> None:
    root = _fake_repo(tmp_path)
    vintage = _write_vintage(root / shadow.VINTAGE_PARENT_RELATIVE_PATH, "2026-09-30")

    with pytest.raises(ValueError, match="未激活"):
        shadow.run_decision(AS_OF, vintage, root=root)

    assert shadow.observation_record_count(root / "research/shadow/s4c_r1/observations.csv") == 0


@pytest.mark.parametrize(
    ("as_of", "match"),
    [
        ("2026-09-29", "first_eligible_prospective_signal"),
        ("2026-09-13", "first_eligible_prospective_signal"),
        ("2026-08-31", "严格晚于 historical_data_cutoff"),
    ],
)
def test_runner_refuses_real_record_before_first_eligible_date(
    tmp_path: Path,
    candidate_verification_stubbed: None,
    frozen_record_time: None,
    as_of: str,
    match: str,
) -> None:
    """写入门必须以候选 completeness 之后的边界校验拒绝非前瞻时点，且不落盘。"""
    root = _fake_repo(tmp_path)
    _write_activation(root)
    vintage = _write_vintage(root / shadow.VINTAGE_PARENT_RELATIVE_PATH, as_of)
    observations = root / "research/shadow/s4c_r1/observations.csv"
    before = observations.read_bytes()

    with pytest.raises(ValueError, match=match):
        shadow.run_decision(pd.Timestamp(as_of), vintage, root=root)

    assert observations.read_bytes() == before
    assert shadow.observation_record_count(observations) == 0


def test_production_write_path_appends_once_and_rejects_rerun(
    tmp_path: Path,
    candidate_verification_stubbed: None,
    frozen_record_time: None,
) -> None:
    root = _fake_repo(tmp_path)
    _write_activation(root)
    vintage = _write_vintage(root / shadow.VINTAGE_PARENT_RELATIVE_PATH, "2026-09-30")
    observations = root / "research/shadow/s4c_r1/observations.csv"

    record = shadow.run_decision(AS_OF, vintage, root=root)

    assert record["signal_date"] == "2026-09-30"
    assert shadow.decision_record_count(observations) == 1
    rows = shadow.read_observation_rows(observations)
    assert rows[0]["candidate_id"] == "S4C_R1"
    assert rows[0]["vintage_identifier"] == "2026-09-30"
    assert rows[0]["execution_status"] == shadow.PENDING_EXECUTION_STATUS

    with pytest.raises(ValueError, match="append-only"):
        shadow.run_decision(AS_OF, vintage, root=root)

    assert shadow.decision_record_count(observations) == 1


def test_production_write_path_rejects_external_vintage_directory(
    tmp_path: Path, candidate_verification_stubbed: None, frozen_record_time: None
) -> None:
    root = _fake_repo(tmp_path)
    _write_activation(root)
    external = _write_vintage(tmp_path / "elsewhere", "2026-09-30")
    observations = root / "research/shadow/s4c_r1/observations.csv"
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="vintages"):
        shadow.run_decision(AS_OF, external, root=root)

    assert observations.read_bytes() == before


def test_external_vintage_is_rejected_before_any_file_read(
    tmp_path: Path, candidate_verification_stubbed: None, frozen_record_time: None
) -> None:
    """不存在的目录也只能得到位置错误，证明不存在对 vintage 文件的读取尝试。"""
    root = _fake_repo(tmp_path)
    _write_activation(root)
    missing_external = tmp_path / "elsewhere" / "2026-09-30"

    with pytest.raises(ValueError, match="vintages"):
        shadow.run_decision(AS_OF, missing_external, root=root)


def test_external_vintage_rejection_never_touches_vintage_readers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidate_verification_stubbed: None,
    frozen_record_time: None,
) -> None:
    root = _fake_repo(tmp_path)
    _write_activation(root)
    external = _write_vintage(tmp_path / "elsewhere", "2026-09-30")

    def tripwire(*args: object, **kwargs: object) -> pd.DataFrame:
        raise AssertionError("位置校验之前不得读取任何 vintage 文件")

    monkeypatch.setattr(shadow, "load_calendar", tripwire)

    with pytest.raises(ValueError, match="vintages"):
        shadow.run_decision(AS_OF, external, root=root)
