"""EXP-V3-07 runner: LOW_VOL permanent bucket & Risk-Budgeted chassis (InvVol & skfolio ERC).

External Evidence Gate:
- Canonical mapping: LOW_VOL (E1_MATURE) & ERC_RISK_PARITY (E2_ESTABLISHED_METHOD).
- External conclusion: Blitz/Pang/van Vliet (2013) document China A-share low-vol/dividend premia;
  ERC is a variance-equalization allocator, not standalone alpha.
- Relevant contradictions: Strictly orthogonal to rejected S4A (unfiltered all-universe inv-vol);
  evaluates risk budgeting strictly inside V3 confirmed-regime equity ceilings (85/60/15).
- Upstream implementation: VectorBT (2018-01-02..2026-11-26) + skfolio RiskBudgeting(VARIANCE)
  + RQAlpha 6.3.0 (2018-01-02..2026-10-30, ¥69k & ¥100k tiered fees).
- Remaining local gap: Whether adding LOW_VOL permanent sleeve & risk-budgeting Value/Growth/LowVol
  cuts 2026-H2 high-vol growth concentration drawdown and improves Calmar/Sharpe vs R0 and S30/ERC.
- Research action: TRANSFER_VALIDATE & UPSTREAM_COMPARE.
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
from research.batches.v3_complexity_hurdle_v2.run import erc_weights, metrics, require, reserve, utc
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/EXP_V3_07_LOWVOL_RISK_BUDGET"
PROTOCOL = ROOT / "research/batches/exp_v3_07_lowvol_risk_budget/PROTOCOL_V1.md"

START = data.EXP_START
RQA_END = data.BUNDLE_CUTOFF_202611
VBT_END = data.EXP_END_202611
STRESS_START = pd.Timestamp("2026-07-01")
CASH = (69000, 100000)

LOWVOL_FALLBACKS = ("512890.SH", "510880.SH")


def _mature_proxy_for_vol(
    sig_dt: pd.Timestamp,
    active_bucket: tuple[str, ...],
    fallbacks: tuple[str, ...],
    adj: pd.DataFrame,
    window: int,
) -> str:
    for c in (*active_bucket, *fallbacks):
        if c in adj.columns and adj.loc[:sig_dt, c].notna().sum() >= window + 1:
            return c
    return active_bucket[0]


def compute_bucket_shares(
    ret_df: pd.DataFrame,
    mode: str,
) -> dict[str, float]:
    """Compute causal bucket weights across VALUE / GROWTH / LOW_VOL."""
    if mode == "inv_vol":
        vols = ret_df.std().clip(lower=1e-6)
        inv = 1.0 / vols
        w = inv / inv.sum()
        return {str(k): float(v) for k, v in w.items()}
    if mode == "erc":
        w = erc_weights(ret_df)
        return {str(k): float(v) for k, v in w.items()}
    raise ValueError(f"Unsupported mode: {mode}")


def build_lowvol_risk_budget_weights(
    panels: Any,
    regime_df: pd.DataFrame,
    *,
    mode: str,  # "r0_baseline" | "r1_lowvol_fixed" | "inv_vol" | "erc"
    vol_window: int = 60,
    rebalance_min_gap_days: int = 10,
    drift_band: float = 0.08,
    end: pd.Timestamp = VBT_END,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    cols = list(panels.etf_adj_close.columns)
    weights = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)
    adj = panels.etf_adj_close
    mask = panels.etf_tradability_mask

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

        val_list = e1._available_bucket(exec_dt, e1.VALUE_SUPER_ETFS, e1.VALUE_FALLBACKS, mask, adj)
        gro_list = e1._available_bucket(
            exec_dt, e1.GROWTH_SUPER_ETFS, e1.GROWTH_FALLBACKS, mask, adj
        )
        lov_list = e1._available_bucket(
            exec_dt, e1.DEFENSIVE_SUPER_ETFS, LOWVOL_FALLBACKS, mask, adj
        )

        desired: dict[str, float] = {}
        if regime == "DEFENSIVE":
            eq_total = 0.15
            for c in lov_list:
                desired[c] = desired.get(c, 0.0) + eq_total / len(lov_list)
        else:
            eq_total = 0.85 if regime == "OFFENSIVE" else 0.60
            if mode == "r0_baseline":
                shares = (
                    {"VALUE": 0.35, "GROWTH": 0.65, "LOW_VOL": 0.0}
                    if style == "GROWTH_LEADING"
                    else (
                        {"VALUE": 0.65, "GROWTH": 0.35, "LOW_VOL": 0.0}
                        if style == "VALUE_LEADING"
                        else {"VALUE": 0.50, "GROWTH": 0.50, "LOW_VOL": 0.0}
                    )
                )
            elif mode == "r1_lowvol_fixed":
                shares = (
                    {"VALUE": 0.25, "GROWTH": 0.45, "LOW_VOL": 0.30}
                    if style == "GROWTH_LEADING"
                    else (
                        {"VALUE": 0.45, "GROWTH": 0.25, "LOW_VOL": 0.30}
                        if style == "VALUE_LEADING"
                        else {"VALUE": 0.35, "GROWTH": 0.35, "LOW_VOL": 0.30}
                    )
                )
            else:
                v_proxy = _mature_proxy_for_vol(
                    sig_dt, val_list, e1.VALUE_FALLBACKS, adj, vol_window
                )
                g_proxy = _mature_proxy_for_vol(
                    sig_dt, gro_list, e1.GROWTH_FALLBACKS, adj, vol_window
                )
                l_proxy = _mature_proxy_for_vol(sig_dt, lov_list, LOWVOL_FALLBACKS, adj, vol_window)
                hist = pd.DataFrame(
                    {
                        "VALUE": adj.loc[:sig_dt, v_proxy],
                        "GROWTH": adj.loc[:sig_dt, g_proxy],
                        "LOW_VOL": adj.loc[:sig_dt, l_proxy],
                    }
                ).dropna().tail(vol_window + 1)
                require(len(hist) == vol_window + 1, f"insufficient vol history @ {sig_dt.date()}")
                ret_df = hist.pct_change(fill_method=None).iloc[1:]
                shares = compute_bucket_shares(ret_df, mode)

            for bucket_name, bucket_codes in (
                ("VALUE", val_list),
                ("GROWTH", gro_list),
                ("LOW_VOL", lov_list),
            ):
                b_w = shares.get(bucket_name, 0.0)
                if b_w > 0:
                    for c in bucket_codes:
                        desired[c] = desired.get(c, 0.0) + (eq_total * b_w) / len(bucket_codes)

        if bool(mask.at[exec_dt, "511010.SH"]):
            res = max(0.0, 1.0 - eq_total)
            if res > 0:
                desired["511010.SH"] = res

        cand = pd.Series(0.0, index=cols, dtype=float)
        for k, v in desired.items():
            cand[k] = float(v)

        l1_diff = float((cand - current_target).abs().sum())
        regime_changed = prev_regime is None or regime != prev_regime
        periodic = (pos - last_rebal_pos >= rebalance_min_gap_days) and l1_diff >= drift_band
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
        "versions": {k: version(k) for k in ("rqalpha", "vectorbt", "skfolio")},
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

        arm_defs = [
            ("R0_V3_EQUAL_BUCKET", dict(mode="r0_baseline", vol_window=60)),
            ("R1_V3_WITH_LOWVOL_CORE", dict(mode="r1_lowvol_fixed", vol_window=60)),
            ("R2_V3_INVVOL_W40", dict(mode="inv_vol", vol_window=40)),
            ("R2_V3_INVVOL_W60", dict(mode="inv_vol", vol_window=60)),
            ("R2_V3_INVVOL_W80", dict(mode="inv_vol", vol_window=80)),
            ("R3_V3_SKFOLIO_ERC_W40", dict(mode="erc", vol_window=40)),
            ("R3_V3_SKFOLIO_ERC_W60", dict(mode="erc", vol_window=60)),
            ("R3_V3_SKFOLIO_ERC_W80", dict(mode="erc", vol_window=80)),
        ]

        weights_map: dict[str, pd.DataFrame] = {}
        for name, kw in arm_defs:
            w, events = build_lowvol_risk_budget_weights(p, reg, **kw, end=VBT_END)
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
            for name, _ in arm_defs:
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
        r0 = report["runs"]["R0_V3_EQUAL_BUCKET_100000"]["full"]
        r3 = report["runs"]["R3_V3_SKFOLIO_ERC_W60_100000"]["full"]
        report["verdict"] = (
            "LOWVOL_RISK_BUDGET_IMPROVES_SHARPE_CALMAR"
            if r3["calmar"] > r0["calmar"] and r3["max_drawdown"] > r0["max_drawdown"]
            else "NO_HURDLE_EDGE_OVER_BASELINE"
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
        "# EXP-V3-07：红利低波常驻底盘与 V3 风险预算定权",
        "",
        f"裁决：`{report['verdict']}`。",
        "",
        "## 1. RQAlpha 6.3.0 原生回放（2018-01-02..2026-10-30，真实分层费率）",
        "",
        "| 回放 | CAGR | MaxDD | Sharpe | Calmar | OOS CAGR | 成交 | 佣金(元) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, r in report["runs"].items():
        m, om = r["full"], r["oos"]
        lines.append(
            f"| {label} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {m['sharpe']:.3f} | "
            f"{m['calmar']:.3f} | {om['cagr']:.2%} | {r['trade_count']} "
            f"| {r['commission_yuan']:.2f} |"
        )
    lines += [
        "",
        "## 2. VectorBT 全窗与 2026-07..11-26 切片",
        "",
        "| Arm | CAGR | MaxDD | Sharpe | Calmar | 2026-07..11-26 收益 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, b in report["vbt"].items():
        fm, sm = b["full_2018_20261126"], b["stress_202607_20261126"]
        lines.append(
            f"| {name} | {fm['cagr']:.2%} | {fm['max_drawdown']:.2%} | {fm['sharpe']:.3f} | "
            f"{fm['calmar']:.3f} | {sm['total_return']:.2%} |"
        )
    with STEM.with_suffix(".md").open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(report["verdict"], flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
