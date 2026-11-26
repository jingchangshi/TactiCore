"""构建并签名发布 V3 进取型低频攻防系统策略规格包 (`StrategyRelease`)。

一个构建器覆盖全部版本：

- ``3.1.0`` / ``3.2.0``：已签归档。构建器只做**逐字节复现校验**，若与已提交文件不同则拒绝写入
  （已签制品不可覆盖、不可就地重签）。
- ``3.2.1``：把所有者 2026-11-24 批准的个股波段语义修订（``POLICY_AMENDMENT_20261124.md``）
  写成机器可读规则与参数；其余规则与参数与 ``3.2.0`` 完全一致。

用法::

    python -m research.ashare.build_v3_release              # 生成/校验 3.2.1
    python -m research.ashare.build_v3_release --version 3.2.0 --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from research.ashare.data.contract import sha256_file
from research.ashare.v3_data import SNAPSHOT_DIR, WHITELIST_PATH
from tacticore.strategy_release import validate_strategy_release

TACTICORE_ROOT = Path(__file__).resolve().parents[2]
ASHARE_INVESTOR_ROOT = Path("/home/jcshi/workspace/AShareInvestor")

RELEASE_DIR = TACTICORE_ROOT / "research/ashare/releases"
FEE_PROFILE_DIR = ASHARE_INVESTOR_ROOT / "docs/v3-offensive-system/fee-profiles"

SUPPORTED_VERSIONS = ("3.1.0", "3.2.0", "3.2.1", "3.3.0")
DEFAULT_VERSION = "3.3.0"

# 所有者批准记录：以批准当时的 git 提交固定字节（文件末尾之后会追加 v3.2.1 指纹行，
# 因此不能用工作树当前字节作为证据哈希，否则会形成循环依赖）。
AMENDMENT_REV = "4979c41dad246a6050fb71d8f2576216dfe60616"
AMENDMENT_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261124.md"
AMENDMENT_REFERENCE = f"git:AShareInvestor@{AMENDMENT_REV}:{AMENDMENT_PATH}"
AMENDMENT_V330_REV = "9c736c2f35a9be73971aacf81440343a491819ca"
AMENDMENT_V330_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261126_V330.md"
AMENDMENT_V330_REFERENCE = f"git:AShareInvestor@{AMENDMENT_V330_REV}:{AMENDMENT_V330_PATH}"
STOCK_SEMANTICS_SCRIPT = "research/ashare/experiments/exp_v3_02_stock_swing_rqalpha.py"
V320_CONTENT_HASH = "05346a961e01f746055143e0bb5790caa9d6460aa579bb26c085cca20d77b55f"
V321_CONTENT_HASH = "9869bd0b0ef02336c09fbaab921f5545d069a60039957c6f58b3fa1736e7eb9a"

_EXIT_V31 = (
    "Dual-anchor regime shift, stock -8% hard stop / +15% breakeven / MA20 trailing, "
    "and 4-tranche + preemptive -12%->0% L2 breaker for sector ETFs"
)
_EXIT_V32 = (
    "Dual-anchor regime shift, stock -8% hard stop / +15% breakeven / MA20 trailing, "
    "and 25% core bottom-grind mode (+10% guarded tactical slot, 2d floor confirm, "
    ">=34% drift harvest, preemptive -12%->0% L2 above 30% weight)"
)
_EXIT_V321 = (
    "Dual-anchor regime shift, stock -8% hard stop / +15% gain raises stop to breakeven only / "
    "unconditional next-session exit after a close below MA20, ETF MA20 trailing take-profit "
    "armed only at >=15% gain, and 25% core bottom-grind mode (+10% guarded tactical slot, "
    "2d floor confirm, >=34% drift harvest, preemptive -12%->0% L2 above 30% weight)"
)

_RULES_COMMON = (
    (
        "Dual-anchor market regime (CSI300 + CSI500/ChiNext + breadth >=45% + "
        "vol >=0.85x) routes OFFENSIVE 85% / STRUCTURAL 60% / DEFENSIVE 15%."
    ),
    (
        "Idle defensive weight deploys into 511010.SH treasury bond ETF reservoir "
        "rather than 0% cash (EXP-V3-01 Full MaxDD -13.79% vs -17.32% cash-only)."
    ),
    (
        "Super ETF universe uses Eastmoney 33-ETF 0.5bp no-min-5 whitelist and "
        "blocks cross-border ETFs above +2.5% IOPV premium or >3-day stale NAV."
    ),
    (
        "Mainboard quality momentum swing enables BP1_PULLBACK ONLY "
        "(+2.329% OOS 100k / +0.592% OOS 70k) and DROPS BP2_BREAKOUT "
        "(-0.187% OOS 100k / -0.001% OOS 70k)."
    ),
)
_RULE_STOCK_V3X = (
    "Every stock pioneer trade requires QualityCore (ROE>5%, EPS>0, "
    "OCF/Profit>50% with PIT ann_date<=T), -8% hard stop, +15% breakeven "
    "arming, and MA20 trailing exit."
)
_RULE_STOCK_V321 = (
    "Every stock pioneer trade requires QualityCore (ROE>5%, EPS>0, "
    "OCF/Profit>50% with PIT ann_date<=T) and a -8% hard stop; reaching +15% gain only "
    "raises the stop to breakeven (cost), while a close below MA20 exits at the next session "
    "unconditionally, with no +15% arming prerequisite (EXP-V3-02 rule, owner amendment "
    "2026-11-24)."
)
_RULE_SECTOR_V31 = (
    "Concentrated sector ETF deconcentration uses 4 tranches (Rule A >=12d monthly / "
    "Rule B +8% rebound / Rule C DEFENSIVE 2d<MA60*0.985) paired with preemptive "
    "-12%->0% 15-day L2 breaker under T+1 execution."
)
_RULE_SECTOR_V32 = (
    "Concentrated sector ETF uses BOTTOM_GRIND_25 (keep 25% strategic core, drop "
    "low-level monthly forced selling, 2-day support floor breakdown confirm, plus "
    "+10% guarded reload only when MA60_slope10>=0, >=7% discount, oversold washout, "
    "and right-side close>MA5; >=34% drift stall harvest; EXP-V3-04 15/0 RT win rate)."
)
_RULES_V321_ADDED = (
    (
        "Mainboard stock pioneer screening does NOT apply the industry-sector top-30% gate by "
        "default (EXP-V3-02 OOS_100K_BP1_QC ind30=False +2.329% vs OOS_100K_QC_IND30_SENS "
        "ind30=True -0.131%); the gate survives only as an explicit research/review switch "
        "(requireIndustryTop30=true)."
    ),
    (
        "ETF trailing take-profit is unchanged: the MA20 trailing exit arms only after "
        "unrealized gain >=15%; an unarmed ETF is never sold merely for closing below MA20."
    ),
    (
        "Encodes the owner-approved 2026-11-24 stock swing semantic amendment "
        "(AShareInvestor POLICY_AMENDMENT_20261124.md at commit 4979c41); applies to decisions "
        "generated after 2026-11-24, historical daily reports are not relabeled, and the "
        "signed v3.2.0 release stays byte-unchanged."
    ),
)

_PARAMS_HEAD: tuple[tuple[str, str], ...] = (
    ("offensive_equity_bps", "8500"),
    ("structural_equity_bps", "6000"),
    ("defensive_equity_bps", "1500"),
    ("defensive_bond_reservoir_etf", "511010.SH"),
    ("super_etf_commission_rate", "0.00005"),
    ("super_etf_min_commission_cents", "0"),
    ("cross_border_max_premium_bps", "250"),
    ("bp1_pullback_status", "ENABLED"),
    ("bp1_oos_100k_net_expectancy_pct", "+2.329"),
    ("bp1_oos_70k_net_expectancy_pct", "+0.592"),
    ("bp2_breakout_status", "DROPPED_NEGATIVE_OOS"),
    ("bp2_oos_100k_net_expectancy_pct", "-0.187"),
    ("bp2_oos_70k_net_expectancy_pct", "-0.001"),
    ("stock_hard_stop_max_loss_bps", "800"),
    ("stock_breakeven_arm_gain_bps", "1500"),
    ("stock_max_positions", "2"),
    ("stock_max_single_weight_bps", "1800"),
    ("stock_risk_budget_per_trade_bps", "130"),
)
_PARAMS_TAIL: tuple[tuple[str, str], ...] = (
    ("l1_warn_drawdown_bps", "1000"),
    ("l2_hard_lifeline_drawdown_bps", "1500"),
    ("l2_preemptive_trigger_drawdown_bps", "1200"),
    ("l2_deconcentration_post_breaker_equity_bps", "0"),
    ("l2_lock_trade_days", "15"),
)
_PARAMS_SECTOR_V31: tuple[tuple[str, str], ...] = (
    ("deconcentration_tranches", "4"),
    ("deconcentration_keep_weight_bps", "1800"),
    ("deconcentration_rebound_trigger_bps", "800"),
    ("deconcentration_monthly_min_gap_days", "12"),
)
_PARAMS_SECTOR_V32: tuple[tuple[str, str], ...] = (
    ("deconcentration_mode", "BOTTOM_GRIND_25"),
    ("deconcentration_tranches", "4"),
    ("deconcentration_keep_weight_bps", "2500"),
    ("deconcentration_rebound_trigger_bps", "800"),
    ("deconcentration_monthly_min_gap_days", "12"),
    ("deconcentration_monthly_rule_enabled", "false"),
    ("deconcentration_support_breakdown_confirm_days", "2"),
    ("grind_tactical_slot_bps", "1000"),
    ("grind_reload_min_discount_bps", "700"),
    ("grind_reload_ma60_slope10_min_bps", "0"),
    ("grind_reload_rsi14_max", "36"),
    ("grind_reload_bias20_max_bps", "-650"),
    ("grind_take_profit_bps", "750"),
    ("grind_drift_harvest_trigger_bps", "3400"),
)

_RESULT_EVIDENCE_V31 = (
    "research/results/EXP_V3_01_REGIME_SUPER_ETF.json",
    "research/results/EXP_V3_01_REGIME_SUPER_ETF.md",
    "research/results/EXP_V3_02_MAINBOARD_STOCK_SWING.json",
    "research/results/EXP_V3_02_MAINBOARD_STOCK_SWING.md",
    "research/results/EXP_V3_03_DECONCENTRATION_PATHS.json",
    "research/results/EXP_V3_03_DECONCENTRATION_PATHS.md",
)
_RESULT_EVIDENCE_V32_ADDED = (
    "research/results/EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.json",
    "research/results/EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.md",
)


def release_filename(version: str) -> str:
    return f"v3_offensive_policy_release_v{version}.json"


def _load_assets(extra: set[str] | None = None) -> list[str]:
    whitelist = json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))
    codes = {str(entry["ts_code"]) for entry in whitelist["entries"]}
    codes.update({"511010.SH", "159558.SZ", "CN_MAINBOARD_QUALITY_SWING_TOP2"})
    if extra:
        codes.update(extra)
    return sorted(codes)


def git_blob_sha256(repo: Path, rev: str, path: str) -> str:
    """SHA-256 of a file's bytes at a pinned git revision (no working-tree dependency)."""
    blob = subprocess.run(
        ["git", "-C", str(repo), "show", f"{rev}:{path}"], check=True, capture_output=True
    ).stdout
    return hashlib.sha256(blob).hexdigest()


