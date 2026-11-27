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

SUPPORTED_VERSIONS = ("3.1.0", "3.2.0", "3.2.1", "3.3.0", "3.3.1", "3.4.0")
DEFAULT_VERSION = "3.4.0"

# 所有者批准记录：以批准当时的 git 提交固定字节（文件末尾之后会追加 v3.2.1 指纹行，
# 因此不能用工作树当前字节作为证据哈希，否则会形成循环依赖）。
AMENDMENT_REV = "4979c41dad246a6050fb71d8f2576216dfe60616"
AMENDMENT_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261124.md"
AMENDMENT_REFERENCE = f"git:AShareInvestor@{AMENDMENT_REV}:{AMENDMENT_PATH}"
AMENDMENT_V330_REV = "9c736c2f35a9be73971aacf81440343a491819ca"
AMENDMENT_V330_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261126_V330.md"
AMENDMENT_V330_REFERENCE = f"git:AShareInvestor@{AMENDMENT_V330_REV}:{AMENDMENT_V330_PATH}"
AMENDMENT_V331_REV = "f91cfe1c622025cd7a846843d48232ddba04a740"
AMENDMENT_V331_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261127_V331.md"
AMENDMENT_V331_REFERENCE = f"git:AShareInvestor@{AMENDMENT_V331_REV}:{AMENDMENT_V331_PATH}"
AMENDMENT_V340_REV = "8d177ec97305be932af4f13d8914b462a75972e2"
AMENDMENT_V340_PATH = "docs/v3-offensive-system/POLICY_AMENDMENT_20261128_V340.md"
AMENDMENT_V340_REFERENCE = f"git:AShareInvestor@{AMENDMENT_V340_REV}:{AMENDMENT_V340_PATH}"
STOCK_SEMANTICS_SCRIPT = "research/ashare/experiments/exp_v3_02_stock_swing_rqalpha.py"
V320_CONTENT_HASH = "05346a961e01f746055143e0bb5790caa9d6460aa579bb26c085cca20d77b55f"
V321_CONTENT_HASH = "9869bd0b0ef02336c09fbaab921f5545d069a60039957c6f58b3fa1736e7eb9a"
V330_CONTENT_HASH = "e192ffc764f2bcf5ccd020e62254d1e1b518a6ab7a9074acd1d91c74a5462051"
V331_CONTENT_HASH = "29ad8fa8e2123df838f0c53630d77e9351dd60ee0ba8ac323e77480da2f9bb50"

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


