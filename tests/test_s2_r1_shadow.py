"""S2 R1 前瞻影子 runner 的 provenance、temporal seal、写入授权与 append-only 契约测试。

全部使用 fixtures / `tmp_path` / synthetic data；不修改系统时间，不运行真实 future observation。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from conftest import build_candidate_repo, write_observations_header, write_prospective_vintage

from research.experiments import run_s2_r1_shadow as shadow
from research.experiments.prospective_evidence import sha256_file

AS_OF = pd.Timestamp("2026-09-30")
SEAL = "2026-09-30T08:00:00+00:00"


def _decision(tmp_path: Path, *, seal: str = SEAL) -> dict[str, str]:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "vintages/2026-09-30", as_of="2026-09-30")
    inputs = shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)
    record = shadow.build_decision_record(
        inputs.prices,
        manifest,
        as_of=AS_OF,
        vintage_identifier=vintage.name,
        prospective_data_hash=inputs.vintage_hash,
        manifest_hash=shadow.manifest_hash(),
        decision_seal_time=seal,
    )
    assert record is not None
    return record


def _repo_with_vintage(tmp_path: Path, **vintage_kwargs: Any) -> Path:
    root = build_candidate_repo(tmp_path / "repo", "S2_R1")
    write_observations_header(shadow.canonical_observations_path(root), shadow.RECORD_FIELDS)
    destination = root / shadow.VINTAGE_PARENT_RELATIVE_PATH / "2026-09-30"
    write_prospective_vintage(destination, as_of="2026-09-30", **vintage_kwargs)
    return root


def _mutate_provenance(vintage: Path, mutate: Any) -> None:
    path = vintage / "provenance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def _decision_symbols(decision: dict[str, str]) -> tuple[str, ...]:
    return tuple(json.loads(decision["desired_targets"]).keys())


# --- candidate identity -------------------------------------------------------------------


def test_candidate_manifest_matches_frozen_repository_inputs() -> None:
    manifest = shadow.load_manifest()

    shadow.verify_candidate(manifest, verify_framework=False)

    assert manifest["candidate_id"] == "S2_R1"
    assert manifest["strategy_semantics"]["trend_window"] == 200
    assert pd.Timestamp(manifest["prospective_start"]) > pd.Timestamp(manifest["historical_cutoff"])
    assert shadow.decision_record_count() == 0


def test_frozen_repository_text_hash_is_newline_invariant_but_raw_hash_is_not(
    tmp_path: Path,
) -> None:
    lf_path = tmp_path / "frozen-lf.txt"
    crlf_path = tmp_path / "frozen-crlf.txt"
    changed_path = tmp_path / "frozen-changed.txt"
    lf_path.write_bytes(b"line one\nline two\n")
    crlf_path.write_bytes(b"line one\r\nline two\r\n")
    changed_path.write_bytes(b"line one\nchanged line\n")

    assert shadow.sha256_frozen_repository_text(lf_path) == (
        shadow.sha256_frozen_repository_text(crlf_path)
    )
    assert shadow.sha256_frozen_repository_text(lf_path) != (
        shadow.sha256_frozen_repository_text(changed_path)
    )
    assert shadow.sha256_file(lf_path) != shadow.sha256_file(crlf_path)


def test_strict_candidate_verification_rejects_framework_version_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = shadow.load_manifest()

    def frozen_version_except_numpy(package: str) -> str:
        if package == "numpy":
            return "0.0.0"
        return manifest["framework_versions"][package]

    monkeypatch.setattr(shadow, "version", frozen_version_except_numpy)

    with pytest.raises(ValueError, match="当前框架版本不一致: numpy"):
        shadow.verify_candidate(manifest)

    shadow.verify_candidate(manifest, verify_framework=False)


# --- vintage provenance authenticity ------------------------------------------------------


def test_valid_vintage_provenance_binds_files_hashes_and_as_of(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")

    inputs = shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)

    assert inputs.provenance.price_as_of == AS_OF
    assert inputs.provenance.calendar_as_of == AS_OF
    assert inputs.provenance.download_timestamp == pd.Timestamp("2026-09-30T07:30:00+00:00")
    assert inputs.provenance.declared_hashes["etf_adjusted_close.csv"] == sha256_file(
        vintage / "etf_adjusted_close.csv"
    )
    assert inputs.provenance.declared_hashes["trading_calendar.csv"] == sha256_file(
        vintage / "trading_calendar.csv"
    )
    assert inputs.prices.index.max() == AS_OF


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"source": "Other Provider"}, "source"),
        ({"end_date": "20260929"}, "end_date"),
        ({"adjustment_type": "前复权"}, "adjustment"),
        ({"download_timestamp": "2026-09-30T07:30:00"}, "必须带时区"),
    ],
)
def test_vintage_provenance_header_drift_is_rejected(
    tmp_path: Path, overrides: dict[str, Any], match: str
) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(
        tmp_path / "2026-09-30", as_of="2026-09-30", provenance_overrides=overrides
    )

    with pytest.raises(ValueError, match=match):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_request_end_date_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    _mutate_provenance(
        vintage,
        lambda payload: payload["symbols"][0]["request_parameters"]["fund_daily"].update(
            {"end_date": "20260929"}
        ),
    )

    with pytest.raises(ValueError, match="request end_date"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_symbol_set_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    _mutate_provenance(vintage, lambda payload: payload["symbols"].pop())

    with pytest.raises(ValueError, match="universe"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_symbol_data_timestamp_after_as_of_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    _mutate_provenance(
        vintage,
        lambda payload: payload["symbols"][0].update({"data_timestamp": "2026-10-01"}),
    )

    with pytest.raises(ValueError, match="data_timestamp 晚于 --as-of"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_price_file_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    _mutate_provenance(
        vintage,
        lambda payload: payload["files"]["etf_adjusted_close.csv"].update({"sha256": "0" * 64}),
    )

    with pytest.raises(ValueError, match="etf_adjusted_close.csv SHA-256"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_calendar_file_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    _mutate_provenance(
        vintage,
        lambda payload: payload["files"]["trading_calendar.csv"].update({"sha256": "0" * 64}),
    )

    with pytest.raises(ValueError, match="trading_calendar.csv SHA-256"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_row_count_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    _mutate_provenance(
        vintage,
        lambda payload: payload["files"]["etf_adjusted_close.csv"].update({"rows": 1}),
    )

    with pytest.raises(ValueError, match="行数与实际文件不一致"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


# --- historical / prospective boundary ----------------------------------------------------


def test_shadow_decision_uses_only_as_of_vintage_data(tmp_path: Path) -> None:
    record = _decision(tmp_path)

    assert record["signal_date"] == "2026-09-30"
    assert record["data_as_of"] == "2026-09-30"
    assert record["vintage_identifier"] == "2026-09-30"
    assert record["candidate_id"] == "S2_R1"
    assert record["protocol_version"] == "V1"
    assert record["execution_date"] == ""
    assert record["execution_status"] == shadow.PENDING_EXECUTION_STATUS
    for field in shadow.EXECUTION_ONLY_FIELDS:
        assert record[field] == ""


def test_vintage_cannot_overwrite_different_historical_data(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(
        tmp_path / "2026-09-30", as_of="2026-09-30", overlap_multiplier=1.01
    )

    with pytest.raises(ValueError, match="重叠但内容不同"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_vintage_after_as_of_is_rejected_instead_of_leaking(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(
        tmp_path / "2026-09-30", as_of="2026-09-30", beyond_as_of=True
    )

    with pytest.raises(ValueError, match="as-of"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_mid_month_vintage_cannot_fabricate_a_month_end_decision(tmp_path: Path) -> None:
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv").loc[
        : pd.Timestamp("2026-09-29")
    ]

    with pytest.raises(ValueError, match="未覆盖完整 signal 月"):
        shadow.validate_month_end_review(calendar, pd.Timestamp("2026-09-29"))


def test_first_eligible_signal_is_derived_from_frozen_monthly_semantics(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv")

    assert shadow.derive_first_eligible_signal(manifest, calendar) == AS_OF


def test_decision_row_tolerates_unavailable_risk_assets(tmp_path: Path) -> None:
    """信号日缺失价格的资产必须标记 UNAVAILABLE，且不稀释仍必须为一的目标权重。"""
    manifest = shadow.load_manifest()
    vintage = write_prospective_vintage(tmp_path / "2026-09-30", as_of="2026-09-30")
    inputs = shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)
    prices = inputs.prices.copy()
    prices.loc[AS_OF, "510300.SS"] = float("nan")

    record = shadow.build_decision_record(
        prices,
        manifest,
        as_of=AS_OF,
        vintage_identifier="2026-09-30",
        prospective_data_hash=inputs.vintage_hash,
        manifest_hash=shadow.manifest_hash(),
        decision_seal_time=SEAL,
    )

    assert record is not None
    assert json.loads(record["trend_states"])["510300.SS"] == "UNAVAILABLE"
    assert "510300.SS" not in json.loads(record["eligible_assets"])
    assert sum(json.loads(record["desired_targets"]).values()) == pytest.approx(1.0)


# --- write gate: canonical paths, temporal seal and append-only ----------------------------


def test_production_write_path_appends_once_and_rejects_rerun(tmp_path: Path) -> None:
    root = _repo_with_vintage(tmp_path)
    observations = shadow.canonical_observations_path(root)

    record = shadow.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

    assert record["signal_date"] == "2026-09-30"
    assert shadow.decision_record_count(observations) == 1
    rows = shadow.read_event_rows(observations, shadow.RECORD_FIELDS)
    assert rows[0]["vintage_identifier"] == "2026-09-30"

    with pytest.raises(ValueError, match="append-only"):
        shadow.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

    assert shadow.decision_record_count(observations) == 1


def test_external_vintage_directory_is_rejected_before_any_read(tmp_path: Path) -> None:
    root = _repo_with_vintage(tmp_path)
    observations = shadow.canonical_observations_path(root)
    before = observations.read_bytes()
    external = write_prospective_vintage(tmp_path / "elsewhere/2026-09-30", as_of="2026-09-30")

    with pytest.raises(ValueError, match="vintages"):
        shadow.run_decision(AS_OF, vintage_dir=external, root=root, decision_seal_time=SEAL)

    assert observations.read_bytes() == before


def test_missing_canonical_vintage_is_not_silently_created(tmp_path: Path) -> None:
    root = build_candidate_repo(tmp_path / "repo", "S2_R1")
    write_observations_header(shadow.canonical_observations_path(root), shadow.RECORD_FIELDS)

    with pytest.raises(FileNotFoundError):
        shadow.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

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
    tmp_path: Path, seal: str, match: str
) -> None:
    root = _repo_with_vintage(tmp_path, extra_calendar_dates=("2026-10-09",))
    observations = shadow.canonical_observations_path(root)
    before = observations.read_bytes()

    with pytest.raises(ValueError, match=match):
        shadow.run_decision(AS_OF, root=root, decision_seal_time=seal)

    assert observations.read_bytes() == before


def test_download_before_the_signal_close_is_rejected(tmp_path: Path) -> None:
    root = _repo_with_vintage(tmp_path, download_timestamp="2026-09-30T06:00:00+00:00")
    observations = shadow.canonical_observations_path(root)
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="signal_close"):
        shadow.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

    assert observations.read_bytes() == before


# --- append-only ---------------------------------------------------------------------------


def test_observation_append_is_duplicate_safe(tmp_path: Path) -> None:
    observations = write_observations_header(tmp_path / "observations.csv", shadow.RECORD_FIELDS)
    record = _decision(tmp_path)

    shadow.append_decision_record(record, observations)

    assert shadow.decision_record_count(observations) == 1

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_decision_record(record, observations)


def test_rejected_decision_write_leaves_the_file_bytes_unchanged(tmp_path: Path) -> None:
    observations = write_observations_header(tmp_path / "observations.csv", shadow.RECORD_FIELDS)
    record = _decision(tmp_path)
    record["execution_date"] = "2026-10-09"
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="不得包含执行结果字段"):
        shadow.append_decision_record(record, observations)

    assert observations.read_bytes() == before


def test_observation_schema_drift_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "observations.csv"
    path.write_text("record_type,candidate_id\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="schema 与冻结协议不一致"):
        shadow.read_event_rows(path, shadow.RECORD_FIELDS)


def test_frozen_observation_scaffold_is_still_header_only() -> None:
    rows = shadow.OBSERVATIONS_PATH.read_text(encoding="utf-8").splitlines()

    assert rows == [",".join(shadow.RECORD_FIELDS)]
    assert shadow.observation_record_count() == 0


# --- execution record contract -------------------------------------------------------------


def _execution_fixture(tmp_path: Path) -> tuple[Path, dict[str, str], dict[str, str]]:
    root = _repo_with_vintage(tmp_path)
    observations = shadow.canonical_observations_path(root)
    decision = _decision(tmp_path)
    shadow.append_decision_record(decision, observations)
    relative_evidence = "research/results/s2_r1_fixture_rqalpha_evidence.json"
    evidence = root / relative_evidence
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps({"fixture": "rqalpha native output"}), encoding="utf-8")
    symbols = _decision_symbols(decision)
    identity = shadow.build_rqalpha_evidence_identity(
        evidence_path=relative_evidence, root=root, expected_framework_version="6.3.0"
    )
    complete = shadow.build_execution_record(
        decision,
        execution_date="2026-10-09",
        execution_status="EXECUTED",
        realized_weights=dict.fromkeys(symbols, 0.0),
        cash_weight=1.0,
        target_deviation=0.0,
        portfolio_value=1_000_000.0,
        drawdown=0.0,
        turnover=0.0,
        execution_evidence=identity,
        expected_symbols=symbols,
        expected_framework_version="6.3.0",
        root=root,
    )
    return root, complete, observations


def test_complete_execution_record_is_accepted_and_keeps_decision_bytes(tmp_path: Path) -> None:
    root, complete, observations = _execution_fixture(tmp_path)
    before = observations.read_text(encoding="utf-8").splitlines()

    shadow.append_execution_record(complete, observations, root=root)

    after = observations.read_text(encoding="utf-8").splitlines()
    assert after[: len(before)] == before
    assert len(after) == len(before) + 1
    assert shadow.observation_record_count(observations) == 2


def test_execution_without_a_decision_is_rejected(tmp_path: Path) -> None:
    root, complete, _observations = _execution_fixture(tmp_path)
    empty = write_observations_header(tmp_path / "empty.csv", shadow.RECORD_FIELDS)
    before = empty.read_bytes()

    with pytest.raises(ValueError, match="唯一对应的 decision"):
        shadow.append_execution_record(complete, empty, root=root)

    assert empty.read_bytes() == before


def test_execution_not_after_signal_date_is_rejected(tmp_path: Path) -> None:
    root, complete, observations = _execution_fixture(tmp_path)
    complete["execution_date"] = "2026-09-30"

    with pytest.raises(ValueError, match="决策必须先于执行"):
        shadow.append_execution_record(complete, observations, root=root)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("realized_weights", "", "realized_weights"),
        ("cash_weight", "", "cash_weight"),
        ("target_deviation", "", "target_deviation"),
        ("portfolio_value", "0", "portfolio_value"),
        ("drawdown", "0.1", "drawdown"),
        ("turnover", "-1", "turnover"),
        ("execution_status", "PENDING", "execution_status"),
        ("execution_evidence", "", "execution_evidence"),
    ],
)
def test_incomplete_execution_record_is_rejected(
    tmp_path: Path, field: str, value: str, match: str
) -> None:
    root, complete, observations = _execution_fixture(tmp_path)
    complete[field] = value
    before = observations.read_bytes()

    with pytest.raises(ValueError, match=match):
        shadow.append_execution_record(complete, observations, root=root)

    assert observations.read_bytes() == before


def test_rqalpha_evidence_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    root, complete, observations = _execution_fixture(tmp_path)
    payload = json.loads(complete["execution_evidence"])
    payload["evidence_sha256"] = "0" * 64
    complete["execution_evidence"] = json.dumps(payload)

    with pytest.raises(ValueError, match="SHA-256"):
        shadow.append_execution_record(complete, observations, root=root)


def test_rqalpha_evidence_missing_file_is_rejected(tmp_path: Path) -> None:
    root, complete, observations = _execution_fixture(tmp_path)
    (root / "research/results/s2_r1_fixture_rqalpha_evidence.json").unlink()

    with pytest.raises(ValueError, match="不存在"):
        shadow.append_execution_record(complete, observations, root=root)


def test_duplicate_execution_is_rejected(tmp_path: Path) -> None:
    root, complete, observations = _execution_fixture(tmp_path)
    shadow.append_execution_record(complete, observations, root=root)
    before = observations.read_bytes()

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_execution_record(complete, observations, root=root)

    assert observations.read_bytes() == before


# --- CLI write authorization ---------------------------------------------------------------


@pytest.mark.parametrize(
    "option",
    ["--vintage-dir", "--record-path", "--generated-at", "--decision-time", "--seal-time"],
)
def test_production_cli_rejects_path_and_time_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, option: str
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["run_s2_r1_shadow", "--as-of", "2026-09-30", option, str(tmp_path)]
    )

    with pytest.raises(SystemExit):
        shadow.main()


def test_verify_candidate_and_as_of_cannot_be_combined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["run_s2_r1_shadow", "--verify-candidate", "--as-of", "x"])

    with pytest.raises(SystemExit):
        shadow.main()


def test_verify_candidate_is_read_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["run_s2_r1_shadow", "--verify-candidate"])

    shadow.main()

    output = capsys.readouterr().out
    assert "校验通过" in output
    assert shadow.observation_record_count() == 0


def test_verify_no_observations_is_stage_specific(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["run_s2_r1_shadow", "--verify-candidate", "--verify-no-observations"]
    )

    shadow.main()

    assert "表头" in capsys.readouterr().out


def test_verify_no_observations_rejects_non_empty_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """stage-specific 检查在已有合法 observation 时必须失败，而不是被静默跳过。"""
    observations = write_observations_header(tmp_path / "observations.csv", shadow.RECORD_FIELDS)
    shadow.append_decision_record(_decision(tmp_path), observations)
    monkeypatch.setattr(shadow, "OBSERVATIONS_PATH", observations)
    monkeypatch.setattr(
        sys, "argv", ["run_s2_r1_shadow", "--verify-candidate", "--verify-no-observations"]
    )

    with pytest.raises(ValueError, match="必须仍为 0 行"):
        shadow.main()
