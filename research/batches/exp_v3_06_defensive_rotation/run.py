"""EXP-V3-06 runner: Low-ticket defensive reserve & trend-filtered defensive asset rotation.

External Evidence Gate:
- Canonical mapping: CHINA_DEFENSIVE_ETF & DEFENSIVE_MOM (E4_OPEN_LOCAL).
- External conclusion: GTAA trend filtering improves drawdown control, but Chinese bond/MMF/gold
  ETF lot sizes, non-super 5-yuan min commission, and 2026-H2 gold crash require local test.
- Relevant contradictions: Shorter trend windows add whipsaw; orthogonal to closed RL-053 / S8A.
- Upstream implementation: VectorBT (2018-01..2026-11-26) + RQAlpha 6.3.0 (..2026-10-30).
- Remaining local gap: Low-ticket bond friction drop & trend-filtered DEFENSIVE rotation.
- Research action: NEW_HYPOTHESIS.
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
STEM = ROOT / "research/results/EXP_V3_06_DEFENSIVE_ROTATION"
PROTOCOL = ROOT / "research/batches/exp_v3_06_defensive_rotation/PROTOCOL_V1.md"

START = data.EXP_START
RQA_END = data.BUNDLE_CUTOFF_202611
VBT_END = data.EXP_END_202611
STRESS_START = pd.Timestamp("2026-07-01")
CASH = (69000, 100000)

LOW_TICKET_BONDS = ("159649.SZ", "511260.SH", "511010.SH")
GOLD_CODE = "518880.SH"


def select_bond_reserve(
    exec_dt: pd.Timestamp,
    mask_df: pd.DataFrame,
    adj_df: pd.DataFrame,
    candidates: tuple[str, ...],
) -> str | None:
    for code in candidates:
        if code not in mask_df.columns or not bool(mask_df.at[exec_dt, code]):
            continue
        obs = int(adj_df.loc[:exec_dt, code].notna().sum())
        if obs >= 20:
            return code
    return "511010.SH" if bool(mask_df.at[exec_dt, "511010.SH"]) else None


def build_defensive_weights(
    panels: Any,
    regime_df: pd.DataFrame,
    *,
    reserve_mode: str,  # "511010" | "low_ticket" | "mmf_idle"
    gold_weight: float = 0.0,
    trend_ma_window: int | None = None,
    rebalance_min_gap_days: int = 10,
    drift_band: float = 0.08,
    end: pd.Timestamp = VBT_END,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Build strictly causal T+1 weights for EXP-V3-06 variants."""
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    cols = list(panels.etf_adj_close.columns)
    weights = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)

    adj = panels.etf_adj_close
    mask = panels.etf_tradability_mask
    ma20_panel = adj.rolling(20, min_periods=20).mean()
    ma_w_panel = (
        adj.rolling(trend_ma_window, min_periods=trend_ma_window).mean()
        if trend_ma_window is not None
        else None
    )

    current_target = pd.Series(0.0, index=cols, dtype=float)
    prev_regime: str | None = None
    last_rebal_pos = -999
    events: list[dict[str, Any]] = []

    for pos in range(len(cal) - 1):
        sig_dt = cal[pos]
        exec_dt = cal[pos + 1]
        reg_row = regime_df.loc[sig_dt]
        regime = str(reg_row["confirmed_regime"])
        style = str(reg_row["style"])

        desired: dict[str, float] = {}
        if regime == "DEFENSIVE":
            div_bucket = e1._available_bucket(
                exec_dt, e1.DEFENSIVE_SUPER_ETFS, e1.DEFENSIVE_FALLBACKS, mask, adj
            )
            div_ok = True
            if trend_ma_window is not None and ma_w_panel is not None:
                # Filter dividend risk sleeve by causal MA trend (fallback to mature proxy ETF)
                trend_code = next(
                    (
                        c
                        for c in (*div_bucket, "512890.SH", "510880.SH")
                        if c in adj.columns and pd.notna(ma_w_panel.at[sig_dt, c])
                    ),
                    div_bucket[0],
                )
                c_sig = adj.at[sig_dt, trend_code]
                m20_sig = ma20_panel.at[sig_dt, trend_code]
                mw_sig = ma_w_panel.at[sig_dt, trend_code]
                div_ok = bool(
                    pd.notna(c_sig) and pd.notna(mw_sig) and c_sig > mw_sig and m20_sig > mw_sig
                )
            if div_ok:
                for c in div_bucket:
                    desired[c] = desired.get(c, 0.0) + 0.15 / len(div_bucket)

            if gold_weight > 0 and bool(mask.at[exec_dt, GOLD_CODE]):
                gold_ok = True
                if trend_ma_window is not None and ma_w_panel is not None:
                    c_g = adj.at[sig_dt, GOLD_CODE]
                    m20_g = ma20_panel.at[sig_dt, GOLD_CODE]
                    mw_g = ma_w_panel.at[sig_dt, GOLD_CODE]
                    gold_ok = bool(
                        pd.notna(c_g) and pd.notna(mw_g) and c_g > mw_g and m20_g > mw_g
                    )
                if gold_ok:
                    desired[GOLD_CODE] = desired.get(GOLD_CODE, 0.0) + gold_weight
        else:
            eq_total = 0.85 if regime == "OFFENSIVE" else 0.60
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

        risk_sum = sum(desired.values())
        rem_reserve = max(0.0, 1.0 - risk_sum)
        if rem_reserve > 1e-6:
            if reserve_mode == "511010":
                res_code = "511010.SH" if bool(mask.at[exec_dt, "511010.SH"]) else None
            elif reserve_mode == "low_ticket":
                res_code = select_bond_reserve(exec_dt, mask, adj, LOW_TICKET_BONDS)
            elif reserve_mode == "mmf_idle":
                res_code = "511880.SH" if bool(mask.at[exec_dt, "511880.SH"]) else None
            else:
                res_code = None
            if res_code is not None:
                desired[res_code] = desired.get(res_code, 0.0) + rem_reserve

        cand = pd.Series(0.0, index=cols, dtype=float)
        for k, v in desired.items():
            cand[k] = float(v)

        l1_diff = float((cand - current_target).abs().sum())
        regime_changed = prev_regime is None or regime != prev_regime
        eff_band = 0.10 if reserve_mode == "low_ticket" else drift_band
        periodic = (pos - last_rebal_pos >= rebalance_min_gap_days) and l1_diff >= eff_band
        if regime_changed or periodic:
            for sym, val in cand.items():
                if val > 0 and not bool(mask.at[exec_dt, sym]):
                    raise RuntimeError(f"Un-tradable positive weight {sym} @ {exec_dt.date()}")
            cand_row = pd.Series(np.nan, index=cols, dtype=float)
            for sym in cols:
                if cand[sym] > 0:
                    cand_row[sym] = cand[sym]
                elif current_target[sym] > 0:
                    cand_row[sym] = 0.0
            weights.loc[exec_dt] = cand_row
            current_target = cand
            last_rebal_pos = pos
            events.append(
                {
                    "signal_date": str(sig_dt.date()),
                    "exec_date": str(exec_dt.date()),
                    "regime": regime,
                }
            )
        prev_regime = regime

    return weights, events


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

        arm_defs: list[tuple[str, dict[str, Any], bool]] = [
            (
                "D0_BASELINE_511010",
                dict(reserve_mode="511010", gold_weight=0.0, trend_ma_window=None),
                True,
            ),
            (
                "D1_LOW_TICKET_RESERVE",
                dict(reserve_mode="low_ticket", gold_weight=0.0, trend_ma_window=None),
                True,
            ),
            (
                "D1B_MMF_IDLE_SWEEP_DIAG",
                dict(reserve_mode="mmf_idle", gold_weight=0.0, trend_ma_window=None),
                True,
            ),
            (
                "D2_TREND_DEF_MA40",
                dict(reserve_mode="low_ticket", gold_weight=0.10, trend_ma_window=40),
                True,
            ),
            (
                "D2_TREND_DEF_MA60",
                dict(reserve_mode="low_ticket", gold_weight=0.10, trend_ma_window=60),
                True,
            ),
            (
                "D2_TREND_DEF_MA90",
                dict(reserve_mode="low_ticket", gold_weight=0.10, trend_ma_window=90),
                True,
            ),
            (
                "D2_TREND_DEF_MA60_511010",
                dict(reserve_mode="511010", gold_weight=0.10, trend_ma_window=60),
                False,
            ),
            (
                "D3_UNFILTERED_GOLD_CTRL",
                dict(reserve_mode="low_ticket", gold_weight=0.10, trend_ma_window=None),
                True,
            ),
        ]

        weights_map: dict[str, pd.DataFrame] = {}
        for name, kw, _ in arm_defs:
            w, events = build_defensive_weights(p, reg, **kw, end=VBT_END)
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
            report["vbt"][name] = {
                "events": len(events),
                "full_2018_20261126": metrics(eq),
                "is_2018_2023": metrics(eq.loc[: data.IS_END]),
                "oos_2024_20261126": metrics(eq.loc[data.IS_END :]),
                "stress_202607_20261126": metrics(eq.loc[STRESS_START:VBT_END]),
            }

        for cash in CASH:
            for name, _, run_rqa in arm_defs:
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
                    "reject_count": len(run["rejects"]),
                    "commission_yuan": round(fees, 2),
                    "commission_to_initial": fees / cash,
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
        d0 = report["runs"]["D0_BASELINE_511010_100000"]["full"]
        d2 = report["runs"]["D2_TREND_DEF_MA60_100000"]["full"]
        report["verdict"] = (
            "DEFENSIVE_TREND_IMPROVES_CARRY_AND_CALMAR"
            if d2["calmar"] > d0["calmar"] and d2["cagr"] >= d0["cagr"]
            else "MARGINAL_OR_MIXED"
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
        "# EXP-V3-06：防御蓄水池降摩擦与趋势过滤防御资产轮动",
        "",
        f"裁决：`{report['verdict']}`。",
        "",
        "## 1. RQAlpha 6.3.0 原生回放（2018-01-02..2026-10-30，真实分层费率）",
        "",
        "| 回放 | CAGR | MaxDD | Sharpe | Calmar | OOS CAGR | 成交 | 佣金(元) | 佣金占比 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, r in report["runs"].items():
        m, om = r["full"], r["oos"]
        lines.append(
            f"| {label} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {m['sharpe']:.3f} | "
            f"{m['calmar']:.3f} | {om['cagr']:.2%} | {r['trade_count']} "
            f"| {r['commission_yuan']:.2f} | {r['commission_to_initial']:.2%} |"
        )
    lines += [
        "",
        "## 2. VectorBT 全窗与 2026-07..11-26 深熊黄金暴跌切片",
        "",
        (
            "| Arm | 全窗 CAGR | 全窗 MaxDD | Sharpe | Calmar "
            "| 2026-07..11-26 收益 | 2026-07..11-26 MaxDD |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, b in report["vbt"].items():
        fm, sm = b["full_2018_20261126"], b["stress_202607_20261126"]
        lines.append(
            f"| {name} | {fm['cagr']:.2%} | {fm['max_drawdown']:.2%} | {fm['sharpe']:.3f} | "
            f"{fm['calmar']:.3f} | {sm['total_return']:.2%} | {sm['max_drawdown']:.2%} |"
        )
    with STEM.with_suffix(".md").open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(report["verdict"], flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