def _v321_amendment_params(amendment_sha: str) -> tuple[tuple[str, str], ...]:
    return (
        ("stock_industry_top30_gate_default", "false"),
        ("stock_industry_top30_gate_research_switch", "requireIndustryTop30"),
        ("stock_ma20_exit_mode", "UNCONDITIONAL_CLOSE_BELOW_MA20_NEXT_SESSION"),
        ("stock_ma20_exit_requires_breakeven_arm", "false"),
        ("stock_breakeven_arm_effect", "RAISE_STOP_TO_COST_ONLY"),
        ("etf_trailing_ma20_requires_arm", "true"),
        ("etf_trailing_ma20_arm_gain_bps", "1500"),
        ("policy_amendment_id", "POLICY_AMENDMENT_20261124"),
        ("policy_amendment_owner_approval_date", "2026-11-24"),
        ("policy_amendment_effective_after", "2026-11-24"),
        ("policy_amendment_record_ref", AMENDMENT_REFERENCE),
        ("policy_amendment_record_sha256", amendment_sha),
        ("supersedes_release_version", "3.2.0"),
        ("supersedes_release_content_hash", V320_CONTENT_HASH),
        ("stock_semantics_reference", STOCK_SEMANTICS_SCRIPT),
        (
            "implementation_sha256_basis",
            "research/ashare/v3_data.py unchanged since v3.1.0 and v3.2.0; the amended stock "
            "semantics are the defaults already implemented in " + STOCK_SEMANTICS_SCRIPT,
        ),
    )


