"""S4C_PORTABLE_REPRODUCTION_CONTRACT_V1 的契约测试（synthetic，不运行求解器）。"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from research.experiments import s4c_portable_reproduction as portability


def _schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "A": [0.60, 0.30, 1.00],
            "B": [0.40, 0.70, 0.00],
            "C": [0.00, 0.00, 0.00],
        },
        index=pd.DatetimeIndex(["2026-01-05", "2026-02-02", "2026-03-02"], name="execution_date"),
    )


def test_contract_tokens_match_the_preregistered_document() -> None:
    """代码常量必须等于预注册契约里的 machine-readable token，防止静默漂移。"""
    text = portability.contract_text()

    assert portability.CONTRACT_NAME in text
    assert re.search(r"SCHEDULE_WEIGHT_ABS_TOL\s*=\s*1e-4", text)
    assert re.search(r"SCHEDULE_WEIGHT_REL_TOL\s*=\s*0\b", text)
    assert portability.SCHEDULE_WEIGHT_ABS_TOL == 1e-4
    assert portability.SCHEDULE_WEIGHT_REL_TOL == 0.0


def test_committed_schedule_reproduces_itself() -> None:
    schedule = _schedule()

    portability.require_portable_reproduction(schedule, schedule.copy())

    assert portability.maximum_absolute_delta(schedule, schedule.copy()) == 0.0
    evidence = portability.reproduction_evidence(schedule, schedule.copy())
    assert evidence["elements_exceeding_tolerance"] == 0
    assert evidence["contract"] == portability.CONTRACT_NAME


def test_solver_noise_inside_the_contract_is_accepted() -> None:
    """观测到的 Linux/GitHub 量级（约 2.8e-5，甚至历史 4.11e-5）必须通过。"""
    committed = _schedule()
    derived = committed.copy()
    derived.loc["2026-01-05", "A"] = committed.loc["2026-01-05", "A"] - 4.11e-05
    derived.loc["2026-01-05", "B"] = committed.loc["2026-01-05", "B"] + 4.11e-05

    portability.require_portable_reproduction(committed, derived)


def test_drift_beyond_the_contract_is_rejected() -> None:
    committed = _schedule()
    derived = committed.copy()
    derived.loc["2026-01-05", "A"] = committed.loc["2026-01-05", "A"] - 1.01e-04
    derived.loc["2026-01-05", "B"] = committed.loc["2026-01-05", "B"] + 1.01e-04

    with pytest.raises(ValueError, match="超出 S4C_PORTABLE_REPRODUCTION_CONTRACT_V1"):
        portability.require_portable_reproduction(committed, derived)


def test_exact_tolerance_boundary_passes_and_just_beyond_fails() -> None:
    committed = _schedule()
    boundary = committed.copy()
    boundary.loc["2026-02-02", "A"] = committed.loc["2026-02-02", "A"] - 1e-04
    boundary.loc["2026-02-02", "B"] = committed.loc["2026-02-02", "B"] + 1e-04
    beyond = committed.copy()
    beyond.loc["2026-02-02", "A"] = committed.loc["2026-02-02", "A"] - (1e-04 + 1e-12)
    beyond.loc["2026-02-02", "B"] = committed.loc["2026-02-02", "B"] + (1e-04 + 1e-12)

    portability.require_portable_reproduction(committed, boundary)
    with pytest.raises(ValueError):
        portability.require_portable_reproduction(committed, beyond)


def test_structure_still_fails_inside_the_numerical_tolerance() -> None:
    """小于 1e-4 的结构变化（asset 进/出、最大权重互换）仍必须被拒绝。"""
    committed = _schedule()
    support_gain = committed.copy()
    support_gain.loc["2026-03-02", "C"] = 5e-05
    support_gain.loc["2026-03-02", "A"] = 1.0 - 5e-05
    swapped = committed.copy()
    swapped.loc["2026-02-02", "A"], swapped.loc["2026-02-02", "B"] = (
        committed.loc["2026-02-02", "B"],
        committed.loc["2026-02-02", "A"],
    )

    with pytest.raises(ValueError, match="support"):
        portability.require_portable_reproduction(committed, support_gain)
    with pytest.raises(ValueError, match="最大权重标的"):
        portability.require_portable_reproduction(committed, swapped)


def test_artifact_identity_invariants_are_not_relaxed_by_the_contract() -> None:
    """契约只放宽数值比较，不放宽日期集合/资产集合/逐行和。"""
    committed = _schedule()
    missing_row = committed.drop(index=committed.index[-1])
    renamed = committed.rename(columns={"C": "D"})
    broken_sum = committed.copy()
    broken_sum.loc["2026-01-05", "A"] = 0.55

    for drifted in (missing_row, renamed, broken_sum):
        with pytest.raises(ValueError):
            portability.require_portable_reproduction(committed, drifted)


def test_contract_document_is_inside_the_repository() -> None:
    path = Path(portability.ROOT) / portability.CONTRACT_RELATIVE_PATH

    assert path.is_file()
    assert "NUMERICALLY_EQUIVALENT" in path.read_text(encoding="utf-8")
