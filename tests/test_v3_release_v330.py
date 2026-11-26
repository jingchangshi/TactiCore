"""v3.3.0 PolicyRelease: five-mechanism integration + TWO_STAGE_GRADUAL approval."""

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

AMENDMENT_V330_REV = "9c736c2f35a9be73971aacf81440343a491819ca"
AMENDMENT_V330_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261126_V330.md"


def _path(version: str) -> Path:
    return RELEASE_DIR / f"v3_offensive_policy_release_v{version}.json"


def _load(version: str) -> dict:
    return json.loads(_path(version).read_text(encoding="utf-8"))


def test_v330_validates_and_matches_winner_parameters() -> None:
    release = _load("3.3.0")
    digest = validate_strategy_release(release)
    assert digest == release["content_hash"]
    assert release["strategy"]["version"] == "3.3.0"
    assert release["production_admission"] == "APPROVED_FOR_ACCOUNT"

    p = release["parameters"]
    assert p["recovery_overlay_enabled"] == "true"
    assert p["recovery_overlay_mode"] == "M2_BREADTH_THRUST"
    assert p["recovery_equity_bps"] == "4000"
    assert p["lowvol_core_permanent_share_bps"] == "3000"
    assert p["defensive_bond_reservoir_etf"] == "159649.SZ"
    assert p["defensive_bond_reservoir_fallback_etf"] == "511260.SH"
    assert p["defensive_bond_reservoir_drift_band_bps"] == "1000"
    assert p["drawdown_control_mode"] == "TWO_STAGE_GRADUAL"
    assert p["drawdown_stage1_bps"] == "800"
    assert p["drawdown_stage1_cap_bps"] == "5000"
    assert p["drawdown_stage2_bps"] == "1100"
    assert p["drawdown_stage2_cap_bps"] == "2500"
    assert p["drawdown_lock_trigger_bps"] == "1350"
    assert p["drawdown_unlock_reanchor_enabled"] == "true"
    assert p["drawdown_unlock_ramp_trade_days"] == "10"
    assert p["sector_pioneer_enabled"] == "true"
    assert p["sector_pioneer_rank_mode"] == "BLEND_20_60"
    assert p["sector_pioneer_max_weight_bps"] == "2000"
    assert p["stock_bp1_min_investable_nav_cny"] == "100000"
    assert p["stock_bp1_block_during_deconcentration"] == "true"
    assert (
        p["supersedes_release_content_hash"]
        == "9869bd0b0ef02336c09fbaab921f5545d069a60039957c6f58b3fa1736e7eb9a"
    )
    assert "tushare" not in json.dumps(release, ensure_ascii=False).lower()


def test_v330_tamper_rejected() -> None:
    release = _load("3.3.0")
    mutated = copy.deepcopy(release)
    mutated["parameters"]["drawdown_control_mode"] = "CPPI_F15_M5"
    with pytest.raises(ValueError, match="invalid_strategy_release"):
        validate_strategy_release(mutated)


@pytest.mark.skipif(
    not (ASHARE_INVESTOR_ROOT / ".git").exists(), reason="AShareInvestor repo not present"
)
def test_v330_amendment_hash_and_cross_repo_parity() -> None:
    blob = subprocess.run(
        [
            "git",
            "-C",
            str(ASHARE_INVESTOR_ROOT),
            "show",
            f"{AMENDMENT_V330_REV}:{AMENDMENT_V330_PATH}",
        ],
        check=True,
        capture_output=True,
    ).stdout
    release = _load("3.3.0")
    assert (
        hashlib.sha256(blob).hexdigest() == release["parameters"]["policy_amendment_record_sha256"]
    )
    copy_path = FEE_PROFILE_DIR / "v3_offensive_policy_release_v3.3.0.json"
    assert copy_path.exists()
    assert copy_path.read_bytes() == _path("3.3.0").read_bytes()
