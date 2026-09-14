"""RQAlpha 原生输出 → authoritative artifact 生产链的契约测试（synthetic，不运行 RQAlpha）。"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from conftest import (
    build_candidate_repo,
    frozen_universe,
    injected_runner_clock,
    rqalpha_analyser_fixture,
    rqalpha_code,
    write_execution_artifact,
)

from research.experiments import prospective_evidence as pe
from research.experiments import run_s2_r1_shadow as s2

SIGNAL_DATE = "2026-09-30"
EXECUTION_DATE = "2026-10-09"
EXECUTION_TIMESTAMP = "2026-10-09T07:05:00+00:00"
ARTIFACT_GENERATED_AT = "2026-10-09T07:30:00+00:00"
ARTIFACT_RELATIVE_PATH = "research/shadow/s2_r1/execution_artifacts/2026-09-30_2026-10-09.json"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return build_candidate_repo(tmp_path / "repo", "S2_R1")


def _targets(root: Path) -> dict[str, float]:
    universe = pd.read_csv(root / "config/universe.csv")
    return {
        str(symbol): (1.0 if index == 0 else 0.0) for index, symbol in enumerate(universe["symbol"])
    }


def _produce_from_analyser(
    root: Path,
    *,
    targets: dict[str, float],
    analyser: dict[str, Any],
    events: pd.DataFrame,
    replayed: list[pd.Timestamp],
) -> dict[str, Any]:
    with injected_runner_clock(ARTIFACT_GENERATED_AT):
        return pe.build_rqalpha_execution_artifact_from_analyser(
            analyser,
            events,
            replayed,
            root=root,
            candidate_id="S2_R1",
            signal_date=SIGNAL_DATE,
            framework_version="6.3.0",
            intended_targets=targets,
            expected_execution_date=EXECUTION_DATE,
        )


def test_native_positions_and_cash_produce_the_derived_execution_facts(repo: Path) -> None:
    targets = _targets(repo)
    symbol = next(iter(targets))
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo,
        execution_date=EXECUTION_DATE,
        realized_weights={symbol: 0.75},
        cash_weight=0.25,
        turnover=0.4,
        max_drawdown=-0.05,
        total_value=2_000_000.0,
    )

    payload = _produce_from_analyser(
        repo, targets=targets, analyser=analyser, events=events, replayed=replayed
    )

    assert payload["realized_weights"][symbol] == pytest.approx(0.75)
    assert payload["cash_weight"] == pytest.approx(0.25)
    assert payload["turnover"] == pytest.approx(0.4)
    assert payload["portfolio"] == {"portfolio_value": 2_000_000.0, "drawdown": -0.05}
    assert payload["schema"] == pe.RQALPHA_ARTIFACT_SCHEMA
    assert payload["execution_status"] == pe.RQALPHA_EXECUTED_STATUS
    assert payload["native"]["execution_status"] == pe.RQALPHA_EXECUTED_STATUS


def test_missing_native_position_becomes_zero_weight(repo: Path) -> None:
    targets = _targets(repo)
    held, absent = list(targets)[0], list(targets)[1]
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo, execution_date=EXECUTION_DATE, realized_weights={held: 1.0}
    )

    payload = _produce_from_analyser(
        repo, targets=targets, analyser=analyser, events=events, replayed=replayed
    )

    assert payload["realized_weights"][held] == pytest.approx(1.0)
    assert payload["realized_weights"][absent] == 0.0
    assert sum(payload["realized_weights"].values()) == pytest.approx(1.0)


def test_production_seam_exposes_no_execution_metrics() -> None:
    """调用方不能通过生产 adapter 参数覆盖 realized/cash/turnover/status/native 说明。"""
    parameters = set(inspect.signature(pe.freeze_prospective_execution_artifact).parameters)

    assert {"analyser", "order_events"} <= parameters
    assert {
        "realized_weights",
        "cash_weight",
        "turnover",
        "execution_status",
        "portfolio",
        "native_evidence",
        "native",
    }.isdisjoint(parameters)


def test_production_seams_expose_no_time_or_destination_authority() -> None:
    """生产 seam 不接受 artifact_generated_at / execution timestamp / 任意目标位置。"""
    forbidden = {
        "artifact_generated_at",
        "execution_timestamp",
        "record_generated_at",
        "artifact_relative_path",
        "execution_date",
    }
    assert forbidden.isdisjoint(
        set(inspect.signature(pe.freeze_prospective_execution_artifact).parameters)
    )
    assert forbidden.isdisjoint(
        set(inspect.signature(pe.build_rqalpha_execution_artifact_from_analyser).parameters)
    )
    # 观测日只能作为断言传入，不能作为时间权威。
    assert (
        "expected_execution_date"
        in inspect.signature(pe.freeze_prospective_execution_artifact).parameters
    )


def test_canonical_artifact_path_is_derived_from_candidate_and_dates(repo: Path) -> None:
    relative = pe.canonical_execution_artifact_relative_path(
        root=repo,
        candidate_id="S2_R1",
        signal_date=SIGNAL_DATE,
        execution_date=EXECUTION_DATE,
    )

    assert relative == ARTIFACT_RELATIVE_PATH
    with pytest.raises(ValueError, match="candidate_id"):
        pe.canonical_execution_artifact_relative_path(
            root=repo,
            candidate_id="../../etc",
            signal_date=SIGNAL_DATE,
            execution_date=EXECUTION_DATE,
        )
    with pytest.raises(ValueError, match="manifest"):
        pe.canonical_execution_artifact_relative_path(
            root=repo,
            candidate_id="UNKNOWN_R9",
            signal_date=SIGNAL_DATE,
            execution_date=EXECUTION_DATE,
        )


def test_producer_rejects_native_facts_that_do_not_add_up(repo: Path) -> None:
    targets = _targets(repo)
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo,
        execution_date=EXECUTION_DATE,
        realized_weights={list(targets)[0]: 0.5},
        cash_weight=0.1,
    )

    with pytest.raises(ValueError, match="合计必须等于"):
        _produce_from_analyser(
            repo, targets=targets, analyser=analyser, events=events, replayed=replayed
        )


def test_producer_rejects_universe_foreign_native_symbols(repo: Path) -> None:
    targets = _targets(repo)
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo, execution_date=EXECUTION_DATE, realized_weights={list(targets)[0]: 1.0}
    )
    analyser["stock_positions"] = analyser["stock_positions"].assign(order_book_id="999999.XSHG")

    with pytest.raises(ValueError, match="rqalpha_symbol"):
        _produce_from_analyser(
            repo, targets=targets, analyser=analyser, events=events, replayed=replayed
        )


def test_portfolio_observation_without_a_replay_is_rejected(repo: Path) -> None:
    """portfolio 里恰好有该日，但 replay 没有在该日发生：仍必须拒绝。"""
    targets = _targets(repo)
    analyser, events, _replayed = rqalpha_analyser_fixture(
        repo,
        execution_date=EXECUTION_DATE,
        realized_weights={list(targets)[0]: 1.0},
        replayed_dates=("2026-10-08",),
    )

    with pytest.raises(ValueError, match="未在 2026-10-09 观测"):
        _produce_from_analyser(
            repo, targets=targets, analyser=analyser, events=events, replayed=[_replayed[0]]
        )


def test_replayed_observation_derives_executed_status(repo: Path) -> None:
    targets = _targets(repo)
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo,
        execution_date=EXECUTION_DATE,
        realized_weights={list(targets)[0]: 1.0},
        replayed_dates=(EXECUTION_DATE,),
    )

    payload = _produce_from_analyser(
        repo, targets=targets, analyser=analyser, events=events, replayed=replayed
    )

    assert payload["execution_status"] == pe.RQALPHA_EXECUTED_STATUS


def test_order_events_are_filtered_by_the_native_date_column(repo: Path) -> None:
    """同标的在两个日期都有 native event 时，只允许 execution 日的说明进入 artifact。"""
    targets = _targets(repo)
    code = rqalpha_code(repo, list(targets)[0])
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo,
        execution_date=EXECUTION_DATE,
        realized_weights={list(targets)[0]: 1.0},
        order_events=((code, "ACTIVE", "execution 日说明"),),
    )
    stale = pd.DataFrame(
        {
            "event": ["ORDER_CREATION_REJECT"],
            "date": [pd.Timestamp("2026-10-08")],
            "rqalpha_symbol": [code],
            "status": ["REJECTED"],
            "message": ["上一日说明"],
        }
    )
    events = pd.concat([stale, events], ignore_index=True)

    payload = _produce_from_analyser(
        repo, targets=targets, analyser=analyser, events=events, replayed=replayed
    )

    assert payload["native_evidence"] == {list(targets)[0]: "execution 日说明"}
    assert [event["message"] for event in payload["native"]["order_events"]] == ["execution 日说明"]


def test_all_cash_execution_with_empty_positions_is_accepted(repo: Path) -> None:
    """持仓为空的合法观测：全部现金、资产权重为零。"""
    targets = _targets(repo)
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo,
        execution_date=EXECUTION_DATE,
        realized_weights={},
        cash_weight=1.0,
        positions_empty=True,
    )

    payload = _produce_from_analyser(
        repo, targets=targets, analyser=analyser, events=events, replayed=replayed
    )

    assert payload["cash_weight"] == pytest.approx(1.0)
    assert set(payload["realized_weights"].values()) == {0.0}


def test_production_seam_writes_the_artifact_and_returns_an_identity(repo: Path) -> None:
    targets = _targets(repo)
    decision = {
        "candidate_id": "S2_R1",
        "signal_date": SIGNAL_DATE,
        "desired_targets": json.dumps(targets, ensure_ascii=False, sort_keys=True),
    }
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo, execution_date=EXECUTION_DATE, realized_weights={list(targets)[0]: 1.0}
    )

    with injected_runner_clock(ARTIFACT_GENERATED_AT):
        identity = pe.freeze_prospective_execution_artifact(
            analyser,
            events,
            replayed,
            root=repo,
            decision=decision,
            framework_version="6.3.0",
            expected_execution_date=EXECUTION_DATE,
        )

    payload = pe.verify_rqalpha_evidence_identity(
        identity, root=repo, expected_framework_version="6.3.0"
    )
    assert payload["evidence_path"] == ARTIFACT_RELATIVE_PATH
    written = json.loads((repo / ARTIFACT_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert written["schema"] == pe.RQALPHA_ARTIFACT_SCHEMA
    assert written["intended_targets"] == targets
    generated_at = pd.Timestamp(written["artifact_generated_at"])
    execution_timestamp = pd.Timestamp(written["execution_timestamp"])
    assert generated_at.tzinfo is not None
    assert generated_at >= execution_timestamp
    assert execution_timestamp == pe.execution_observation_instant(EXECUTION_DATE)


def test_production_seam_rejects_a_future_execution_observation(repo: Path) -> None:
    """未注入的 runner 时钟不能为尚未发生的观测冻结 authoritative artifact。"""
    targets = _targets(repo)
    decision = {
        "candidate_id": "S2_R1",
        "signal_date": SIGNAL_DATE,
        "desired_targets": json.dumps(targets, ensure_ascii=False, sort_keys=True),
    }
    future_day = "2035-01-02"
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo, execution_date=future_day, realized_weights={list(targets)[0]: 1.0}
    )

    with pytest.raises(ValueError, match="尚未发生"):
        pe.freeze_prospective_execution_artifact(
            analyser,
            events,
            replayed,
            root=repo,
            decision=decision,
            framework_version="6.3.0",
        )
    assert not (repo / "research/shadow/s2_r1/execution_artifacts").exists()


def test_naive_runner_clock_is_rejected(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """naive / 无时区的时钟返回一律拒绝，不得静默当作 UTC。"""
    targets = _targets(repo)
    decision = {
        "candidate_id": "S2_R1",
        "signal_date": SIGNAL_DATE,
        "desired_targets": json.dumps(targets, ensure_ascii=False, sort_keys=True),
    }
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo, execution_date=EXECUTION_DATE, realized_weights={list(targets)[0]: 1.0}
    )
    monkeypatch.setattr(pe, "runner_utc_now", lambda: pd.Timestamp("2026-10-09 07:30:00"))

    with pytest.raises(ValueError, match="时区"):
        pe.freeze_prospective_execution_artifact(
            analyser,
            events,
            replayed,
            root=repo,
            decision=decision,
            framework_version="6.3.0",
        )


def test_expected_execution_date_is_only_an_assertion(repo: Path) -> None:
    """expected_execution_date 与 native replay 证据不符时必须拒绝。"""
    targets = _targets(repo)
    decision = {
        "candidate_id": "S2_R1",
        "signal_date": SIGNAL_DATE,
        "desired_targets": json.dumps(targets, ensure_ascii=False, sort_keys=True),
    }
    analyser, events, replayed = rqalpha_analyser_fixture(
        repo, execution_date=EXECUTION_DATE, realized_weights={list(targets)[0]: 1.0}
    )
    with injected_runner_clock(ARTIFACT_GENERATED_AT):
        with pytest.raises(ValueError, match="未在 2026-10-12 观测"):
            pe.freeze_prospective_execution_artifact(
                analyser,
                events,
                replayed,
                root=repo,
                decision=decision,
                framework_version="6.3.0",
                expected_execution_date="2026-10-12",
            )


def test_artifact_overwrite_is_rejected(repo: Path) -> None:
    targets = _targets(repo)
    relative = write_execution_artifact(
        repo,
        candidate_id="S2_R1",
        signal_date=SIGNAL_DATE,
        desired_targets=targets,
        execution_timestamp=EXECUTION_TIMESTAMP,
        artifact_generated_at=ARTIFACT_GENERATED_AT,
    )
    payload = json.loads((repo / relative).read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="拒绝覆盖"):
        pe.write_rqalpha_execution_artifact(
            payload,
            path=repo / relative,
            frozen_universe=frozen_universe(repo),
            expected_framework_version="6.3.0",
        )


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda payload: payload.update({"cash_weight": 0.9}), "cash_weight"),
        (lambda payload: payload.update({"turnover": 9.0}), "turnover"),
        (lambda payload: payload["portfolio"].update({"drawdown": -0.9}), "drawdown"),
        (
            lambda payload: payload["realized_weights"].update(
                {next(iter(payload["realized_weights"])): 0.01}
            ),
            "realized_weights",
        ),
        (lambda payload: payload.update({"execution_status": "PARTIAL"}), "execution_status"),
        (
            lambda payload: payload.update({"native_evidence": {"510300.SS": "调用方自述"}}),
            "native_evidence",
        ),
    ],
)
def test_internally_inconsistent_artifact_is_rejected_even_with_a_valid_sha(
    repo: Path, mutate: Any, match: str
) -> None:
    """artifact 的派生指标必须能被 native facts 复算；重新算过 SHA 也不能通过。"""
    relative = write_execution_artifact(
        repo,
        candidate_id="S2_R1",
        signal_date=SIGNAL_DATE,
        desired_targets=_targets(repo),
        execution_timestamp=EXECUTION_TIMESTAMP,
        artifact_generated_at=ARTIFACT_GENERATED_AT,
        order_events=((rqalpha_code(repo, "510300.SS"), "ACTIVE", "native 成交说明"),),
    )
    path = repo / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    identity = s2.build_rqalpha_evidence_identity(
        evidence_path=relative, root=repo, expected_framework_version="6.3.0"
    )

    # identity 本身是有效 SHA，说明 rejection 来自 artifact 内部不一致而非 hash 失配。
    pe.verify_rqalpha_evidence_identity(identity, root=repo, expected_framework_version="6.3.0")
    with pytest.raises(ValueError, match=match):
        pe.verify_rqalpha_artifact_payload(
            payload, frozen_universe=frozen_universe(repo), expected_framework_version="6.3.0"
        )