_EXIT_V331 = (
    "Execution Architecture v2: dual-anchor regime with M2 post-icepoint 40% RECOVERY sleeve, "
    "unconditional <=4-ETF chassis (1 VALUE + 1 GROWTH + 2 LOW_VOL) with upward-only sticky "
    "selection, sector_pioneer disabled, 159649.SZ->511260.SH->511010.SH bond reservoir (10% "
    "drift band), bidirectional target alignment with stateless 35%/d 2-day glide convergence, "
    "P1 trailing scoped to SECTOR_PIONEER only, stock-only -8% hard stop / +15% breakeven / MA20 "
    "trailing (BP1 gated at >=100k CNY, manual re-verification >=95k CNY), deconcentration "
    "cancelled, and TWO_STAGE_GRADUAL drawdown control (-8%->50%, -11%->25%, -13.5%->10% 10d "
    "lock + unlock work-peak reanchor)"
)
_RULES_V331 = (
    (
        "Dual-anchor market regime + M2 breadth-thrust recovery overlay routes OFFENSIVE 85% / "
        "STRUCTURAL 60% / RECOVERY 40% (10d icepoint pct60<15% & pct20<15%, thrust pct20>=45% "
        "or +30pp/5d with pct20>=40% and amount>=1.15x; stops back on 5d-low break) / DEFENSIVE "
        "15% (EXP-V3-08 7 triggers, 0 false breakouts)."
    ),
    (
        "Unconditional 1+1+2 (<=4 ETFs) chassis across all NAV tiers (1 VALUE: "
        "159330.SZ>530050.SH>510140.SH; 1 GROWTH: 159205.SZ>159337.SZ>589850.SH>159290.SZ>"
        "589060.SH>589330.SH; 2 LOW_VOL: 159549.SZ+159207.SZ) with 30% permanent LOW_VOL core "
        "and upward-only sticky member retention (EXP-V3-12 R2)."
    ),
    (
        "Sector ETF pioneer is disabled (sector_pioneer_enabled=false; 20% budget merged back "
        "into base super-ETF chassis) and 159558.SZ BOTTOM_GRIND_25 deconcentration plan is "
        "cancelled (deconcentration_plan_enabled=false; treated as UNMANAGED_LEGACY target=0)."
    ),
    (
        "Stateless bidirectional target alignment (regime_target_enforced_on_existing_holdings"
        "=true, equity_align_drift_band_bps=500, align_glide_carryover_bps=3500): excess<=37% "
        "clears in 1d else max(35%, excess-35%); P0+P3-SELL share max(P0, glide) with legacy "
        "sold first and <2% non-target tail clean-sweep; P3-BUY strictly enforces "
        "post_buy_total_risk<=router_effective_cap."
    ),
    (
        "Idle defensive weight deploys via bond reservoir priority (159649.SZ normal ETF -> "
        "511260.SH -> 511010.SH) with 10% drift band and >=5,000 CNY normal-ETF / >=1,000 CNY "
        "super-ETF min buy tickets (100-share integer lots)."
    ),
    (
        "Mainboard BP1_PULLBACK stocks open only when investable NAV >= 100,000 CNY (conditional "
        "owner governance: re-verify BP1 leg before first stock order once NAV >= 95,000 CNY); "
        "-8% hard stop applies strictly to STOCK_BP1, while P1 ETF trailing covers "
        "SECTOR_PIONEER only (EXP-V3-02 & EXP-V3-12)."
    ),
    (
        "TWO_STAGE_GRADUAL drawdown control caps risk equity at 50% (-8% work DD) / 25% (-11% "
        "work DD) / 10d lock (-13.5% work DD, 10% normal cap) then re-anchors work peak with "
        "10d ramp while keeping all-time true_peak strictly un-reanchored."
    ),
)
_RESULT_EVIDENCE_V331 = (
    "research/results/EXP_V3_12_V331_ARCHITECTURE.json",
    "research/results/EXP_V3_12_V331_ARCHITECTURE.md",
    "research/results/EXP_V3_12_V331_ARCHITECTURE_R2.json",
    "research/results/EXP_V3_12_V331_ARCHITECTURE_R2.md",
)


def _v331_params(
    amendment_v331_sha: str, amendment_v330_sha: str, v321_amendment_sha: str
) -> dict[str, str]:
    params = _v330_params(amendment_v330_sha, v321_amendment_sha)
    params.update(
        {
            "deconcentration_plan_enabled": "false",
            "deconcentration_mode": "BOTTOM_GRIND_25",
            "sector_pioneer_enabled": "false",
            "regime_target_enforced_on_existing_holdings": "true",
            "align_glide_carryover_bps": "3500",
            "equity_align_drift_band_bps": "500",
            "chassis_single_etf_per_style_bucket": "true",
            "p1_etf_trailing_sleeves": "SECTOR_PIONEER",
            "l1_warn_drawdown_bps": "800",
            "drawdown_stage1_bps": "800",
            "l2_normal_trigger_drawdown_bps": "1350",
            "l2_hard_lifeline_drawdown_bps": "1350",
            "drawdown_lock_trigger_bps": "1350",
            "l2_normal_post_breaker_equity_bps": "1000",
            "drawdown_normal_post_lock_cap_bps": "1000",
            "l2_deconcentration_post_breaker_equity_bps": "0",
            "drawdown_conc_post_lock_cap_bps": "0",
            "l2_lock_trade_days": "10",
            "policy_amendment_id": "POLICY_AMENDMENT_20261127_V331",
            "policy_amendment_owner_approval_date": "2026-11-27",
            "policy_amendment_effective_after": "2026-11-27",
            "policy_amendment_record_ref": AMENDMENT_V331_REFERENCE,
            "policy_amendment_record_sha256": amendment_v331_sha,
            "supersedes_release_version": "3.3.0",
            "supersedes_release_content_hash": V330_CONTENT_HASH,
            "integration_study_ref": "research/batches/exp_v3_12_v331_architecture/run_r2.py",
        }
    )
    params.pop("l2_lock_allow_m2_early_release", None)
    return params


