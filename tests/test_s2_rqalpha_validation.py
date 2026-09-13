import hashlib
from pathlib import Path

import pandas as pd

from research.experiments.run_s2_rqalpha_validation import (
    actual_weight_table,
    build_frozen_target_schedule,
    build_symbol_mapping,
    parse_native_results,
    target_for_replay,
)
from tacticore.data.prices import load_price_csv
from tacticore.strategies.multi_asset_trend import (
    build_month_end_targets,
    build_signal_change_execution_weights,
    load_trend_config,
)

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_target_schedule_is_stable_and_contains_only_changes() -> None:
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    config = load_trend_config(ROOT / "config/strategy.toml")
    schedule = build_frozen_target_schedule(prices, config)
    expected_dates = (
        build_signal_change_execution_weights(prices, build_month_end_targets(prices, config))
        .dropna(how="all")
        .index
    )
    serialized = schedule.reset_index().to_csv(
        index=False, float_format="%.8f", lineterminator="\n"
    )

    assert schedule.index.equals(expected_dates)
    assert len(schedule) == 103
    assert hashlib.sha256(serialized.encode()).hexdigest() == (
        "9cc5a8e70751f274cb7c4f900784400bd8de684450833ba6d4034fd75ca70b61"
    )


def test_symbol_mapping_matches_frozen_s2_universe() -> None:
    config = load_trend_config(ROOT / "config/strategy.toml")
    symbols = [*config.risk_symbols, config.fallback_symbol]

    mapping = build_symbol_mapping(ROOT / "config/universe.csv", symbols)

    assert mapping["510300.SS"] == "510300.XSHG"
    assert mapping["159920.SZ"] == "159920.XSHE"
    assert mapping["511010.SS"] == "511010.XSHG"
    assert set(mapping) == set(symbols)


def test_target_is_never_replayed_before_or_between_execution_dates() -> None:
    schedule = pd.DataFrame(
        {"A": [1.0, 0.0], "BOND": [0.0, 1.0]},
        index=pd.to_datetime(["2024-02-01", "2024-04-01"]),
    )
    mapping = {"A": "A.XSHG", "BOND": "BOND.XSHG"}

    assert target_for_replay(schedule, mapping, pd.Timestamp("2024-01-31 15:00")) is None
    assert target_for_replay(schedule, mapping, pd.Timestamp("2024-03-01 15:00")) is None
    assert target_for_replay(schedule, mapping, pd.Timestamp("2024-02-01 15:00")) == {"A.XSHG": 1.0}
    assert target_for_replay(schedule, mapping, pd.Timestamp("2024-04-01 15:00")) == {
        "BOND.XSHG": 1.0
    }


def test_s2_v2_historical_evidence_is_unchanged() -> None:
    report = ROOT / "research/results/S2_DECISION_AUDIT_V2.md"

    assert hashlib.sha256(report.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == (
        "6118d8ff605dd8204a1b0b2c350825c4fc6b9252f005395da747d83fdf9c100a"
    )


def test_rqalpha_native_results_are_parsed_without_recomputing_risk() -> None:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    analyser = {
        "summary": {
            "total_returns": 0.12,
            "annualized_returns": 0.08,
            "max_drawdown": 0.09,
            "sharpe": 0.7,
            "cash": 123.0,
            "turnover": 2.5,
        },
        "trades": pd.DataFrame({"transaction_cost": [2.0, 3.0]}),
        "stock_account": pd.DataFrame({"cash": [500.0, 123.0]}, index=dates),
        "portfolio": pd.DataFrame(
            {"cash": [500.0, 123.0], "total_value": [1_000.0, 1_100.0]}, index=dates
        ),
    }
    events = pd.DataFrame(
        {
            "event": ["ORDER_CREATION_PASS", "ORDER_CREATION_REJECT"],
            "order_id": [1, None],
            "status": ["ACTIVE", "REJECTED"],
            "message": ["", "not enough money"],
        }
    )

    parsed = parse_native_results(analyser, events).iloc[0]

    assert parsed["total_return"] == 0.12
    assert parsed["cagr"] == 0.08
    assert parsed["max_drawdown"] == -0.09
    assert parsed["sharpe"] == 0.7
    assert parsed["transaction_cost"] == 5.0
    assert parsed["native_order_count"] == 1
    assert parsed["native_failed_order_events"] == 1
    assert parsed["cash_failure_events"] == 1
    assert parsed["cash_rejection_events"] == 1
    assert parsed["cash_residual_cancellation_events"] == 0
    assert parsed["trade_count"] == 2


def test_missing_native_position_is_treated_as_zero_weight() -> None:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    analyser = {
        "portfolio": pd.DataFrame(
            {"cash": [500.0, 600.0], "total_value": [1_000.0, 1_000.0]}, index=dates
        ),
        "stock_positions": pd.DataFrame(
            {
                "order_book_id": ["A.XSHG", "B.XSHG", "A.XSHG"],
                "market_value": [300.0, 200.0, 400.0],
            },
            index=pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-03"]),
        ),
    }

    weights = actual_weight_table(analyser, {"A.XSHG": "A", "B.XSHG": "B"}, ["A", "B"])

    assert weights.loc[dates[0]].to_dict() == {"A": 0.3, "B": 0.2, "cash": 0.5}
    assert weights.loc[dates[1]].to_dict() == {"A": 0.4, "B": 0.0, "cash": 0.6}
