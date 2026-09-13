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


def _blend_summary(cagr_by_pair: dict[tuple[float, float], float]) -> pd.DataFrame:
    rows = [
        {"series_kind": "blend", "s2_share": s2_share, "s4c_share": s4c_share, "cagr": cagr}
        for (s2_share, s4c_share), cagr in cagr_by_pair.items()
    ]
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("cagr_by_pair", "expected"),
    [
        (
            {
                (1.0, 0.0): 0.12,
                (0.75, 0.25): 0.115,
                (0.5, 0.5): 0.105,
                (0.25, 0.75): 0.10,
                (0.0, 1.0): 0.09,
            },
            "FEASIBLE_WITH_EXISTING_COMPONENTS",
        ),
        (
            {
                (1.0, 0.0): 0.13,
                (0.75, 0.25): 0.099,
                (0.5, 0.5): 0.098,
                (0.25, 0.75): 0.097,
                (0.0, 1.0): 0.09,
            },
            "FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT",
        ),
        (
            {
                (1.0, 0.0): 0.098,
                (0.75, 0.25): 0.097,
                (0.5, 0.5): 0.096,
                (0.25, 0.75): 0.095,
                (0.0, 1.0): 0.09,
            },
            "PLAUSIBLE_BUT_PROSPECTIVE_EVIDENCE_INSUFFICIENT",
        ),
        (
            {
                (1.0, 0.0): 0.094,
                (0.75, 0.25): 0.09,
                (0.5, 0.5): 0.088,
                (0.25, 0.75): 0.086,
                (0.0, 1.0): 0.08,
            },
            "NOT_SUPPORTED_BY_EXISTING_COMPONENTS",
        ),
    ],
)
def test_objective_decision_thresholds_are_preregistered(
    cagr_by_pair: dict[tuple[float, float], float], expected: str
) -> None:
    decision = objective.objective_feasibility_decision(
        _blend_summary(cagr_by_pair), corrected=True
    )

    assert decision == expected
    assert decision in objective.DECISION_TOKENS


def test_failed_reproduction_blocks_the_decision() -> None:
    summary = _blend_summary(dict.fromkeys(EXPECTED_BLEND_WEIGHTS, 0.12))

    assert (
        objective.objective_feasibility_decision(summary, corrected=False)
        == "BLOCKED_BY_CORRECTNESS"
    )


def test_complexity_verdict_uses_the_preregistered_margins() -> None:
    blends = pd.DataFrame(
        [
            {"cagr": 0.101, "max_drawdown": -0.20},
            {"cagr": 0.099, "max_drawdown": -0.16},
        ]
    )
    s30 = pd.Series({"cagr": 0.099, "max_drawdown": -0.15})

    assert objective.complexity_verdict(blends, s30) == "COMPLEXITY_NOT_JUSTIFIED_BY_THIS_EVIDENCE"
    s30_better = pd.Series({"cagr": 0.0945, "max_drawdown": -0.15})
    assert objective.complexity_verdict(blends, s30_better) == "COMPLEXITY_CLEARS_S30_HURDLE"
    deeper = pd.DataFrame([{"cagr": 0.0995, "max_drawdown": -0.12}])
    assert objective.complexity_verdict(deeper, s30) == "COMPLEXITY_CLEARS_S30_HURDLE"


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
