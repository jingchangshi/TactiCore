"""EXP-V3-04B: V32 磨底回补门②（折价门）单因素消融与约束计数诊断。

预注册协议：`research/batches/exp_v3_04b/PROTOCOL_V1.md`（先提交、后一次授权运行）。

================================================================================
External Evidence Gate（8 项前置强制声明）
================================================================================
- Canonical mapping: `EXP-V3-04B` -> `V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION`（registry 既有条目，
  四门槛之门②单因素消融，非新策略）。
- External tier: `E4_OPEN_LOCAL`（沿用 registry 条目）。
- External conclusion: 外部证据只支持深跌低吸需趋势/折价/止稳过滤这一族的一般结论，
  不回答折价门在其余三门存在时是否冗余。
- Relevant contradictions: `EXP-V3-04` 3×3 高原 `disc = 6%/7%/8%` 结果逐位相同，与规格中
  “>=7% discount 为独立护栏”的表述矛盾；本实验只检验该矛盾。
- Upstream implementation: VectorBT `tacticore/engines/vectorbt_adapter.py:run_target_weights`；
  原生 RQAlpha 6.3.0 复核复用原脚本 `_run_rqalpha_check`。
- Existing TactiCore evidence: `RL-055` 与 `research/results/EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.*`。
- Remaining local gap: 门②在 9 窗口 V32 路径上是否曾为唯一否决条件，以及去掉它的影响。
- Research action: `BOUNDED_ABLATION`。

================================================================================
PIT Tradability Gate（6 要素强制声明）
================================================================================
1. Date-aware universe: 与 `EXP-V3-04` 相同的 9 窗口与标的，`etf_tradability_mask` 原样传入。
2. Asset lifetime metadata: `research/ashare/v3_data.py` 的 `etf_lifetimes`（只读 import）。
3. Pre-listing fallback handling: 不回填；`159558.SZ` 仅从 `2024-07-16` 起评估。
4. Missing execution price / suspension: `NaN` 不补零；`T` 收盘信号、`T+1` 执行。
5. Strategy inception: 每窗 `25%` 目标 ETF + `75%` `511010.SH` 起步。
6. Executability of every positive target: VectorBT `validate_execution_targets`；
   原生 RQAlpha 4 窗口（截至 bundle `2026-08-31`）拒单计数。
================================================================================

原脚本 `exp_v3_04_bottom_grind_cost_reduction.py` 不修改；本文件只复写 `GUARDED_GRIND`
分支以加入门②开关与逐日门槛记录，并以 `V32_REPRO == V32` 逐位一致证明复写等价。
"""

# ruff: noqa: E501  (Markdown table rows in the report renderer)
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.ashare.experiments.exp_v3_04_bottom_grind_cost_reduction import (
    VARIANTS,
    WINDOWS,
    VariantConfig,
    _compute_rsi14,
    _run_rqalpha_check,
    _simulate_sleeve,
)
from research.ashare.v3_data import (
    V3StitchedPanels,
    compute_v3_market_regime_series,
    load_stitched_panels,
    verify_v3_provenance,
)
from tacticore.engines.vectorbt_adapter import run_target_weights

RESULTS_DIR = Path(__file__).resolve().parents[3] / "research/results"
OUT_JSON = RESULTS_DIR / "EXP_V3_04B_DISCOUNT_GATE_ABLATION.json"
OUT_MD = RESULTS_DIR / "EXP_V3_04B_DISCOUNT_GATE_ABLATION.md"
RQ_WINDOWS = ("IS_512480_19_23", "OOS_512480_24_26", "OOS_159558_24_26", "OOS_159558_2026")

V32_CFG = next(v for v in VARIANTS if v.name == "V32_GUARDED_BOTTOM_GRIND_25")
STATIC_CFG = VARIANTS[0]


