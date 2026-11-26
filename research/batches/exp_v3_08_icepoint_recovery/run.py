"""EXP-V3-08 runner: Post-icepoint asymmetric right-side recovery state machine.

External Evidence Gate:
- Canonical mapping: BREADTH_THRUST_RECOVERY (E3_MIXED_CONDITIONAL).
- External conclusion: Zweig breadth thrusts work at US bear bottoms, while Yang/Gebka/Hudson (2019)
  highlight frequent dead-cat bounces in China A-shares.
- Relevant contradictions: Strictly orthogonal to rejected S3B (monthly 11-sector breadth switch);
  keeps exit rules intact and tests low-bound recovery probes after extreme breadth icepoints.
- Upstream implementation: VectorBT (2018-01..2026-11-26) + RQAlpha 6.3.0 (..2026-10-30).
- Remaining local gap: Whether M1 or M2 captures V-rebounds without excessive dead-cat whipsaw.
  V-rebounds without excessive dead-cat-bounce whipsaw in 2022/2026-11.
- Research action: LOCAL_ADJUDICATION.
"""

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
from research.ashare.experiments import exp_v3_01_regime_super_etf as e1
from research.batches.v3_complexity_hurdle_v2.native import NORMAL, SUPER, replay
from research.batches.v3_complexity_hurdle_v2.run import metrics, require, reserve, utc
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/EXP_V3_08_ICEPOINT_RECOVERY"
PROTOCOL = ROOT / "research/batches/exp_v3_08_icepoint_recovery/PROTOCOL_V1.md"

START = data.EXP_START
RQA_END = data.BUNDLE_CUTOFF_202611
VBT_END = data.EXP_END_202611
CASH = (69000, 100000)

SLICES = {
    "rebound_2020_covid": ("2020-02-01", "2020-07-31"),
    "rebound_2022_shanghai": ("2022-04-01", "2022-07-31"),
    "rebound_2024_feb": ("2024-02-01", "2024-05-31"),
    "rebound_2024_924": ("2024-09-01", "2024-11-30"),
    "deadcat_2026_bear": ("2026-09-01", "2026-11-26"),
}


