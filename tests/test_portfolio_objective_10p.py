"""10% portfolio-objective feasibility 的预注册契约测试。

这些测试只保护 TactiCore 自有语义：冻结组件身份、固定权重集合、无杠杆、PIT、共同区间、
裁决规则与输出 schema。它们不复测 VectorBT 内部实现。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.experiments import run_portfolio_objective_10p as objective
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs, validate_execution_targets

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BLEND_WEIGHTS = (
    (1.00, 0.00),
    (0.75, 0.25),
    (0.50, 0.50),
    (0.25, 0.75),
    (0.00, 1.00),
)


@pytest.fixture(scope="module")
def prices() -> pd.DataFrame:
    return load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")


@pytest.fixture(scope="module")
def component_schedules(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    s2 = objective.load_frozen_schedule(
        objective.S2_FROZEN_TARGETS, objective.S2_FROZEN_SHA256, prices.columns
    )
    s4c = objective.load_frozen_schedule(
        objective.S4C_FROZEN_TARGETS, objective.S4C_FROZEN_SHA256, prices.columns
    )
    return s2, s4c


def test_frozen_component_artifacts_match_the_registered_hashes() -> None:
    assert (
        objective.sha256_frozen_repository_text(objective.S2_FROZEN_TARGETS)
        == objective.S2_FROZEN_SHA256
    )
    assert (
        objective.sha256_frozen_repository_text(objective.S4C_FROZEN_TARGETS)
        == objective.S4C_FROZEN_SHA256
    )


def test_tampered_frozen_schedule_is_rejected(tmp_path: Path) -> None:
    # S2 的冻结日程哈希已登记在 S2 R1 manifest 中；这里用一份等价副本验证 hash gate。
    tampered = tmp_path / "s2.csv"
    tampered.write_text("execution_date,510300.SS\n2013-04-01,1\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="SHA-256"):
        objective.load_frozen_schedule(
            tampered, objective.S2_FROZEN_SHA256, pd.Index(["510300.SS"])
        )


def test_blend_weights_are_exactly_the_preregistered_coarse_pairs() -> None:
    assert objective.BLEND_WEIGHTS == EXPECTED_BLEND_WEIGHTS
    for s2_share, s4c_share in objective.BLEND_WEIGHTS:
        assert s2_share >= 0.0 and s4c_share >= 0.0
        assert s2_share + s4c_share == pytest.approx(1.0)


def test_unregistered_blend_weights_are_refused(
    component_schedules: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    s2, s4c = component_schedules

    with pytest.raises(ValueError, match="未预注册"):
        objective.blend_target_schedule(s2, s4c, 0.63, 0.37)


def test_blend_schedule_is_long_only_and_fully_invested(
    prices: pd.DataFrame, component_schedules: tuple[pd.DataFrame, pd.DataFrame]
) -> None:
    s2, s4c = component_schedules

    for s2_share, s4c_share in objective.BLEND_WEIGHTS:
        blend = objective.blend_target_schedule(s2, s4c, s2_share, s4c_share)
        assert list(blend.columns) == list(prices.columns)
        assert blend.ge(0.0).all().all()
        deviation = blend.sum(axis=1).sub(1.0).abs()
        assert deviation.le(objective.ROW_SUM_TOLERANCE).all()


def test_blend_index_is_the_union_of_component_submission_dates(
    component_schedules: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    s2, s4c = component_schedules
    blend = objective.blend_target_schedule(s2, s4c, 0.5, 0.5)

    assert blend.index.equals(s2.index.union(s4c.index))
    assert blend.index.equals(s4c.index)
    assert blend.index.name == "execution_date"
    assert blend.index.is_monotonic_increasing and not blend.index.has_duplicates


def test_standalone_anchors_keep_their_own_frozen_schedules(
    component_schedules: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    s2, s4c = component_schedules

    # 两个候选各自按自己的冻结日程回放：S2 是 103 行的 SIGNAL_CHANGE_ONLY，
    # S4C 是 161 行的月频提交。它们不是同一个提交日程。
    assert len(s2) == 103
    assert len(s4c) == 161
    assert not s2.index.equals(s4c.index)
    assert s2.index.difference(s4c.index).empty


def test_derived_union_endpoints_are_not_the_standalone_candidates(
    component_schedules: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    s2, s4c = component_schedules
    derived_s2_only = objective.blend_target_schedule(s2, s4c, 1.0, 0.0)
    derived_s4c_only = objective.blend_target_schedule(s2, s4c, 0.0, 1.0)

    # 0/100 的派生目标向量等于 S4C 的冻结目标，但它的提交日程是并集日程，
    # 因此它是独立命名的派生序列，而不是 S4C_R1 的单独回放。
    pd.testing.assert_frame_equal(derived_s4c_only, s4c, check_names=False)
    # 1/0 的派生日程是并集（161 行）而非 S2 R1 自己的 103 行提交日程；
    # 不得据此声称复现 S2_R1。
    assert len(derived_s2_only) == len(s4c) == 161
    assert not derived_s2_only.index.equals(s2.index)
    expected = s2.reindex(s4c.index).ffill()
    pd.testing.assert_frame_equal(derived_s2_only, expected, check_names=False)


def test_interior_blend_rows_are_convex_combinations_of_frozen_component_states(
    component_schedules: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    s2, s4c = component_schedules
    interior = [(0.75, 0.25), (0.50, 0.50), (0.25, 0.75)]

    for s2_share, s4c_share in interior:
        blend = objective.blend_target_schedule(s2, s4c, s2_share, s4c_share)
        left = s2.reindex(blend.index).ffill()
        right = s4c.reindex(blend.index).ffill()
        pd.testing.assert_frame_equal(
            blend, (s2_share * left + s4c_share * right), check_names=False
        )


def test_building_blends_does_not_touch_the_frozen_inputs(
    component_schedules: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    s2, s4c = component_schedules

    for s2_share, s4c_share in objective.BLEND_WEIGHTS:
        objective.blend_target_schedule(s2, s4c, s2_share, s4c_share)

    assert (
        objective.sha256_frozen_repository_text(objective.S2_FROZEN_TARGETS)
        == objective.S2_FROZEN_SHA256
    )
    assert (
        objective.sha256_frozen_repository_text(objective.S4C_FROZEN_TARGETS)
        == objective.S4C_FROZEN_SHA256
    )


def test_blend_targets_never_backdate_before_component_inception(
    component_schedules: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    s2, s4c = component_schedules
    blend = objective.blend_target_schedule(s2, s4c, 0.5, 0.5)

    assert blend.index[0] >= objective.PRIMARY_START
    assert blend.index[-1] <= objective.EVALUATION_END
    assert s2.index[0] >= objective.PRIMARY_START and s4c.index[0] >= objective.PRIMARY_START


def test_every_blend_row_is_pit_legal(
    prices: pd.DataFrame, component_schedules: tuple[pd.DataFrame, pd.DataFrame]
) -> None:
    s2, s4c = component_schedules
    mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))

    for s2_share, s4c_share in objective.BLEND_WEIGHTS:
        blend = objective.blend_target_schedule(s2, s4c, s2_share, s4c_share)
        validate_execution_targets(blend, prices, mask, lifetimes)


def _decision_summary(
    anchor_cagrs: tuple[float, float],
    interior_cagrs: tuple[float, float, float],
    endpoint_cagrs: tuple[float, float],
) -> pd.DataFrame:
    """构造裁决输入：两个真实 anchor、三个内部 blend、两个上下文端点。"""
    rows: list[dict[str, object]] = []
    for name, cagr in zip(objective.ANCHOR_SERIES_NAMES, anchor_cagrs, strict=True):
        rows.append({"series": name, "series_kind": "component_anchor", "cagr": cagr})
    for name, cagr in zip(objective.INTERIOR_BLEND_SERIES_NAMES, interior_cagrs, strict=True):
        rows.append({"series": name, "series_kind": "blend", "cagr": cagr})
    for name, cagr in zip(
        (
            "BLEND_S2_100_S4C_00",
            "BLEND_S2_00_S4C_100",
        ),
        endpoint_cagrs,
        strict=True,
    ):
        rows.append({"series": name, "series_kind": "blend", "cagr": cagr})
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("anchors", "interior", "endpoints", "expected"),
    [
        ((0.08, 0.11), (0.105, 0.115, 0.125), (0.09, 0.13), "FEASIBLE_WITH_EXISTING_COMPONENTS"),
        (
            (0.08, 0.105),
            (0.097, 0.098, 0.099),
            (0.09, 0.11),
            "FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT",
        ),
        (
            (0.08, 0.09),
            (0.094, 0.093, 0.092),
            (0.13, 0.12),
            "NOT_SUPPORTED_BY_EXISTING_COMPONENTS",
        ),
        (
            (0.08, 0.09),
            (0.094, 0.093, 0.096),
            (0.09, 0.10),
            "PLAUSIBLE_BUT_PROSPECTIVE_EVIDENCE_INSUFFICIENT",
        ),
        (
            (0.08, 0.096),
            (0.09, 0.091, 0.092),
            (0.09, 0.10),
            "PLAUSIBLE_BUT_PROSPECTIVE_EVIDENCE_INSUFFICIENT",
        ),
        ((0.06, 0.08), (0.09, 0.088, 0.086), (0.08, 0.09), "NOT_SUPPORTED_BY_EXISTING_COMPONENTS"),
    ],
)
def test_objective_decision_thresholds_are_preregistered(
    anchors: tuple[float, float],
    interior: tuple[float, float, float],
    endpoints: tuple[float, float],
    expected: str,
) -> None:
    decision = objective.objective_feasibility_decision(
        _decision_summary(anchors, interior, endpoints), corrected=True
    )

    assert decision == expected
    assert decision in objective.DECISION_TOKENS


def test_derived_endpoint_cannot_drive_component_dependence() -> None:
    # 一个高 CAGR 的派生 100/0 端点不是 standalone S2_R1，不得把裁决升级为
    # FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT。
    summary = _decision_summary((0.07, 0.08), (0.090, 0.088, 0.086), (0.20, 0.19))

    assert (
        objective.objective_feasibility_decision(summary, corrected=True)
        == "NOT_SUPPORTED_BY_EXISTING_COMPONENTS"
    )


def test_high_standalone_anchor_can_drive_component_dependence() -> None:
    summary = _decision_summary((0.07, 0.115), (0.090, 0.088, 0.086), (0.07, 0.115))

    assert (
        objective.objective_feasibility_decision(summary, corrected=True)
        == "FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT"
    )


def test_failed_reproduction_blocks_the_decision() -> None:
    summary = _decision_summary((0.12, 0.12), (0.12, 0.12, 0.12), (0.12, 0.12))

    assert (
        objective.objective_feasibility_decision(summary, corrected=False)
        == "BLOCKED_BY_CORRECTNESS"
    )


def test_complexity_verdict_uses_the_preregistered_margins() -> None:
    names = objective.INTERIOR_BLEND_SERIES_NAMES
    blends = pd.DataFrame(
        [
            {"series": names[0], "cagr": 0.101, "max_drawdown": -0.20},
            {"series": names[1], "cagr": 0.099, "max_drawdown": -0.16},
            {"series": names[2], "cagr": 0.098, "max_drawdown": -0.17},
        ]
    )
    s30 = pd.Series({"cagr": 0.099, "max_drawdown": -0.15})

    assert objective.complexity_verdict(blends, s30) == "COMPLEXITY_NOT_JUSTIFIED_BY_THIS_EVIDENCE"
    s30_better = pd.Series({"cagr": 0.0945, "max_drawdown": -0.15})
    assert objective.complexity_verdict(blends, s30_better) == "COMPLEXITY_CLEARS_S30_HURDLE"
    deeper = pd.DataFrame(
        [
            {"series": names[0], "cagr": 0.0995, "max_drawdown": -0.12},
            {"series": names[1], "cagr": 0.099, "max_drawdown": -0.13},
            {"series": names[2], "cagr": 0.098, "max_drawdown": -0.14},
        ]
    )
    assert objective.complexity_verdict(deeper, s30) == "COMPLEXITY_CLEARS_S30_HURDLE"


def test_complexity_verdict_refuses_derived_endpoints() -> None:
    blends = pd.DataFrame([{"series": "BLEND_S2_100_S4C_00", "cagr": 0.20, "max_drawdown": -0.10}])
    s30 = pd.Series({"cagr": 0.099, "max_drawdown": -0.15})

    with pytest.raises(ValueError, match="内部固定 blend"):
        objective.complexity_verdict(blends, s30)


def test_protocol_output_schema_is_frozen() -> None:
    assert objective.SUMMARY_COLUMNS == (
        "series",
        "series_kind",
        "submission_policy",
        "s2_share",
        "s4c_share",
        "evaluation_start",
        "evaluation_end",
        "cagr",
        "max_drawdown",
        "sharpe",
        "calmar",
        "worst_year",
        "turnover",
        "trade_count",
        "average_holding_days",
        "submission_count",
        "annualized_submission_count",
        "actual_order_days",
        "annualized_action_days",
    )
    assert objective.PERIOD_COLUMNS[:2] == ("series", "period")
    assert objective.ROLLING_COLUMNS[0] == "series"
    assert objective.DIVERSIFICATION_COLUMNS[0] == "series"


def test_derived_submission_policy_is_named_separately() -> None:
    assert objective.DERIVED_UNION_TARGET_SUBMISSION == "DERIVED_UNION_TARGET_SUBMISSION"
    assert "SIGNAL_CHANGE_ONLY" not in objective.DERIVED_UNION_TARGET_SUBMISSION
    assert "MONTHLY_TARGET_SUBMISSION" == "MONTHLY_TARGET_SUBMISSION"


def test_diversification_rows_separate_proximity_from_diversification() -> None:
    summary = pd.DataFrame(
        [
            {
                "series": "S2_R1_committed_anchor",
                "series_kind": "component_anchor",
                "s2_share": None,
                "s4c_share": None,
                "cagr": 0.06,
                "max_drawdown": -0.26,
                "sharpe": 0.65,
            },
            {
                "series": "S4C_R1_committed_anchor",
                "series_kind": "component_anchor",
                "s2_share": None,
                "s4c_share": None,
                "cagr": 0.12,
                "max_drawdown": -0.18,
                "sharpe": 1.09,
            },
            {
                "series": "BLEND_S2_50_S4C_50",
                "series_kind": "blend",
                "s2_share": 0.5,
                "s4c_share": 0.5,
                "cagr": 0.10,
                "max_drawdown": -0.16,
                "sharpe": 1.0,
            },
        ]
    )

    rows = objective.diversification_rows(summary)

    assert rows[0]["weighted_anchor_cagr"] == pytest.approx(0.09)
    assert rows[0]["cagr_beyond_weighted_anchor"] == pytest.approx(0.01)
    assert rows[0]["max_drawdown_improves_anchor"] is True
    assert rows[0]["sharpe_improves_anchor"] is False


def test_preregistered_windows_and_targets_are_unchanged() -> None:
    assert objective.PRIMARY_START == pd.Timestamp("2013-04-01")
    assert objective.EVALUATION_END == pd.Timestamp("2026-08-31")
    assert objective.S2_REPRODUCTION_START == pd.Timestamp("2013-03-29")
    assert objective.TARGET_CAGR == 0.10
    assert objective.NEAR_TARGET_CAGR == 0.095
    assert len(objective.PERIODS) == 4


def test_primary_summary_excludes_s30_and_common_window_includes_it() -> None:
    assert objective.PRIMARY_SERIES_NAMES == objective.ANCHOR_SERIES_NAMES + (
        objective.BLEND_SERIES_NAMES
    )
    assert objective.S30_SERIES_NAME not in objective.PRIMARY_SERIES_NAMES
    assert objective.S30_SERIES_NAME in objective.COMMON_WINDOW_SERIES_NAMES
    assert objective.COMMON_WINDOW_SERIES_NAMES == objective.PRIMARY_SERIES_NAMES + (
        objective.S30_SERIES_NAME,
    )
    assert objective.INTERIOR_BLEND_SERIES_NAMES == (
        "BLEND_S2_75_S4C_25",
        "BLEND_S2_50_S4C_50",
        "BLEND_S2_25_S4C_75",
    )
    assert len(objective.BLEND_SERIES_NAMES) == 5
    assert objective.ANNUAL_COLUMNS == ("series", "year", "return")


def test_s2_correctness_gate_is_identity_based() -> None:
    # S2 的 correctness 依赖冻结身份与回放输入，而不是任何性能容差。
    identity = pd.DataFrame(
        [
            {"gate": "identity", "passed": True},
            {"gate": "identity", "passed": True},
            {"gate": "descriptive_only", "passed": False},
        ]
    )
    assert objective.correctness_passed(identity) is True

    broken = pd.DataFrame(
        [
            {"gate": "identity", "passed": True},
            {"gate": "identity", "passed": False},
            {"gate": "descriptive_only", "passed": True},
        ]
    )
    assert objective.correctness_passed(broken) is False

    checks = pd.DataFrame(
        [
            {
                "series": "S2_R1_committed_anchor",
                "check": "replay_input_equals_frozen_schedule",
                "gate": "identity",
                "passed": True,
            },
            {
                "series": "S2_R1_committed_anchor",
                "check": "committed_metric_descriptive",
                "gate": "descriptive_only",
                "passed": True,
            },
        ]
    )
    assert objective.CORRECTNESS_COLUMNS[1:3] == ("check", "gate")
    assert checks["gate"].eq("identity").sum() == 1


def test_s4c_portability_tolerance_matches_the_existing_s4c_rule() -> None:
    assert objective.s4c_portability_tolerance(0.05) == pytest.approx(1e-4)
    assert objective.s4c_portability_tolerance(-0.18) == pytest.approx(1e-4)
    assert objective.s4c_portability_tolerance(12.0) == pytest.approx(1.2e-3)


def test_s30_common_window_inception_is_enforced() -> None:
    assert objective.S30_COMMON_WINDOW_START == pd.Timestamp("2014-01-15")

    objective.assert_s30_inception(pd.Timestamp("2014-01-15"))
    with pytest.raises(ValueError, match="共同窗口 inception"):
        objective.assert_s30_inception(pd.Timestamp("2013-04-01"))


def test_annual_rows_keep_each_series_own_history() -> None:
    index_early = pd.date_range("2013-04-01", "2014-12-31", freq="D")
    index_late = pd.date_range("2014-01-15", "2014-12-31", freq="D")
    early = pd.Series(1.0 + 0.0001 * pd.RangeIndex(len(index_early)), index=index_early)
    late = pd.Series(1.0 + 0.0002 * pd.RangeIndex(len(index_late)), index=index_late)

    frame = objective.annual_rows(
        [
            ("BLEND_S2_50_S4C_50", early, pd.Timestamp("2013-04-01")),
            ("S30_REFERENCE", late, pd.Timestamp("2014-01-15")),
        ]
    )

    blend_years = frame.loc[frame["series"].eq("BLEND_S2_50_S4C_50"), "year"].tolist()
    s30_years = frame.loc[frame["series"].eq("S30_REFERENCE"), "year"].tolist()
    assert blend_years == [2013, 2014]
    assert s30_years == [2014]
    assert list(frame.columns) == list(objective.ANNUAL_COLUMNS)
