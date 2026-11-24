"""V3 Offensive System Phase 2 governance, gate, release, and frozen-boundary tests."""

from __future__ import annotations

import ast
import copy
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from research.ashare.data.contract import sha256_file
from research.ashare.v3_data import (
    _chain_bundle_tail_adjusted_close,
    _chain_snapshot_only_adjusted_close,
    _daily_total_return_multiplier,
)
from tacticore.strategy_release import validate_strategy_release

TACTICORE_ROOT = Path(__file__).resolve().parents[1]
ASHARE_INVESTOR_ROOT = TACTICORE_ROOT.parent / "AShareInvestor"

RELEASE_TC_V31 = TACTICORE_ROOT / "research/ashare/releases/v3_offensive_policy_release_v3.1.0.json"
RELEASE_AI_V31 = (
    ASHARE_INVESTOR_ROOT
    / "docs/v3-offensive-system/fee-profiles/v3_offensive_policy_release_v3.1.0.json"
)
RELEASE_TC = TACTICORE_ROOT / "research/ashare/releases/v3_offensive_policy_release_v3.2.0.json"
RELEASE_AI = (
    ASHARE_INVESTOR_ROOT
    / "docs/v3-offensive-system/fee-profiles/v3_offensive_policy_release_v3.2.0.json"
)

GATE_FIELDS = (
    "Canonical mapping",
    "External tier",
    "External conclusion",
    "Relevant contradictions",
    "Upstream implementation",
    "Existing TactiCore evidence",
    "Remaining local gap",
    "Research action",
)
PIT_ITEMS = ("1.", "2.", "3.", "4.", "5.", "6.")


def test_evidence_registry_contains_complete_v3_entries() -> None:
    registry_path = TACTICORE_ROOT / "research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml"
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    sources = data["sources"]
    entries = {entry["strategy_id"]: entry for entry in data["entries"]}

    expected = {
        "V3_DUAL_ANCHOR_SUPER_ETF": "APPROVED_FOR_ACCOUNT_V3",
        "V3_MAINBOARD_SWING_BREAKOUT_PULLBACK": "BP1_APPROVED_BP2_REJECTED_OOS",
        "V3_CONCENTRATED_SECTOR_EXIT": "APPROVED_PREEMPTIVE_L2_V3",
        "V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION": "APPROVED_BOTTOM_GRIND_25_V32",
    }
    for sid, expected_status in expected.items():
        assert sid in entries
        entry = entries[sid]
        assert entry["tacticore"]["local_status"] == expected_status
        assert entry["tacticore"]["local_evidence_refs"]
        for src_id in entry["canonical_sources"]:
            assert src_id in sources


def test_goal_and_experiment_docstrings_have_required_gates() -> None:
    goal_text = (TACTICORE_ROOT / "docs/goal.md").read_text(encoding="utf-8")
    for field in GATE_FIELDS:
        assert field in goal_text, f"Missing {field} in docs/goal.md"
    for item in PIT_ITEMS:
        assert item in goal_text, f"Missing PIT item {item} in docs/goal.md"

    exp_files = (
        TACTICORE_ROOT / "research/ashare/experiments/exp_v3_01_regime_super_etf.py",
        TACTICORE_ROOT / "research/ashare/experiments/exp_v3_02_stock_swing_rqalpha.py",
        TACTICORE_ROOT / "research/ashare/experiments/exp_v3_03_deconcentration_paths.py",
        TACTICORE_ROOT / "research/ashare/experiments/exp_v3_04_bottom_grind_cost_reduction.py",
    )
    for path in exp_files:
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
        assert doc is not None
        for field in GATE_FIELDS:
            assert field in doc, f"Missing {field} in {path.name}"
        for item in PIT_ITEMS:
            assert item in doc, f"Missing PIT item {item} in {path.name}"


def test_v3_policy_release_parity_and_tamper_rejection() -> None:
    assert RELEASE_TC_V31.exists()
    if ASHARE_INVESTOR_ROOT.is_dir():
        assert RELEASE_AI_V31.exists()
        assert RELEASE_TC_V31.read_bytes() == RELEASE_AI_V31.read_bytes()

    assert RELEASE_TC.exists()
    raw_tc = RELEASE_TC.read_bytes()
    if ASHARE_INVESTOR_ROOT.is_dir():
        assert RELEASE_AI.exists()
        assert raw_tc == RELEASE_AI.read_bytes()

    payload = json.loads(raw_tc.decode("utf-8"))
    verified_hash = validate_strategy_release(payload)
    assert verified_hash == payload["content_hash"]
    assert payload["production_admission"] == "APPROVED_FOR_ACCOUNT"
    assert payload["parameters"]["bp1_pullback_status"] == "ENABLED"
    assert payload["parameters"]["bp2_breakout_status"] == "DROPPED_NEGATIVE_OOS"
    assert payload["parameters"]["l2_preemptive_trigger_drawdown_bps"] == "1200"
    assert payload["parameters"]["l2_deconcentration_post_breaker_equity_bps"] == "0"
    assert payload["parameters"]["deconcentration_mode"] == "BOTTOM_GRIND_25"
    assert payload["parameters"]["deconcentration_keep_weight_bps"] == "2500"
    assert payload["parameters"]["grind_tactical_slot_bps"] == "1000"
    assert payload["parameters"]["grind_take_profit_bps"] == "750"
    assert payload["parameters"]["grind_drift_harvest_trigger_bps"] == "3400"

    mutated_param = copy.deepcopy(payload)
    mutated_param["parameters"]["l2_preemptive_trigger_drawdown_bps"] = "1300"
    with pytest.raises(ValueError, match="invalid_strategy_release"):
        validate_strategy_release(mutated_param)

    mutated_hash = copy.deepcopy(payload)
    flip = "0" if mutated_hash["content_hash"][-1] != "0" else "1"
    mutated_hash["content_hash"] = mutated_hash["content_hash"][:-1] + flip
    with pytest.raises(ValueError, match="invalid_strategy_release"):
        validate_strategy_release(mutated_hash)


