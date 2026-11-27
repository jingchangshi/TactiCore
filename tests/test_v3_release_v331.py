"""v3.3.1 PolicyRelease: Execution Architecture v2 + strict schema & cross-repo parity."""

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

AMENDMENT_V331_REV = "f91cfe1c622025cd7a846843d48232ddba04a740"
AMENDMENT_V331_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261127_V331.md"
V330_CONTENT_HASH = "e192ffc764f2bcf5ccd020e62254d1e1b518a6ab7a9074acd1d91c74a5462051"


def _path(version: str) -> Path:
    return RELEASE_DIR / f"v3_offensive_policy_release_v{version}.json"


def _load(version: str) -> dict:
    return json.loads(_path(version).read_text(encoding="utf-8"))


def test_v331_validates_and_matches_strict_schema() -> None:
    release = _load("3.3.1")
    digest = validate_strategy_release(release)
    assert digest == release["content_hash"]
    assert release["strategy"]["version"] == "3.3.1"
    assert release["production_admission"] == "APPROVED_FOR_ACCOUNT"

    p = release["parameters"]
    assert p["sector_pioneer_enabled"] == "false"
    assert p["deconcentration_plan_enabled"] == "false"
    assert p["deconcentration_mode"] == "BOTTOM_GRIND_25"
    assert p["regime_target_enforced_on_existing_holdings"] == "true"
    assert p["align_glide_carryover_bps"] == "3500"
    assert p["equity_align_drift_band_bps"] == "500"
    assert p["chassis_single_etf_per_style_bucket"] == "true"
    assert p["p1_etf_trailing_sleeves"] == "SECTOR_PIONEER"
    assert "l2_lock_allow_m2_early_release" not in p

    # Alias consistency checks mirrored from FinanceMCP validateV331Parameters
    assert p["l1_warn_drawdown_bps"] == p["drawdown_stage1_bps"] == "800"
    assert (
        p["l2_normal_trigger_drawdown_bps"]
        == p["drawdown_lock_trigger_bps"]
        == p["l2_hard_lifeline_drawdown_bps"]
        == "1350"
    )
    assert (
        p["l2_normal_post_breaker_equity_bps"] == p["drawdown_normal_post_lock_cap_bps"] == "1000"
    )
    assert (
        p["l2_deconcentration_post_breaker_equity_bps"]
        == p["drawdown_conc_post_lock_cap_bps"]
        == "0"
    )
    assert p["l2_lock_trade_days"] == "10"

    assert p["supersedes_release_version"] == "3.3.0"
    assert p["supersedes_release_content_hash"] == V330_CONTENT_HASH
    assert "tushare" not in json.dumps(release, ensure_ascii=False).lower()


def test_v331_tamper_rejected() -> None:
    release = _load("3.3.1")
    mutated = copy.deepcopy(release)
    mutated["parameters"]["sector_pioneer_enabled"] = "true"
    with pytest.raises(ValueError, match="invalid_strategy_release"):
        validate_strategy_release(mutated)


@pytest.mark.skipif(
    not (ASHARE_INVESTOR_ROOT / ".git").exists(), reason="AShareInvestor repo not present"
)
def test_v331_amendment_hash_and_cross_repo_parity() -> None:
    blob = subprocess.run(
        [
            "git",
            "-C",
            str(ASHARE_INVESTOR_ROOT),
            "show",
            f"{AMENDMENT_V331_REV}:{AMENDMENT_V331_PATH}",
        ],
        check=True,
        capture_output=True,
    ).stdout
    release = _load("3.3.1")
    assert (
        hashlib.sha256(blob).hexdigest() == release["parameters"]["policy_amendment_record_sha256"]
    )
    copy_path = FEE_PROFILE_DIR / "v3_offensive_policy_release_v3.3.1.json"
    assert copy_path.exists()
    assert copy_path.read_bytes() == _path("3.3.1").read_bytes()