def _simulate_guarded(
    panels: V3StitchedPanels,
    regime_df: pd.DataFrame,
    *,
    etf_code: str,
    start_str: str,
    end_str: str,
    cfg: VariantConfig,
    gate2_enabled: bool,
    fees: float = 0.00005,
    slippage: float = 0.0005,
) -> tuple[dict[str, Any], pd.DataFrame, list[str], dict[str, int]]:
    """Original GUARDED_GRIND state machine with a gate-2 switch and per-day gate logging."""
    if cfg.mode != "GUARDED_GRIND":
        raise ValueError("guarded_grind_only")
    start, end = pd.Timestamp(start_str), pd.Timestamp(end_str)
    cal = panels.calendar[(panels.calendar >= start) & (panels.calendar <= end)]
    cols = [etf_code, "511010.SH"]
    px = panels.etf_adj_close[cols]
    s = px[etf_code]

    ma5 = s.rolling(5, min_periods=5).mean()
    ma20 = s.rolling(20, min_periods=20).mean()
    ma60 = s.rolling(60, min_periods=60).mean()
    ma60_slp10 = ma60 / ma60.shift(10) - 1.0
    r14 = _compute_rsi14(s)
    r14_min3 = r14.rolling(3, min_periods=1).min()
    high60 = s.rolling(60, min_periods=20).max()
    bias20_min3 = ((s - ma20) / ma20).rolling(3, min_periods=1).min()

    core_w = 0.25
    slot_w = 0.10
    one_way = fees + slippage

    weights = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)
    cur_w = 0.25
    weights.loc[cal[0]] = [cur_w, round(1.0 - cur_w, 6)]

    sh: dict[str, float] = {
        etf_code: (100_000.0 * cur_w * (1.0 - one_way)) / float(s.loc[cal[0]]),
        "511010.SH": (100_000.0 * (1.0 - cur_w) * (1.0 - one_way))
        / float(px.loc[cal[0], "511010.SH"]),
    }
    pending: dict[pd.Timestamp, float] = {}
    addon_px: float | None = None
    last_sell_px: float | None = None
    last_sell_pos = -999
    cooldown_until = -1
    rt_returns: list[float] = []
    trades = 0
    diag = {
        "evaluation_days": 0,
        "candidate_days": 0,
        "binding_count": 0,
        "binding_recent_sell_branch": 0,
        "binding_high60_branch": 0,
        "gate2_fail_days_any": 0,
        "entries": 0,
    }

    for pos in range(1, len(cal) - 1):
        dt, next_dt = cal[pos], cal[pos + 1]
        if dt in pending:
            nav_b = sh[etf_code] * float(s.loc[dt]) + sh["511010.SH"] * float(
                px.loc[dt, "511010.SH"]
            )
            nw = pending.pop(dt)
            sh[etf_code] = (nav_b * nw * (1.0 - 0.5 * one_way)) / float(s.loc[dt])
            sh["511010.SH"] = (nav_b * (1.0 - nw) * (1.0 - 0.5 * one_way)) / float(
                px.loc[dt, "511010.SH"]
            )

        nav_t = sh[etf_code] * float(s.loc[dt]) + sh["511010.SH"] * float(px.loc[dt, "511010.SH"])
        live_w = (sh[etf_code] * float(s.loc[dt])) / nav_t if nav_t > 0.0 else 0.0

        c = float(s.loc[dt])
        cp = float(s.loc[cal[pos - 1]])
        m5 = float(ma5.loc[dt]) if pd.notna(ma5.loc[dt]) else c
        m20 = float(ma20.loc[dt]) if pd.notna(ma20.loc[dt]) else None
        m60 = float(ma60.loc[dt]) if pd.notna(ma60.loc[dt]) else None
        slp60 = float(ma60_slp10.loc[dt]) if pd.notna(ma60_slp10.loc[dt]) else -0.05
        rn = float(r14.loc[dt]) if pd.notna(r14.loc[dt]) else 50.0
        rm3 = float(r14_min3.loc[dt]) if pd.notna(r14_min3.loc[dt]) else 50.0
        bm3 = float(bias20_min3.loc[dt]) if pd.notna(bias20_min3.loc[dt]) else 0.0
        h60 = float(high60.loc[dt]) if pd.notna(high60.loc[dt]) else c
        reg = str(regime_df.loc[dt, "confirmed_regime"])
        in_bull = m60 is not None and m20 is not None and c > m60 and m20 > m60

        is_drift_harvest = False
        new_w: float | None = None
        if addon_px is not None:
            tp_grind = (not in_bull) and (c >= addon_px * (1.0 + cfg.tp_gain))
            tp_bull = in_bull and (
                (c >= addon_px * 1.15 and c < m5)
                or (m20 is not None and c < m20 and c >= addon_px * 1.04)
            )
            tight_stop = cfg.use_tight_stop and c < addon_px * 0.90 and cp < addon_px * 0.90
            if tp_grind or tp_bull or tight_stop:
                sell_exec = float(s.loc[next_dt])
                rt_returns.append(
                    (sell_exec * (1.0 - one_way)) / (addon_px * (1.0 + one_way)) - 1.0
                )
                if tight_stop:
                    cooldown_until = pos + 25
                last_sell_px = c
                last_sell_pos = pos
                addon_px = None
                new_w = core_w
        else:
            overweight_stall = (
                cfg.allow_drift_harvest
                and live_w >= 0.34
                and ((rn >= 68.0 and c < m5) or (m20 is not None and c >= m20 * 1.10 and c < cp))
            )
            if overweight_stall:
                new_w = core_w
                is_drift_harvest = True
                last_sell_px = c
                last_sell_pos = pos
            elif pos > cooldown_until:
                if cfg.ma60_slope10_floor is None:
                    shield_ok = True
                elif reg == "DEFENSIVE":
                    shield_ok = slp60 >= 0.0
                else:
                    shield_ok = slp60 >= cfg.ma60_slope10_floor
                recent_branch = last_sell_px is not None and pos - last_sell_pos <= 90
                disc_rule = (
                    c <= last_sell_px * (1.0 - cfg.disc)
                    if (last_sell_px is not None and recent_branch)
                    else (c <= h60 * 0.85)
                )
                oversold_ok = (rm3 <= 36.0) or (bm3 <= -0.065)
                turn_ok = (c > cp) and (c >= m5 * 0.995)
                diag["evaluation_days"] += 1
                if not disc_rule:
                    diag["gate2_fail_days_any"] += 1
                if shield_ok and oversold_ok and turn_ok:
                    diag["candidate_days"] += 1
                    if not disc_rule:
                        diag["binding_count"] += 1
                        key = (
                            "binding_recent_sell_branch"
                            if recent_branch
                            else "binding_high60_branch"
                        )
                        diag[key] += 1
                disc_ok = disc_rule if gate2_enabled else True
                if shield_ok and disc_ok and oversold_ok and turn_ok:
                    addon_px = float(s.loc[next_dt])
                    new_w = round(core_w + slot_w, 6)
                    diag["entries"] += 1

        if new_w is not None and (is_drift_harvest or abs(new_w - cur_w) > 1e-6):
            weights.loc[next_dt] = [new_w, round(1.0 - new_w, 6)]
            pending[next_dt] = new_w
            cur_w = new_w
            trades += 1

    res = run_target_weights(
        px,
        weights,
        fees=fees,
        slippage=slippage,
        initial_cash=100_000.0,
        metric_start=cal[0],
        tradability_mask=panels.etf_tradability_mask[cols],
        lifetimes={k: panels.etf_lifetimes[k] for k in cols},
    )
    eq = res.equity.loc[cal[0] : cal[-1]]
    tot_ret = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
    mdd = float((eq / eq.cummax() - 1.0).min())
    rets = eq.pct_change().dropna()
    sharpe = float(np.sqrt(252.0) * rets.mean() / rets.std(ddof=1)) if rets.std(ddof=1) > 0 else 0.0
    wins = sum(1 for x in rt_returns if x > 0.0)
    losses = sum(1 for x in rt_returns if x <= 0.0)
    avg_rt = float(np.mean(rt_returns)) if rt_returns else 0.0
    metrics = {
        "total_return": round(tot_ret, 4),
        "max_drawdown": round(mdd, 4),
        "sharpe": round(sharpe, 2),
        "trades": trades,
        "rt_wins": wins,
        "rt_losses": losses,
        "avg_rt_return": round(avg_rt, 4),
    }
    return metrics, weights, cols, diag


