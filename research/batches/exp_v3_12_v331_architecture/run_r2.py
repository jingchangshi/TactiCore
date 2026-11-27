"""EXP-V3-12 R2 runner: upward-only sticky + single-switch sector_pioneer ablation + PROTOCOL_V2 gate."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.ashare import v3_data_202611 as data
from research.ashare.v3_data import rq_to_ts, ts_to_rq
from research.batches.exp_v3_11_v330_integration.analytics import (
    compute_calendar_stats,
    compute_roundtrip_stats,
)
from research.batches.exp_v3_11_v330_integration.run import (
    CASH,
    LOW_TICKET_BONDS_RQ,
    LOW_VOL_PRIMARY_RQ,
    OOS_CASH_START,
    OOS_CONC_START,
    RQA_END,
    START,
    VBT_END,
    apply_drawdown_overlay_202611,
    build_v3_base_chassis_weights,
    load_sector_pioneer_pool,
    make_group_fn,
)
from research.batches.exp_v3_12_v331_architecture.run import (
    replay_v331_account,
    select_v331_targets,
)
from research.batches.v3_account_replay_v2.policy import FOCUS, GOLD, GROWTH, VALUE, indicators
from research.batches.v3_account_replay_v2.stock_signals import (
    build_causal_bp1_candidates_202611,
)
from research.batches.v3_complexity_hurdle_v2.native import replay
from research.batches.v3_complexity_hurdle_v2.run import require, reserve, utc

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/EXP_V3_12_V331_ARCHITECTURE_R2"
V1_JSON = ROOT / "research/results/EXP_V3_12_V331_ARCHITECTURE.json"
PROTOCOL = ROOT / "research/batches/exp_v3_12_v331_architecture/PROTOCOL_V2.md"


def select_v331_targets_upward_sticky(
    *,
    regime: str,
    style: str,
    occupied_weight: float,
    features: dict[str, Any],
    sector_pool_rq: tuple[str, ...],
    use_lowvol_core: bool,
    use_sector_pioneer: bool,
    bp1_active_budget: bool,
    use_v331_budget_merge: bool = True,
    sticky_mode: str = "upward",  # "upward" | "none"
    held_mv: dict[str, float] | None = None,
) -> dict[str, float]:
    """Select target weights with upward-only sticky rule:

    For each bucket in strict priority order (high -> low), pick the FIRST member
    that is either (held & holdable) or (currently buyable/valid).
    """

    def valid(c: str) -> bool:
        return c in features and pd.notna(features[c].ma20) and features[c].raw > 0

    def holdable(c: str) -> bool:
        return bool(held_mv and held_mv.get(c, 0.0) > 0 and c in features and pd.notna(features[c].raw) and features[c].raw > 0)

    def eligible(c: str) -> bool:
        if sticky_mode == "upward":
            return holdable(c) or valid(c)
        return valid(c)

    if sticky_mode == "none":
        return select_v331_targets(
            regime=regime,
            style=style,
            occupied_weight=occupied_weight,
            features=features,
            sector_pool_rq=sector_pool_rq,
            use_lowvol_core=use_lowvol_core,
            use_sector_pioneer=use_sector_pioneer,
            bp1_active_budget=bp1_active_budget,
            use_v331_budget_merge=use_v331_budget_merge,
            hold_sticky=False,
            held_mv=held_mv,
        )

    budget_map = {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "RECOVERY": 0.40, "DEFENSIVE": 0.15}
    room = max(0.0, budget_map[regime] - occupied_weight)
    out: dict[str, float] = {}

    if regime == "DEFENSIVE":
        if room <= 0:
            return {}
        if use_lowvol_core:
            lv = [c for c in LOW_VOL_PRIMARY_RQ if eligible(c)][:2]
            if lv:
                for c in lv:
                    out[c] = room / len(lv)
                return out
        if eligible(GOLD):
            out[GOLD] = min(room, 0.10)
            return out
        return {}

    if regime == "RECOVERY":
        base = room
        pioneer_room = 0.0
    elif regime == "OFFENSIVE":
        if use_sector_pioneer or not use_v331_budget_merge:
            pioneer_cap = 0.40 if bp1_active_budget else 0.20
            base = min(room, 0.45 if bp1_active_budget else 0.65)
            pioneer_room = max(0.0, min(0.20, room - base, pioneer_cap)) if use_sector_pioneer else 0.0
        else:
            base = min(room, 0.65 if bp1_active_budget else 0.85)
            pioneer_room = 0.0
    else:  # STRUCTURAL
        if use_sector_pioneer or not use_v331_budget_merge:
            pioneer_cap = 0.30 if bp1_active_budget else 0.20
            base = min(room, 0.30 if bp1_active_budget else 0.40)
            pioneer_room = max(0.0, min(0.20, room - base, pioneer_cap)) if use_sector_pioneer else 0.0
        else:
            base = min(room, 0.50 if bp1_active_budget else 0.60)
            pioneer_room = 0.0

    if base > 0:
        if use_lowvol_core:
            shares = (
                {"VALUE": 0.25, "GROWTH": 0.45, "LOW_VOL": 0.30}
                if style == "GROWTH_LEADING"
                else (
                    {"VALUE": 0.45, "GROWTH": 0.25, "LOW_VOL": 0.30}
                    if style == "VALUE_LEADING"
                    else {"VALUE": 0.35, "GROWTH": 0.35, "LOW_VOL": 0.30}
                )
            )
            val_c = next((c for c in VALUE if eligible(c)), None)
            gro_c = next((c for c in GROWTH if eligible(c)), None)
            lv_cs = [c for c in LOW_VOL_PRIMARY_RQ if eligible(c)][:2]
            if val_c:
                out[val_c] = base * shares["VALUE"]
            if gro_c:
                out[gro_c] = base * shares["GROWTH"]
            if lv_cs:
                for c in lv_cs:
                    out[c] = (base * shares["LOW_VOL"]) / len(lv_cs)
        else:
            gold = min(base, 0.10)
            if gold > 0 and eligible(GOLD):
                out[GOLD] = gold
            growth = {"GROWTH_LEADING": 0.65, "VALUE_LEADING": 0.35}.get(style, 0.50)
            for grp, share in ((VALUE, 1.0 - growth), (GROWTH, growth)):
                c = next((x for x in grp if eligible(x)), None)
                if c and base > gold:
                    out[c] = (base - gold) * share

    if use_sector_pioneer and pioneer_room >= 0.02:
        scored: list[tuple[float, str]] = []
        for c in sector_pool_rq:
            if not valid(c):
                continue
            r = features[c]
            if pd.notna(r.ma60) and pd.notna(r.ret20) and pd.notna(r.ret60) and r.c > r.ma60:
                scored.append((0.5 * float(r.ret20) + 0.5 * float(r.ret60), c))
        if scored:
            scored.sort(key=lambda x: (-x[0], x[1]))
            pick = scored[0][1]
            out[pick] = out.get(pick, 0.0) + min(pioneer_room, 0.20)

    return {c: w for c, w in out.items() if w > 0.01}


def run_with_upward_sticky(**kwargs: Any) -> dict[str, Any]:
    """Run replay_v331_account with upward-only sticky injected cleanly into select_v331_targets."""
    import research.batches.exp_v3_12_v331_architecture.run as r12_mod

    sticky_mode = str(kwargs.pop("sticky_mode", "upward"))
    orig_fn = r12_mod.select_v331_targets

    def _patched_selector(**sel_kw: Any) -> dict[str, float]:
        sel_kw.pop("hold_sticky", None)
        return select_v331_targets_upward_sticky(**sel_kw, sticky_mode=sticky_mode)

    r12_mod.select_v331_targets = _patched_selector  # type: ignore[assignment]
    try:
        res = replay_v331_account(**kwargs, hold_sticky=(sticky_mode != "none"))
    finally:
        r12_mod.select_v331_targets = orig_fn  # type: ignore[assignment]

    bp1_sleeve = res["roundtrips"]["by_sleeve"].get("stock_bp1", {})
    res["bp1_summary"] = {
        "closed_trades": int(bp1_sleeve.get("closed_trades", 0)),
        "open_shares_at_end": int(res["roundtrips"]["open_shares_at_end"].get("stock_bp1", 0)),
        "pnl_yuan": float(res["pnl_attribution"].get("stock_bp1", 0.0)),
        "realized_pnl_yuan": float(bp1_sleeve.get("total_realized_pnl_yuan", 0.0)),
    }
    return res


def main() -> int:
    reserve(STEM)
    v1 = json.loads(V1_JSON.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "started": utc(),
        "runner_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "versions": {k: version(k) for k in ("rqalpha", "vectorbt")},
        "protocol_sha256": data.sha256_file(PROTOCOL),
        "v1_reference_sha256": data.sha256_file(V1_JSON),
        "chassis_rqa": {},
        "account_replay": {},
        "selection": {},
        "gates": {},
    }
    try:
        prov = data.verify_v3_202611_provenance(verify_content=True)
        report["snapshot_id"] = prov.snapshot_id
        p = data.load_stitched_panels_202611(prov)
        reg = data.compute_v3_regime_series_202611(prov, p.index_close, p.calendar, use_cache=True)
        sector_pool_ts = load_sector_pioneer_pool()
        sector_pool_rq = tuple(ts_to_rq(c) for c in sector_pool_ts)
        group_fn = make_group_fn(sector_pool_ts)

        # 1) Full-window RQAlpha chassis replay (a) CLEAN vs (b) WITH_PIONEER
        eff_reg_by_arm: dict[str, pd.Series] = {}
        for name, use_pioneer in (
            ("V3_3_1_CLEAN_UPWARD_STICKY", False),
            ("V3_3_1_WITH_PIONEER_ABLATION", True),
        ):
            base_w, eff_reg, _ = build_v3_base_chassis_weights(
                p,
                reg,
                sector_pool_ts=sector_pool_ts,
                use_recovery=True,
                use_lowvol_core=True,
                use_low_ticket_bond=True,
                use_sector_pioneer=use_pioneer,
                end=VBT_END,
            )
            eff_reg_by_arm[name] = eff_reg
            ow, _ = apply_drawdown_overlay_202611(
                p, base_w, eff_reg, ctrl_mode="c3_gradual", use_low_ticket_bond=True, end=VBT_END
            )
            for cash in CASH:
                label = f"{name}_{cash}"
                sys.stdout.write(f"{utc()} chassis {label}\n")
                sys.stdout.flush()
                eq, run = replay(ow, cash, prov.super_etf_codes, True, start=START, end=RQA_END)
                fees = sum(float(f["commission"]) for f in run["fills"])
                report["chassis_rqa"][label] = {
                    "full": compute_calendar_stats(eq),
                    "is": compute_calendar_stats(eq.loc[: data.IS_END]),
                    "oos": compute_calendar_stats(eq.loc[data.IS_END :]),
                    "roundtrips": compute_roundtrip_stats(run["fills"], group_fn),
                    "trade_count": len(run["fills"]),
                    "commission_yuan": round(fees, 2),
                    "dates_pass": run["dates_pass"],
                    "fill_capture_pass": run["fill_capture_pass"],
                    "fees_pass": run["commission_audit"]["fees_pass"],
                    "illegal_non_lot_fills": len(run["commission_audit"]["illegal_non_lot_fills"]),
                }

        # 2) Unified account replays for (a), (b), (c) across all 6 cells
        codes_rq = sorted({FOCUS, GOLD, *VALUE, *GROWTH, *LOW_VOL_PRIMARY_RQ, *LOW_TICKET_BONDS_RQ, *sector_pool_rq})
        feat_dfs = {}
        for rq in codes_rq:
            ts = rq_to_ts(rq)
            if ts in p.etf_adj_close.columns and ts in p.etf_raw_close.columns:
                df = indicators(p.etf_adj_close[ts], p.etf_raw_close[ts])
                df["ret60"] = df["c"] / df["c"].shift(60) - 1.0
                df = df.where(p.etf_tradability_mask[ts], np.nan)
                feat_dfs[rq] = df
        features: dict[str, dict[str, Any]] = {}
        for dt in p.calendar:
            d_s = str(dt.date())
            features[d_s] = {
                rq: row for rq, df in feat_dfs.items() for row in [df.loc[dt]]
                if pd.notna(row["c"]) and pd.notna(row["raw"]) and float(row["raw"]) > 0
            }
        white_rq = {ts_to_rq(c) for c in prov.super_etf_codes}
        stock_cands, _ = build_causal_bp1_candidates_202611(oos_start=OOS_CASH_START, bundle_end=RQA_END)
        cal_rqa = p.calendar[p.calendar <= RQA_END]
        days_cash = [str(d.date()) for d in cal_rqa[cal_rqa >= OOS_CASH_START]]
        days_conc = [str(d.date()) for d in cal_rqa[cal_rqa >= OOS_CONC_START]]

        mkt_clean = {str(dt.date()): (str(eff_reg_by_arm["V3_3_1_CLEAN_UPWARD_STICKY"].at[dt]), str(reg.at[dt, "style"])) for dt in p.calendar}
        mkt_pioneer = {str(dt.date()): (str(eff_reg_by_arm["V3_3_1_WITH_PIONEER_ABLATION"].at[dt]), str(reg.at[dt, "style"])) for dt in p.calendar}

        arms_cfg = (
            ("V3_3_1_CLEAN_UPWARD_STICKY", mkt_clean, False, "upward"),
            ("V3_3_1_WITH_PIONEER_ABLATION", mkt_pioneer, True, "upward"),
            ("V3_3_1_NO_STICKY_REF", mkt_clean, False, "none"),
        )
        for scenario, s_days, seed in (("OOS_CASH", days_cash, 0.0), ("CORE25", days_conc, 0.25), ("LEGACY70", days_conc, 0.70)):
            for cash in CASH:
                for arm_name, mkt, use_pioneer, sticky_mode in arms_cfg:
                    cell = f"{scenario}_{cash}_{arm_name}"
                    sys.stdout.write(f"{utc()} acct {cell}\n")
                    sys.stdout.flush()
                    report["account_replay"][cell] = run_with_upward_sticky(
                        days=s_days,
                        market=mkt,
                        features=features,
                        stock_candidates=stock_cands,
                        white=white_rq,
                        sector_pool_rq=sector_pool_rq,
                        capital=float(cash),
                        seed=seed,
                        use_sector_pioneer=use_pioneer,
                        use_deconc_plan=False,
                        align_glide_carryover_w=0.35,
                        p1_etf_trailing_sleeves=("SECTOR_PIONEER",),
                        sticky_mode=sticky_mode,
                        use_stateless_align_due=True,
                        equity_drift_band=0.05,
                        use_v331_budget_merge=True,
                        group_fn=group_fn,
                    )

        rqa_list = list(report["chassis_rqa"].values())
        acct_list = list(report["account_replay"].values())
        report["gates"] = {
            "chassis_order_dates": all(r["dates_pass"] for r in rqa_list),
            "chassis_lots_and_capture": all(r["fill_capture_pass"] and r["illegal_non_lot_fills"] == 0 for r in rqa_list),
            "chassis_commissions": all(r["fees_pass"] for r in rqa_list),
            "account_zero_violations": all(c["violation_count"] == 0 for c in acct_list),
        }
        require(all(report["gates"].values()), "EXP-V3-12 R2 integrity gate failed")

        # Compare (a) CLEAN_UPWARD_STICKY vs V3_3_0 baseline from V1 (exact EXP-V3-11 parity)
        v330_keys = {
            "OOS_CASH_69000": "OOS_CASH_69000_V3_3_0_WITH_PIONEER",
            "OOS_CASH_100000": "OOS_CASH_100000_V3_3_0_WITH_PIONEER",
            "CORE25_69000": "CORE25_69000_V3_3_0_WITH_PIONEER",
            "CORE25_100000": "CORE25_100000_V3_3_0_WITH_PIONEER",
            "LEGACY70_69000": "LEGACY70_69000_V3_3_0_GRIND25",
            "LEGACY70_100000": "LEGACY70_100000_V3_3_0_GRIND25",
        }
        all_6_true_dd_ok = True
        for scen_cash, old_k in v330_keys.items():
            old_r = v1["account_replay"][old_k]
            new_r = report["account_replay"][f"{scen_cash}_V3_3_1_CLEAN_UPWARD_STICKY"]
            if new_r["true_max_dd"] > old_r["true_max_dd"] + 1e-6:
                all_6_true_dd_ok = False

        k69_calmar_ok = sum(
            1
            for scen in ("OOS_CASH_69000", "CORE25_69000", "LEGACY70_69000")
            if report["account_replay"][f"{scen}_V3_3_1_CLEAN_UPWARD_STICKY"]["metrics"]["calmar"]
            >= v1["account_replay"][v330_keys[scen]]["metrics"]["calmar"] - 0.05
        )
        c69 = report["chassis_rqa"]["V3_3_1_CLEAN_UPWARD_STICKY_69000"]["full"]
        c100 = report["chassis_rqa"]["V3_3_1_CLEAN_UPWARD_STICKY_100000"]["full"]
        leg69_br = report["account_replay"]["LEGACY70_69000_V3_3_1_CLEAN_UPWARD_STICKY"]["breach_days"]
        leg100_br = report["account_replay"]["LEGACY70_100000_V3_3_1_CLEAN_UPWARD_STICKY"]["breach_days"]

        pioneer_dominates_69k = all(
            report["account_replay"][f"{scen}_V3_3_1_WITH_PIONEER_ABLATION"]["metrics"]["calmar"]
            > report["account_replay"][f"{scen}_V3_3_1_CLEAN_UPWARD_STICKY"]["metrics"]["calmar"] + 0.05
            and report["account_replay"][f"{scen}_V3_3_1_WITH_PIONEER_ABLATION"]["true_max_dd"]
            <= report["account_replay"][f"{scen}_V3_3_1_CLEAN_UPWARD_STICKY"]["true_max_dd"]
            for scen in ("OOS_CASH_69000", "CORE25_69000", "LEGACY70_69000")
        )

        v331_approved = (
            c69["max_drawdown"] > -0.15
            and c100["max_drawdown"] > -0.15
            and all_6_true_dd_ok
            and leg69_br <= 5
            and leg100_br <= 5
            and k69_calmar_ok >= 2
        )
        report["selection"] = {
            "v331_clean_approved": v331_approved,
            "all_6_true_max_dd_not_worse_than_v330": all_6_true_dd_ok,
            "k69_calmar_ge_v330_minus_005_count": k69_calmar_ok,
            "legacy70_69k_breach_days": leg69_br,
            "legacy70_100k_breach_days": leg100_br,
            "pioneer_dominates_69k": pioneer_dominates_69k,
            "l2_lock_allow_m2_early_release": False,
        }
        report["verdict"] = "V3_3_1_CLEAN_APPROVED" if v331_approved else "V3_3_1_NEEDS_REVIEW"
    except Exception as exc:
        import traceback

        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        report["verdict"] = "ERROR"
    finally:
        report["finished"] = utc()
        report["exit_code"] = 0 if report.get("verdict") == "V3_3_1_CLEAN_APPROVED" else 1
        STEM.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if report.get("verdict") != "ERROR":
            lines = [
                "# EXP-V3-12 R2：新粘性规则 + 行业先导严格单开关消融（PROTOCOL_V2）",
                "",
                f"裁决：`{report['verdict']}` | `69k Calmar达标`：`{report['selection']['k69_calmar_ge_v330_minus_005_count']}/3` | `全6组TrueDD不劣`：`{report['selection']['all_6_true_max_dd_not_worse_than_v330']}` | `先导69k双占优`：`{report['selection']['pioneer_dominates_69k']}`",
                "",
                "## 1. 全窗底盘 RQAlpha 6.3.0 原生回放（2018-01-02..2026-10-30）",
                "",
                "| 回放 | Full CAGR | IS CAGR | OOS CAGR | MaxDD | Sharpe | Calmar | 笔数 | 佣金(元) |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for label, r in report["chassis_rqa"].items():
                f, is_, oos = r["full"], r["is"], r["oos"]
                lines.append(
                    f"| {label} | {f['cagr']:.2%} | {is_['cagr']:.2%} | {oos['cagr']:.2%} "
                    f"| {f['max_drawdown']:.2%} | {f['sharpe']:.3f} | {f['calmar']:.3f} "
                    f"| {r['trade_count']} | {r['commission_yuan']:.2f} |"
                )
            lines += [
                "",
                "## 2. 统一账户严格消融对照（2024-02/07..2026-10-30，含 BP1 笔数与盈亏）",
                "",
                "| 场景 | CAGR(净) | MaxDD(净) | 真实Peak DD | 穿-15%天 | Calmar | Sharpe | 摩擦(元) | BP1平仓笔数 / 盈亏(元) |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for cell, r in report["account_replay"].items():
                m, bp1 = r["metrics"], r["bp1_summary"]
                lines.append(
                    f"| {cell} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {-r['true_max_dd']:.2%} "
                    f"| {r['breach_days']} | {m['calmar']:.3f} | {m['sharpe']:.3f} | {r['total_friction_yuan']:.2f} "
                    f"| {bp1['closed_trades']} / {bp1['pnl_yuan']:.2f} |"
                )
            STEM.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        STEM.with_suffix(".attempt").unlink(missing_ok=True)
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
