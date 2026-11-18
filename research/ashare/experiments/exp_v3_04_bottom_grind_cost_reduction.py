"""EXP-V3-04: 159558 保留 25% 底仓震荡磨底降本模式与反负向护栏实证研究。

================================================================================
External Evidence Gate（8 项前置强制声明）
================================================================================
- Canonical mapping: `EXP-V3-04` -> `V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION`
  （高波动行业 ETF 25% 底仓留存 + 四重防负向护栏 `10%` 机动降本波段槽
  + `>=34%` 超配脉冲锁盈策略，承接并扩展 `EXP-V3-03`）。
- External tier: `E4_OPEN_LOCAL`
  （低成本万 0.5 免五高波行业 ETF 账户保留 25% 核心仓位并在底部震荡做 T 降本，
  常见零售做 T 方法极易在阴跌或横盘中“越操作越亏损”，属高度本地化约束与路径依赖问题）。
- External conclusion: 在严格 `T` 日收盘信号 -> `T+1` 执行、万 0.5 免五
  （并对照万 2.5 最低 5 元敏感性）与单边 5bp 滑点约束下，
  对四类常见散户做 T/减仓机制（`C2` 无过滤 6% 固定网格、
  `C3` MA20 交叉追涨杀跌、`C4` 10% 窄止损高频洗出、`C5` 取消 MA60 走平斜率防飞刀盾）
  vs `C0` 静态 25% 底仓 vs `C1` 旧版 18% 按月强卖 vs 主策略 `V32_GUARDED_BOTTOM_GRIND_25`
  在全周期及 4 阶段 IS 熊市/5 阶段 OOS 窗口进行孤立与组合级对照。
- Relevant contradictions: 学术与实盘反复证明均值回归网格在单边熊市极易“接飞刀”，
  均线交叉在箱体震荡期反复被打耳光（whipsaw），窄止损在 3%~4% 日波幅的半导体 ETF 上
  会被噪音频繁震出导致越做越亏。唯有“取消低位月度强卖 + 四重非负向入场护栏
  （MA60 10日斜率>=0 + 严格折价>=7% + RSI14<=36 或 Bias20<=-6.5% + 右侧阳线企稳）
  + 无窄止损靠组合前置 -12%/-15% L2 熔断兜底 + >=34% 漂移超买锁盈”方可取得稳定正贡献。
- Upstream implementation: 全周期与参数高原筛选严格复用
  `tacticore/engines/vectorbt_adapter.py:run_target_weights`；原生整手、T+1、现金与费用执行复核
  严格复用原生 **RQAlpha 6.3.0**（`research/ashare/engines/rqalpha_replay.py`）。
- Existing TactiCore evidence: 承接 `RL-054`（`EXP-V3-03` 证伪滞后 `-15%->15%` 熔断、
  锁定前置 `-12%->0%` L2 保护），严禁修改冻结域 `S2_R1` / `S4C_R1` / `RL-053`。
- Remaining local gap: 检验在保留 25% 底仓与万 0.5 免五真实费率下，
  `V32_GUARDED_BOTTOM_GRIND_25` 能否同时在 IS（含三段熊市）与 OOS（含 2024–2026 `159558.SZ`）
  跑赢或至少不拖累静态 25% 底仓，保持平坦 3×3 参数高原，且原生 RQAlpha 0 拒单。
- Research action: `NEW_HYPOTHESIS`（消融证伪负向机制 + 3×3 参数高原 + RQAlpha 整手复核）。

================================================================================
PIT Tradability Gate（6 要素强制声明）
================================================================================
1. Date-aware universe: 仅纳入窗口期已过上市热身期且 `etf_tradability_mask == True` 的行业 ETF
   （`512480.SH`, `515790.SH`, `512170.SH`, `159558.SZ`）及国债蓄水池 `511010.SH`。
2. Asset lifetime metadata: 绑定 `v3_data.py` 中的 `AssetLifetime` 与 `tradability_mask`。
3. Pre-listing fallback handling: 严禁回填未上市历史（`159558.SZ` 仅从 2024-07-16 起评估；
   2019–2023 IS 使用同类高波行业 ETF `512480.SH`/`515790.SH`/`512170.SH` 作独立外推检验）。
4. Missing execution price / suspension: `NaN` 不补零；`T` 日收盘信号，`T+1` 执行。
5. Strategy inception: 各窗口均从独立 25% 目标 ETF + 75% `511010.SH`（或初始重仓对照）起步：
   - IS: `512480.SH` (2019–2023 / 2021–2023)、`515790.SH` (2022–2023)、`512170.SH` (2021–2023)
   - OOS: `512480.SH` (2024–2026)、`159558.SZ` (2024–2026 / 2026 YTD)、`515790.SH`、`512170.SH`
   - RQAlpha 原生整手复核覆盖截至 `2026-08-31`（已显式标注，不跨界伪造）。
6. Executability of every positive target: `validate_execution_targets` 全程校验
   与 RQAlpha 原生整手 0 拒单核对。
================================================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.ashare.engines.rqalpha_replay import replay_frozen_schedule
from research.ashare.v3_data import (
    BUNDLE_CUTOFF,
    BUNDLE_PATH,
    V3StitchedPanels,
    compute_v3_market_regime_series,
    load_stitched_panels,
    ts_to_rq,
    verify_v3_provenance,
)
from tacticore.engines.vectorbt_adapter import run_target_weights

RESULTS_DIR = Path("/home/jcshi/workspace/TactiCore/research/results")

WINDOWS: tuple[tuple[str, str, str, str, str], ...] = (
    ("IS_512480_19_23", "IS", "512480.SH", "2019-09-02", "2023-12-29"),
    ("IS_512480_BEAR", "IS", "512480.SH", "2021-08-02", "2023-12-29"),
    ("IS_515790_BEAR", "IS", "515790.SH", "2022-08-15", "2023-12-29"),
    ("IS_512170_BEAR", "IS", "512170.SH", "2021-07-01", "2023-12-29"),
    ("OOS_512480_24_26", "OOS", "512480.SH", "2024-01-02", "2026-11-13"),
    ("OOS_159558_24_26", "OOS", "159558.SZ", "2024-07-16", "2026-11-13"),
    ("OOS_159558_2026", "OOS", "159558.SZ", "2026-01-05", "2026-11-13"),
    ("OOS_515790_24_26", "OOS", "515790.SH", "2024-01-02", "2026-11-13"),
    ("OOS_512170_24_26", "OOS", "512170.SH", "2024-01-02", "2026-11-13"),
)


@dataclass(frozen=True)
class VariantConfig:
    """消融对照组与定型策略规格。"""

    name: str
    mode: str
    disc: float = 0.07
    tp_gain: float = 0.075
    ma60_slope10_floor: float | None = 0.0
    use_tight_stop: bool = False
    allow_drift_harvest: bool = True


VARIANTS: tuple[VariantConfig, ...] = (
    VariantConfig(name="C0_STATIC_25", mode="STATIC_25"),
    VariantConfig(name="C1_LEGACY_18_MONTHLY", mode="LEGACY_18_MONTHLY"),
    VariantConfig(name="C2_NAIVE_GRID_6PCT", mode="NAIVE_GRID_6PCT"),
    VariantConfig(name="C3_MA20_CROSS_SWING", mode="MA20_CROSS_SWING"),
    VariantConfig(
        name="C4_TIGHT_STOP_10PCT",
        mode="GUARDED_GRIND",
        ma60_slope10_floor=-0.005,
        use_tight_stop=True,
    ),
    VariantConfig(
        name="C5_NO_MA60_SLOPE_SHIELD",
        mode="GUARDED_GRIND",
        ma60_slope10_floor=None,
        use_tight_stop=False,
    ),
    VariantConfig(
        name="V32_GUARDED_BOTTOM_GRIND_25",
        mode="GUARDED_GRIND",
        disc=0.07,
        tp_gain=0.075,
        ma60_slope10_floor=0.0,
        use_tight_stop=False,
        allow_drift_harvest=True,
    ),
)


def _compute_rsi14(series: pd.Series) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0).ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    down = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    rs = up / down.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _simulate_sleeve(
    panels: V3StitchedPanels,
    regime_df: pd.DataFrame,
    *,
    etf_code: str,
    start_str: str,
    end_str: str,
    cfg: VariantConfig,
    fees: float = 0.00005,
    slippage: float = 0.0005,
) -> tuple[dict[str, Any], pd.DataFrame, list[str]]:
    """以 25% 底仓 + 75% 国债底盘隔离检验各类磨底波段规则的纯增量收益与负向风险。"""
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

    core_w = 0.18 if cfg.mode == "LEGACY_18_MONTHLY" else 0.25
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
    grid_anchor = float(s.loc[cal[0]])
    last_exec_pos = 0
    cooldown_until = -1
    rt_returns: list[float] = []
    trades = 0

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
        if cfg.mode == "STATIC_25":
            pass
        elif cfg.mode == "LEGACY_18_MONTHLY":
            if cur_w > core_w + 1e-6:
                is_m1 = dt.month != cal[pos - 1].month and (pos - last_exec_pos >= 12)
                ref_p = last_sell_px if last_sell_px is not None else float(s.loc[cal[0]])
                if c >= ref_p * 1.08 or is_m1:
                    new_w = core_w
                    last_sell_px = c
                    last_exec_pos = pos
        elif cfg.mode == "NAIVE_GRID_6PCT":
            if c <= grid_anchor * 0.94 and cur_w < 0.45 - 1e-6:
                new_w = round(min(0.45, cur_w + slot_w), 6)
                addon_px = float(s.loc[next_dt])
                grid_anchor = c
            elif c >= grid_anchor * 1.06 and cur_w > 0.25 + 1e-6:
                new_w = round(max(0.25, cur_w - slot_w), 6)
                if addon_px is not None:
                    sell_exec = float(s.loc[next_dt])
                    rt_returns.append(
                        (sell_exec * (1.0 - one_way)) / (addon_px * (1.0 + one_way)) - 1.0
                    )
                    addon_px = None
                grid_anchor = c
        elif cfg.mode == "MA20_CROSS_SWING":
            if m20 is not None:
                if cur_w <= 0.25 + 1e-6 and c > m20 and cp <= float(ma20.loc[cal[pos - 1]] or m20):
                    new_w = round(core_w + slot_w, 6)
                    addon_px = float(s.loc[next_dt])
                elif cur_w > 0.25 + 1e-6 and c < m20 and cp >= float(ma20.loc[cal[pos - 1]] or m20):
                    new_w = core_w
                    if addon_px is not None:
                        sell_exec = float(s.loc[next_dt])
                        rt_returns.append(
                            (sell_exec * (1.0 - one_way)) / (addon_px * (1.0 + one_way)) - 1.0
                        )
                        addon_px = None
        elif cfg.mode == "GUARDED_GRIND":
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
                    and (
                        (rn >= 68.0 and c < m5) or (m20 is not None and c >= m20 * 1.10 and c < cp)
                    )
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
                    disc_ok = (
                        c <= last_sell_px * (1.0 - cfg.disc)
                        if (last_sell_px is not None and pos - last_sell_pos <= 90)
                        else (c <= h60 * 0.85)
                    )
                    oversold_ok = (rm3 <= 36.0) or (bm3 <= -0.065)
                    turn_ok = (c > cp) and (c >= m5 * 0.995)
                    if shield_ok and disc_ok and oversold_ok and turn_ok:
                        addon_px = float(s.loc[next_dt])
                        new_w = round(core_w + slot_w, 6)

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
    return metrics, weights, cols


def _run_rqalpha_check(
    weights: pd.DataFrame,
    cols: list[str],
    start_str: str,
    end_str: str,
    *,
    min_commission: float,
) -> dict[str, Any]:
    start = pd.Timestamp(start_str)
    rq_end = min(pd.Timestamp(end_str), BUNDLE_CUTOFF)
    sched = weights.loc[start:rq_end].copy()
    sched = sched.loc[sched.notna().any(axis=1)]
    mapping = {c: ts_to_rq(c) for c in cols}
    res = replay_frozen_schedule(
        sched,
        mapping,
        start=start,
        end=rq_end,
        initial_cash=100_000.0,
        bundle_path=BUNDLE_PATH,
        asset_class="ETF",
        partial_fill_on_insufficient_cash=True,
        min_commission=min_commission,
    )
    nav = res.analyser["portfolio"]["unit_net_value"]
    rq_mdd = float((nav / nav.cummax() - 1.0).min())
    rejects = int(
        (res.order_events["event"] == "ORDER_CREATION_REJECT").sum()
        if not res.order_events.empty
        else 0
    )
    return {
        "window": f"{start.date()}..{rq_end.date()}"
        + (" (partial, bundle cutoff 2026-08-31)" if pd.Timestamp(end_str) > BUNDLE_CUTOFF else ""),
        "min_commission": min_commission,
        "total_return": round(float(nav.iloc[-1] / nav.iloc[0] - 1.0), 4),
        "max_drawdown": round(rq_mdd, 4),
        "order_rejects": rejects,
    }


def run_exp_v3_04() -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    prov = verify_v3_provenance(verify_content=True)
    panels = load_stitched_panels(prov)
    regime_df = compute_v3_market_regime_series(prov, panels.index_close, panels.calendar)

    all_rows: list[dict[str, Any]] = []
    baseline_by_window: dict[str, dict[str, Any]] = {}
    primary_weights_cache: dict[str, tuple[pd.DataFrame, list[str], str, str, str]] = {}

    for wname, split, code, st, ed in WINDOWS:
        base_m, _, _ = _simulate_sleeve(
            panels, regime_df, etf_code=code, start_str=st, end_str=ed, cfg=VARIANTS[0]
        )
        baseline_by_window[wname] = base_m
        for cfg in VARIANTS:
            m, w_df, cols = _simulate_sleeve(
                panels, regime_df, etf_code=code, start_str=st, end_str=ed, cfg=cfg
            )
            if cfg.name == "V32_GUARDED_BOTTOM_GRIND_25":
                primary_weights_cache[wname] = (w_df, cols, st, ed, split)
            all_rows.append(
                {
                    "window_name": wname,
                    "split": split,
                    "etf_code": code,
                    "variant": cfg.name,
                    "total_return": m["total_return"],
                    "excess_vs_static25": round(m["total_return"] - base_m["total_return"], 4),
                    "max_drawdown": m["max_drawdown"],
                    "mdd_diff_vs_static25": round(m["max_drawdown"] - base_m["max_drawdown"], 4),
                    "sharpe": m["sharpe"],
                    "trades": m["trades"],
                    "rt_wins": m["rt_wins"],
                    "rt_losses": m["rt_losses"],
                    "avg_rt_return": m["avg_rt_return"],
                }
            )

    summary_rows: list[dict[str, Any]] = []
    for cfg in VARIANTS:
        vrows = [r for r in all_rows if r["variant"] == cfg.name]
        is_r = [r for r in vrows if r["split"] == "IS"]
        oos_r = [r for r in vrows if r["split"] == "OOS"]
        tw = sum(int(r["rt_wins"]) for r in vrows)
        tl = sum(int(r["rt_losses"]) for r in vrows)
        summary_rows.append(
            {
                "variant": cfg.name,
                "is_excess_vs_25_pp": round(
                    float(np.mean([r["excess_vs_static25"] for r in is_r])) * 100.0, 2
                ),
                "is_mdd_diff_pp": round(
                    float(np.mean([r["mdd_diff_vs_static25"] for r in is_r])) * 100.0, 2
                ),
                "oos_excess_vs_25_pp": round(
                    float(np.mean([r["excess_vs_static25"] for r in oos_r])) * 100.0, 2
                ),
                "oos_mdd_diff_pp": round(
                    float(np.mean([r["mdd_diff_vs_static25"] for r in oos_r])) * 100.0, 2
                ),
                "worst_window_diff_pp": round(
                    min(float(r["excess_vs_static25"]) for r in vrows) * 100.0, 2
                ),
                "total_rt_wins": tw,
                "total_rt_losses": tl,
                "rt_win_rate_pct": round(100.0 * tw / (tw + tl), 1) if (tw + tl) > 0 else None,
            }
        )

    plateau_rows: list[dict[str, Any]] = []
    for disc in (0.06, 0.07, 0.08):
        for tp in (0.065, 0.075, 0.085):
            pcfg = VariantConfig(
                name=f"PLATEAU_D{int(disc * 100)}_T{int(tp * 1000)}",
                mode="GUARDED_GRIND",
                disc=disc,
                tp_gain=tp,
                ma60_slope10_floor=0.0,
            )
            is_d, oos_d, is_dd, oos_dd = [], [], [], []
            tw, tl = 0, 0
            for wname, split, code, st, ed in WINDOWS:
                m, _, _ = _simulate_sleeve(
                    panels, regime_df, etf_code=code, start_str=st, end_str=ed, cfg=pcfg
                )
                bm = baseline_by_window[wname]
                dr = (m["total_return"] - bm["total_return"]) * 100.0
                dm = (m["max_drawdown"] - bm["max_drawdown"]) * 100.0
                if split == "IS":
                    is_d.append(dr)
                    is_dd.append(dm)
                else:
                    oos_d.append(dr)
                    oos_dd.append(dm)
                tw += int(m["rt_wins"])
                tl += int(m["rt_losses"])
            plateau_rows.append(
                {
                    "disc": disc,
                    "tp_gain": tp,
                    "is_excess_pp": round(float(np.mean(is_d)), 2),
                    "is_mdd_diff_pp": round(float(np.mean(is_dd)), 2),
                    "oos_excess_pp": round(float(np.mean(oos_d)), 2),
                    "oos_mdd_diff_pp": round(float(np.mean(oos_dd)), 2),
                    "rt_wins": tw,
                    "rt_losses": tl,
                }
            )

    rqalpha_checks: list[dict[str, Any]] = []
    for wname in ("IS_512480_19_23", "OOS_512480_24_26", "OOS_159558_24_26", "OOS_159558_2026"):
        w_df, cols, st, ed, split = primary_weights_cache[wname]
        w_base, cols_b, _, _, _ = (
            *_simulate_sleeve(
                panels, regime_df, etf_code=cols[0], start_str=st, end_str=ed, cfg=VARIANTS[0]
            )[1:],
            st,
            ed,
            split,
        )
        rq_base = _run_rqalpha_check(w_base, cols_b, st, ed, min_commission=0.0)
        rq_free = _run_rqalpha_check(w_df, cols, st, ed, min_commission=0.0)
        rq_min5 = _run_rqalpha_check(w_df, cols, st, ed, min_commission=5.0)
        rqalpha_checks.append(
            {
                "window_name": wname,
                "split": split,
                "etf_code": cols[0],
                "rq_window": rq_free["window"],
                "static25_ret": rq_base["total_return"],
                "static25_mdd": rq_base["max_drawdown"],
                "grind25_min0_ret": rq_free["total_return"],
                "grind25_min0_mdd": rq_free["max_drawdown"],
                "grind25_min0_rejects": rq_free["order_rejects"],
                "grind25_min5_ret": rq_min5["total_return"],
                "grind25_min5_mdd": rq_min5["max_drawdown"],
                "grind25_min5_rejects": rq_min5["order_rejects"],
            }
        )

    prim = next(r for r in summary_rows if r["variant"] == "V32_GUARDED_BOTTOM_GRIND_25")
    verdict = (
        "PASS_GUARDED_BOTTOM_GRIND_25"
        if prim["is_excess_vs_25_pp"] >= 0.0
        and prim["oos_excess_vs_25_pp"] > 0.0
        and prim["total_rt_losses"] == 0
        and all(c["grind25_min0_rejects"] == 0 for c in rqalpha_checks)
        else "REVIEW_REQUIRED"
    )

    report = {
        "experiment_id": "EXP-V3-04",
        "strategy_id": "V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION",
        "snapshot_id": prov.snapshot_id,
        "verdict": verdict,
        "locked_params": {
            "deconcentration_mode": "BOTTOM_GRIND_25",
            "deconcentration_keep_weight_bps": "2500",
            "deconcentration_monthly_rule_enabled": "false",
            "deconcentration_support_breakdown_confirm_days": "2",
            "grind_tactical_slot_bps": "1000",
            "grind_reload_min_discount_bps": "700",
            "grind_reload_ma60_slope10_min_bps": "0",
            "grind_reload_rsi14_max": "36",
            "grind_reload_bias20_max_bps": "-650",
            "grind_take_profit_bps": "750",
            "grind_drift_harvest_trigger_bps": "3400",
        },
        "variant_summary": summary_rows,
        "plateau_3x3": plateau_rows,
        "rqalpha_native_checks": rqalpha_checks,
        "window_rows": all_rows,
    }

    (RESULTS_DIR / "EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(all_rows).to_csv(
        RESULTS_DIR / "EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.csv", index=False
    )

    lines = [
        "# EXP-V3-04: 25% 底仓震荡磨底降本模式与反负向护栏验证报告",
        "",
        f"- **Snapshot ID**: `{prov.snapshot_id}`",
        (
            f"- **主裁决结论**: `{verdict}`"
            f"（IS 均值相对静态 25% `{prim['is_excess_vs_25_pp']:+.2f}pp`、"
            f"OOS 均值 `{prim['oos_excess_vs_25_pp']:+.2f}pp`、"
            f"OOS MDD 改善 `{prim['oos_mdd_diff_pp']:+.2f}pp`、"
            f"已完成波段胜率 `{prim['total_rt_wins']} 胜 / {prim['total_rt_losses']} 负`）"
        ),
        "",
        "## 一、主策略 vs 负向做 T 反照对照汇总（孤立 25% 底仓对比）",
        "",
        (
            "| 策略变体 | IS 超额收益 | IS MDD 改善 | OOS 超额收益 | OOS MDD 改善 | "
            "最差单窗差 | 波段胜/负 | 波段胜率 |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sr in summary_rows:
        wr = f"{sr['rt_win_rate_pct']:.1f}%" if sr["rt_win_rate_pct"] is not None else "N/A"
        lines.append(
            f"| {sr['variant']} | {sr['is_excess_vs_25_pp']:+.2f}pp | "
            f"{sr['is_mdd_diff_pp']:+.2f}pp | "
            f"{sr['oos_excess_vs_25_pp']:+.2f}pp | {sr['oos_mdd_diff_pp']:+.2f}pp | "
            f"{sr['worst_window_diff_pp']:+.2f}pp | "
            f"{sr['total_rt_wins']}/{sr['total_rt_losses']} | {wr} |"
        )
    lines.extend(
        [
            "",
            "## 二、3×3 参数高原检查（`disc` × `tp_gain`，`MA60_slope10 >= 0`）",
            "",
            "| 折价门槛 | 止盈目标 | IS 超额 | IS MDD 改善 | OOS 超额 | OOS MDD 改善 | 胜/负 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for pr in plateau_rows:
        lines.append(
            f"| {pr['disc'] * 100:.0f}% | {pr['tp_gain'] * 100:.1f}% | "
            f"{pr['is_excess_pp']:+.2f}pp | {pr['is_mdd_diff_pp']:+.2f}pp | "
            f"{pr['oos_excess_pp']:+.2f}pp | {pr['oos_mdd_diff_pp']:+.2f}pp | "
            f"{pr['rt_wins']}/{pr['rt_losses']} |"
        )
    lines.extend(
        [
            "",
            "## 三、原生 RQAlpha 6.3.0 整手实盘撮合复核",
            "",
            (
                "| 窗口 | ETF | 区间 | 静态25%收益/MDD | "
                "磨底降本(免五)收益/MDD | 磨底降本(5元低消) | 拒单 |"
            ),
            "| --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for rc in rqalpha_checks:
        lines.append(
            f"| {rc['window_name']} | {rc['etf_code']} | {rc['rq_window']} | "
            f"{rc['static25_ret'] * 100:+.2f}% / {rc['static25_mdd'] * 100:.2f}% | "
            f"{rc['grind25_min0_ret'] * 100:+.2f}% / {rc['grind25_min0_mdd'] * 100:.2f}% | "
            f"{rc['grind25_min5_ret'] * 100:+.2f}% / {rc['grind25_min5_mdd'] * 100:.2f}% | "
            f"{rc['grind25_min0_rejects']} |"
        )
    lines.append("")
    (RESULTS_DIR / "EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    out = run_exp_v3_04()
    print("EXP-V3-04 Verdict:", out["verdict"])
    for sr in out["variant_summary"]:
        print(" ", sr)
    for rc in out["rqalpha_native_checks"]:
        print(" RQ:", rc)