_EXIT_V340 = (
    "V3.4 Tri-Pillar: CORE_40 all-weather core (15% 159549/159207 + 10% 518880.SH ±400bps "
    "wide band [6%,14%] & >=5,000 CNY + 15% 159649.SZ ±1000bps) + 60% dynamic satellite "
    "(1 VALUE + 1 GROWTH upward-sticky), ICE_10 15d 35% floor (disabled under P0 L2), "
    "B1 756d ERP+B/P dual envelope (5% hysteresis, normal DEFENSIVE=25%), REGIME_ONLY "
    "low-turnover execution (10% satellite drift band), QualityCore v2 BP1 (>=100k, re-verify "
    ">=95k), and scalar-only FVO (default 0, ±1000bps, TTL<=20d, zero positive on L1/bubble)"
)
_RULES_V340 = (
    (
        "CORE_40 all-weather strategic core (15% no-min-5 LOW_VOL 159549.SZ+159207.SZ, "
        "10% physical gold 518880.SH with ±400bps wide band [6%,14%] & >=5,000 CNY single-leg "
        "active rebalance, and 15% strategic treasury bond 159649.SZ ±1000bps band) paired with "
        "60% dynamic 1 VALUE + 1 GROWTH upward-sticky satellite (B1_G5_DIAG 5% gold rejected)."
    ),
    (
        "Dual-anchor market regime + M2 40% RECOVERY + ICE_10 15d 35% damping floor "
        "(pct_above_ma60 < 10% triggers 15-trade-day window; disabled under P0 L2 lock which "
        "enforces 10% hard lifeline; normal DEFENSIVE strictly stays 25%)."
    ),
    (
        "B1 756d strictly causal ERP+B/P dual-confirmed envelope with 5% hysteresis: "
        "EXTREME_UNDERVAL (erp>=80% & bp>=70%, exit <75% or <65%) lifts ICE_10 42.5% / "
        "RECOVERY 50% / STRUCTURAL 65%; EXTREME_BUBBLE (erp<=15% & bp<=15%, exit >20% or >20%) "
        "caps OFFENSIVE 70% / STRUCTURAL 50% without lifting ICE_10; normal DEFENSIVE=25%. "
        "B2 implied expectation tilt is dropped from trading and schema-rejected."
    ),
    (
        "REGIME_ONLY low-turnover execution with stateless bidirectional alignment "
        "(align_glide_carryover_bps=3500, <2% dust clean-sweep, post-P3-SELL buy_headroom): "
        "style flips without regime/budget change stay silent when satellite drift <10% "
        "(gold within ±4%, bond within ±10%)."
    ),
    (
        "Mainboard BP1_PULLBACK stocks require investable NAV >= 100,000 CNY (re-verify before "
        "first stock order at NAV >= 95,000 CNY), non-target <=30%, and 40-quarter PIT "
        "QualityCore v2 (annualized roe_dt>6%, basic_eps>0, ocf_to_profit>=50%, bps>0, "
        "ann_date<=T, age<=550d); -8% hard stop / +15% breakeven / MA20 trailing."
    ),
    (
        "Bounded scalar-only Forward View Overlay (FVO): default equity_delta_bps=0, "
        "capped at ±1000bps, TTL<=20 trade days, positive FVO forced to 0 on P0>=8% (L1) or "
        "EXTREME_BUBBLE, halved to ±500bps when 60d attribution <=-150bps, clamped to "
        "[Floor, Cap]; no style_tilt."
    ),
    (
        "TWO_STAGE_GRADUAL drawdown control (-8%->50%, -11%->25%, -13.5%->10% 10d lock + "
        "unlock work-peak reanchor with 10d ramp; true_peak never re-anchored) and 3-month "
        "parameter freeze 2026-11-30..2027-02-28."
    ),
)
_RESULT_EVIDENCE_V340 = (
    "research/ashare/pit_fundamental_builder.py",
    "research/ashare/exp_v3_13_backtest.py",
    "research/ashare/exp_v3_14_backtest.py",
    "research/ashare/reports/exp_v3_13_report.md",
    "research/ashare/reports/exp_v3_13_summary.json",
    "research/ashare/reports/exp_v3_14_report.md",
    "research/ashare/reports/exp_v3_14_summary.json",
)