def _mean_pp(values: list[float]) -> float:
    return float(np.mean(values)) * 100.0


def _arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    is_r = [r for r in rows if r["split"] == "IS"]
    oos_r = [r for r in rows if r["split"] == "OOS"]
    return {
        "arm": arm,
        "is_excess_pp": _mean_pp(
            [r[arm]["total_return"] - r["static25"]["total_return"] for r in is_r]
        ),
        "is_mdd_diff_pp": _mean_pp(
            [r[arm]["max_drawdown"] - r["static25"]["max_drawdown"] for r in is_r]
        ),
        "oos_excess_pp": _mean_pp(
            [r[arm]["total_return"] - r["static25"]["total_return"] for r in oos_r]
        ),
        "oos_mdd_diff_pp": _mean_pp(
            [r[arm]["max_drawdown"] - r["static25"]["max_drawdown"] for r in oos_r]
        ),
        "rt_wins": sum(int(r[arm]["rt_wins"]) for r in rows),
        "rt_losses": sum(int(r[arm]["rt_losses"]) for r in rows),
        "trades": sum(int(r[arm]["trades"]) for r in rows),
    }


def run_exp_v3_04b() -> dict[str, Any]:
    for out in (OUT_JSON, OUT_MD):
        if out.exists():
            raise RuntimeError(f"refuse_overwrite:{out}")
    prov = verify_v3_provenance(verify_content=True)
    panels = load_stitched_panels(prov)
    regime_df = compute_v3_market_regime_series(prov, panels.index_close, panels.calendar)

    rows: list[dict[str, Any]] = []
    weights_cache: dict[str, dict[str, Any]] = {}
    for wname, split, code, st, ed in WINDOWS:
        kw = {"etf_code": code, "start_str": st, "end_str": ed}
        base_m, _, _ = _simulate_sleeve(panels, regime_df, cfg=STATIC_CFG, **kw)
        v32_m, v32_w, cols = _simulate_sleeve(panels, regime_df, cfg=V32_CFG, **kw)
        rep_m, rep_w, _, diag = _simulate_guarded(
            panels, regime_df, cfg=V32_CFG, gate2_enabled=True, **kw
        )
        abl_m, abl_w, _, abl_diag = _simulate_guarded(
            panels, regime_df, cfg=V32_CFG, gate2_enabled=False, **kw
        )
        weights_cache[wname] = {"v32": v32_w, "abl": abl_w, "cols": cols, "st": st, "ed": ed}
        rows.append(
            {
                "window_name": wname,
                "split": split,
                "etf_code": code,
                "static25": base_m,
                "v32": v32_m,
                "v32_repro": rep_m,
                "v32_no_gate2": abl_m,
                "repro_identical": bool(v32_w.equals(rep_w) and v32_m == rep_m),
                "ablation_weights_identical": bool(v32_w.equals(abl_w)),
                "ablation_metrics_identical": bool(v32_m == abl_m),
                "diagnostics_v32_path": diag,
                "ablation_entries": abl_diag["entries"],
            }
        )

    rq_rows: list[dict[str, Any]] = []
    for wname in RQ_WINDOWS:
        wc = weights_cache[wname]
        row: dict[str, Any] = {"window_name": wname, "etf_code": wc["cols"][0]}
        for arm in ("v32", "abl"):
            for min_c in (0.0, 5.0):
                r = _run_rqalpha_check(
                    wc[arm], wc["cols"], wc["st"], wc["ed"], min_commission=min_c
                )
                row["rq_window"] = r["window"]
                tag = f"{arm}_min{int(min_c)}"
                row[f"{tag}_ret"] = r["total_return"]
                row[f"{tag}_mdd"] = r["max_drawdown"]
                row[f"{tag}_rejects"] = r["order_rejects"]
        row["identical"] = all(
            row[f"v32_min{m}_{k}"] == row[f"abl_min{m}_{k}"]
            for m in (0, 5)
            for k in ("ret", "mdd", "rejects")
        )
        rq_rows.append(row)

    binding_total = sum(r["diagnostics_v32_path"]["binding_count"] for r in rows)
    all_repro = all(r["repro_identical"] for r in rows)
    vbt_identical = all(
        r["ablation_weights_identical"] and r["ablation_metrics_identical"] for r in rows
    )
    weights_identical = all(r["ablation_weights_identical"] for r in rows)
    rq_identical = all(r["identical"] for r in rq_rows)
    summ_v32 = _arm_summary(rows, "v32")
    summ_abl = _arm_summary(rows, "v32_no_gate2")
    abl_rejects = sum(r["abl_min0_rejects"] + r["abl_min5_rejects"] for r in rq_rows)

    if not all_repro:
        verdict = "INVALID_RUN"
        reason = "V32_REPRO differs from original V32 in at least one window"
    elif (binding_total == 0 and not (vbt_identical and rq_identical)) or (
        binding_total > 0 and weights_identical
    ):
        verdict = "INVALID_RUN"
        reason = "binding count inconsistent with ablation identity"
    elif binding_total == 0:
        verdict = "GATE2_INERT_SIMPLIFICATION_ELIGIBLE"
        reason = "gate 2 never the sole veto; VBT and native RQAlpha bit-identical"
    else:
        not_worse = (
            summ_abl["is_excess_pp"] >= summ_v32["is_excess_pp"]
            and summ_abl["oos_excess_pp"] >= summ_v32["oos_excess_pp"]
            and summ_abl["is_mdd_diff_pp"] >= summ_v32["is_mdd_diff_pp"]
            and summ_abl["oos_mdd_diff_pp"] >= summ_v32["oos_mdd_diff_pp"]
            and summ_abl["rt_losses"] <= summ_v32["rt_losses"]
            and abl_rejects == 0
        )
        verdict = "GATE2_BINDING_REMOVAL_NOT_WORSE" if not_worse else "GATE2_BINDING_RETAIN"
        reason = "gate 2 binding; pre-registered not-worse test applied"

    report = {
        "experiment_id": "EXP-V3-04B",
        "strategy_id": "V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION",
        "protocol": "research/batches/exp_v3_04b/PROTOCOL_V1.md",
        "snapshot_id": prov.snapshot_id,
        "verdict": verdict,
        "verdict_reason": reason,
        "production_admission": "NOT_APPROVED",
        "binding_count_total": binding_total,
        "repro_identical_all_windows": all_repro,
        "vbt_ablation_identical_all_windows": vbt_identical,
        "rqalpha_ablation_identical_all_windows": rq_identical,
        "summary": [summ_v32, summ_abl],
        "window_rows": rows,
        "rqalpha_native_checks": rq_rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(_render_md(report), encoding="utf-8")
    return report


def _render_md(rep: dict[str, Any]) -> str:
    lines = [
        "# EXP-V3-04B: V32 磨底回补门②（折价门）消融报告",
        "",
        "## External Evidence Gate",
        "",
        "- Canonical mapping: `EXP-V3-04B` -> `V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION`"
        "（registry 既有条目；四门槛之门②单因素消融）。",
        "- External tier: `E4_OPEN_LOCAL`。",
        "- External conclusion: 外部证据只支持深跌低吸需过滤的一般结论，不回答门②在其余三门存在时"
        "是否冗余。",
        "- Relevant contradictions: `EXP-V3-04` 3×3 高原 `disc = 6%/7%/8%` 结果逐位相同，与"
        "“>=7% discount 为独立护栏”的规格表述矛盾。",
        "- Upstream implementation: VectorBT `run_target_weights`；原生 RQAlpha 6.3.0 复用原脚本"
        " `_run_rqalpha_check`。",
        "- Existing TactiCore evidence: `RL-055`、`EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.*`。",
        "- Remaining local gap: 门②是否曾为唯一否决条件；去掉它的影响。",
        "- Research action: `BOUNDED_ABLATION`。",
        "",
        "## PIT Tradability Gate",
        "",
        "1. Date-aware universe: 与 `EXP-V3-04` 相同 9 窗口与标的，`etf_tradability_mask` 原样传入。",
        "2. Asset lifetime metadata: `v3_data.py` `etf_lifetimes`（只读）。",
        "3. Pre-listing fallback handling: 不回填；`159558.SZ` 自 `2024-07-16` 起。",
        "4. Missing execution price / suspension: `NaN` 不补零；`T` 收盘信号、`T+1` 执行。",
        "5. Strategy inception: 每窗 25% 目标 ETF + 75% `511010.SH`。",
        "6. Executability of every positive target: VectorBT `validate_execution_targets`；"
        "RQAlpha 4 窗口拒单计数（bundle 截至 2026-08-31）。",
        "",
        "## 裁决",
        "",
        f"- **Verdict**: `{rep['verdict']}`（{rep['verdict_reason']}）",
        f"- production_admission: `{rep['production_admission']}`；协议 `{rep['protocol']}`",
        f"- Snapshot ID: `{rep['snapshot_id']}`",
        f"- 复写等价（V32_REPRO == V32，9 窗口）: `{rep['repro_identical_all_windows']}`",
        f"- 门② binding count 合计: `{rep['binding_count_total']}`",
        f"- VectorBT 消融逐位一致: `{rep['vbt_ablation_identical_all_windows']}`；"
        f"原生 RQAlpha 逐位一致: `{rep['rqalpha_ablation_identical_all_windows']}`",
        "",
        "## 一、门②约束诊断（V32 路径）",
        "",
        "| 窗口 | 评估日 | 候选日(①③④通过) | binding | 近卖出分支 | 60日高点分支 | 门②失败(任意) | V32 入场 | 去门②入场 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rep["window_rows"]:
        d = r["diagnostics_v32_path"]
        lines.append(
            f"| {r['window_name']} | {d['evaluation_days']} | {d['candidate_days']} | "
            f"{d['binding_count']} | {d['binding_recent_sell_branch']} | "
            f"{d['binding_high60_branch']} | {d['gate2_fail_days_any']} | {d['entries']} | "
            f"{r['ablation_entries']} |"
        )
    lines += [
        "",
        "## 二、消融对照（相对静态 25% 的均值）",
        "",
        "| 臂 | IS 超额 | IS MDD 差 | OOS 超额 | OOS MDD 差 | 胜/负 | 调仓数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sm in rep["summary"]:
        lines.append(
            f"| {sm['arm']} | {sm['is_excess_pp']:+.2f}pp | {sm['is_mdd_diff_pp']:+.2f}pp | "
            f"{sm['oos_excess_pp']:+.2f}pp | {sm['oos_mdd_diff_pp']:+.2f}pp | "
            f"{sm['rt_wins']}/{sm['rt_losses']} | {sm['trades']} |"
        )
    lines += [
        "",
        "## 三、逐窗口（VectorBT）",
        "",
        "| 窗口 | 静态25% 收益/MDD | V32 收益/MDD | 去门② 收益/MDD | V32 胜/负 | 去门② 胜/负 | 权重一致 |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for r in rep["window_rows"]:
        b, v, a = r["static25"], r["v32"], r["v32_no_gate2"]
        lines.append(
            f"| {r['window_name']} | {b['total_return'] * 100:+.2f}% / {b['max_drawdown'] * 100:.2f}% | "
            f"{v['total_return'] * 100:+.2f}% / {v['max_drawdown'] * 100:.2f}% | "
            f"{a['total_return'] * 100:+.2f}% / {a['max_drawdown'] * 100:.2f}% | "
            f"{v['rt_wins']}/{v['rt_losses']} | {a['rt_wins']}/{a['rt_losses']} | "
            f"{r['ablation_weights_identical']} |"
        )
    lines += [
        "",
        "## 四、原生 RQAlpha 6.3.0 复核",
        "",
        "| 窗口 | 区间 | V32 免五 收益/MDD | 去门② 免五 收益/MDD | V32 5元 | 去门② 5元 | 拒单(V32/去门②) | 一致 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for q in rep["rqalpha_native_checks"]:
        lines.append(
            f"| {q['window_name']} | {q['rq_window']} | "
            f"{q['v32_min0_ret'] * 100:+.2f}% / {q['v32_min0_mdd'] * 100:.2f}% | "
            f"{q['abl_min0_ret'] * 100:+.2f}% / {q['abl_min0_mdd'] * 100:.2f}% | "
            f"{q['v32_min5_ret'] * 100:+.2f}% | {q['abl_min5_ret'] * 100:+.2f}% | "
            f"{q['v32_min0_rejects'] + q['v32_min5_rejects']}/"
            f"{q['abl_min0_rejects'] + q['abl_min5_rejects']} | {q['identical']} |"
        )
    lines += [
        "",
        "## 边界",
        "",
        "- 结果仅为新版本候选（`NOT_APPROVED`）；不修改 `v3.2.0` / `v3.2.1`、FinanceMCP 运行参数或"
        " `EXP-V3-04` 原产物。",
        "- 诊断只覆盖原 9 窗口的 V32 路径；未覆盖窗口外的未来行情。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    out = run_exp_v3_04b()
    print("EXP-V3-04B Verdict:", out["verdict"], "|", out["verdict_reason"])
    print("binding_count_total:", out["binding_count_total"])
    for sm in out["summary"]:
        print(" ", sm)