_EXIT_V330 = (
    "Dual-anchor regime with M2 post-icepoint 40% RECOVERY sleeve, permanent 30% low-vol core, "
    "159649.SZ->511260.SH reservoir with 10% drift band, 20/60 blend top-1 super sector ETF "
    "pioneer (<=20%), stock -8% hard stop / +15% breakeven / MA20 trailing (BP1 gated at "
    ">=100k CNY & non-concentrated), BOTTOM_GRIND_25 for 159558.SZ, and TWO_STAGE_GRADUAL "
    "drawdown controller (-8%->50%, -11%->25%, -13.5%->lock 10d + unlock work-peak reanchor)"
)
_RULES_V330 = (
    (
        "Dual-anchor market regime + M2 breadth-thrust recovery overlay routes OFFENSIVE 85% / "
        "STRUCTURAL 60% / RECOVERY 40% (10d icepoint pct60<15% & pct20<15%, thrust pct20>=45% "
        "or +30pp/5d with pct20>=40% and amount>=1.15x; stops back on 5d-low break) / DEFENSIVE "
        "15% (EXP-V3-08 7 triggers, 0 false breakouts)."
    ),
    (
        "Base super-ETF chassis reserves 30% permanent LOW_VOL core (159549.SZ/159207.SZ) across "
        "OFFENSIVE/STRUCTURAL/RECOVERY and 100% of DEFENSIVE equity, cutting bear-market "
        "drawdown without monthly ERC refitting churn (EXP-V3-07 R1)."
    ),
    (
        "Idle defensive weight deploys via low-ticket bond reservoir priority "
        "(159649.SZ -> 511260.SH -> 511010.SH) with 10% periodic drift band and >=5,000 CNY "
        "minimum active buy ticket (EXP-V3-06 D1)."
    ),
    (
        "Super Sector ETF pioneer enables 20 industry_theme Super ETFs ranked by "
        "0.5*ret20 + 0.5*ret60 above MA60 (top-1, <=20% weight). Mainboard BP1_PULLBACK stocks "
        "open only when investable NAV >= 100,000 CNY and not in active deconcentration."
    ),
    _RULE_STOCK_V321,
    _RULE_SECTOR_V32,
    (
        "TWO_STAGE_GRADUAL drawdown control caps risk equity at 50% (-8% work DD) / 25% (-11% "
        "work DD) / 10d lock (-13.5% work DD, 0% concentrated / 10% normal) then re-anchors "
        "work peak with 10d ramp while keeping all-time true_peak strictly un-reanchored."
    ),
)
_RESULT_EVIDENCE_V330 = (
    "research/results/V3_COMPLEXITY_HURDLE_V2.json",
    "research/results/V3_COMPLEXITY_HURDLE_V2.md",
    "research/results/EXP_V3_05B_ACCOUNT_REPLAY_FULL.json",
    "research/results/EXP_V3_05B_ACCOUNT_REPLAY_FULL.md",
    "research/results/EXP_V3_06_DEFENSIVE_ROTATION.json",
    "research/results/EXP_V3_06_DEFENSIVE_ROTATION.md",
    "research/results/EXP_V3_07_LOWVOL_RISK_BUDGET.json",
    "research/results/EXP_V3_07_LOWVOL_RISK_BUDGET.md",
    "research/results/EXP_V3_08_ICEPOINT_RECOVERY.json",
    "research/results/EXP_V3_08_ICEPOINT_RECOVERY.md",
    "research/results/EXP_V3_09_DRAWDOWN_CONTROL_V2.json",
    "research/results/EXP_V3_09_DRAWDOWN_CONTROL_V2.md",
    "research/results/EXP_V3_10_PIONEER_ALPHA.json",
    "research/results/EXP_V3_10_PIONEER_ALPHA.md",
    "research/results/EXP_V3_11_V330_INTEGRATION.json",
    "research/results/EXP_V3_11_V330_INTEGRATION.md",
)


