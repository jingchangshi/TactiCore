"""Runner for EXP-V3-05B: Native RQAlpha replay with PIT circ_mv BP1 stock leg."""

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
from research.ashare.v3_data import ts_to_rq
from research.batches.v3_account_replay_v2.native import replay_full_account
from research.batches.v3_account_replay_v2.policy import (
    FOCUS,
    GOLD,
    GROWTH,
    SECTORS,
    VALUE,
    indicators,
)
from research.batches.v3_account_replay_v2.stock_signals import (
    MIN_CIRC_MV_WAN,
    build_causal_bp1_candidates_202611,
)

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/EXP_V3_05B_ACCOUNT_REPLAY_FULL"
PROTOCOL = ROOT / "research/batches/v3_account_replay_v2/PROTOCOL_V2.md"

OOS_CONC_START = pd.Timestamp("2024-07-01")
OOS_CASH_START = pd.Timestamp("2024-02-01")
END = data.BUNDLE_CUTOFF_202611


def utc() -> str:
    return pd.Timestamp.now("UTC").isoformat()


def reserve(stem: Path) -> None:
    markers = [stem.with_suffix(ext) for ext in (".md", ".json", ".attempt")]
    if any(p.exists() for p in markers):
        raise FileExistsError("prior result/attempt exists; single-attempt rule blocks rerun")
    with markers[-1].open("x", encoding="utf-8") as f:
        f.write(utc() + "\n")


def _series_metrics(eq: pd.Series) -> dict[str, Any]:
    ret = eq.pct_change(fill_method=None).iloc[1:]
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1.0 / 365.25)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0)
    total_ret = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
    dd = float((eq / eq.cummax() - 1.0).min())
    sharpe = float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() else None
    calmar = cagr / abs(dd) if dd < 0 else None
    return {
        "total_return": total_ret,
        "cagr": cagr,
        "max_drawdown": dd,
        "sharpe": sharpe,
        "calmar": calmar,
        "final_nav": float(eq.iloc[-1]),
    }


