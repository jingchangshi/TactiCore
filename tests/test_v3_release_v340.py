"""v3.4.0 Tri-Pillar PolicyRelease: strict schema, B2 rejection, and cross-repo parity."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tacticore.strategy_release import validate_strategy_release

TACTICORE_ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = TACTICORE_ROOT / "research/ashare/releases"
ASHARE_INVESTOR_ROOT = Path("/home/jcshi/workspace/AShareInvestor")
FEE_PROFILE_DIR = ASHARE_INVESTOR_ROOT / "docs/v3-offensive-system/fee-profiles"

AMENDMENT_V340_REV = "8d177ec97305be932af4f13d8914b462a75972e2"
AMENDMENT_V340_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261128_V340.md"
V331_CONTENT_HASH = "29ad8fa8e2123df838f0c53630d77e9351dd60ee0ba8ac323e77480da2f9bb50"


def _path(version: str) -> Path:
    return RELEASE_DIR / f"v3_offensive_policy_release_v{version}.json"


def _load(version: str) -> dict:
    return json.loads(_path(version).read_text(encoding="utf-8"))


def _rehash(value: dict) -> dict:
    payload = {key: val for key, val in value.items() if key != "content_hash"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    value["content_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return value


def test_v340_validates_and_matches_strict_schema() -> None:
    release = _load("3.4.0")
    digest = validate_strategy_release(release)
    assert digest == release["content_hash"]
    assert release["strategy"]["version"] == "3.4.0"
    assert release["production_admission"] == "APPROVED_FOR_ACCOUNT"
    assert "518880.SH" in release["inputs"]["assets"]

    p = release["parameters"]
    assert p["lowvol_core_mode"] == "CORE_40"
    assert p["lowvol_core_permanent_share_bps"] == "1500"
    assert p["gold_core_etf"] == "518880.SH"
    assert p["gold_core_share_bps"] == "1000"
    assert p["gold_core_drift_band_bps"] == "400"
    assert p["gold_core_min_trade_cny"] == "5000"
    assert p["strategic_bond_core_share_bps"] == "1500"
    assert p["defensive_bond_reservoir_etf"] == "159649.SZ"
    assert p["defensive_bond_reservoir_drift_band_bps"] == "1000"
    assert p["satellite_max_share_bps"] == "6000"

    assert p["defensive_equity_bps"] == "2500"
    assert p["ice10_floor_enabled"] == "true"
    assert p["ice10_equity_bps"] == "3500"
    assert p["ice10_window_trade_days"] == "15"
    assert p["ice10_disable_on_p0_lock"] == "true"

    assert p["fundamental_envelope_enabled"] == "true"
    assert p["fundamental_envelope_mode"] == "B1_PIT_ERP_BP_DUAL_756D"
    assert p["fundamental_underval_ice10_bps"] == "4250"
    assert p["fundamental_underval_recovery_bps"] == "5000"
    assert p["fundamental_underval_structural_bps"] == "6500"
    assert p["fundamental_underval_defensive_bps"] == "2500"
    assert p["fundamental_bubble_offensive_bps"] == "7000"
    assert p["fundamental_bubble_structural_bps"] == "5000"
    assert p["fundamental_bubble_ice10_bps"] == "3500"

    assert p["align_trigger_mode"] == "REGIME_ONLY"
    assert p["equity_align_drift_band_bps"] == "1000"
    assert p["quality_core_version"] == "v2"
    assert p["quality_core_roe_dt_ann_min_bps"] == "600"
    assert p["quality_core_ocf_to_profit_min_bps"] == "5000"
    assert p["stock_bp1_min_investable_nav_cny"] == "100000"
    assert p["stock_bp1_reverify_nav_cny"] == "95000"

    assert p["fvo_enabled"] == "true"
    assert p["fvo_scalar_only"] == "true"
    assert p["fvo_equity_delta_default_bps"] == "0"
    assert p["fvo_max_abs_delta_bps"] == "1000"
    assert p["fvo_max_ttl_trade_days"] == "20"
    assert p["fvo_zero_positive_on_l1_or_bubble"] == "true"
    assert p["fvo_60d_attribution_halve_trigger_bps"] == "-150"
    assert p["fvo_60d_attribution_halved_cap_bps"] == "500"

    assert p["policy_freeze_start_date"] == "2026-11-30"
    assert p["policy_freeze_end_date"] == "2027-02-28"
    assert p["supersedes_release_version"] == "3.3.1"
    assert p["supersedes_release_content_hash"] == V331_CONTENT_HASH
    assert "tushare" not in json.dumps(release, ensure_ascii=False).lower()


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "implied_expectation_tilt",
        "b2_implied_expectation_tilt_enabled",
        "b2_tilt_step_bps",
        "l2_lock_allow_m2_early_release",
        "fvo_style_tilt",
    ],
)
def test_v340_rejects_forbidden_b2_m2_and_style_tilt_keys(forbidden_key: str) -> None:
    release = _load("3.4.0")
    mutated = copy.deepcopy(release)
    mutated["parameters"][forbidden_key] = "true"
    _rehash(mutated)
    with pytest.raises(ValueError, match="invalid_strategy_release"):
        validate_strategy_release(mutated)


def test_v340_tamper_rejected() -> None:
    release = _load("3.4.0")
    mutated = copy.deepcopy(release)
    mutated["parameters"]["gold_core_share_bps"] = "500"
    with pytest.raises(ValueError, match="invalid_strategy_release"):
        validate_strategy_release(mutated)


@pytest.mark.skipif(
    not (ASHARE_INVESTOR_ROOT / ".git").exists(), reason="AShareInvestor repo not present"
)
def test_v340_amendment_hash_and_cross_repo_parity() -> None:
    blob = subprocess.run(
        [
            "git",
            "-C",
            str(ASHARE_INVESTOR_ROOT),
            "show",
            f"{AMENDMENT_V340_REV}:{AMENDMENT_V340_PATH}",
        ],
        check=True,
        capture_output=True,
    ).stdout
    release = _load("3.4.0")
    assert (
        hashlib.sha256(blob).hexdigest() == release["parameters"]["policy_amendment_record_sha256"]
    )
    copy_path = FEE_PROFILE_DIR / "v3_offensive_policy_release_v3.4.0.json"
    assert copy_path.exists()
    assert copy_path.read_bytes() == _path("3.4.0").read_bytes()
