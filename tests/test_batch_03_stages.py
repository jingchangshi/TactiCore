import numpy as np
import pandas as pd
import pytest

from research.experiments.run_s4c_erc_skfolio_transfer import (
    S4CConfig,
    SolverFailure,
    erc_weights,
)
from research.experiments.run_s4c_erc_skfolio_transfer import (
    build_targets as build_s4c_targets,
)
from research.experiments.run_s4c_erc_skfolio_transfer import (
    decision as s4c_decision,
)
from research.experiments.run_s10a_robustness import (
    RobustnessSpec,
    build_targets,
    fixed_period_drawdown_gate,
)
from research.experiments.run_s10a_robustness import (
    decision as s10_decision,
)
from research.experiments.run_s27a_rqalpha_execution_review import (
    build_frozen_schedule,
    schedule_execution,
)
from research.experiments.run_s27a_rqalpha_execution_review import (
    decision as s27_decision,
)
from tacticore.data.prices import load_price_csv
from tacticore.strategies.multi_asset_trend import (
    build_execution_weights,
    load_trend_config,
)
from tacticore.strategies.trend_inverse_vol import (
    build_month_end_targets,
    load_trend_inverse_vol_config,
)
from tacticore.strategies.volatility_targeting import (
    build_month_end_targets as build_frozen_s10_targets,
)
from tacticore.strategies.volatility_targeting import (
    load_volatility_targeting_config,
)

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_s27_schedule_preserves_monthly_targets_and_next_observation_timing() -> None:
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    schedule, _ = build_frozen_schedule(prices)
    config = load_trend_inverse_vol_config(ROOT / "config/s27_trend_inverse_vol.toml")
    trend = load_trend_config(ROOT / "config/strategy.toml")
    targets, _ = build_month_end_targets(prices, config, trend.risk_symbols)
    expected = build_execution_weights(prices, targets).dropna(how="all").loc[:, schedule.columns]
    assert schedule.equals(expected)
    assert schedule.ge(0).all().all()
    assert np.allclose(schedule.sum(axis=1), 1.0, atol=1e-12)
    replay = schedule_execution(prices, schedule)
    assert replay.dropna(how="all").index.equals(schedule.index)


def test_s10_experiment_evaluator_reproduces_frozen_targets_without_fill() -> None:
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    config = load_volatility_targeting_config(ROOT / "config/s10a_vol_targeting.toml")
    spec = RobustnessSpec(
        config.symbols,
        config.base_weights,
        config.vol_window,
        config.target_volatility,
        config.max_scale,
        config.min_scale,
        config.fees,
        config.slippage,
        config.initial_cash,
    )
    actual, _ = build_targets(prices, spec)
    expected, _ = build_frozen_s10_targets(prices, config)
    pd.testing.assert_frame_equal(actual, expected)


def test_s4c_official_erc_weights_are_long_only_and_fully_invested() -> None:
    returns = pd.DataFrame(
        np.random.default_rng(1).normal(0, 0.01, size=(60, 6)), columns=list("ABCDEF")
    )
    weights = erc_weights(returns)
    assert weights.ge(0).all()
    assert weights.sum() == pytest.approx(1.0)


def test_s4c_falls_back_when_fewer_than_six_assets_have_history() -> None:
    dates = pd.bdate_range("2024-01-02", periods=70)
    prices = pd.DataFrame(
        {symbol: 100 + np.arange(len(dates)) for symbol in ["A", "B", "C", "D", "E", "BOND"]},
        index=dates,
    )
    targets, equal, inverse, diagnostics = build_s4c_targets(
        prices, ("A", "B", "C", "D", "E"), S4CConfig("BOND")
    )
    assert diagnostics.eligible_asset_count.eq(0).all()
    for frame in (targets, equal, inverse):
        assert frame["BOND"].eq(1.0).all()


def test_s4c_solver_failure_is_not_reclassified_as_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = pd.bdate_range("2024-01-02", periods=70)
    prices = pd.DataFrame(
        {
            symbol: 100 + np.arange(len(dates)) * (1 + index / 100)
            for index, symbol in enumerate(["A", "B", "C", "D", "E", "F", "BOND"])
        },
        index=dates,
    )
    monkeypatch.setattr(
        "research.experiments.run_s4c_erc_skfolio_transfer.erc_weights",
        lambda _: (_ for _ in ()).throw(SolverFailure("synthetic failure")),
    )
    with pytest.raises(SolverFailure, match="synthetic failure"):
        build_s4c_targets(prices, ("A", "B", "C", "D", "E", "F"), S4CConfig("BOND"))


def test_s27_decision_requires_exact_replay() -> None:
    native = pd.Series(
        {
            "average_execution_date_total_absolute_weight_deviation": 0.01,
            "materially_off_target_execution_dates": 0,
            "cash_rejection_events": 0,
            "average_cash_ratio": 0.01,
            "cagr": 0.07,
            "vectorbt_cagr": 0.08,
            "max_drawdown": -0.15,
            "vectorbt_max_drawdown": -0.12,
        }
    )
    schedule = pd.DataFrame({"A": [1.0]}, index=pd.to_datetime(["2024-01-02"]))
    assert s27_decision(native, [], schedule, pd.DataFrame()) == "BLOCK_S27A_EXECUTION_REPRODUCTION"


def test_s10_decision_blocks_before_interpreting_variants() -> None:
    assert (
        s10_decision(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), False)
        == "BLOCK_S10A_ROBUSTNESS_REPRODUCTION"
    )


def test_s10_fixed_period_drawdown_uses_signed_no_worse_semantics() -> None:
    periods = pd.DataFrame(
        {
            "max_drawdown": [-0.10, -0.10, -0.10, -0.20],
            "comparator_max_drawdown": [-0.13, -0.13, -0.13, -0.10],
        }
    )
    assert fixed_period_drawdown_gate(periods)


def test_s4c_decision_blocks_insufficient_coverage() -> None:
    diagnostics = pd.DataFrame({"eligible_asset_count": [0, 0, 6]})
    assert s4c_decision(pd.DataFrame(), diagnostics) == "BLOCK_S4C_DATA_COVERAGE"
