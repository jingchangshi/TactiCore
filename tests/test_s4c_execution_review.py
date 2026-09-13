"""S4C 权威执行审查的预注册 gate、冻结目标契约与决策名称测试。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.experiments import run_s4c_rqalpha_execution_review as review

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("510300.SS", "510500.SS", "511010.SS")


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


def test_reproduction_gate_requires_machine_tolerance() -> None:
    expected = pd.Series(
        {"cagr": 0.1, "max_drawdown": -0.2, "sharpe": 1.0, "calmar": 0.5, "turnover": 3.0}
    )
    assert review.reproduces(dict(expected), expected)
    assert not review.reproduces({**dict(expected), "calmar": 0.5 + 1e-9}, expected)


def test_committed_targets_fail_closed_when_they_drift(tmp_path: Path) -> None:
    path = tmp_path / "frozen.csv"
    path.write_text("execution_date,A\n2013-04-01,1\n", encoding="utf-8", newline="")
    assert review.assert_committed_matches("execution_date,A\n2013-04-01,1\n", path)
    with pytest.raises(ValueError):
        review.assert_committed_matches("execution_date,A\n2013-04-01,0.5\n", path)
    with pytest.raises(FileNotFoundError):
        review.assert_committed_matches("", tmp_path / "missing.csv")


def test_target_artifact_normalizes_checkout_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "frozen.csv"
    path.write_text("execution_date,A\r\n2013-04-01,1\r\n", encoding="utf-8", newline="")
    assert review.assert_committed_matches("execution_date,A\n2013-04-01,1\n", path)


def test_frozen_target_artifact_matches_frozen_semantics() -> None:
    prices, mask, lifetimes, config, risk_symbols = review.load_review_inputs()
    schedule, _diagnostics, start = review.build_frozen_schedule(
        prices, risk_symbols, mask, lifetimes, config
    )
    _sha256, serialized = review.schedule_sha256(schedule)
    committed = review.load_committed_schedule()
    pd.testing.assert_frame_equal(committed.astype(float), schedule)
    assert review.assert_committed_matches(serialized) == review.schedule_sha256(schedule)[0]
    assert len(schedule) == 161
    assert start == pd.Timestamp("2013-04-01")
    assert schedule.index[0] == pd.Timestamp("2013-04-01")
    assert schedule.index.is_monotonic_increasing and not schedule.index.has_duplicates
    assert schedule.index.name == "execution_date"
    assert schedule.ge(0).all().all()
    assert schedule.sum(axis=1).round(12).eq(1.0).all()


def test_native_replay_uses_the_frozen_schedule_without_recomputation(
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
        review.run_native_replay(prices, schedule, config, schedule.index[0], Path(tmp_path))
    assert captured["schedule"].equals(schedule)
