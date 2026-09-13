"""S4C 权威执行审查 V2 的 reproduction portability、gate、冻结契约与决策名测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from research.experiments import run_s4c_rqalpha_execution_review as review

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("510300.SS", "510500.SS", "511010.SS")
ACCEPTED_BASELINE = {
    "cagr": 0.1163753501739464,
    "max_drawdown": -0.18351196288598648,
    "sharpe": 1.0911209093079228,
    "calmar": 0.634156751111909,
    "turnover": 11.79026465782429,
}
# 当前 Windows 平台观察到的一阶漂移（V2 容差必须容纳）。
OBSERVED_PLATFORM_DRIFT = {
    "cagr": -1.9342885204665095e-07,
    "max_drawdown": -4.000413379168233e-07,
    "sharpe": -1.8268639836449552e-06,
    "calmar": -2.4364449349167927e-06,
    "turnover": 1.1280265456982778e-04,
}


def _schedule(count: int = 10) -> pd.DataFrame:
    dates = pd.date_range("2013-04-01", periods=count, freq="MS", name="execution_date")
    schedule = pd.DataFrame(0.0, index=dates, columns=list(SYMBOLS))
    schedule["510300.SS"] = 0.6
    schedule["510500.SS"] = 0.4
    return schedule


def _native(**overrides: object) -> pd.Series:
    values: dict[str, object] = {
        "all_frozen_dates_processed": True,
        "extra_replayed_dates": 0,
        "average_execution_date_total_absolute_weight_deviation": 0.01,
        "materially_off_target_execution_dates": 0,
        "cash_rejection_events": 0,
        "average_cash_ratio": 0.001,
        "cagr": 0.11,
        "vectorbt_cagr": 0.116,
        "max_drawdown": -0.19,
        "vectorbt_max_drawdown": -0.1835,
    }
    values.update(overrides)
    return pd.Series(values)


def _differences(evidence: list[str] | None = None) -> pd.DataFrame:
    if not evidence:
        return pd.DataFrame(columns=["date", "symbol", "native_evidence"])
    return pd.DataFrame({"native_evidence": evidence})


def test_decision_names_match_the_frozen_protocol() -> None:
    assert review.ADVANCE == "ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW"
    assert review.DO_NOT_ADVANCE == "DO_NOT_ADVANCE_S4C_EXECUTION"
    assert review.BLOCK_REPRODUCTION == "BLOCK_S4C_EXECUTION_REPRODUCTION"
    assert review.BLOCK_ENVIRONMENT == "BLOCK_S4C_EXECUTION_ENVIRONMENT"


def test_frozen_center_is_sixty_returns_over_sixty_one_prices() -> None:
    assert review.RETURNS_WINDOW == 60
    assert review.PRICE_WINDOW == 61


def test_v2_reproduction_tolerance_is_frozen_at_1e_4() -> None:
    assert review.REPRODUCTION_RTOL == 1e-4
    assert review.REPRODUCTION_ATOL == 1e-4


def test_reproduction_accepts_identical_metrics() -> None:
    expected = pd.Series(ACCEPTED_BASELINE)
    assert review.performance_reproduces(dict(ACCEPTED_BASELINE), expected)


def test_reproduction_accepts_the_observed_platform_drift() -> None:
    expected = pd.Series(ACCEPTED_BASELINE)
    observed = {
        key: ACCEPTED_BASELINE[key] + OBSERVED_PLATFORM_DRIFT[key] for key in ACCEPTED_BASELINE
    }
    table = review.reproduction_table(observed, expected)
    assert bool(table.reproduced.iloc[0])
    assert table.passed.all()
    assert set(table.metric) == set(review.REPRODUCED_METRICS)
    assert (table.tolerance > 0).all()


def test_reproduction_passes_exactly_at_the_tolerance_boundary() -> None:
    expected = pd.Series({**ACCEPTED_BASELINE, "cagr": 0.0})
    observed = {**ACCEPTED_BASELINE, "cagr": review.metric_tolerance(0.0)}
    assert review.metric_tolerance(0.0) == review.REPRODUCTION_ATOL
    assert review.performance_reproduces(observed, expected)


def test_reproduction_fails_just_outside_the_tolerance_boundary() -> None:
    expected = pd.Series({**ACCEPTED_BASELINE, "cagr": 0.0})
    observed = {**ACCEPTED_BASELINE, "cagr": review.metric_tolerance(0.0) + 1e-9}
    assert not review.performance_reproduces(observed, expected)


def test_turnover_uses_the_same_relative_rule() -> None:
    expected = pd.Series(ACCEPTED_BASELINE)
    tolerance = review.metric_tolerance(ACCEPTED_BASELINE["turnover"])
    assert tolerance > review.REPRODUCTION_ATOL
    observed = {**ACCEPTED_BASELINE, "turnover": ACCEPTED_BASELINE["turnover"] + 0.5 * tolerance}
    assert review.performance_reproduces(observed, expected)
    observed = {**ACCEPTED_BASELINE, "turnover": ACCEPTED_BASELINE["turnover"] + 2.0 * tolerance}
    assert not review.performance_reproduces(observed, expected)


def test_reproduction_table_flags_a_materially_different_strategy() -> None:
    expected = pd.Series(ACCEPTED_BASELINE)
    observed = {**ACCEPTED_BASELINE, "cagr": ACCEPTED_BASELINE["cagr"] + 0.02}
    table = review.reproduction_table(observed, expected)
    assert not bool(table.reproduced.iloc[0])
    assert not bool(table.loc[table.metric.eq("cagr"), "passed"].iloc[0])


def test_execution_gates_pass_at_the_frozen_boundary() -> None:
    schedule = _schedule()
    vectorbt_cagr = 0.116
    vectorbt_max_drawdown = -0.1835
    native = _native(
        average_execution_date_total_absolute_weight_deviation=0.03,
        materially_off_target_execution_dates=1,
        average_cash_ratio=0.02,
        cagr=vectorbt_cagr - 0.02,
        vectorbt_cagr=vectorbt_cagr,
        max_drawdown=vectorbt_max_drawdown - 0.05,
        vectorbt_max_drawdown=vectorbt_max_drawdown,
    )
    assert (
        review.execution_decision(native, list(schedule.index), schedule, _differences())
        == review.ADVANCE
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"cash_rejection_events": 1},
        {"average_execution_date_total_absolute_weight_deviation": 0.0301},
        {"materially_off_target_execution_dates": 2},
        {"average_cash_ratio": 0.0201},
        {"extra_replayed_dates": 1},
        {"all_frozen_dates_processed": False},
        {"cagr": 0.0959},
        {"cagr": 0.0},
        {"max_drawdown": -0.2336},
    ],
)
def test_each_hard_gate_failure_stops_advancement(overrides: dict[str, object]) -> None:
    schedule = _schedule()
    native = _native(**overrides)
    assert (
        review.execution_decision(native, list(schedule.index), schedule, _differences())
        == review.DO_NOT_ADVANCE
    )


@pytest.mark.parametrize(
    "evidence",
    [["UNEXPLAINED_EXECUTION_DIFFERENCE"], ["UNKNOWN"], [""]],
)
def test_unexplained_material_differences_stop_advancement(evidence: list[str]) -> None:
    schedule = _schedule()
    assert (
        review.execution_decision(_native(), list(schedule.index), schedule, _differences(evidence))
        == review.DO_NOT_ADVANCE
    )


def test_explained_material_differences_do_not_stop_advancement() -> None:
    schedule = _schedule()
    assert (
        review.execution_decision(
            _native(),
            list(schedule.index),
            schedule,
            _differences(["sys_analyser 成交数量 900/1000"]),
        )
        == review.ADVANCE
    )


def test_replay_date_mismatch_blocks_reproduction() -> None:
    schedule = _schedule()
    assert (
        review.execution_decision(_native(), list(schedule.index[:-1]), schedule, _differences())
        == review.BLOCK_REPRODUCTION
    )


def test_frozen_target_artifact_structure_and_hash_are_exact() -> None:
    prices, mask, lifetimes, config, risk_symbols = review.load_review_inputs()
    schedule = review.load_committed_schedule()
    assert (
        review.verify_frozen_identity(schedule, prices, mask, lifetimes)
        == review.FROZEN_TARGET_SHA256
    )
    assert len(schedule) == review.FROZEN_TARGET_ROWS == 161
    assert schedule.index[0] == pd.Timestamp("2013-04-01")
    assert schedule.index[-1] == pd.Timestamp("2026-08-03")
    assert schedule.index.name == "execution_date"
    assert schedule.index.is_monotonic_increasing and not schedule.index.has_duplicates
    assert schedule.ge(0).all().all()
    assert schedule.sum(axis=1).round(12).eq(1.0).all()
    derived, _diagnostics, start = review.build_frozen_schedule(
        prices, risk_symbols, mask, lifetimes, config
    )
    assert start == pd.Timestamp("2013-04-01")
    review.audit_recomputation(review.schedule_sha256(derived)[1])


def test_verify_frozen_identity_rejects_a_tampered_artifact(tmp_path: Path) -> None:
    path = tmp_path / "frozen.csv"
    path.write_text("execution_date,510300.SS\n2013-04-01,1\n", encoding="utf-8", newline="")
    schedule = review.load_committed_schedule(path)
    with pytest.raises(ValueError, match="SHA-256"):
        review.verify_frozen_identity(schedule, pd.DataFrame(), pd.DataFrame(), {}, path)


def test_audit_recomputation_fails_on_semantic_drift(tmp_path: Path) -> None:
    path = tmp_path / "frozen.csv"
    path.write_text("execution_date,510300.SS\n2013-04-01,1\n", encoding="utf-8", newline="")
    review.audit_recomputation("execution_date,510300.SS\n2013-04-01,1\n", path)
    with pytest.raises(ValueError):
        review.audit_recomputation("execution_date,510300.SS\n2013-04-01,0.5\n", path)


def test_committed_targets_tolerate_checkout_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "frozen.csv"
    path.write_text("execution_date,510300.SS\r\n2013-04-01,1\r\n", encoding="utf-8", newline="")
    review.audit_recomputation("execution_date,510300.SS\n2013-04-01,1\n", path)


def test_native_replay_uses_the_committed_schedule_without_recomputation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, pd.DataFrame] = {}
    schedule = _schedule(count=1)

    def fake_run(*args: object, **kwargs: object) -> None:
        captured["schedule"] = args[0]  # type: ignore[assignment]
        raise RuntimeError("captured before RQAlpha")

    monkeypatch.setattr(review, "run_rqalpha_frozen_targets", fake_run)
    prices = pd.DataFrame(
        {"510300.SS": [1.0, 1.0, 1.0], "510500.SS": [1.0, 1.0, 1.0], "511010.SS": [1.0, 1.0, 1.0]},
        index=pd.DatetimeIndex(["2013-03-29", "2013-04-01", "2013-04-02"]),
    )
    config = review.S4CConfig("511010.SS")
    with pytest.raises(RuntimeError):
        review.run_native_replay(prices, schedule, config, Path(tmp_path))
    assert captured["schedule"].equals(schedule)


def test_reproduction_failure_prevents_the_native_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    schedule = _schedule()
    baseline = tmp_path / "baseline.csv"
    pd.DataFrame([ACCEPTED_BASELINE]).to_csv(baseline, index=False)

    class _Result:
        metrics = {**ACCEPTED_BASELINE, "cagr": ACCEPTED_BASELINE["cagr"] + 0.02}

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("RQAlpha must not run after a reproduction failure")

    monkeypatch.setattr(
        review, "load_review_inputs", lambda: (None, None, None, review.S4CConfig("x"), ("y",))
    )
    monkeypatch.setattr(review, "build_frozen_schedule", lambda *a, **k: (schedule, None, None))
    monkeypatch.setattr(review, "schedule_sha256", lambda frame: ("deadbeef", "serialized"))
    monkeypatch.setattr(review, "load_committed_schedule", lambda: schedule)
    monkeypatch.setattr(review, "verify_frozen_identity", lambda *a, **k: "deadbeef")
    monkeypatch.setattr(review, "audit_recomputation", lambda *a, **k: None)
    monkeypatch.setattr(review, "replay_vectorbt", lambda *a, **k: _Result())
    monkeypatch.setattr(review, "run_native_replay", fail_if_called)
    monkeypatch.setattr(review, "BASELINE", baseline)
    monkeypatch.setattr(sys, "argv", ["runner", "--output-dir", str(tmp_path)])

    review.main()
    assert review.BLOCK_REPRODUCTION in capsys.readouterr().out