def _build_etf_features(
    panels: Any, white_ts: set[str]
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    codes_rq = sorted({FOCUS, GOLD, *SECTORS, *VALUE, *GROWTH})
    from research.ashare.v3_data import rq_to_ts

    feat_dfs: dict[str, pd.DataFrame] = {}
    for rq in codes_rq:
        ts = rq_to_ts(rq)
        if ts in panels.etf_adj_close.columns and ts in panels.etf_raw_close.columns:
            df = indicators(panels.etf_adj_close[ts], panels.etf_raw_close[ts])
            df = df.where(panels.etf_tradability_mask[ts], np.nan)
            feat_dfs[rq] = df

    features: dict[str, dict[str, Any]] = {}
    for dt in panels.calendar:
        d = str(dt.date())
        day_map: dict[str, Any] = {}
        for rq, df in feat_dfs.items():
            row = df.loc[dt]
            if pd.notna(row["c"]) and pd.notna(row["raw"]) and float(row["raw"]) > 0:
                day_map[rq] = row
        features[d] = day_map

    white_rq = {ts_to_rq(c) for c in white_ts}
    return features, white_rq


def _summarize_cell(name: str, cfg: dict[str, Any], res: dict[str, Any]) -> dict[str, Any]:
    rows = res["daily"]
    dates = pd.to_datetime([r["date"] for r in rows])
    native_eq = pd.Series([r["nav"] for r in rows], index=dates, dtype=float)
    net_slip_eq = pd.Series(
        [r["net_nav_after_5bp_stock_slip"] for r in rows], index=dates, dtype=float
    )
    fills = res["fills"]
    stock_fills = [f for f in fills if f["group"] == "stock"]
    etf_fills = [f for f in fills if f["group"] != "stock"]
    comm_total = sum(float(f["commission"]) for f in fills)
    tax_total = sum(float(f["tax"]) for f in fills)
    other_total = sum(float(f["other"]) for f in fills)
    slip_total = sum(float(f["stock_slip_5bp"]) for f in fills)
    triggers = sum(1 for r in rows if r["trigger"])
    locked_days = sum(1 for r in rows if r["locked"])
    breach_days = sum(1 for r in rows if r["breach"] > 0)
    stock_pnl = sum(float(r["pnl"].get("stock", 0.0)) for r in rows)
    conc_pnl = sum(float(r["pnl"].get("concentrated", 0.0)) for r in rows)
    broad_pnl = sum(float(r["pnl"].get("broad", 0.0)) for r in rows)
    ind_pnl = sum(float(r["pnl"].get("industry", 0.0)) for r in rows)
    gold_pnl = sum(float(r["pnl"].get("gold", 0.0)) for r in rows)
    main_pf = ("000", "001", "002", "003", "600", "601", "603", "605")
    max_stocks_held = max(
        (
            sum(
                1
                for sym in r["weights"]
                if sym != FOCUS
                and sym[:3] in main_pf
                and sym.endswith((".XSHG", ".XSHE"))
            )
            for r in rows
        ),
        default=0,
    )
    return {
        "cell": name,
        **cfg,
        "native_metrics": _series_metrics(native_eq),
        "net_after_5bp_stock_slip": _series_metrics(net_slip_eq),
        "redline_breached": breach_days > 0,
        "breach_days": breach_days,
        "max_dd": float(max(r["dd"] for r in rows)),
        "l2_triggers": triggers,
        "locked_days": locked_days,
        "fill_count": len(fills),
        "stock_fill_count": len(stock_fills),
        "etf_fill_count": len(etf_fills),
        "max_concurrent_stocks": max_stocks_held,
        "commission_yuan": round(comm_total, 2),
        "tax_yuan": round(tax_total, 2),
        "other_fees_yuan": round(other_total, 2),
        "explicit_stock_slip_5bp_yuan": round(slip_total, 2),
        "total_friction_yuan": round(comm_total + tax_total + other_total + slip_total, 2),
        "pnl_attribution": {
            "stock": round(stock_pnl, 2),
            "concentrated_159558": round(conc_pnl, 2),
            "broad": round(broad_pnl, 2),
            "industry": round(ind_pnl, 2),
            "gold": round(gold_pnl, 2),
        },
        "violation_count": len(res["violations"]),
        "violations": res["violations"],
        "reject_count": len(res["rejects"]),
        "sample_stock_fills": stock_fills[:20],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# EXP-V3-05B：解锁 PIT 流通市值个股先锋腿的完整 V3 单账户原生回放",
        "",
        (
            f"裁决：`{report['verdict']}`（仅 OOS 评估；IS 因缺失 2017–2023 当次公告版 PIT 财务"
            "继续保持 `IS_STOCK_BLOCKED_DATA`）。"
        ),
        "",
        "## 1. 信号漏斗审计（`2024-02-01..2026-10-30`，`circ_mv >= 500,000 万元 = 50 亿元`）",
        "",
        *(f"- `{k}`: `{v}`" for k, v in report["signal_stats"].items()),
        "",
        "## 2. 全账户原生 RQAlpha 回放总表（含 5bp 股票显式滑点后净值）",
        "",
        (
            "| Cell | 区间 | 股票 | L2 | CAGR(含滑点) | MaxDD(含滑点) | Sharpe "
            "| 触发L2次数 | 穿-15%天数 | 股票成交 | 股票PnL(元) | 159558 PnL "
            "| 总摩擦(元) | 违规数 |"
        ),
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for c in report["cells"].values():
        m = c["net_after_5bp_stock_slip"]
        p = c["pnl_attribution"]
        l2_str = "LOCK" if c["lock_enabled"] else "NONE"
        lines.append(
            f"| {c['cell']} | {c['start']}..{c['end']} | "
            f"{'ON' if c['enable_stocks'] else 'OFF'} | {l2_str} | {m['cagr']:.2%} | "
            f"{m['max_drawdown']:.2%} | {m['sharpe']:.3f} | {c['l2_triggers']} | "
            f"{c['breach_days']} | {c['stock_fill_count']} | {p['stock']:.0f} | "
            f"{p['concentrated_159558']:.0f} | {c['total_friction_yuan']:.1f} | "
            f"{c['violation_count']} |"
        )
    lines += [
        "",
        "## 3. 完整性门槛",
        *(f"- `{k}`: `{v}`" for k, v in report["gates"].items()),
    ]
    if "error" in report:
        lines += ["", f"错误：`{report['error']}`"]
    return "\n".join(lines) + "\n"


def main() -> int:
    reserve(STEM)
    report: dict[str, Any] = {
        "started": utc(),
        "runner_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "versions": {"rqalpha": version("rqalpha")},
        "circ_mv_threshold_wan": MIN_CIRC_MV_WAN,
        "protocol_sha256": data.sha256_file(PROTOCOL),
        "signal_stats": {},
        "cells": {},
        "gates": {},
    }
    try:
        prov = data.verify_v3_202611_provenance(verify_content=True)
        report["snapshot_id"] = prov.snapshot_id
        panels = data.load_stitched_panels_202611(prov)
        reg = data.compute_v3_regime_series_202611(
            prov, panels.index_close, panels.calendar, use_cache=True
        )
        market = {
            str(dt.date()): (str(row["confirmed_regime"]), str(row["style"]))
            for dt, row in reg.iterrows()
        }
        features, white_rq = _build_etf_features(panels, set(prov.super_etf_codes))
        candidates_by_date, sig_stats = build_causal_bp1_candidates_202611(
            oos_start=OOS_CASH_START, bundle_end=END
        )
        report["signal_stats"] = sig_stats

        cal_all = panels.calendar[panels.calendar <= END]
        specs: list[tuple[str, pd.Timestamp, float, float, bool, bool]] = [
            ("CORE25_69000_LOCK", OOS_CONC_START, 69000.0, 0.25, True, True),
            ("CORE25_69000_NEVER_L2", OOS_CONC_START, 69000.0, 0.25, False, True),
            ("CORE25_100000_LOCK", OOS_CONC_START, 100000.0, 0.25, True, True),
            ("CORE25_100000_NEVER_L2", OOS_CONC_START, 100000.0, 0.25, False, True),
            ("HEAVY70_69000_LOCK", OOS_CONC_START, 69000.0, 0.70, True, True),
            ("HEAVY70_69000_NEVER_L2", OOS_CONC_START, 69000.0, 0.70, False, True),
            ("HEAVY70_100000_LOCK", OOS_CONC_START, 100000.0, 0.70, True, True),
            ("HEAVY70_100000_NEVER_L2", OOS_CONC_START, 100000.0, 0.70, False, True),
            ("CORE25_100000_ETF_ONLY_LOCK", OOS_CONC_START, 100000.0, 0.25, True, False),
            ("HEAVY70_100000_ETF_ONLY_LOCK", OOS_CONC_START, 100000.0, 0.70, True, False),
            ("OOS_CASH_2024_100000_LOCK", OOS_CASH_START, 100000.0, 0.0, True, True),
            ("OOS_CASH_2024_69000_LOCK", OOS_CASH_START, 69000.0, 0.0, True, True),
        ]

        for name, start_ts, cash, seed, lock_on, enable_stocks in specs:
            print(utc(), name, flush=True)
            days = [str(d.date()) for d in cal_all[cal_all >= start_ts]]
            res = replay_full_account(
                days,
                market,
                features,
                candidates_by_date,
                white_rq,
                cash,
                seed,
                lock_on,
                enable_stocks=enable_stocks,
            )
            cfg = {
                "start": days[0],
                "end": days[-1],
                "initial_cash": cash,
                "seed": seed,
                "lock_enabled": lock_on,
                "enable_stocks": enable_stocks,
            }
            report["cells"][name] = _summarize_cell(name, cfg, res)

        all_cells = list(report["cells"].values())
        report["gates"] = {
            "zero_violations": all(c["violation_count"] == 0 for c in all_cells),
            "stock_signals_present": sig_stats["qualified_bp1"] > 0
            and any(c["stock_fill_count"] > 0 for c in all_cells),
            "circ_mv_unit_wan_verified": sig_stats["circ_mv_missing"]
            < sig_stats["bp1_tech_raw"] * 0.05,
        }
        report["verdict"] = (
            "FULL_V3_REPLAY_VERIFIED"
            if all(report["gates"].values())
            else "FAILED_GATE"
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["gates"]["completed"] = False
        report["verdict"] = "INVALID_RUN"

    code = int(report["verdict"] != "FULL_V3_REPLAY_VERIFIED")
    report.update(finished=utc(), exit_code=code)
    with STEM.with_suffix(".json").open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, allow_nan=False, indent=1)
        f.write("\n")
    with STEM.with_suffix(".md").open("x", encoding="utf-8") as f:
        f.write(_markdown(report))
    print(report["verdict"], flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
