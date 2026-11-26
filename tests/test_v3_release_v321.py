"""v3.2.1 PolicyRelease: owner-approved 2026-11-24 stock semantics; signed archives untouched."""

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

# Raw file-byte SHA-256 of the signed archives as committed before v3.2.1 existed.
SIGNED_FILE_SHA256 = {
    "3.1.0": "d714c5d86662d14aa34bc8bf9e14b6a07a1d3656168a2c28c2a32584fe65fc1e",
    "3.2.0": "f5837f16686b0f152beb739ea5be1b999d0db3bb90d312c0869901a8be7e4104",
}
SIGNED_CONTENT_HASH = {
    "3.1.0": "eeacd72de68d463a045a1be1159bede7b3dbae13da92f9b05e68983995e4e008",
    "3.2.0": "05346a961e01f746055143e0bb5790caa9d6460aa579bb26c085cca20d77b55f",
}
V321_CONTENT_HASH = "9869bd0b0ef02336c09fbaab921f5545d069a60039957c6f58b3fa1736e7eb9a"
AMENDMENT_REV = "4979c41dad246a6050fb71d8f2576216dfe60616"
AMENDMENT_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261124.md"


def _path(version: str) -> Path:
    return RELEASE_DIR / f"v3_offensive_policy_release_v{version}.json"


def _load(version: str) -> dict:
    return json.loads(_path(version).read_text(encoding="utf-8"))


def _builder_inputs_available() -> bool:
    try:
        from research.ashare.v3_data import SNAPSHOT_DIR, WHITELIST_PATH
    except Exception:  # noqa: BLE001 - research extras absent in a minimal env
        return False
    amendment_repo = (ASHARE_INVESTOR_ROOT / ".git").exists()
    return (
        (SNAPSHOT_DIR / "manifest.json").is_file() and WHITELIST_PATH.is_file() and (amendment_repo)
    )


needs_inputs = pytest.mark.skipif(
    not _builder_inputs_available(),
    reason="PIT snapshot manifest / whitelist / AShareInvestor repo not present on this host",
)


@pytest.mark.parametrize("version", ["3.1.0", "3.2.0"])
def test_signed_archive_bytes_unchanged(version: str) -> None:
    raw = _path(version).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SIGNED_FILE_SHA256[version]
    assert validate_strategy_release(json.loads(raw)) == SIGNED_CONTENT_HASH[version]


@needs_inputs
@pytest.mark.parametrize("version", ["3.1.0", "3.2.0", "3.2.1"])
def test_builder_reproduces_committed_release_byte_for_byte(version: str) -> None:
    from research.ashare.build_v3_release import build_v3_release_payload, render_release

    rendered = render_release(build_v3_release_payload(version)).encode("utf-8")
    assert rendered == _path(version).read_bytes()


@needs_inputs
def test_emit_refuses_to_overwrite_a_differing_signed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from research.ashare import build_v3_release as builder

    target = tmp_path / "v3_offensive_policy_release_v3.2.0.json"
    original = _path("3.2.0").read_bytes()
    target.write_bytes(original.replace(b'"1200"', b'"1300"', 1))
    monkeypatch.setattr(builder, "output_paths", lambda version: (target,))
    with pytest.raises(RuntimeError, match="signed_release_drift"):
        builder.emit_release("3.2.0")
    assert target.read_bytes() != original  # untouched, not "repaired" by re-signing


def test_v321_validates_and_encodes_owner_amendment() -> None:
    release = _load("3.2.1")
    assert validate_strategy_release(release) == V321_CONTENT_HASH
    assert release["strategy"]["version"] == "3.2.1"
    assert release["production_admission"] == "APPROVED_FOR_ACCOUNT"
    p = release["parameters"]
    assert p["stock_industry_top30_gate_default"] == "false"
    assert p["stock_industry_top30_gate_research_switch"] == "requireIndustryTop30"
    assert p["stock_ma20_exit_mode"] == "UNCONDITIONAL_CLOSE_BELOW_MA20_NEXT_SESSION"
    assert p["stock_ma20_exit_requires_breakeven_arm"] == "false"
    assert p["stock_breakeven_arm_effect"] == "RAISE_STOP_TO_COST_ONLY"
    assert p["stock_breakeven_arm_gain_bps"] == "1500"
    assert p["etf_trailing_ma20_requires_arm"] == "true"
    assert p["etf_trailing_ma20_arm_gain_bps"] == "1500"
    assert p["policy_amendment_owner_approval_date"] == "2026-11-24"
    assert p["supersedes_release_content_hash"] == SIGNED_CONTENT_HASH["3.2.0"]
    refs = {e["reference"]: e["sha256"] for e in release["evidence"]}
    amendment_ref = f"git:AShareInvestor@{AMENDMENT_REV}:{AMENDMENT_PATH}"
    assert refs[amendment_ref] == p["policy_amendment_record_sha256"]
    assert "tushare" not in json.dumps(release, ensure_ascii=False).lower()


def test_v321_differs_from_v320_only_in_amended_semantics() -> None:
    v320, v321 = _load("3.2.0"), _load("3.2.1")
    for key in ("schema_version", "research_status", "applicability", "inputs"):
        assert v321[key] == v320[key]
    assert v321["strategy"]["id"] == v320["strategy"]["id"]
    # Implementation unchanged: v3_data.py carries the same signed hash in all three releases.
    assert v321["strategy"]["implementation_sha256"] == v320["strategy"]["implementation_sha256"]
    for key in ("signal_timing", "earliest_execution", "fees", "lot_size"):
        assert v321["execution_assumptions"][key] == v320["execution_assumptions"][key]
    # Every v3.2.0 parameter is carried with the identical value; only new keys are added.
    for key, value in v320["parameters"].items():
        assert v321["parameters"][key] == value
    # Only the stock exit rule is rewritten; every other v3.2.0 rule is verbatim.
    stock_rule = v320["rules"][4]
    assert stock_rule.startswith("Every stock pioneer trade")
    assert [r for r in v320["rules"] if r != stock_rule] == [
        r for r in v321["rules"][: len(v320["rules"])] if not r.startswith("Every stock pioneer")
    ]
    assert "unconditionally" in v321["rules"][4]
    # v3.2.0 evidence is a strict prefix of v3.2.1 evidence.
    assert v321["evidence"][: len(v320["evidence"])] == v320["evidence"]


def test_v321_tamper_rejected() -> None:
    release = _load("3.2.1")
    mutated = copy.deepcopy(release)
    mutated["parameters"]["stock_ma20_exit_requires_breakeven_arm"] = "true"
    with pytest.raises(ValueError, match="invalid_strategy_release"):
        validate_strategy_release(mutated)


@pytest.mark.skipif(
    not (ASHARE_INVESTOR_ROOT / ".git").exists(), reason="AShareInvestor repo not present"
)
def test_amendment_hash_is_pinned_git_blob_and_copy_parity() -> None:
    blob = subprocess.run(
        ["git", "-C", str(ASHARE_INVESTOR_ROOT), "show", f"{AMENDMENT_REV}:{AMENDMENT_PATH}"],
        check=True,
        capture_output=True,
    ).stdout
    release = _load("3.2.1")
    assert (
        hashlib.sha256(blob).hexdigest() == release["parameters"]["policy_amendment_record_sha256"]
    )
    copy_path = FEE_PROFILE_DIR / "v3_offensive_policy_release_v3.2.1.json"
    if copy_path.exists():
        assert copy_path.read_bytes() == _path("3.2.1").read_bytes()