def compute_recovery_overlay_series(
    panels: Any,
    regime_df: pd.DataFrame,
    *,
    mode: str,  # "baseline" | "m1_ma20" | "m2_thrust"
    ice_th: float = 0.15,
    recovery_weight: float = 0.35,
) -> tuple[pd.Series, pd.Series, dict[str, int]]:
    """Return effective (regime_or_recovery, target_eq_weight, trigger_stats) over calendar."""
    cal = panels.calendar
    if mode == "baseline":
        eff_reg = regime_df["confirmed_regime"].astype(str)
        eff_w = eff_reg.map(
            {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "DEFENSIVE": 0.15}
        ).astype(float)
        return eff_reg, eff_w, {"recovery_entries": 0, "false_breakout_stops": 0, "upgrades": 0}

    hs300 = panels.index_close["000300.SH"]
    csi500 = panels.index_close["000905.SH"]
    cyb = panels.index_close["399006.SZ"]
    ma20_hs = hs300.rolling(20, min_periods=20).mean()
    ma20_500 = csi500.rolling(20, min_periods=20).mean()
    ma20_cyb = cyb.rolling(20, min_periods=20).mean()

    pct60 = regime_df["pct_above_ma60"]
    pct20 = regime_df["pct_above_ma20"]
    amt_r = regime_df["amount_vs_ma20"]
    ice_20 = pct60.rolling(20, min_periods=1).min() < ice_th
    ice_both_10 = (pct60.rolling(10, min_periods=1).min() < ice_th) & (
        pct20.rolling(10, min_periods=1).min() < ice_th
    )

    hs_abv = (hs300 > ma20_hs).fillna(False)
    gr_abv = ((csi500 > ma20_500) | (cyb > ma20_cyb)).fillna(False)
    hs_2d = hs_abv & hs_abv.shift(1, fill_value=False)
    gr_2d = gr_abv & gr_abv.shift(1, fill_value=False)

    p20_5d_ago = pct20.shift(5)
    thrust_ok = ((pct20 >= 0.45) | ((pct20 - p20_5d_ago) >= 0.30)) & (pct20 >= 0.40)

    eff_regs: list[str] = []
    eff_ws: list[float] = []
    in_recovery = False
    trigger_low_hs = 0.0
    trigger_low_500 = 0.0
    cooldown_until = -1
    stats = {"recovery_entries": 0, "false_breakout_stops": 0, "upgrades": 0}
    base_map = {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "DEFENSIVE": 0.15}

    for i, dt in enumerate(cal):
        reg = str(regime_df.at[dt, "confirmed_regime"])
        if reg != "DEFENSIVE":
            if in_recovery:
                stats["upgrades"] += 1
            in_recovery = False
            eff_regs.append(reg)
            eff_ws.append(base_map[reg])
            continue

        if in_recovery:
            # Stop out back to DEFENSIVE if closing below pre-trigger 5d lows or crash override
            stop_hit = bool(regime_df.at[dt, "crash_override"]) or (
                float(hs300.iloc[i]) < trigger_low_hs and float(csi500.iloc[i]) < trigger_low_500
            )
            if stop_hit:
                in_recovery = False
                cooldown_until = i + 10
                stats["false_breakout_stops"] += 1
                eff_regs.append("DEFENSIVE")
                eff_ws.append(0.15)
            else:
                eff_regs.append("RECOVERY")
                eff_ws.append(recovery_weight)
            continue

        # Not in recovery and confirmed_regime == DEFENSIVE
        triggered = False
        if i >= cooldown_until:
            ar = float(amt_r.iloc[i]) if pd.notna(amt_r.iloc[i]) else 0.0
            if mode == "m1_ma20":
                anchor_ok = bool(hs_2d.iloc[i]) or bool(gr_2d.iloc[i])
                triggered = bool(ice_20.iloc[i]) and anchor_ok and ar >= 1.05
            elif mode == "m2_thrust":
                triggered = bool(ice_both_10.iloc[i]) and bool(thrust_ok.iloc[i]) and ar >= 1.15
        if triggered:
            lo_idx = max(0, i - 4)
            trigger_low_hs = float(hs300.iloc[lo_idx : i + 1].min())
            trigger_low_500 = float(csi500.iloc[lo_idx : i + 1].min())
            in_recovery = True
            stats["recovery_entries"] += 1
            eff_regs.append("RECOVERY")
            eff_ws.append(recovery_weight)
        else:
            eff_regs.append("DEFENSIVE")
            eff_ws.append(0.15)

    return pd.Series(eff_regs, index=cal), pd.Series(eff_ws, index=cal), stats


def build_recovery_weights(
    panels: Any,
    regime_df: pd.DataFrame,
    *,
    mode: str,
    ice_th: float = 0.15,
    recovery_weight: float = 0.35,
    end: pd.Timestamp = VBT_END,
) -> tuple[pd.DataFrame, dict[str, int]]:
    eff_reg, eff_w, stats = compute_recovery_overlay_series(
        panels, regime_df, mode=mode, ice_th=ice_th, recovery_weight=recovery_weight
    )
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    cols = list(panels.etf_adj_close.columns)
    weights = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)
    adj = panels.etf_adj_close
    mask = panels.etf_tradability_mask

    current_target = pd.Series(0.0, index=cols, dtype=float)
    prev_state: str | None = None
    last_rebal_pos = -999

    for pos in range(len(cal) - 1):
        sig_dt = cal[pos]
        exec_dt = cal[pos + 1]
        state = str(eff_reg.at[sig_dt])
        eq_total = float(eff_w.at[sig_dt])
        style = str(regime_df.at[sig_dt, "style"])

        desired: dict[str, float] = {}
        if state == "DEFENSIVE":
            div_list = e1._available_bucket(
                exec_dt, e1.DEFENSIVE_SUPER_ETFS, e1.DEFENSIVE_FALLBACKS, mask, adj
            )
            for c in div_list:
                desired[c] = desired.get(c, 0.0) + eq_total / len(div_list)
        else:
            val_list = e1._available_bucket(
                exec_dt, e1.VALUE_SUPER_ETFS, e1.VALUE_FALLBACKS, mask, adj
            )
            gro_list = e1._available_bucket(
                exec_dt, e1.GROWTH_SUPER_ETFS, e1.GROWTH_FALLBACKS, mask, adj
            )
            gro_share, val_share = (
                (0.65, 0.35)
                if style == "GROWTH_LEADING"
                else ((0.35, 0.65) if style == "VALUE_LEADING" else (0.50, 0.50))
            )
            for c in val_list:
                desired[c] = desired.get(c, 0.0) + (eq_total * val_share) / len(val_list)
            for c in gro_list:
                desired[c] = desired.get(c, 0.0) + (eq_total * gro_share) / len(gro_list)

        if bool(mask.at[exec_dt, "511010.SH"]):
            res = max(0.0, 1.0 - eq_total)
            if res > 0:
                desired["511010.SH"] = res

        cand = pd.Series(0.0, index=cols, dtype=float)
        for k, v in desired.items():
            cand[k] = float(v)

        l1_diff = float((cand - current_target).abs().sum())
        state_changed = prev_state is None or state != prev_state
        periodic = (pos - last_rebal_pos >= 10) and l1_diff >= 0.08
        if state_changed or periodic:
            cand_row = pd.Series(np.nan, index=cols, dtype=float)
            for sym in cols:
                if cand[sym] > 0:
                    cand_row[sym] = cand[sym]
                elif current_target[sym] > 0:
                    cand_row[sym] = 0.0
            weights.loc[exec_dt] = cand_row
            current_target = cand
            last_rebal_pos = pos
        prev_state = state

    return weights, stats