def _v340_params(
    amendment_v340_sha: str,
    amendment_v331_sha: str,
    amendment_v330_sha: str,
    v321_amendment_sha: str,
) -> dict[str, str]:
    params = _v331_params(amendment_v331_sha, amendment_v330_sha, v321_amendment_sha)
    params.update(
        {
            "defensive_equity_bps": "2500",
            "lowvol_core_mode": "CORE_40",
            "lowvol_core_permanent_share_bps": "1500",
            "gold_core_etf": "518880.SH",
            "gold_core_share_bps": "1000",
            "gold_core_drift_band_bps": "400",
            "gold_core_min_trade_cny": "5000",
            "strategic_bond_core_share_bps": "1500",
            "defensive_bond_reservoir_min_trade_cny": "5000",
            "satellite_max_share_bps": "6000",
            "ice10_floor_enabled": "true",
            "ice10_pct_ma60_max_bps": "1000",
            "ice10_window_trade_days": "15",
            "ice10_equity_bps": "3500",
            "ice10_disable_on_p0_lock": "true",
            "fundamental_envelope_enabled": "true",
            "fundamental_envelope_mode": "B1_PIT_ERP_BP_DUAL_756D",
            "fundamental_envelope_lookback_days": "756",
            "fundamental_hysteresis_bps": "500",
            "fundamental_underval_erp_enter_bps": "8000",
            "fundamental_underval_erp_exit_bps": "7500",
            "fundamental_underval_bp_enter_bps": "7000",
            "fundamental_underval_bp_exit_bps": "6500",
            "fundamental_bubble_erp_enter_bps": "1500",
            "fundamental_bubble_erp_exit_bps": "2000",
            "fundamental_bubble_bp_enter_bps": "1500",
            "fundamental_bubble_bp_exit_bps": "2000",
            "fundamental_underval_offensive_bps": "8500",
            "fundamental_underval_structural_bps": "6500",
            "fundamental_underval_recovery_bps": "5000",
            "fundamental_underval_ice10_bps": "4250",
            "fundamental_underval_defensive_bps": "2500",
            "fundamental_bubble_offensive_bps": "7000",
            "fundamental_bubble_structural_bps": "5000",
            "fundamental_bubble_recovery_bps": "4000",
            "fundamental_bubble_ice10_bps": "3500",
            "fundamental_bubble_defensive_bps": "2500",
            "align_trigger_mode": "REGIME_ONLY",
            "equity_align_drift_band_bps": "1000",
            "satellite_align_drift_band_bps": "1000",
            "quality_core_version": "v2",
            "quality_core_roe_dt_ann_min_bps": "600",
            "quality_core_eps_min": "0",
            "quality_core_ocf_to_profit_min_bps": "5000",
            "quality_core_bps_min": "0",
            "quality_core_strict_ann_date": "true",
            "stock_bp1_reverify_nav_cny": "95000",
            "fvo_enabled": "true",
            "fvo_scalar_only": "true",
            "fvo_equity_delta_default_bps": "0",
            "fvo_max_abs_delta_bps": "1000",
            "fvo_max_ttl_trade_days": "20",
            "fvo_zero_positive_on_l1_or_bubble": "true",
            "fvo_l1_drawdown_bps": "800",
            "fvo_60d_attribution_halve_trigger_bps": "-150",
            "fvo_60d_attribution_halved_cap_bps": "500",
            "policy_amendment_id": "POLICY_AMENDMENT_20261128_V340",
            "policy_amendment_owner_approval_date": "2026-11-28",
            "policy_amendment_effective_after": "2026-11-28",
            "policy_amendment_record_ref": AMENDMENT_V340_REFERENCE,
            "policy_amendment_record_sha256": amendment_v340_sha,
            "policy_freeze_start_date": "2026-11-30",
            "policy_freeze_end_date": "2027-02-28",
            "supersedes_release_version": "3.3.1",
            "supersedes_release_content_hash": V331_CONTENT_HASH,
            "integration_study_ref": "research/ashare/exp_v3_14_backtest.py",
        }
    )
    params.pop("l2_lock_allow_m2_early_release", None)
    return params


