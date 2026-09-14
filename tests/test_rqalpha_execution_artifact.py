"""Native RQAlpha → authoritative artifact producer 的契约测试（synthetic，不运行 RQAlpha）。"""

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
    native_rqalpha_output,
    rqalpha_code,
    write_execution_artifact,
)

from research.experiments import prospective_evidence as pe
from research.experiments import run_s2_r1_shadow as s2

SIGNAL_DATE = "2026-09-30"
EXECUTION_TIMESTAMP = "2026-10-09T07:05:00+00:00"
ARTIFACT_GENERATED_AT = "2026-10-09T07:30:00+00:00"
ARTIFACT_RELATIVE_PATH = "research/results/s2_r1_producer_artifact.json"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return build_candidate_repo(tmp_path / "repo", "S2_R1")


def _targets(root: Path) -> dict[str, float]:
    universe = pd.read_csv(root / "config/universe.csv")
    return {
        str(symbol): (1.0 if index == 0 else 0.0) for index, symbol in enumerate(universe["symbol"])
    }


def _produce(root: Path, *, targets: dict[str, float], native: dict[str, Any]) -> dict[str, Any]:
    return pe.build_rqalpha_execution_artifact_payload(
        root=root,
        candidate_id="S2_R1",
        signal_date=SIGNAL_DATE,
        execution_timestamp=EXECUTION_TIMESTAMP,
        artifact_generated_at=ARTIFACT_GENERATED_AT,
        framework_version="6.3.0",
        intended_targets=targets,
        native=native,
    )


def test_native_positions_and_cash_produce_the_derived_execution_facts(repo: Path) -> None:
    targets = _targets(repo)
    symbol = next(iter(targets))
    native = native_rqalpha_output(
        repo,
        realized_weights={symbol: 0.75},
        cash_weight=0.25,
        turnover=0.4,
        max_drawdown=-0.05,
        total_value=2_000_000.0,
    )

    payload = _produce(repo, targets=targets, native=native)

    assert payload["realized_weights"][symbol] == pytest.approx(0.75)
    assert payload["cash_weight"] == pytest.approx(0.25)
    assert payload["turnover"] == pytest.approx(0.4)
    assert payload["portfolio"] == {"portfolio_value": 2_000_000.0, "drawdown": -0.05}
    assert payload["schema"] == pe.RQALPHA_ARTIFACT_SCHEMA


def test_missing_native_position_becomes_zero_weight(repo: Path) -> None:
    targets = _targets(repo)
    held, absent = list(targets)[0], list(targets)[1]
    native = native_rqalpha_output(repo, realized_weights={held: 1.0})

    payload = _produce(repo, targets=targets, native=native)

    assert payload["realized_weights"][held] == pytest.approx(1.0)
    assert payload["realized_weights"][absent] == 0.0
    assert sum(payload["realized_weights"].values()) == pytest.approx(1.0)


def test_producer_exposes_only_native_facts(repo: Path) -> None:
    """调用方不能通过 producer 参数覆盖 realized/cash/turnover/status/native 说明。"""
    parameters = set(inspect.signature(pe.build_rqalpha_execution_artifact_payload).parameters)

    assert "native" in parameters
    assert {
        "realized_weights",
        "cash_weight",
        "turnover",
        "execution_status",
        "portfolio",
        "native_evidence",
    }.isdisjoint(parameters)


def test_producer_rejects_native_facts_that_do_not_add_up(repo: Path) -> None:
    targets = _targets(repo)
    native = native_rqalpha_output(repo, realized_weights={list(targets)[0]: 0.5}, cash_weight=0.1)
    native["cash"] = 999.0

    with pytest.raises(ValueError, match="合计必须等于"):
        _produce(repo, targets=targets, native=native)


def test_producer_rejects_universe_foreign_native_symbols(repo: Path) -> None:
    targets = _targets(repo)
    native = native_rqalpha_output(repo, realized_weights={list(targets)[0]: 1.0})
    native["order_book_values"] = {"999999.XSHG": 1_000_000.0}

    with pytest.raises(ValueError, match="rqalpha_symbol"):
        _produce(repo, targets=targets, native=native)


def test_artifact_overwrite_is_rejected(repo: Path) -> None:
    targets = _targets(repo)
    relative = write_execution_artifact(
        repo,
        relative_path=ARTIFACT_RELATIVE_PATH,
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
        (
            lambda payload: payload["portfolio"].update({"drawdown": -0.9}),
            "drawdown",
        ),
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
    relative = "research/results/s2_r1_inconsistent_artifact.json"
    write_execution_artifact(
        repo,
        relative_path=relative,
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