def main() -> int:
    reserve(STEM)
    report: dict[str, Any] = {
        "started": utc(),
        "runner_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "versions": {k: version(k) for k in ("rqalpha", "vectorbt")},
        "protocol_sha256": data.sha256_file(PROTOCOL),
        "vbt": {},
        "runs": {},
        "gates": {},
    }
    try:
        prov = data.verify_v3_202611_provenance(verify_content=True)
        report["snapshot_id"] = prov.snapshot_id
        p = data.load_stitched_panels_202611(prov)
        reg = data.compute_v3_regime_series_202611(prov, p.index_close, p.calendar, use_cache=True)

        configs: list[tuple[str, str, float, float, bool]] = [
            ("M0_V3_BASELINE", "baseline", 0.15, 0.15, True),
            ("M1_ICE12_W30", "m1_ma20", 0.12, 0.30, False),
            ("M1_ICE12_W35", "m1_ma20", 0.12, 0.35, False),
            ("M1_ICE12_W40", "m1_ma20", 0.12, 0.40, False),
            ("M1_ICE15_W30", "m1_ma20", 0.15, 0.30, False),
            ("M1_ICE15_W35", "m1_ma20", 0.15, 0.35, True),
            ("M1_ICE15_W40", "m1_ma20", 0.15, 0.40, True),
            ("M1_ICE18_W30", "m1_ma20", 0.18, 0.30, False),
            ("M1_ICE18_W35", "m1_ma20", 0.18, 0.35, False),
            ("M1_ICE18_W40", "m1_ma20", 0.18, 0.40, False),
            ("M2_THRUST_ICE15_W35", "m2_thrust", 0.15, 0.35, False),
            ("M2_THRUST_ICE15_W40", "m2_thrust", 0.15, 0.40, True),
        ]

        weights_map: dict[str, pd.DataFrame] = {}
        for name, mode, ice_th, rec_w, _ in configs:
            w, stats = build_recovery_weights(
                p, reg, mode=mode, ice_th=ice_th, recovery_weight=rec_w, end=VBT_END
            )
            weights_map[name] = w
            prices, mask, targets = (
                f.loc[:VBT_END] for f in (p.etf_adj_close, p.etf_tradability_mask, w)
            )
            validate_execution_targets(targets, prices, mask, p.etf_lifetimes)
            rates = np.array(
                [SUPER if c in prov.super_etf_codes else NORMAL for c in w.columns]
            )[None, :]
            eq = run_target_weights(
                prices,
                targets,
                fees=rates,
                slippage=0.0002,
                initial_cash=100000.0,
                metric_start=START,
                tradability_mask=mask,
                lifetimes=p.etf_lifetimes,
            ).equity.loc[START:VBT_END]
            slice_metrics = {
                s_name: {
                    "return": float(eq.loc[s_st:s_ed].iloc[-1] / eq.loc[s_st:s_ed].iloc[0] - 1.0),
                    "max_dd": float((eq.loc[s_st:s_ed] / eq.loc[s_st:s_ed].cummax() - 1.0).min()),
                }
                for s_name, (s_st, s_ed) in SLICES.items()
            }
            report["vbt"][name] = {
                "stats": stats,
                "full_2018_20261126": metrics(eq),
                "slices": slice_metrics,
            }

        for cash in CASH:
            for name, _, _, _, run_rqa in configs:
                if not run_rqa:
                    continue
                label = f"{name}_{cash}"
                print(utc(), label, flush=True)
                eq, run = replay(
                    weights_map[name], cash, prov.super_etf_codes, True, start=START, end=RQA_END
                )
                fees = sum(float(f["commission"]) for f in run["fills"])
                report["runs"][label] = {
                    "full": metrics(eq),
                    "is": metrics(eq.loc[: data.IS_END]),
                    "oos": metrics(eq.loc[data.IS_END :]),
                    "trade_count": len(run["fills"]),
                    "commission_yuan": round(fees, 2),
                    "dates_pass": run["dates_pass"],
                    "fill_capture_pass": run["fill_capture_pass"],
                    "fees_pass": run["commission_audit"]["fees_pass"],
                    "illegal_non_lot_fills": len(run["commission_audit"]["illegal_non_lot_fills"]),
                }

        runs_list = list(report["runs"].values())
        report["gates"] = {
            "order_dates": all(r["dates_pass"] for r in runs_list),
            "lots_and_capture": all(
                r["fill_capture_pass"] and r["illegal_non_lot_fills"] == 0 for r in runs_list
            ),
            "commissions": all(r["fees_pass"] for r in runs_list),
        }
        require(all(report["gates"].values()), "integrity gate failed")
        m0 = report["runs"]["M0_V3_BASELINE_100000"]["full"]
        m1 = report["runs"]["M1_ICE15_W35_100000"]["full"]
        m2 = report["runs"]["M2_THRUST_ICE15_W40_100000"]["full"]
        best = m1 if m1["calmar"] >= m2["calmar"] else m2
        report["verdict"] = (
            "ASYMMETRIC_RECOVERY_NET_POSITIVE"
            if best["calmar"] > m0["calmar"] and best["cagr"] > m0["cagr"]
            else "NO_NET_EDGE_AFTER_WHIPSAW"
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["verdict"] = "INVALID_RUN"

    code = int(report["verdict"] == "INVALID_RUN")
    report.update(finished=utc(), exit_code=code)
    with STEM.with_suffix(".json").open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, allow_nan=False, indent=1)
        f.write("\n")

    lines = [
        "# EXP-V3-08：8.1% 极端冰点后的非对称右侧复苏与仓位爬坡",
        "",
        f"裁决：`{report['verdict']}`。",
        "",
        "## 1. RQAlpha 6.3.0 原生回放（2018-01-02..2026-10-30，真实分层费率）",
        "",
        "| 回放 | CAGR | MaxDD | Sharpe | Calmar | 成交 | 佣金(元) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, r in report["runs"].items():
        m = r["full"]
        lines.append(
            f"| {label} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {m['sharpe']:.3f} | "
            f"{m['calmar']:.3f} | {r['trade_count']} | {r['commission_yuan']:.2f} |"
        )
    lines += [
        "",
        "## 2. VectorBT 高原与五大历史复苏/死猫跳切片（2018-01-02..2026-11-26）",
        "",
        (
            "| Arm | 触发 | 假突破 | 升级 | 全窗 CAGR | 全窗 MaxDD | 2020疫反 | 2024.924 "
            "| 2026.9-11死猫 |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, b in report["vbt"].items():
        st, fm, sl = b["stats"], b["full_2018_20261126"], b["slices"]
        lines.append(
            f"| {name} | {st['recovery_entries']} | {st['false_breakout_stops']} "
            f"| {st['upgrades']} | {fm['cagr']:.2%} | {fm['max_drawdown']:.2%} "
            f"| {sl['rebound_2020_covid']['return']:.2%} | {sl['rebound_2024_924']['return']:.2%} "
            f"| {sl['deadcat_2026_bear']['return']:.2%} |"
        )
    with STEM.with_suffix(".md").open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(report["verdict"], flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
