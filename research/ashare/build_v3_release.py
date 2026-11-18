"""构建并签名发布 V3 进取型低频攻防系统策略规格包 (`StrategyRelease`)。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.ashare.data.contract import sha256_file
from research.ashare.v3_data import SNAPSHOT_DIR, WHITELIST_PATH
from tacticore.strategy_release import validate_strategy_release

TACTICORE_ROOT = Path("/home/jcshi/workspace/TactiCore")
ASHARE_INVESTOR_ROOT = Path("/home/jcshi/workspace/AShareInvestor")

OUT_TACTICORE = TACTICORE_ROOT / "research/ashare/releases/v3_offensive_policy_release_v3.1.0.json"
OUT_ASHARE_INVESTOR = (
    ASHARE_INVESTOR_ROOT
    / "docs/v3-offensive-system/fee-profiles/v3_offensive_policy_release_v3.1.0.json"
)


def _load_assets() -> list[str]:
    whitelist = json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))
    codes = {str(entry["ts_code"]) for entry in whitelist["entries"]}
    codes.update({"511010.SH", "159558.SZ", "CN_MAINBOARD_QUALITY_SWING_TOP2"})
    return sorted(codes)


def build_v3_release_payload() -> dict[str, Any]:
    impl_sha = sha256_file(TACTICORE_ROOT / "research/ashare/v3_data.py")
    manifest_path = SNAPSHOT_DIR / "manifest.json"
    evidence_paths: list[tuple[str, Path]] = [
        (str(manifest_path), manifest_path),
        (str(WHITELIST_PATH), WHITELIST_PATH),
        (
            "research/results/EXP_V3_01_REGIME_SUPER_ETF.json",
            TACTICORE_ROOT / "research/results/EXP_V3_01_REGIME_SUPER_ETF.json",
        ),
        (
            "research/results/EXP_V3_01_REGIME_SUPER_ETF.md",
            TACTICORE_ROOT / "research/results/EXP_V3_01_REGIME_SUPER_ETF.md",
        ),
        (
            "research/results/EXP_V3_02_MAINBOARD_STOCK_SWING.json",
            TACTICORE_ROOT / "research/results/EXP_V3_02_MAINBOARD_STOCK_SWING.json",
        ),
        (
            "research/results/EXP_V3_02_MAINBOARD_STOCK_SWING.md",
            TACTICORE_ROOT / "research/results/EXP_V3_02_MAINBOARD_STOCK_SWING.md",
        ),
        (
            "research/results/EXP_V3_03_DECONCENTRATION_PATHS.json",
            TACTICORE_ROOT / "research/results/EXP_V3_03_DECONCENTRATION_PATHS.json",
        ),
        (
            "research/results/EXP_V3_03_DECONCENTRATION_PATHS.md",
            TACTICORE_ROOT / "research/results/EXP_V3_03_DECONCENTRATION_PATHS.md",
        ),
    ]
    evidence = [{"reference": ref, "sha256": sha256_file(path)} for ref, path in evidence_paths]

    payload: dict[str, Any] = {
        "schema_version": "strategy-release-1",
        "research_status": "RESEARCH_PUBLISHED",
        "production_admission": "APPROVED_FOR_ACCOUNT",
        "strategy": {
            "id": "V3_OFFENSIVE_LOW_FREQ_SYSTEM",
            "version": "3.1.0",
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
            "exit": (
                "Dual-anchor regime shift, stock -8% hard stop / +15% breakeven / MA20 "
                "trailing, and 4-tranche + preemptive -12%->0% L2 breaker for sector ETFs"
            ),
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
        "rules": [
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
            (
                "Every stock pioneer trade requires QualityCore (ROE>5%, EPS>0, "
                "OCF/Profit>50% with PIT ann_date<=T), -8% hard stop, +15% breakeven "
                "arming, and MA20 trailing exit."
            ),
            (
                "Concentrated sector ETF deconcentration uses 4 tranches (Rule A >=12d "
                "monthly / Rule B +8% rebound / Rule C DEFENSIVE 2d<MA60*0.985) paired with "
                "preemptive -12%->0% 15-day L2 breaker under T+1 execution."
            ),
        ],
        "parameters": {
            "offensive_equity_bps": "8500",
            "structural_equity_bps": "6000",
            "defensive_equity_bps": "1500",
            "defensive_bond_reservoir_etf": "511010.SH",
            "super_etf_commission_rate": "0.00005",
            "super_etf_min_commission_cents": "0",
            "cross_border_max_premium_bps": "250",
            "bp1_pullback_status": "ENABLED",
            "bp1_oos_100k_net_expectancy_pct": "+2.329",
            "bp1_oos_70k_net_expectancy_pct": "+0.592",
            "bp2_breakout_status": "DROPPED_NEGATIVE_OOS",
            "bp2_oos_100k_net_expectancy_pct": "-0.187",
            "bp2_oos_70k_net_expectancy_pct": "-0.001",
            "stock_hard_stop_max_loss_bps": "800",
            "stock_breakeven_arm_gain_bps": "1500",
            "stock_max_positions": "2",
            "stock_max_single_weight_bps": "1800",
            "stock_risk_budget_per_trade_bps": "130",
            "deconcentration_tranches": "4",
            "deconcentration_keep_weight_bps": "1800",
            "deconcentration_rebound_trigger_bps": "800",
            "deconcentration_monthly_min_gap_days": "12",
            "l1_warn_drawdown_bps": "1000",
            "l2_hard_lifeline_drawdown_bps": "1500",
            "l2_preemptive_trigger_drawdown_bps": "1200",
            "l2_deconcentration_post_breaker_equity_bps": "0",
            "l2_lock_trade_days": "15",
        },
        "evidence": evidence,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    validate_strategy_release(payload)
    return payload


def main() -> str:
    payload = build_v3_release_payload()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    OUT_TACTICORE.parent.mkdir(parents=True, exist_ok=True)
    OUT_ASHARE_INVESTOR.parent.mkdir(parents=True, exist_ok=True)
    OUT_TACTICORE.write_text(rendered, encoding="utf-8")
    OUT_ASHARE_INVESTOR.write_text(rendered, encoding="utf-8")
    return str(payload["content_hash"])


if __name__ == "__main__":
    digest = main()
    print("V3 PolicyRelease v3.1.0 emitted:", digest)