def build_v3_release_payload(version: str = DEFAULT_VERSION) -> dict[str, Any]:
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported_release_version:{version}")
    if version in {"3.3.0", "3.3.1", "3.4.0"}:
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
        if version in {"3.3.1", "3.4.0"}:
            ev_refs.extend(_RESULT_EVIDENCE_V331)
        if version == "3.4.0":
            ev_refs.extend(_RESULT_EVIDENCE_V340)
        evidence_v33x: list[dict[str, str]] = [
            {"reference": str(snap_manifest), "sha256": sha256_file(snap_manifest)},
            {"reference": str(aux_manifest), "sha256": sha256_file(aux_manifest)},
            {"reference": str(WHITELIST_PATH), "sha256": sha256_file(WHITELIST_PATH)},
            *[{"reference": ref, "sha256": sha256_file(TACTICORE_ROOT / ref)} for ref in ev_refs],
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
        extra_assets = {"159649.SZ", "511260.SH"}
        if version in {"3.3.1", "3.4.0"}:
            amendment_v331_sha = git_blob_sha256(
                ASHARE_INVESTOR_ROOT, AMENDMENT_V331_REV, AMENDMENT_V331_PATH
            )
            evidence_v33x.append(
                {"reference": AMENDMENT_V331_REFERENCE, "sha256": amendment_v331_sha}
            )
            for ref in (
                "research/batches/exp_v3_12_v331_architecture/PROTOCOL_V1.md",
                "research/batches/exp_v3_12_v331_architecture/PROTOCOL_V2.md",
                "research/batches/exp_v3_12_v331_architecture/run.py",
                "research/batches/exp_v3_12_v331_architecture/run_r2.py",
            ):
                evidence_v33x.append(
                    {"reference": ref, "sha256": sha256_file(TACTICORE_ROOT / ref)}
                )
        if version == "3.4.0":
            amendment_v340_sha = git_blob_sha256(
                ASHARE_INVESTOR_ROOT, AMENDMENT_V340_REV, AMENDMENT_V340_PATH
            )
            evidence_v33x.append(
                {"reference": AMENDMENT_V340_REFERENCE, "sha256": amendment_v340_sha}
            )
            extra_assets.add("518880.SH")
            exit_v33x = _EXIT_V340
            rules_v33x = list(_RULES_V340)
            params_v33x = _v340_params(
                amendment_v340_sha, amendment_v331_sha, amendment_v330_sha, amendment_v321_sha
            )
            lot_size_v33x = (
                "100 shares integer board lots; >=1,000 CNY Super ETF / >=5,000 CNY Normal ETF "
                "(including 518880.SH & 159649.SZ); >=8,000 CNY per stock pioneer trade"
            )
        elif version == "3.3.1":
            exit_v33x = _EXIT_V331
            rules_v33x = list(_RULES_V331)
            params_v33x = _v331_params(amendment_v331_sha, amendment_v330_sha, amendment_v321_sha)
            lot_size_v33x = (
                "100 shares integer board lots; >=1,000 CNY Super ETF / >=5,000 CNY Normal ETF; "
                ">=8,000 CNY per stock pioneer trade"
            )
        else:
            exit_v33x = _EXIT_V330
            rules_v33x = list(_RULES_V330)
            params_v33x = _v330_params(amendment_v330_sha, amendment_v321_sha)
            lot_size_v33x = (
                "100 shares integer board lots; minimum >=8,000 CNY per stock pioneer trade"
            )

        payload_v33x: dict[str, Any] = {
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
                "exit": exit_v33x,
                "fees": (
                    "Super ETF 0.5bp commission (min 0 CNY); normal ETF 2.5bp (min 5 CNY); "
                    "stocks 2.5bp (min 5 CNY) + 5bp sell stamp tax + 0.1bp transfer; 5bp slip"
                ),
                "lot_size": lot_size_v33x,
            },
            "inputs": {
                "source": (
                    "FinanceMCP research-export PIT snapshot v3_snapshot_20261126 + "
                    "v3_aux_20261126 + RQAlpha bundle_202611"
                ),
                "snapshot": "93cfb3e05e49d11e121b687930dc9e5040493e3dbaf23294325040ac468947ec",
                "start_date": "2018-01-02",
                "end_date": "2026-11-26",
                "assets": _load_assets(extra_assets),
            },
            "rules": rules_v33x,
            "parameters": params_v33x,
            "evidence": evidence_v33x,
        }
        encoded = json.dumps(
            payload_v33x, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        payload_v33x["content_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        validate_strategy_release(payload_v33x)
        return payload_v33x

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
