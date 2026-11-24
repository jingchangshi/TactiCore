"""P2-10: opt-in contract-violation exit code for the read-only S4C portability diagnostic.

默认行为保持“只诊断、exit 0”；只有显式 `--fail-on-contract-violation` 才在
`within_contract = false` 时以非零码失败。测试用 stub report，不重跑 solver。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.experiments import s4c_numerical_portability_diagnostic as diagnostic


def _report(within_contract: bool) -> dict[str, object]:
    return {
        "diagnostic": "S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_V1",
        "contract_compliance": {
            "within_contract": within_contract,
            "elements_exceeding_tolerance": 0 if within_contract else 3,
            "maximum_absolute_delta": 0.0 if within_contract else 2.5e-4,
        },
    }


@pytest.fixture
def stub_report(monkeypatch: pytest.MonkeyPatch) -> object:
    def install(within_contract: bool) -> None:
        monkeypatch.setattr(
            diagnostic,
            "build_report",
            lambda label, head: _report(within_contract),
        )

    return install


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> Path:
    output = tmp_path / "diagnostic.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["s4c_numerical_portability_diagnostic", "--output", str(output), *extra],
    )
    diagnostic.main()
    return output


@pytest.mark.parametrize("within_contract", [True, False])
def test_default_diagnostic_exits_zero_regardless_of_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_report: object,
    within_contract: bool,
) -> None:
    stub_report(within_contract)  # type: ignore[operator]

    output = _run(tmp_path, monkeypatch)

    assert (
        json.loads(output.read_text(encoding="utf-8"))["contract_compliance"]["within_contract"]
        is within_contract
    )


@pytest.mark.parametrize(("within_contract", "exit_code"), [(True, 0), (False, 1)])
def test_opt_in_flag_fails_only_on_a_contract_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_report: object,
    within_contract: bool,
    exit_code: int,
) -> None:
    stub_report(within_contract)  # type: ignore[operator]

    if exit_code == 0:
        _run(tmp_path, monkeypatch, "--fail-on-contract-violation")
    else:
        with pytest.raises(SystemExit) as error:
            _run(tmp_path, monkeypatch, "--fail-on-contract-violation")
        assert error.value.code == exit_code

    # 违约时报告仍必须先落盘，供独立分类使用。
    output = tmp_path / "diagnostic.json"
    assert output.is_file()


def _schedule(rows: list[list[float]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        index=pd.to_datetime(["2024-01-31", "2024-02-29"]),
        columns=["A", "B"],
        dtype=float,
    )


def test_contract_compliance_requires_structural_and_numerical_contract() -> None:
    base = _schedule([[0.60, 0.40], [0.55, 0.45]])
    assert diagnostic.contract_compliance(base, base.copy())["within_contract"] is True

    # 同一 support/最大权重下的 5e-5 漂移：在 1e-4 容差内。
    small = _schedule([[0.60005, 0.39995], [0.55, 0.45]])
    assert diagnostic.contract_compliance(base, small)["within_contract"] is True

    # 超出数值容差。
    exceed = _schedule([[0.6002, 0.3998], [0.55, 0.45]])
    evidence = diagnostic.contract_compliance(base, exceed)
    assert evidence["within_contract"] is False
    assert evidence["elements_exceeding_tolerance"] > 0

    # support 从 {A,B} 变为 {A}：结构变化不得借容差通过。
    support = _schedule([[1.0, 0.0], [0.55, 0.45]])
    evidence = diagnostic.contract_compliance(base, support)
    assert evidence["within_contract"] is False
    assert "support" in str(evidence["contract_error"])

    # 非有限值必须违约，即使超差计数可能为 0。
    nonfinite = _schedule([[np.inf, 0.0], [0.55, 0.45]])
    evidence = diagnostic.contract_compliance(base, nonfinite)
    assert evidence["within_contract"] is False
    assert evidence["nonfinite_elements"] > 0

    # 轴/列集合不一致。
    axis = base.rename(columns={"A": "C"})
    evidence = diagnostic.contract_compliance(base, axis)
    assert evidence["within_contract"] is False
    assert evidence["contract_error"] is not None
