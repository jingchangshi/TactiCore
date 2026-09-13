"""S4C R1 候选冻结身份、前瞻边界与 append-only scaffold 的契约测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from research.experiments import run_s2_r1_shadow as s2_shadow
from research.experiments import verify_s4c_r1_candidate as candidate

ROOT = Path(__file__).resolve().parents[1]


def test_candidate_manifest_matches_frozen_repository_inputs() -> None:
    manifest = candidate.load_manifest()

    candidate.verify_candidate(manifest, verify_framework=False)

    assert manifest["candidate_id"] == "S4C_R1"
    assert manifest["candidate_version"] == "R1"
    assert manifest["prospective_activation"] == "NOT_ACTIVE"
    assert candidate.observation_row_count() == 0


def test_frozen_target_identity_is_exact() -> None:
    manifest = candidate.load_manifest()

    digest = candidate.verify_frozen_targets(manifest)

    assert digest == candidate.FROZEN_TARGET_SHA256
    schedule = candidate.load_committed_schedule()
    assert len(schedule) == candidate.FROZEN_TARGET_ROWS == 161
    assert schedule.index[0] == pd.Timestamp("2013-04-01")
    assert schedule.index[-1] == pd.Timestamp("2026-08-03")


def test_first_prospective_signal_is_after_freeze_and_is_a_month_end() -> None:
    manifest = candidate.load_manifest()

    candidate.verify_prospective_boundary(manifest)

    freeze_moment = pd.Timestamp(manifest["freeze_timestamp"]).tz_convert("UTC").tz_localize(None)
    first_signal = pd.Timestamp(manifest["first_eligible_prospective_signal"])
    assert first_signal > freeze_moment.normalize()
    assert first_signal > pd.Timestamp(manifest["historical_cutoff"])
    assert first_signal == first_signal + pd.offsets.MonthEnd(0)


def test_backdated_prospective_signal_is_rejected() -> None:
    manifest = candidate.load_manifest()
    manifest["first_eligible_prospective_signal"] = "2026-08-31"

    with pytest.raises(ValueError, match="晚于 historical_cutoff"):
        candidate.verify_prospective_boundary(manifest)


def test_prospective_signal_on_the_freeze_date_is_still_rejected() -> None:
    manifest = candidate.load_manifest()
    manifest["freeze_timestamp"] = "2026-09-30T12:00:00Z"

    with pytest.raises(ValueError, match="严格晚于候选冻结日"):
        candidate.verify_prospective_boundary(manifest)


def test_first_prospective_signal_must_be_a_month_end() -> None:
    manifest = candidate.load_manifest()
    manifest["first_eligible_prospective_signal"] = "2026-09-29"

    with pytest.raises(ValueError, match="自然月末"):
        candidate.verify_prospective_boundary(manifest)


def test_prospective_activation_is_not_authorized_by_this_goal() -> None:
    manifest = candidate.load_manifest()
    manifest["prospective_activation"] = "ACTIVE"

    with pytest.raises(ValueError, match="不授权激活"):
        candidate.verify_candidate(manifest, verify_framework=False)


def test_frozen_identity_hash_mismatch_is_rejected() -> None:
    manifest = candidate.load_manifest()
    manifest["frozen_identity_artifacts"]["config/strategy.toml"] = "0" * 64

    with pytest.raises(ValueError, match="冻结身份 hash 不一致"):
        candidate.verify_candidate(manifest, verify_framework=False)


def test_tampered_target_artifact_is_rejected_by_hash(tmp_path: Path) -> None:
    path = tmp_path / "frozen.csv"
    path.write_text("execution_date,510300.SS\n2013-04-01,1\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="SHA-256"):
        candidate.verify_frozen_targets(candidate.load_manifest(), target_path=path)


def test_strategy_semantics_reject_a_submission_policy_rewrite() -> None:
    manifest = candidate.load_manifest()
    manifest["strategy_semantics"]["target_submission_policy"] = "SIGNAL_CHANGE_ONLY"

    with pytest.raises(ValueError, match="目标提交政策被改写"):
        candidate.verify_strategy_semantics(manifest)


def test_s4c_and_s2_are_frozen_with_different_submission_policies() -> None:
    s4c = candidate.load_manifest()
    s2 = s2_shadow.load_manifest()

    assert s4c["strategy_semantics"]["target_submission_policy"] == "MONTHLY_TARGET_SUBMISSION"
    assert s2["strategy_semantics"]["execution_policy"] == "SIGNAL_CHANGE_ONLY"
    assert s4c["strategy_semantics"]["returns_window"] == 60
    assert s2["strategy_semantics"]["trend_window"] == 200


def test_observation_schema_separates_asset_and_portfolio_materiality() -> None:
    assert "material_asset_differences" in candidate.RECORD_FIELDS
    assert "material_portfolio_tracking_date" in candidate.RECORD_FIELDS
    assert "portfolio_total_absolute_weight_deviation" in candidate.RECORD_FIELDS
    assert candidate.RECORD_FIELDS.index(
        "material_asset_differences"
    ) != candidate.RECORD_FIELDS.index("material_portfolio_tracking_date")


def test_observation_scaffold_is_header_only() -> None:
    rows = candidate.OBSERVATIONS_PATH.read_text(encoding="utf-8").splitlines()

    assert rows == [",".join(candidate.RECORD_FIELDS)]
    assert candidate.observation_row_count() == 0


def test_observation_schema_drift_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "observations.csv"
    path.write_text("record_type,candidate_id\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="schema 与冻结协议不一致"):
        candidate.observation_row_count(path)


def test_verifier_refuses_to_emit_prospective_records(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["verify", "--verify-candidate"])

    candidate.main()

    output = capsys.readouterr().out
    assert "校验通过" in output
    assert "NOT_ACTIVE" in output
    assert candidate.observation_row_count() == 0


def test_framework_versions_match_the_frozen_manifest() -> None:
    manifest = candidate.load_manifest()

    candidate.verify_framework_versions(manifest)