def _v330_params(amendment_sha: str, v321_amendment_sha: str) -> dict[str, str]:
    base = dict(
        [
            *_PARAMS_HEAD,
            *_PARAMS_SECTOR_V32,
            *_PARAMS_TAIL,
            *_v321_amendment_params(v321_amendment_sha),
        ]
    )
    base.update(
        {
            "defensive_bond_reservoir_etf": "159649.SZ",
            "defensive_bond_reservoir_fallback_etf": "511260.SH",
            "defensive_bond_reservoir_tertiary_etf": "511010.SH",
            "defensive_bond_reservoir_drift_band_bps": "1000",
            "l1_warn_drawdown_bps": "800",
            "l2_hard_lifeline_drawdown_bps": "1500",
            "l2_preemptive_trigger_drawdown_bps": "1200",
            "l2_normal_post_breaker_equity_bps": "1000",
            "l2_deconcentration_post_breaker_equity_bps": "0",
            "l2_lock_trade_days": "10",
            "recovery_overlay_enabled": "true",
            "recovery_overlay_mode": "M2_BREADTH_THRUST",
            "recovery_equity_bps": "4000",
            "recovery_icepoint_pct_ma60_max_bps": "1500",
            "recovery_icepoint_pct_ma20_max_bps": "1500",
            "recovery_icepoint_lookback_days": "10",
            "recovery_thrust_pct_ma20_min_bps": "4500",
            "recovery_thrust_5d_jump_min_bps": "3000",
            "recovery_thrust_floor_pct_ma20_bps": "4000",
            "recovery_min_amount_vs_ma20_bps": "11500",
            "recovery_false_breakout_cooldown_days": "10",
            "lowvol_core_permanent_share_bps": "3000",
            "drawdown_control_mode": "TWO_STAGE_GRADUAL",
            "drawdown_stage1_bps": "800",
            "drawdown_stage1_cap_bps": "5000",
            "drawdown_stage2_bps": "1100",
            "drawdown_stage2_cap_bps": "2500",
            "drawdown_lock_trigger_bps": "1350",
            "drawdown_normal_post_lock_cap_bps": "1000",
            "drawdown_conc_post_lock_cap_bps": "0",
            "drawdown_unlock_reanchor_enabled": "true",
            "drawdown_unlock_ramp_trade_days": "10",
            "sector_pioneer_enabled": "true",
            "sector_pioneer_rank_mode": "BLEND_20_60",
            "sector_pioneer_top_k": "1",
            "sector_pioneer_max_weight_bps": "2000",
            "sector_pioneer_require_above_ma60": "true",
            "stock_bp1_min_investable_nav_cny": "100000",
            "stock_bp1_block_during_deconcentration": "true",
            "policy_amendment_id": "POLICY_AMENDMENT_20261126_V330",
            "policy_amendment_owner_approval_date": "2026-11-26",
            "policy_amendment_effective_after": "2026-11-26",
            "policy_amendment_record_ref": AMENDMENT_V330_REFERENCE,
            "policy_amendment_record_sha256": amendment_sha,
            "supersedes_release_version": "3.2.1",
            "supersedes_release_content_hash": V321_CONTENT_HASH,
            "integration_study_ref": "research/batches/exp_v3_11_v330_integration/run.py",
        }
    )
    return base


