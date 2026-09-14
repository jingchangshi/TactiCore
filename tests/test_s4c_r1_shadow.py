"""S4C R1 前瞻影子 runner 的 activation、provenance、temporal seal 与 append-only 契约测试。

全部使用 fixtures / `tmp_path` / synthetic data；不修改系统时间，不运行真实 future observation。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from conftest import (
    build_candidate_repo,
    rqalpha_code,
    write_execution_artifact,
    write_observations_header,
    write_prospective_vintage,
)

from research.experiments import run_s4c_r1_shadow as shadow
from research.experiments import verify_s4c_r1_candidate as candidate

AS_OF = pd.Timestamp("2026-09-30")
SEAL = "2026-09-30T08:00:00+00:00"
EXECUTION_TIMESTAMP = "2026-10-09T07:05:00+00:00"
ARTIFACT_GENERATED_AT = "2026-10-09T07:30:00+00:00"
EXECUTION_SEAL = "2026-10-09T08:00:00+00:00"
# COMMIT A 之前冻结的 candidate_manifest.json（CRLF 归一化）SHA-256。
FROZEN_MANIFEST_SHA256 = "09469df0ec06d741bee2f176fd1f8334154edafe84afef5b01d889222f6cd908"


@pytest.fixture(autouse=True)
def _frozen_runner_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """execution 行的时间只能来自 runner 时钟；测试用注入时钟复现 fixture 时点。"""
    monkeypatch.setattr(shadow, "_now_utc_iso", lambda: EXECUTION_SEAL)


def _fake_repo(tmp_path: Path) -> Path:
    return build_candidate_repo(tmp_path / "repo", "S4C_R1")


def _activation_payload(root: Path) -> dict[str, Any]:
    return json.loads((root / shadow.ACTIVATION_RELATIVE_PATH).read_text(encoding="utf-8"))


def _write_activation(root: Path, **overrides: Any) -> Path:
    payload = _activation_payload(root)
    payload.update(overrides)
    path = shadow.canonical_activation_path(root)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _repo_with_vintage(tmp_path: Path, **vintage_kwargs: Any) -> Path:
    root = _fake_repo(tmp_path)
    write_observations_header(shadow.canonical_observations_path(root), shadow.RECORD_FIELDS)
    write_prospective_vintage(
        root / shadow.VINTAGE_PARENT_RELATIVE_PATH / "2026-09-30",
        as_of="2026-09-30",
        **vintage_kwargs,
    )
    return root


@pytest.fixture
def candidate_verification_stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """写入门测试隔离候选完整性校验；该步在真实仓库上单独覆盖。"""
    monkeypatch.setattr(shadow, "verify_candidate_shadow", lambda *args, **kwargs: None)


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
    missing.unlink()

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
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")

    with pytest.raises(ValueError, match="严格晚于 historical_data_cutoff"):
        shadow.validate_month_end(
            shadow.load_calendar(vintage / "trading_calendar.csv"),
            pd.Timestamp("2026-08-31"),
            manifest,
        )


@pytest.mark.parametrize("as_of", ["2026-09-01", "2026-09-13", "2026-09-29"])
def test_pre_eligible_signal_is_rejected(tmp_path: Path, as_of: str) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")

    with pytest.raises(ValueError, match="first_eligible_prospective_signal"):
        shadow.validate_month_end(
            shadow.load_calendar(vintage / "trading_calendar.csv"),
            pd.Timestamp(as_of),
            manifest,
        )


def test_first_eligible_signal_is_accepted_by_pure_validation(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")

    shadow.validate_month_end(
        shadow.load_calendar(vintage / "trading_calendar.csv"), AS_OF, manifest
    )

    inputs = shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)
    target, diagnostics = shadow.derive_target(inputs.prices, manifest, AS_OF)

    assert diagnostics["regime"] in {"RISK", "FALLBACK"}
    assert float(target.sum()) == pytest.approx(1.0)


def test_incomplete_signal_month_cannot_fabricate_a_month_end_decision(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv").loc[
        : pd.Timestamp("2026-09-29")
    ]

    with pytest.raises(ValueError, match="未覆盖完整 signal 月"):
        shadow.validate_month_end(calendar, AS_OF, manifest)


def test_as_of_must_be_the_last_canonical_trading_day(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv")
    calendar.loc[pd.Timestamp("2026-09-30")] = 0

    with pytest.raises(ValueError, match="最后一个 canonical 交易日"):
        shadow.validate_month_end(calendar, AS_OF, manifest)


def test_vintage_after_as_of_is_rejected_instead_of_leaking(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(
        tmp_path / "2026-09-30", as_of="2026-09-30", beyond_as_of=True
    )

    with pytest.raises(ValueError, match="as-of"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_vintage_cannot_overwrite_different_historical_data(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(
        tmp_path / "2026-09-30", as_of="2026-09-30", overlap_multiplier=1.01
    )

    with pytest.raises(ValueError, match="重叠但内容不同"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_provenance_source_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(
        tmp_path / "2026-09-30",
        as_of="2026-09-30",
        provenance_overrides={"source": "RQData"},
    )

    with pytest.raises(ValueError, match="source"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_provenance_price_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    path = vintage / "provenance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["files"]["etf_adjusted_close.csv"]["sha256"] = "0" * 64
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


# --- canonical candidate-specific vintage location ---------------------------------------


def test_canonical_vintage_location_passes_pure_validation(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    vintage = write_prospective_vintage(
        root / shadow.VINTAGE_PARENT_RELATIVE_PATH / "2026-09-30", as_of="2026-09-30"
    )

    shadow.verify_canonical_vintage_location(
        vintage, AS_OF, canonical_parent=root / shadow.VINTAGE_PARENT_RELATIVE_PATH
    )


def test_external_vintage_directory_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    external = write_prospective_vintage(tmp_path / "elsewhere/2026-09-30", as_of="2026-09-30")

    with pytest.raises(ValueError, match="vintages"):
        shadow.verify_canonical_vintage_location(
            external, AS_OF, canonical_parent=root / shadow.VINTAGE_PARENT_RELATIVE_PATH
        )


def test_wrong_vintage_basename_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    vintage = write_prospective_vintage(
        root / shadow.VINTAGE_PARENT_RELATIVE_PATH / "2026-10-30", as_of="2026-10-30"
    )

    with pytest.raises(ValueError, match="目录名必须等于 --as-of"):
        shadow.verify_canonical_vintage_location(
            vintage, AS_OF, canonical_parent=root / shadow.VINTAGE_PARENT_RELATIVE_PATH
        )


# --- decision / execution separation -----------------------------------------------------


def _decision_record(root: Path, *, seal: str = SEAL) -> dict[str, str]:
    manifest = shadow.load_manifest(root / shadow.MANIFEST_RELATIVE_PATH)
    vintage_path = root / shadow.VINTAGE_PARENT_RELATIVE_PATH / "2026-09-30"
    inputs = shadow.load_prospective_inputs(vintage_path, manifest, as_of=AS_OF, root=root)
    return shadow.build_decision_record(
        inputs.prices,
        manifest,
        as_of=AS_OF,
        vintage_identifier=vintage_path.name,
        prospective_data_hash=inputs.vintage_hash,
        historical_manifest_hash=FROZEN_MANIFEST_SHA256,
        decision_seal_time=seal,
        root=root,
    )


def test_decision_record_carries_no_execution_evidence(tmp_path: Path) -> None:
    root = _repo_with_vintage(tmp_path)
    record = _decision_record(root)

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
    root = _repo_with_vintage(tmp_path)
    record = _decision_record(root)
    record["execution_date"] = "2026-10-09"

    with pytest.raises(ValueError, match="不得包含执行结果字段"):
        shadow.verify_decision_row_is_fixed_before_execution(record)


def test_decision_generated_before_the_signal_close_is_rejected(tmp_path: Path) -> None:
    root = _repo_with_vintage(tmp_path)
    record = _decision_record(root)
    record["record_generated_at"] = "2026-09-30T06:00:00+00:00"

    with pytest.raises(ValueError, match="不得早于 signal_close"):
        shadow.verify_record_generation_time(record)


def test_decision_sealed_after_the_signal_day_is_rejected(tmp_path: Path) -> None:
    root = _repo_with_vintage(tmp_path)
    record = _decision_record(root)
    record["record_generated_at"] = "2026-10-09T02:00:00+00:00"

    with pytest.raises(ValueError, match="必须等于 signal_date"):
        shadow.verify_record_generation_time(record)


# --- execution record completeness ---------------------------------------------------------


_EVIDENCE_RELATIVE_PATH = "research/results/s4c_r1_fixture_rqalpha_artifact.json"


def _execution_fixture(
    tmp_path: Path, **artifact_kwargs: Any
) -> tuple[Path, dict[str, str], dict[str, str], Path]:
    root = _repo_with_vintage(tmp_path)
    observations = shadow.canonical_observations_path(root)
    decision = _decision_record(root)
    shadow.append_decision_record(decision, observations)
    symbols = tuple(json.loads(decision["desired_targets"]).keys())
    write_execution_artifact(
        root,
        relative_path=_EVIDENCE_RELATIVE_PATH,
        candidate_id="S4C_R1",
        signal_date=decision["signal_date"],
        desired_targets=json.loads(decision["desired_targets"]),
        execution_timestamp=EXECUTION_TIMESTAMP,
        artifact_generated_at=ARTIFACT_GENERATED_AT,
        **artifact_kwargs,
    )
    identity = shadow.build_rqalpha_evidence_identity(
        evidence_path=_EVIDENCE_RELATIVE_PATH, root=root, expected_framework_version="6.3.0"
    )
    complete = shadow.build_execution_record(
        decision,
        execution_evidence=identity,
        expected_symbols=symbols,
        expected_framework_version="6.3.0",
        root=root,
    )
    return root, decision, complete, observations


def test_complete_execution_row_is_accepted_after_its_decision(tmp_path: Path) -> None:
    root, _decision_row, complete, observations = _execution_fixture(tmp_path)
    before = observations.read_text(encoding="utf-8").splitlines()

    shadow.append_execution_record(complete, observations, root=root)

    after = observations.read_text(encoding="utf-8").splitlines()
    assert after[: len(before)] == before
    assert len(after) == len(before) + 1
    assert shadow.observation_record_count(observations) == 2


def test_execution_without_a_decision_is_rejected(tmp_path: Path) -> None:
    root, _decision_row, complete, _observations = _execution_fixture(tmp_path)
    empty = write_observations_header(tmp_path / "empty.csv", shadow.RECORD_FIELDS)
    before = empty.read_bytes()

    with pytest.raises(ValueError, match="唯一对应的 decision"):
        shadow.append_execution_record(complete, empty, root=root)

    assert empty.read_bytes() == before


def test_execution_must_follow_the_decision(tmp_path: Path) -> None:
    root, _decision_row, complete, observations = _execution_fixture(tmp_path)
    complete["execution_date"] = "2026-09-30"
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="决策必须先于执行"):
        shadow.append_execution_record(complete, observations, root=root)

    assert observations.read_bytes() == before


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("realized_weights", "", "realized_weights"),
        ("cash_weight", "", "cash_weight"),
        ("portfolio_total_absolute_weight_deviation", "", "portfolio_total"),
        ("material_portfolio_tracking_date", "", "material_portfolio_tracking_date"),
        ("material_asset_differences", "", "material_asset_differences"),
        ("turnover", "", "turnover"),
        ("execution_status", "PENDING", "execution_status"),
        ("execution_evidence", "", "execution_evidence"),
    ],
)
def test_incomplete_execution_row_is_rejected(
    tmp_path: Path, field: str, value: str, match: str
) -> None:
    root, _decision_row, complete, observations = _execution_fixture(tmp_path)
    complete[field] = value
    before = observations.read_bytes()

    with pytest.raises(ValueError, match=match):
        shadow.append_execution_record(complete, observations, root=root)

    assert observations.read_bytes() == before


def test_material_portfolio_flag_must_match_the_5pp_rule(tmp_path: Path) -> None:
    root, _decision_row, complete, observations = _execution_fixture(tmp_path)
    complete["material_portfolio_tracking_date"] = "true"

    with pytest.raises(ValueError, match="material_portfolio_tracking_date"):
        shadow.append_execution_record(complete, observations, root=root)


def _shift_one_asset(
    targets: dict[str, float], *, delta: float
) -> tuple[dict[str, float], dict[str, float]]:
    """把最大权重标的降 delta、现金升 delta，保持组合完整。"""
    symbol = max(targets, key=lambda name: targets[name])
    assert targets[symbol] > delta
    realized = dict(targets)
    realized[symbol] = targets[symbol] - delta
    return realized, {"cash_weight": delta}


def test_material_asset_difference_below_5pp_is_not_reported(tmp_path: Path) -> None:
    root, _decision_row, complete, observations = _execution_fixture(tmp_path)
    assert complete["material_asset_differences"] == "[]"
    assert complete["material_portfolio_tracking_date"] == "false"
    symbol = max(
        json.loads(complete["desired_targets"]), key=json.loads(complete["desired_targets"]).get
    )
    before = observations.read_bytes()
    complete["material_asset_differences"] = json.dumps(
        [{"symbol": symbol, "intended": 0.2, "realized": 0.17, "native_evidence": "fixture"}]
    )

    with pytest.raises(ValueError, match="超过 5pp"):
        shadow.append_execution_record(complete, observations, root=root)

    assert observations.read_bytes() == before


def test_material_asset_difference_above_5pp_requires_artifact_native_evidence(
    tmp_path: Path,
) -> None:
    root = _repo_with_vintage(tmp_path)
    decision = _decision_record(root)
    observations = shadow.canonical_observations_path(root)
    shadow.append_decision_record(decision, observations)
    targets = json.loads(decision["desired_targets"])
    realized, extra = _shift_one_asset(targets, delta=0.06)
    symbol = max(targets, key=lambda name: targets[name])
    without_evidence = "research/results/s4c_r1_fixture_without_native_evidence.json"
    write_execution_artifact(
        root,
        relative_path=without_evidence,
        candidate_id="S4C_R1",
        signal_date=decision["signal_date"],
        desired_targets=targets,
        realized_weights=realized,
        execution_timestamp=EXECUTION_TIMESTAMP,
        artifact_generated_at=ARTIFACT_GENERATED_AT,
        **extra,
    )
    identity_without_evidence = shadow.build_rqalpha_evidence_identity(
        evidence_path=without_evidence, root=root, expected_framework_version="6.3.0"
    )
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="native_evidence"):
        shadow.build_execution_record(
            decision,
            execution_evidence=identity_without_evidence,
            expected_symbols=tuple(targets),
            expected_framework_version="6.3.0",
            root=root,
        )

    assert observations.read_bytes() == before

    write_execution_artifact(
        root,
        relative_path=_EVIDENCE_RELATIVE_PATH,
        candidate_id="S4C_R1",
        signal_date=decision["signal_date"],
        desired_targets=targets,
        realized_weights=realized,
        execution_timestamp=EXECUTION_TIMESTAMP,
        artifact_generated_at=ARTIFACT_GENERATED_AT,
        order_events=((rqalpha_code(root, symbol), "ACTIVE", "sys_analyser native 成交说明"),),
        **extra,
    )
    identity = shadow.build_rqalpha_evidence_identity(
        evidence_path=_EVIDENCE_RELATIVE_PATH, root=root, expected_framework_version="6.3.0"
    )
    complete = shadow.build_execution_record(
        decision,
        execution_evidence=identity,
        expected_symbols=tuple(targets),
        expected_framework_version="6.3.0",
        root=root,
    )

    assert complete["material_portfolio_tracking_date"] == "true"
    differences = json.loads(complete["material_asset_differences"])
    assert [entry["symbol"] for entry in differences] == [symbol]
    assert differences[0]["native_evidence"] == "sys_analyser native 成交说明"

    mutations = [
        ("material_asset_differences", json.dumps([], ensure_ascii=False)),
        (
            "material_asset_differences",
            json.dumps(
                [
                    {
                        "symbol": entry["symbol"],
                        "intended": entry["intended"],
                        "realized": entry["realized"],
                        "native_evidence": "调用方自述",
                    }
                    for entry in differences
                ],
                ensure_ascii=False,
            ),
        ),
    ]
    for field, value in mutations:
        mutated = dict(complete)
        mutated[field] = value
        before = observations.read_bytes()
        with pytest.raises(ValueError, match="material_asset_differences"):
            shadow.append_execution_record(mutated, observations, root=root)
        assert observations.read_bytes() == before

    shadow.append_execution_record(complete, observations, root=root)
    assert shadow.observation_record_count(observations) == 2


def test_rqalpha_evidence_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    root, _decision_row, complete, observations = _execution_fixture(tmp_path)
    payload = json.loads(complete["execution_evidence"])
    payload["evidence_sha256"] = "0" * 64
    complete["execution_evidence"] = json.dumps(payload)

    with pytest.raises(ValueError, match="SHA-256"):
        shadow.append_execution_record(complete, observations, root=root)


def test_duplicate_execution_is_rejected(tmp_path: Path) -> None:
    root, _decision_row, complete, observations = _execution_fixture(tmp_path)
    shadow.append_execution_record(complete, observations, root=root)
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_execution_record(complete, observations, root=root)

    assert observations.read_bytes() == before


def test_duplicate_decision_is_rejected(tmp_path: Path) -> None:
    root, _decision_row, complete, observations = _execution_fixture(tmp_path)
    decision = shadow.read_event_rows(observations, shadow.RECORD_FIELDS)[0]
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_decision_record(decision, observations)

    assert observations.read_bytes() == before


def test_observation_schema_drift_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "observations.csv"
    path.write_text("record_type,candidate_id\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="schema 与冻结协议不一致"):
        shadow.read_observation_rows(path)


def test_frozen_observation_scaffold_is_still_header_only() -> None:
    rows = candidate.OBSERVATIONS_PATH.read_text(encoding="utf-8").splitlines()

    assert rows == [",".join(candidate.RECORD_FIELDS)]
    assert shadow.observation_record_count(candidate.OBSERVATIONS_PATH) == 0


# --- production write gate ----------------------------------------------------------------


def test_runner_refuses_to_write_when_not_active(
    tmp_path: Path, candidate_verification_stubbed: None
) -> None:
    root = _repo_with_vintage(tmp_path)
    (root / shadow.ACTIVATION_RELATIVE_PATH).unlink()

    with pytest.raises(ValueError, match="未激活"):
        shadow.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

    assert shadow.observation_record_count(shadow.canonical_observations_path(root)) == 0


def test_production_write_path_appends_once_and_rejects_rerun(
    tmp_path: Path, candidate_verification_stubbed: None
) -> None:
    root = _repo_with_vintage(tmp_path)
    observations = shadow.canonical_observations_path(root)

    record = shadow.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

    assert record["signal_date"] == "2026-09-30"
    assert shadow.decision_record_count(observations) == 1
    rows = shadow.read_observation_rows(observations)
    assert rows[0]["candidate_id"] == "S4C_R1"
    assert rows[0]["vintage_identifier"] == "2026-09-30"
    assert rows[0]["execution_status"] == shadow.PENDING_EXECUTION_STATUS

    with pytest.raises(ValueError, match="append-only"):
        shadow.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

    assert shadow.decision_record_count(observations) == 1


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
    as_of: str,
    match: str,
) -> None:
    """写入门必须在读取任何 vintage 之前拒绝非前瞻时点，且不落盘。"""
    root = _fake_repo(tmp_path)
    write_observations_header(shadow.canonical_observations_path(root), shadow.RECORD_FIELDS)
    observations = shadow.canonical_observations_path(root)
    before = observations.read_bytes()

    with pytest.raises(ValueError, match=match):
        shadow.run_decision(pd.Timestamp(as_of), root=root, decision_seal_time=SEAL)

    assert observations.read_bytes() == before
    assert shadow.observation_record_count(observations) == 0
    assert not (root / shadow.VINTAGE_PARENT_RELATIVE_PATH).exists()


@pytest.mark.parametrize(
    ("seal", "match"),
    [
        ("2026-09-30T06:59:00+00:00", "signal_close"),
        ("2026-09-30T07:00:00+00:00", "download_timestamp"),
        ("2026-09-30T16:00:00+00:00", "signal_date"),
        ("2026-10-09T02:00:00+00:00", "signal_date"),
    ],
)
def test_temporal_seal_rejects_illegal_decision_instants(
    tmp_path: Path, candidate_verification_stubbed: None, seal: str, match: str
) -> None:
    root = _repo_with_vintage(tmp_path, extra_calendar_dates=("2026-10-09",))
    observations = shadow.canonical_observations_path(root)
    before = observations.read_bytes()

    with pytest.raises(ValueError, match=match):
        shadow.run_decision(AS_OF, root=root, decision_seal_time=seal)

    assert observations.read_bytes() == before


def test_download_before_the_signal_close_is_rejected(
    tmp_path: Path, candidate_verification_stubbed: None
) -> None:
    root = _repo_with_vintage(tmp_path, download_timestamp="2026-09-30T06:00:00+00:00")
    observations = shadow.canonical_observations_path(root)
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="signal_close"):
        shadow.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

    assert observations.read_bytes() == before


def test_external_vintage_directory_is_rejected_by_the_write_gate(
    tmp_path: Path, candidate_verification_stubbed: None
) -> None:
    root = _fake_repo(tmp_path)
    write_observations_header(shadow.canonical_observations_path(root), shadow.RECORD_FIELDS)
    external = write_prospective_vintage(tmp_path / "elsewhere/2026-09-30", as_of="2026-09-30")
    observations = shadow.canonical_observations_path(root)
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="vintages"):
        shadow.run_decision(AS_OF, vintage_dir=external, root=root, decision_seal_time=SEAL)

    assert observations.read_bytes() == before


def test_external_vintage_is_rejected_before_any_file_read(
    tmp_path: Path, candidate_verification_stubbed: None
) -> None:
    """不存在的目录也只能得到位置错误，证明不存在对 vintage 文件的读取尝试。"""
    root = _fake_repo(tmp_path)
    write_observations_header(shadow.canonical_observations_path(root), shadow.RECORD_FIELDS)
    missing_external = tmp_path / "elsewhere" / "2026-09-30"

    with pytest.raises(ValueError, match="vintages"):
        shadow.run_decision(AS_OF, vintage_dir=missing_external, root=root, decision_seal_time=SEAL)


def test_external_vintage_rejection_never_touches_vintage_readers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidate_verification_stubbed: None
) -> None:
    root = _fake_repo(tmp_path)
    write_observations_header(shadow.canonical_observations_path(root), shadow.RECORD_FIELDS)
    external = write_prospective_vintage(tmp_path / "elsewhere/2026-09-30", as_of="2026-09-30")

    def tripwire(*args: object, **kwargs: object) -> pd.DataFrame:
        raise AssertionError("位置校验之前不得读取任何 vintage 文件")

    monkeypatch.setattr(shadow, "load_calendar", tripwire)

    with pytest.raises(ValueError, match="vintages"):
        shadow.run_decision(AS_OF, vintage_dir=external, root=root, decision_seal_time=SEAL)


# --- CLI write authorization --------------------------------------------------------------


@pytest.mark.parametrize(
    "option",
    ["--vintage-dir", "--record-path", "--activation-path", "--generated-at", "--seal-time"],
)
def test_production_cli_rejects_path_and_time_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, option: str
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["run_s4c_r1_shadow", "--as-of", "2026-09-30", option, str(tmp_path)]
    )

    with pytest.raises(SystemExit):
        shadow.main()


def test_explicit_as_of_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_s4c_r1_shadow"])

    with pytest.raises(SystemExit):
        shadow.main()


def test_read_only_verification_modes_cannot_write(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["run_s4c_r1_shadow", "--verify-candidate", "--verify-activation"]
    )

    shadow.main()

    output = capsys.readouterr().out
    assert "校验通过" in output
    assert shadow.observation_record_count(candidate.OBSERVATIONS_PATH) == 0


def test_read_only_modes_reject_as_of(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["run_s4c_r1_shadow", "--verify-candidate", "--as-of", "2026-09-30"]
    )

    with pytest.raises(SystemExit):
        shadow.main()