def test_release_evidence_hashes_match_on_disk() -> None:
    payload = json.loads(RELEASE_TC.read_text(encoding="utf-8"))
    evidence = payload["evidence"]
    refs = {item["reference"]: item["sha256"] for item in evidence}

    expected_local = (
        "research/results/EXP_V3_01_REGIME_SUPER_ETF.json",
        "research/results/EXP_V3_01_REGIME_SUPER_ETF.md",
        "research/results/EXP_V3_02_MAINBOARD_STOCK_SWING.json",
        "research/results/EXP_V3_02_MAINBOARD_STOCK_SWING.md",
        "research/results/EXP_V3_03_DECONCENTRATION_PATHS.json",
        "research/results/EXP_V3_03_DECONCENTRATION_PATHS.md",
        "research/results/EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.json",
        "research/results/EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.md",
    )
    for rel in expected_local:
        target = TACTICORE_ROOT / rel
        assert rel in refs
        assert target.exists()
        assert sha256_file(target) == refs[rel]

    for ref, recorded_sha in refs.items():
        path = Path(ref) if Path(ref).is_absolute() else (TACTICORE_ROOT / ref)
        if not path.is_absolute():
            assert path.exists()
            assert sha256_file(path) == recorded_sha
        elif path.exists():
            assert sha256_file(path) == recorded_sha


def test_frozen_shadow_and_transfer_artifacts_untouched() -> None:
    # vectorbt_adapter.py 曾在此守卫中；2026-11-23 的契约加固显式修改了它的
    # 零方差 Sharpe 与首日换手语义，改由 test_adapters.py 的显式测试保护。
    frozen_paths = (
        "research/shadow/s2_r1/candidate_manifest.json",
        "research/shadow/s4c_r1/candidate_manifest.json",
        "research/results/ACCOUNT_TRANSFER_V1.json",
        "tacticore/engines/rqalpha_adapter.py",
    )
    res = subprocess.run(
        ["git", "-C", str(TACTICORE_ROOT), "status", "--porcelain", "--", *frozen_paths],
        check=True,
        capture_output=True,
        text=True,
    )
    assert res.stdout.strip() == ""


# --------------------------------------------------------------------------------------
# 复权串联：缺失 pre_close 不是零收益
# --------------------------------------------------------------------------------------


def test_snapshot_only_adjusted_chain_keeps_frozen_normalization() -> None:
    """锁定已发布 V3 结果使用的归一化口径：m0 参与每日相对倍数。

    这不是新语义：`first_close * cumprod((close/pre_close) / m0)` 是冻结研究
    的口径。若要改成"只丢弃首日收益"，必须开新的研究版本并重跑，不能在本
    契约加固中静默改数。
    """
    close = pd.Series([1.01, 1.02])
    pre_close = pd.Series([1.0, 1.01])
    m0 = 1.01
    m1 = 1.02 / 1.01

    chained = _chain_snapshot_only_adjusted_close(close, pre_close)

    assert chained.iloc[0] == pytest.approx(1.01)
    assert chained.iloc[1] == pytest.approx(1.01 * (m1 / m0))


def test_snapshot_only_missing_first_pre_close_is_rejected() -> None:
    """首日 m0 未知就无法按冻结口径归一化：显式失败，不以 1.0 冒充。"""
    close = pd.Series([1.0, 1.1])
    pre_close = pd.Series([np.nan, 1.0])

    with pytest.raises(ValueError, match="首日"):
        _chain_snapshot_only_adjusted_close(close, pre_close)


def test_missing_pre_close_is_not_carried_as_zero_return() -> None:
    """缺失日及其后累计收益不可恢复：保持 NaN，绝不填补 1.0 后继续 cumprod。"""
    close = pd.Series([1.0, 1.1, 1.21, 1.331])
    pre_close = pd.Series([1.0, np.nan, 1.1, 1.21])

    chained = _chain_snapshot_only_adjusted_close(close, pre_close)

    assert chained.iloc[0] == pytest.approx(1.0)
    assert chained.iloc[1:].isna().all(), chained.to_dict()


def test_bundle_tail_missing_first_pre_close_is_unknown() -> None:
    """bundle 尾段没有归一化豁免：首日 pre_close 缺失则整段未知。"""
    close = pd.Series([1.0, 1.1])
    pre_close = pd.Series([np.nan, 1.0])

    chained = _chain_bundle_tail_adjusted_close(1.0, close, pre_close)

    assert chained.isna().all(), chained.to_dict()


def test_bundle_tail_complete_data_chains_daily_multipliers() -> None:
    close = pd.Series([1.1, 1.21])
    pre_close = pd.Series([1.0, 1.1])

    chained = _chain_bundle_tail_adjusted_close(2.0, close, pre_close)

    assert chained.to_numpy() == pytest.approx([2.2, 2.42])


def test_non_positive_pre_close_is_rejected_not_filled() -> None:
    with pytest.raises(ValueError, match="pre_close"):
        _daily_total_return_multiplier(pd.Series([1.0, 1.1]), pd.Series([1.0, 0.0]))


def test_non_positive_close_is_rejected_not_chained() -> None:
    with pytest.raises(ValueError, match="close"):
        _daily_total_return_multiplier(pd.Series([1.0, 0.0]), pd.Series([0.99, 1.0]))
