"""Dual-candidate synthetic readiness drill：证明真实 2026-09-30 cycle 不需要改代码。

整个 drill 只用 synthetic fixture 数据与 `tmp_path`，不接触任何真实 2026-09 市场数据，也不
在仓库内写入任何 observation。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from conftest import (
    MockTushareApi,
    build_candidate_repo,
    injected_runner_clock,
    rqalpha_analyser_fixture,
    rqalpha_code,
    write_execution_artifact,
    write_observations_header,
)

from research.experiments import freeze_prospective_vintage as freeze
from research.experiments import prospective_evidence as pe
from research.experiments import run_s2_r1_shadow as s2
from research.experiments import run_s4c_r1_shadow as s4c
from tacticore.data.tushare import SOURCE

AS_OF = pd.Timestamp("2026-09-30")
SEAL = "2026-09-30T08:00:00+00:00"
DOWNLOAD_TIMESTAMP = "2026-09-30T07:30:00+00:00"
EXECUTION_DATE = "2026-10-09"
EXECUTION_TIMESTAMP = "2026-10-09T07:05:00+00:00"
ARTIFACT_GENERATED_AT = "2026-10-09T07:30:00+00:00"
EXECUTION_SEAL = "2026-10-09T08:00:00+00:00"


@pytest.fixture(autouse=True)
def _frozen_runner_clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """未来 synthetic execution 时点由注入的 runner 时钟复现，不修改系统时间。"""
    monkeypatch.setattr(s2, "_now_utc_iso", lambda: EXECUTION_SEAL)
    monkeypatch.setattr(s4c, "_now_utc_iso", lambda: EXECUTION_SEAL)


@pytest.fixture
def drill_repo(tmp_path: Path) -> Path:
    """生产 snapshot 路径：MockTushare → freeze_vintage（两个候选）→ canonical vintage。"""
    root = tmp_path / "repo"
    build_candidate_repo(root, "S2_R1")
    build_candidate_repo(root, "S4C_R1")
    write_observations_header(s2.canonical_observations_path(root), s2.RECORD_FIELDS)
    write_observations_header(s4c.canonical_observations_path(root), s4c.RECORD_FIELDS)
    api = MockTushareApi()
    s2_vintage = freeze.freeze_vintage(
        api,
        candidate_id="S2_R1",
        as_of=AS_OF,
        root=root,
        downloaded_at=DOWNLOAD_TIMESTAMP,
    )
    s4c_vintage = freeze.freeze_vintage(
        api,
        candidate_id="S4C_R1",
        as_of=AS_OF,
        root=root,
        downloaded_at=DOWNLOAD_TIMESTAMP,
    )
    assert s2_vintage == root / s2.VINTAGE_PARENT_RELATIVE_PATH / "2026-09-30"
    assert s4c_vintage == root / s4c.VINTAGE_PARENT_RELATIVE_PATH / "2026-09-30"
    return root


def _fixture_artifact(root: Path, candidate_id: str, decision: dict[str, str]) -> str:
    """用 decision 的冻结目标走生产 seam 写出一份 synthetic RQAlpha execution artifact。"""
    return write_execution_artifact(
        root,
        candidate_id=candidate_id,
        signal_date=decision["signal_date"],
        desired_targets=json.loads(decision["desired_targets"]),
        execution_timestamp=EXECUTION_TIMESTAMP,
        artifact_generated_at=ARTIFACT_GENERATED_AT,
    )


def _produce_artifact(root: Path, decision: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """native-shaped RQAlpha 输出 → 生产 artifact seam → identity + 落盘 payload。"""
    targets = json.loads(decision["desired_targets"])
    symbol = next(iter(targets))
    analyser, events, replayed = rqalpha_analyser_fixture(
        root,
        execution_date=EXECUTION_DATE,
        realized_weights=targets,
        order_events=((rqalpha_code(root, symbol), "ACTIVE", "fixture native 成交说明"),),
    )
    with injected_runner_clock(ARTIFACT_GENERATED_AT):
        identity = pe.freeze_prospective_execution_artifact(
            analyser,
            events,
            replayed,
            root=root,
            decision=decision,
            framework_version="6.3.0",
            expected_execution_date=EXECUTION_DATE,
        )
    relative = json.loads(identity)["evidence_path"]
    payload = json.loads((root / relative).read_text(encoding="utf-8"))
    return identity, payload


def _symbols(decision: dict[str, str]) -> tuple[str, ...]:
    return tuple(json.loads(decision["desired_targets"]).keys())


def test_dual_candidate_synthetic_full_cycle_requires_no_code_change(drill_repo: Path) -> None:
    root = drill_repo
    s2_observations = s2.canonical_observations_path(root)
    s4c_observations = s4c.canonical_observations_path(root)

    # 1. 生产 snapshot 路径产出的 vintage 必须先通过机器验证：source、universe 身份、文件 hash。
    frozen_universe = pe.load_frozen_universe(root)
    for candidate in (s2, s4c):
        vintage = root / candidate.VINTAGE_PARENT_RELATIVE_PATH / "2026-09-30"
        provenance = json.loads((vintage / "provenance.json").read_text(encoding="utf-8"))
        assert provenance["source"] == SOURCE
        assert provenance["end_date"] == "20260930"
        assert provenance["universe"]["sha256"] == frozen_universe.sha256
        for name, entry in provenance["files"].items():
            assert pe.sha256_file(vintage / name) == entry["sha256"]

    # 2. 两个候选各自从 candidate-specific canonical vintage 生成 decision。
    s2_decision = s2.run_decision(AS_OF, root=root, decision_seal_time=SEAL)
    s4c_decision = s4c.run_decision(AS_OF, root=root, decision_seal_time=SEAL)
    assert s2_decision["signal_date"] == s4c_decision["signal_date"] == "2026-09-30"
    assert s2_decision["candidate_id"] == "S2_R1"
    assert s4c_decision["candidate_id"] == "S4C_R1"
    assert s2_decision["vintage_identifier"] == s4c_decision["vintage_identifier"] == "2026-09-30"
    # 同一外源快照不等于同一 candidate evidence identity：每个 candidate 绑定自己的 manifest。
    assert s2_decision["historical_manifest_hash"] != s4c_decision["historical_manifest_hash"]
    assert s2.decision_record_count(s2_observations) == 1
    assert s4c.decision_record_count(s4c_observations) == 1

    decisions_before_execution = {
        "s2": s2_observations.read_bytes(),
        "s4c": s4c_observations.read_bytes(),
    }

    # 3. 重复 decision 必须被拒绝且不改变 bytes。
    with pytest.raises(ValueError, match="append-only"):
        s2.run_decision(AS_OF, root=root, decision_seal_time=SEAL)
    with pytest.raises(ValueError, match="append-only"):
        s4c.run_decision(AS_OF, root=root, decision_seal_time=SEAL)
    assert s2_observations.read_bytes() == decisions_before_execution["s2"]
    assert s4c_observations.read_bytes() == decisions_before_execution["s4c"]

    # 4. 生产 artifact seam 不得暴露时间或目标位置权威；时间只能来自 runner 时钟。
    for seam in (pe.freeze_prospective_execution_artifact,):
        parameters = set(inspect.signature(seam).parameters)
        assert {
            "artifact_generated_at",
            "execution_timestamp",
            "record_generated_at",
            "artifact_relative_path",
            "execution_date",
        }.isdisjoint(parameters)

    # 5. native-shaped RQAlpha 输出 → 生产 artifact → 时间链真实性检查。
    s2_identity, s2_artifact = _produce_artifact(root, s2_decision)
    s4c_identity, s4c_artifact = _produce_artifact(root, s4c_decision)
    observation = pe.execution_observation_instant(EXECUTION_DATE)
    for payload in (s2_artifact, s4c_artifact):
        assert payload["execution_status"] == pe.RQALPHA_EXECUTED_STATUS
        assert pd.Timestamp(payload["execution_timestamp"]) == observation
        generated_at = pd.Timestamp(payload["artifact_generated_at"])
        assert generated_at.tzinfo is not None
        assert generated_at >= observation

    # 6. 由 artifact identity 构造完整 execution 事件。
    s2_symbols = _symbols(s2_decision)
    s4c_symbols = _symbols(s4c_decision)
    s2_execution = s2.build_execution_record(
        s2_decision,
        execution_evidence=s2_identity,
        expected_symbols=s2_symbols,
        expected_framework_version="6.3.0",
        root=root,
    )
    s4c_execution = s4c.build_execution_record(
        s4c_decision,
        execution_evidence=s4c_identity,
        expected_symbols=s4c_symbols,
        expected_framework_version="6.3.0",
        root=root,
    )
    assert s2_execution["execution_date"] == s4c_execution["execution_date"] == "2026-10-09"
    assert s2_execution["execution_status"] == s4c_execution["execution_status"] == "EXECUTED"

    # 7. 不完整 execution 必须被拒绝，且 decision bytes 不变。
    incomplete = dict(s2_execution)
    incomplete["realized_weights"] = ""
    with pytest.raises(ValueError, match="realized_weights"):
        s2.append_execution_record(incomplete, s2_observations, root=root)
    incomplete_s4c = dict(s4c_execution)
    incomplete_s4c["portfolio_total_absolute_weight_deviation"] = ""
    with pytest.raises(ValueError, match="portfolio_total"):
        s4c.append_execution_record(incomplete_s4c, s4c_observations, root=root)
    assert s2_observations.read_bytes() == decisions_before_execution["s2"]
    assert s4c_observations.read_bytes() == decisions_before_execution["s4c"]

    # 8. 完整 execution 只能追加在对应 decision 之后。
    s2.append_execution_record(s2_execution, s2_observations, root=root)
    s4c.append_execution_record(s4c_execution, s4c_observations, root=root)
    assert s2.observation_record_count(s2_observations) == 2
    assert s4c.observation_record_count(s4c_observations) == 2

    # 9. 先前的 decision bytes 逐字节未变。
    assert s2_observations.read_bytes().startswith(decisions_before_execution["s2"])
    assert s4c_observations.read_bytes().startswith(decisions_before_execution["s4c"])
    assert s2_observations.read_bytes() != decisions_before_execution["s2"]

    # 10. 重复 execution 必须被拒绝。
    execution_bytes = {
        "s2": s2_observations.read_bytes(),
        "s4c": s4c_observations.read_bytes(),
    }
    with pytest.raises(ValueError, match="append-only"):
        s2.append_execution_record(s2_execution, s2_observations, root=root)
    with pytest.raises(ValueError, match="append-only"):
        s4c.append_execution_record(s4c_execution, s4c_observations, root=root)
    assert s2_observations.read_bytes() == execution_bytes["s2"]
    assert s4c_observations.read_bytes() == execution_bytes["s4c"]


def test_readiness_drill_never_touches_the_repository_evidence(drill_repo: Path) -> None:
    """drill 只在 tmp_path 内写入；仓库 canonical observations 保持零记录。"""
    s2.run_decision(AS_OF, root=drill_repo, decision_seal_time=SEAL)
    s4c.run_decision(AS_OF, root=drill_repo, decision_seal_time=SEAL)

    assert s2.observation_record_count(s2.OBSERVATIONS_PATH) == 0
    assert s4c.observation_record_count(s4c.OBSERVATIONS_PATH) == 0
    assert not (s2.ROOT / s2.VINTAGE_PARENT_RELATIVE_PATH).exists()
    assert not (s4c.ROOT / s4c.VINTAGE_PARENT_RELATIVE_PATH).exists()


def test_drill_rejects_execution_without_its_decision(drill_repo: Path, tmp_path: Path) -> None:
    s2_decision = s2.run_decision(AS_OF, root=drill_repo, decision_seal_time=SEAL)
    symbols = _symbols(s2_decision)
    identity = s2.build_rqalpha_evidence_identity(
        evidence_path=_fixture_artifact(drill_repo, "S2_R1", s2_decision),
        root=drill_repo,
        expected_framework_version="6.3.0",
    )
    execution = s2.build_execution_record(
        s2_decision,
        execution_evidence=identity,
        expected_symbols=symbols,
        expected_framework_version="6.3.0",
        root=drill_repo,
    )
    empty = write_observations_header(tmp_path / "empty.csv", s2.RECORD_FIELDS)
    before = empty.read_bytes()

    with pytest.raises(ValueError, match="唯一对应的 decision"):
        s2.append_execution_record(execution, empty, root=drill_repo)

    assert empty.read_bytes() == before


def test_drill_is_deterministic_across_runs(drill_repo: Path, tmp_path: Path) -> None:
    """同一 fixture 下两次独立构造产生完全相同的 decision identity（无 wall-clock 依赖）。"""
    first = s2.run_decision(AS_OF, root=drill_repo, decision_seal_time=SEAL)
    second_repo = tmp_path / "second"
    build_candidate_repo(second_repo, "S2_R1")
    write_observations_header(s2.canonical_observations_path(second_repo), s2.RECORD_FIELDS)
    freeze.freeze_vintage(
        MockTushareApi(),
        candidate_id="S2_R1",
        as_of=AS_OF,
        root=second_repo,
        downloaded_at=DOWNLOAD_TIMESTAMP,
    )
    second = s2.run_decision(AS_OF, root=second_repo, decision_seal_time=SEAL)

    assert first["desired_targets"] == second["desired_targets"]
    assert first["prospective_data_hash"] == second["prospective_data_hash"]
    assert first["trend_states"] == second["trend_states"]


def test_drill_fixture_types_are_candidate_specific(drill_repo: Path, tmp_path: Path) -> None:
    """S2 与 S4C 的 observation schema 必须保持不同，不能共用一份表。"""
    assert s2.RECORD_FIELDS != s4c.RECORD_FIELDS
    assert set(s2.EXECUTION_ONLY_FIELDS).isdisjoint({"material_asset_differences"})
    assert "material_asset_differences" in s4c.EXECUTION_ONLY_FIELDS
    assert "target_deviation" in s2.EXECUTION_ONLY_FIELDS
    assert "target_deviation" not in s4c.EXECUTION_ONLY_FIELDS


def test_drill_uses_no_network_or_credentials(
    monkeypatch: pytest.MonkeyPatch, drill_repo: Path
) -> None:
    """drill 不依赖 TUSHARE_TOKEN，也不调用任何下载入口。"""
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    record: dict[str, Any] = s2.run_decision(AS_OF, root=drill_repo, decision_seal_time=SEAL)

    assert record["record_type"] == "decision"
