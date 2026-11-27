"""Cross-repo v3.4.0 Tri-Pillar parity conformance tests across all 12 golden scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from research.batches.exp_v3_11_v330_integration.run import BOND_SET_TS
from tacticore.v34_reference_engine import (
    evaluate_b1_state,
    evaluate_v340_decision,
    resolve_scalar_fvo,
)

FIXTURE_PATH = Path(
    "/home/jcshi/workspace/AShareInvestor/docs/v3-offensive-system/conformance/parity_fixtures_v340.json"
)
RELEASE_V340_PATH = (
    Path(__file__).resolve().parents[1]
    / "research/ashare/releases/v3_offensive_policy_release_v3.4.0.json"
)


def _load_fixtures() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parity_fixture_metadata_matches_signed_v340_release() -> None:
    fixtures = _load_fixtures()
    release = json.loads(RELEASE_V340_PATH.read_text(encoding="utf-8"))
    assert fixtures["schema_version"] == "v340-parity-fixtures-1"
    assert fixtures["policy_version"] == "3.4.0"
    assert fixtures["policy_content_hash"] == release["content_hash"]
    assert len(fixtures["scenarios"]) == 12


def test_all_12_v340_golden_scenarios_match_field_by_field() -> None:
    fixtures = _load_fixtures()
    tol_bps = int(fixtures["tolerances"]["target_weight_bps"])
    bond_tol_bps = int(fixtures["tolerances"]["bond_target_tolerance_bps"])

    for scenario in fixtures["scenarios"]:
        sid = scenario["id"]
        exp = scenario["expected"]
        actual = evaluate_v340_decision(scenario)

        # Deterministic idempotence
        rerun = evaluate_v340_decision(scenario)
        assert json.dumps(actual, sort_keys=True) == json.dumps(rerun, sort_keys=True), sid

        # Field-by-field conformance
        assert actual["b1_state"] == exp["b1_state"], sid
        assert actual["effective_regime"] == exp["effective_regime"], sid
        assert actual["fvo_applied_delta_bps"] == exp["fvo_applied_delta_bps"], sid
        assert actual["fvo_zero_reason"] == exp["fvo_zero_reason"], sid
        assert actual["align_due"] == exp["align_due"], sid
        assert actual["bp1_permitted"] == exp["bp1_permitted"], sid
        assert actual["qualified_bp1_codes"] == exp["qualified_bp1_codes"], sid
        assert actual["rejected_bp1_reasons"] == exp["rejected_bp1_reasons"], sid
        assert actual["router_effective_cap_bps"] == exp["router_effective_cap_bps"], sid
        assert abs(actual["target_bond_bps"] - exp["target_bond_bps"]) <= bond_tol_bps, sid
        assert actual["actions_by_code"] == exp["actions_by_code"], sid
        assert actual["orders"] == exp["orders"], sid
        assert actual["post_buy_risk_bps"] == exp["post_buy_risk_bps"], sid

        assert set(actual["target_weights_bps"]) == set(exp["target_weights_bps"]), sid
        for code, exp_bps in exp["target_weights_bps"].items():
            assert abs(actual["target_weights_bps"][code] - exp_bps) <= tol_bps, (sid, code)

        # Cross-repo safety invariants
        pos_by_code = {p["code"]: p for p in scenario["positions"]}
        buy_codes = {o["code"] for o in actual["orders"] if o["side"] == "BUY"}
        sell_codes = {o["code"] for o in actual["orders"] if o["side"] == "SELL"}
        assert not (buy_codes & sell_codes), f"same-day buy+sell: {sid}"
        for o in actual["orders"]:
            if o["side"] == "SELL":
                sellable = int(pos_by_code[o["code"]]["sellable"])
                assert o["qty"] <= sellable, f"sell > sellable: {sid} {o}"
        if any(o["side"] == "BUY" and o["code"] not in BOND_SET_TS for o in actual["orders"]):
            assert actual["post_buy_risk_bps"] <= actual["router_effective_cap_bps"], sid


def test_b1_5pct_hysteresis_and_fvo_guards() -> None:
    # B1 5% hysteresis keeps EXTREME_UNDERVAL while >=0.75 / >=0.65, exits below
    assert evaluate_b1_state(0.76, 0.66, "EXTREME_UNDERVAL") == "EXTREME_UNDERVAL"
    assert evaluate_b1_state(0.74, 0.66, "EXTREME_UNDERVAL") == "NEUTRAL"
    assert evaluate_b1_state(0.19, 0.19, "EXTREME_BUBBLE") == "EXTREME_BUBBLE"
    assert evaluate_b1_state(0.21, 0.19, "EXTREME_BUBBLE") == "NEUTRAL"

    # FVO attribution <= -150bps halves bandwidth from +-1000bps to +-500bps
    halved = resolve_scalar_fvo(
        {
            "equity_delta_bps": 900,
            "expires_trade_date": "20261215",
            "ttl_trade_days": 10,
            "attribution_60d_bps": -150,
            "status": "ACTIVE",
        },
        as_of="20261130",
        b1_state="NEUTRAL",
        work_dd_bps=100,
        locked=False,
    )
    assert halved.applied_delta_bps == 500
    assert halved.effective_cap_bps == 500

    # FVO style_tilt and B2 trading keys rejected
    with pytest.raises(ValueError, match="fvo_style_tilt_forbidden"):
        resolve_scalar_fvo(
            {"equity_delta_bps": 200, "style_tilt": "GROWTH"},
            as_of="20261130",
            b1_state="NEUTRAL",
            work_dd_bps=100,
            locked=False,
        )
    with pytest.raises(ValueError, match="b2_trading_keys_forbidden"):
        evaluate_v340_decision({"implied_expectation_tilt": "IMPROVING_STEEP"})


def test_nav_95k_bp1_reverify_gate_and_fvo_floor_cap_clamp() -> None:
    fixtures = _load_fixtures()
    s12 = dict(fixtures["scenarios"][-1])
    s12["bp1_reverified"] = False
    res = evaluate_v340_decision(s12)
    assert res["bp1_permitted"] is False
    assert "600036.SH" not in res["actions_by_code"]

    # OFFENSIVE +800bps FVO clamped at 8500bps Cap
    s08 = dict(fixtures["scenarios"][7])
    s08["regime"] = "OFFENSIVE"
    res_cap = evaluate_v340_decision(s08)
    assert res_cap["router_effective_cap_bps"] == 8500

    # DEFENSIVE -800bps FVO clamped at 2500bps Floor
    s08_floor = dict(fixtures["scenarios"][7])
    s08_floor["regime"] = "DEFENSIVE"
    s08_floor["fvo"] = {
        "overlay_id": "fvo-floor",
        "equity_delta_bps": -800,
        "expires_trade_date": "20261215",
        "ttl_trade_days": 10,
        "attribution_60d_bps": 0,
        "status": "ACTIVE",
    }
    res_floor = evaluate_v340_decision(s08_floor)
    assert res_floor["router_effective_cap_bps"] == 2500
