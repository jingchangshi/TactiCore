"""Cross-repo v3.3.1 Execution Architecture v2 parity conformance tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.batches.exp_v3_11_v330_integration.run import BOND_SET_TS
from research.batches.exp_v3_12_v331_architecture.decision_parity import (
    evaluate_v331_decision,
)

FIXTURE_PATH = Path(
    "/home/jcshi/workspace/AShareInvestor/docs/v3-offensive-system/conformance/parity_fixtures_v331.json"
)
RELEASE_V331_PATH = (
    Path(__file__).resolve().parents[1]
    / "research/ashare/releases/v3_offensive_policy_release_v3.3.1.json"
)


def _load_fixtures() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parity_fixture_metadata_matches_signed_v331_release() -> None:
    fixtures = _load_fixtures()
    release = json.loads(RELEASE_V331_PATH.read_text(encoding="utf-8"))
    assert fixtures["schema_version"] == "v331-parity-fixtures-1"
    assert fixtures["policy_version"] == "3.3.1"
    assert fixtures["policy_content_hash"] == release["content_hash"]
    assert 12 <= len(fixtures["scenarios"]) <= 15


def test_all_v331_parity_scenarios_match_decision_reference() -> None:
    fixtures = _load_fixtures()
    tol_bps = int(fixtures["tolerances"]["target_weight_bps"])
    for scenario in fixtures["scenarios"]:
        sid = scenario["id"]
        exp = scenario["expected"]
        inv = exp["invariants"]

        actual = evaluate_v331_decision(scenario)
        if inv.get("idempotent_if_rerun", True):
            rerun = evaluate_v331_decision(scenario)
            assert json.dumps(actual, sort_keys=True) == json.dumps(rerun, sort_keys=True), sid

        assert actual["align_due"] == exp["align_due"], sid
        assert actual["router_effective_cap_bps"] == exp["router_effective_cap_bps"], sid
        assert actual["actions_by_code"] == exp["actions_by_code"], sid
        assert actual["orders"] == exp["orders"], sid

        # Target equity weight parity (<= 50 bps)
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
            if o["code"] not in BOND_SET_TS:
                assert o["stage"] != 1 or o["reason"] not in {"HARD_STOP_8PCT", "MA20_TRAILING"}, (
                    f"unexpected P1 ETF sell: {sid} {o}"
                )

        assert len(actual["target_weights_bps"]) <= 4, f"chassis > 4 ETFs: {sid}"
        if inv.get("zero_actions", False):
            assert actual["orders"] == [], sid
        if any(o["side"] == "BUY" and o["code"] not in BOND_SET_TS for o in actual["orders"]):
            assert actual["post_buy_risk_bps"] <= actual["router_effective_cap_bps"], sid