def build_v3_release_payload(version: str = DEFAULT_VERSION) -> dict[str, Any]:
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported_release_version:{version}")
    if version == "3.3.0":
        from research.ashare import v3_data_202611 as d2611

        impl_path = TACTICORE_ROOT / "research/ashare/v3_data_202611.py"
        impl_sha = sha256_file(impl_path)
        snap_manifest = d2611.SNAPSHOT_DIR_202611 / "manifest.json"
        aux_manifest = d2611.AUX_DIR_202611 / "aux_manifest.json"
        amendment_v330_sha = git_blob_sha256(
            ASHARE_INVESTOR_ROOT, AMENDMENT_V330_REV, AMENDMENT_V330_PATH
        )
        amendment_v321_sha = git_blob_sha256(ASHARE_INVESTOR_ROOT, AMENDMENT_REV, AMENDMENT_PATH)
        ev_refs = [*_RESULT_EVIDENCE_V31, *_RESULT_EVIDENCE_V32_ADDED, *_RESULT_EVIDENCE_V330]
        evidence_v330: list[dict[str, str]] = [
            {"reference": str(snap_manifest), "sha256": sha256_file(snap_manifest)},
            {"reference": str(aux_manifest), "sha256": sha256_file(aux_manifest)},
            {"reference": str(WHITELIST_PATH), "sha256": sha256_file(WHITELIST_PATH)},
            *[
                {"reference": ref, "sha256": sha256_file(TACTICORE_ROOT / ref)}
                for ref in ev_refs
            ],
            {"reference": AMENDMENT_V330_REFERENCE, "sha256": amendment_v330_sha},
            {
                "reference": "research/batches/exp_v3_11_v330_integration/run.py",
                "sha256": sha256_file(
                    TACTICORE_ROOT / "research/batches/exp_v3_11_v330_integration/run.py"
                ),
            },
            {
                "reference": "research/ashare/v3_data_202611.py",
                "sha256": impl_sha,
            },
        ]
        payload_v330: dict[str, Any] = {
            "schema_version": "strategy-release-1",
            "research_status": "RESEARCH_PUBLISHED",
            "production_admission": "APPROVED_FOR_ACCOUNT",
            "strategy": {
                "id": "V3_OFFENSIVE_LOW_FREQ_SYSTEM",
                "version": "3.3.0",
                "implementation_sha256": impl_sha,
            },
            "applicability": {
                "market": "CN_ASHARE_MAINBOARD_AND_EXCHANGE_ETF",
                "environment": "EASTMONEY_100K_LOW_FREQ_ACCOUNT",
            },
            "execution_assumptions": {
                "signal_timing": "End-of-day PIT close indicators after market close (T)",
                "earliest_execution": (
                    "Next trading session T+1 (open_auction for stocks; T+1 ETF rebalance)"
                ),
                "exit": _EXIT_V330,
                "fees": (
                    "Super ETF 0.5bp commission (min 0 CNY); normal ETF 2.5bp (min 5 CNY); "
                    "stocks 2.5bp (min 5 CNY) + 5bp sell stamp tax + 0.1bp transfer; 5bp slip"
                ),
                "lot_size": (
                    "100 shares integer board lots; minimum >=8,000 CNY per stock pioneer trade"
                ),
            },
            "inputs": {
                "source": (
                    "FinanceMCP research-export PIT snapshot v3_snapshot_20261126 + "
                    "v3_aux_20261126 + RQAlpha bundle_202611"
                ),
                "snapshot": "93cfb3e05e49d11e121b687930dc9e5040493e3dbaf23294325040ac468947ec",
                "start_date": "2018-01-02",
                "end_date": "2026-11-26",
                "assets": _load_assets({"159649.SZ", "511260.SH"}),
            },
            "rules": list(_RULES_V330),
            "parameters": _v330_params(amendment_v330_sha, amendment_v321_sha),
            "evidence": evidence_v330,
        }
        encoded = json.dumps(
            payload_v330, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        payload_v330["content_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        validate_strategy_release(payload_v330)
        return payload_v330

    impl_sha = sha256_file(TACTICORE_ROOT / "research/ashare/v3_data.py")
    manifest_path = SNAPSHOT_DIR / "manifest.json"
    evidence: list[dict[str, str]] = [
        {"reference": str(manifest_path), "sha256": sha256_file(manifest_path)},
        {"reference": str(WHITELIST_PATH), "sha256": sha256_file(WHITELIST_PATH)},
    ]
    result_refs = list(_RESULT_EVIDENCE_V31)
    if version != "3.1.0":
        result_refs.extend(_RESULT_EVIDENCE_V32_ADDED)
    evidence.extend(
        {"reference": ref, "sha256": sha256_file(TACTICORE_ROOT / ref)} for ref in result_refs
    )

    if version == "3.1.0":
        exit_text = _EXIT_V31
        rules = [*_RULES_COMMON, _RULE_STOCK_V3X, _RULE_SECTOR_V31]
        params = [*_PARAMS_HEAD, *_PARAMS_SECTOR_V31, *_PARAMS_TAIL]
    elif version == "3.2.0":
        exit_text = _EXIT_V32
        rules = [*_RULES_COMMON, _RULE_STOCK_V3X, _RULE_SECTOR_V32]
        params = [*_PARAMS_HEAD, *_PARAMS_SECTOR_V32, *_PARAMS_TAIL]
    else:
        amendment_sha = git_blob_sha256(ASHARE_INVESTOR_ROOT, AMENDMENT_REV, AMENDMENT_PATH)
        exit_text = _EXIT_V321
        rules = [*_RULES_COMMON, _RULE_STOCK_V321, _RULE_SECTOR_V32, *_RULES_V321_ADDED]
        params = [
            *_PARAMS_HEAD,
            *_PARAMS_SECTOR_V32,
            *_PARAMS_TAIL,
            *_v321_amendment_params(amendment_sha),
        ]
        evidence.append({"reference": AMENDMENT_REFERENCE, "sha256": amendment_sha})
        evidence.append(
            {
                "reference": STOCK_SEMANTICS_SCRIPT,
                "sha256": sha256_file(TACTICORE_ROOT / STOCK_SEMANTICS_SCRIPT),
            }
        )

    payload: dict[str, Any] = {
        "schema_version": "strategy-release-1",
        "research_status": "RESEARCH_PUBLISHED",
        "production_admission": "APPROVED_FOR_ACCOUNT",
        "strategy": {
            "id": "V3_OFFENSIVE_LOW_FREQ_SYSTEM",
            "version": version,
            "implementation_sha256": impl_sha,
        },
        "applicability": {
            "market": "CN_ASHARE_MAINBOARD_AND_EXCHANGE_ETF",
            "environment": "EASTMONEY_100K_LOW_FREQ_ACCOUNT",
        },
        "execution_assumptions": {
            "signal_timing": "End-of-day PIT close indicators after market close (T)",
            "earliest_execution": (
                "Next trading session T+1 (open_auction for stocks; T+1 ETF rebalance)"
            ),
            "exit": exit_text,
            "fees": (
                "Super ETF 0.5bp commission (min 0 CNY); normal ETF 2.5bp (min 5 CNY); "
                "stocks 2.5bp (min 5 CNY) + 5bp sell stamp tax + 0.1bp transfer; 5bp slip"
            ),
            "lot_size": (
                "100 shares integer board lots; minimum >=8,000 CNY per stock pioneer trade"
            ),
        },
        "inputs": {
            "source": (
                "FinanceMCP research-export PIT snapshot v3_snapshot_20261113 "
                "+ RQAlpha bundle_202609"
            ),
            "snapshot": "ca43f6393393056d6b318bba792c3f6c70c7c5d786f72a7ec6beab366d5b5a78",
            "start_date": "2018-01-02",
            "end_date": "2026-11-13",
            "assets": _load_assets(),
        },
        "rules": rules,
        "parameters": dict(params),
        "evidence": evidence,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    validate_strategy_release(payload)
    return payload


def render_release(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def output_paths(version: str) -> tuple[Path, Path]:
    name = release_filename(version)
    return RELEASE_DIR / name, FEE_PROFILE_DIR / name


def emit_release(version: str = DEFAULT_VERSION, *, write: bool = True) -> str:
    """Build `version`; write missing copies, refuse to overwrite any differing signed file."""
    payload = build_v3_release_payload(version)
    rendered = render_release(payload).encode("utf-8")
    for path in output_paths(version):
        if path.exists():
            if path.read_bytes() != rendered:
                raise RuntimeError(f"signed_release_drift:{path}")
            continue
        if not write:
            raise RuntimeError(f"signed_release_missing:{path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rendered)
    return str(payload["content_hash"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=SUPPORTED_VERSIONS, default=DEFAULT_VERSION)
    parser.add_argument("--check", action="store_true", help="verify only; never write")
    args = parser.parse_args()
    digest = emit_release(args.version, write=not args.check)
    print(f"V3 PolicyRelease v{args.version} content_hash:", digest)


if __name__ == "__main__":
    main()
