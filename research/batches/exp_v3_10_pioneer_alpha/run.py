"""EXP-V3-10 runner: 23 Super Sector ETF Pioneer (10A) & High-Div Low-Vol Pre-Study (10B).

External Evidence Gate:
- Line 10A: CHINA_INDUSTRY_ETF / CHINA_THEME_ETF (E4_OPEN_LOCAL; super ETF fee structure).
- Line 10B: LOW_VOL + VALUE (E3_MIXED_CONDITIONAL; BOUNDED_SHORT_WINDOW_PRE_STUDY).
- Relevant contradictions: Strictly orthogonal to rejected S3A/S3B/S3C (11 fixed normal-fee ETFs);
  10B is bounded by dv_ttm coverage (2024-01-02..2026-11-17) and cannot be directly promoted.
- Upstream implementation: VectorBT (10A 2018-01-02..2026-11-26) + RQAlpha 6.3.0 (10A ..2026-10-30;
  10B 2024-02-01..2026-10-30 at ¥69k & ¥100k tiered fees, CS stamp tax, and 5bp explicit slippage).
- Research action: NEW_HYPOTHESIS (10A) / BOUNDED_SHORT_WINDOW_PRE_STUDY (10B).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from importlib.metadata import version
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rqalpha import run_func
from rqalpha.const import INSTRUMENT_TYPE
from rqalpha.core.events import EVENT
from rqalpha.environment import Environment

from research.ashare import v3_data_202611 as data
from research.ashare.engines.bundle_source import bundle_calendar, open_bundle_source
from research.ashare.experiments import exp_v3_01_regime_super_etf as e1
from research.ashare.v3_data import rq_to_ts
from research.batches.v3_account_replay_v2.native import TieredFees
from research.batches.v3_account_replay_v2.stock_signals import (
    MIN_CIRC_MV_WAN,
    _is_mainboard,
    _load_pit_financial_table_202611,
    _lookup_quality_core,
    build_causal_bp1_candidates_202611,
)
from research.batches.v3_complexity_hurdle_v2.native import NORMAL, SUPER, replay
from research.batches.v3_complexity_hurdle_v2.run import metrics, require, reserve, utc
from tacticore.engines.rqalpha_adapter import build_rqalpha_config
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/EXP_V3_10_PIONEER_ALPHA"
PROTOCOL = ROOT / "research/batches/exp_v3_10_pioneer_alpha/PROTOCOL_V1.md"

START = data.EXP_START
RQA_END = data.BUNDLE_CUTOFF_202611
VBT_END = data.EXP_END_202611
OOS_10B_START = pd.Timestamp("2024-02-01")
CASH = (69000, 100000)

PIT_INDUSTRY_PROXIES: tuple[str, ...] = (
    "512480.SH",  # 半导体
    "515790.SH",  # 光伏
    "512170.SH",  # 医药
    "512880.SH",  # 证券
    "515030.SH",  # 新能源车
    "512660.SH",  # 军工
    "512400.SH",  # 有色金属
    "512800.SH",  # 银行
    "159928.SZ",  # 消费
    "512690.SH",  # 酒/白电消费
)


def build_sector_pioneer_weights(
    panels: Any,
    regime_df: pd.DataFrame,
    sector_super_codes: tuple[str, ...],
    *,
    top_k: int,  # 0 (no pioneer), 1, or 2
    rank_mode: str = "ret60",  # "ret60" | "blend"
    trend_filter: bool = True,
    rebalance_min_gap_days: int = 10,
    end: pd.Timestamp = VBT_END,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """40/25/15 V3 Broad Chassis + up to 20% PIT Super Sector/Proxy ETF momentum pioneer."""
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    adj = panels.etf_adj_close
    mask = panels.etf_tradability_mask
    cols = list(adj.columns)
    weights = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)

    pool_all = tuple(dict.fromkeys([*sector_super_codes, *PIT_INDUSTRY_PROXIES]))
    ma60_panel = adj.rolling(60, min_periods=60).mean()
    ret20_panel = adj / adj.shift(20) - 1.0
    ret60_panel = adj / adj.shift(60) - 1.0

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
            div_list = e1._available_bucket(
                exec_dt, e1.DEFENSIVE_SUPER_ETFS, e1.DEFENSIVE_FALLBACKS, mask, adj
            )
            for c in div_list:
                desired[c] = desired.get(c, 0.0) + 0.15 / len(div_list)
        else:
            chassis_w = 0.60 if regime == "OFFENSIVE" else 0.40
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
                desired[c] = desired.get(c, 0.0) + (chassis_w * val_share) / len(val_list)
            for c in gro_list:
                desired[c] = desired.get(c, 0.0) + (chassis_w * gro_share) / len(gro_list)

            pioneer_w = 0.25 if regime == "OFFENSIVE" else 0.20
            if top_k > 0:
                scored: list[tuple[float, str]] = []
                for c in pool_all:
                    if c not in adj.columns or not bool(mask.at[exec_dt, c]):
                        continue
                    c_sig = adj.at[sig_dt, c]
                    m60 = ma60_panel.at[sig_dt, c]
                    r60 = ret60_panel.at[sig_dt, c]
                    r20 = ret20_panel.at[sig_dt, c]
                    if pd.isna(c_sig) or pd.isna(m60) or pd.isna(r60) or pd.isna(r20):
                        continue
                    if trend_filter and not (float(c_sig) > float(m60)):
                        continue
                    sc = float(r60) if rank_mode == "ret60" else 0.5 * float(r20) + 0.5 * float(r60)
                    scored.append((sc, c))
                scored.sort(key=lambda x: (-x[0], x[1]))
                picks = [c for _, c in scored[:top_k]]
                if picks:
                    for c in picks:
                        desired[c] = desired.get(c, 0.0) + pioneer_w / len(picks)

        risk_sum = sum(desired.values())
        rem = max(0.0, 1.0 - risk_sum)
        if rem > 1e-6 and bool(mask.at[exec_dt, "511010.SH"]):
            desired["511010.SH"] = desired.get("511010.SH", 0.0) + rem

        cand = pd.Series(0.0, index=cols, dtype=float)
        for k, v in desired.items():
            cand[k] = float(v)
        l1_diff = float((cand - current_target).abs().sum())
        regime_changed = prev_regime is None or regime != prev_regime
        periodic = (pos - last_rebal_pos >= rebalance_min_gap_days) and l1_diff >= 0.08
        if regime_changed or periodic:
            cand_row = pd.Series(np.nan, index=cols, dtype=float)
            for sym in cols:
                if cand[sym] > 0:
                    cand_row[sym] = cand[sym]
                elif current_target[sym] > 0:
                    cand_row[sym] = 0.0
            weights.loc[exec_dt] = cand_row
            current_target = cand
            last_rebal_pos = pos
            events.append({"exec_date": str(exec_dt.date()), "regime": regime})
        prev_regime = regime

    return weights, events


def load_pit_basic_tables() -> (
    tuple[dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]], dict[str, Any]]
):
    """Load exact-date PIT circ_mv & dv_ttm per ts_code and audit dv_ttm coverage."""
    db = pd.read_csv(
        data.AUX_DIR_202611 / "daily_basic_pit.csv",
        usecols=["ts_code", "trade_date", "circ_mv", "dv_ttm"],
        dtype={"ts_code": str, "trade_date": str, "circ_mv": float, "dv_ttm": float},
    )
    nonnull_dv = db[db["dv_ttm"].notna()]
    audit = {
        "rows": len(db),
        "dv_ttm_nonnull_rows": len(nonnull_dv),
        "dv_ttm_min_date": str(nonnull_dv["trade_date"].min()),
        "dv_ttm_max_date": str(nonnull_dv["trade_date"].max()),
        "20261126_dv_ttm_nonnull": int(
            (db[db["trade_date"] == "20261126"]["dv_ttm"].notna()).sum()
        ),
    }
    db["dt_int"] = db["trade_date"].astype(np.int64)
    db = db.sort_values(["ts_code", "dt_int"])
    out: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for code, grp in db.groupby("ts_code", sort=False):
        out[str(code)] = (
            grp["dt_int"].to_numpy(dtype=np.int64),
            grp["circ_mv"].to_numpy(dtype=np.float64),
            grp["dv_ttm"].to_numpy(dtype=np.float64),
        )
    return out, audit


def lookup_exact_circ_and_dv(
    table: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]], ts_code: str, dt_int: int
) -> tuple[float | None, float | None]:
    rec = table.get(ts_code)
    if rec is None:
        return None, None
    dts, cmv, dv = rec
    idx = int(np.searchsorted(dts, dt_int))
    if idx < len(dts) and int(dts[idx]) == dt_int:
        c = float(cmv[idx]) if np.isfinite(cmv[idx]) else None
        d = float(dv[idx]) if np.isfinite(dv[idx]) else None
        return c, d
    return None, None


def build_high_div_lowvol_candidates(
    *,
    basic_table: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    oos_start: pd.Timestamp = OOS_10B_START,
    bundle_end: pd.Timestamp = RQA_END,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Build causal High-Dividend + Low-Vol QualityCore pullback candidates."""
    src = open_bundle_source(data.BUNDLE_PATH_202611)
    cal = bundle_calendar(src, pd.Timestamp("2022-07-01"), bundle_end)
    cal_ints = np.array([int(d.strftime("%Y%m%d")) for d in cal], dtype=np.int64)
    cal_set = set(cal_ints.tolist())
    n_days = len(cal_ints)
    oos_int = int(oos_start.strftime("%Y%m%d"))

    main_insts = [
        i
        for i in src.get_instruments(types=["CS"])
        if _is_mainboard(i.order_book_id)
        and pd.Timestamp(i.listed_date) <= bundle_end
        and pd.Timestamp(i.de_listed_date) >= cal[0]
    ]
    end_dt = bundle_end.to_pydatetime()

    vol60_cols: dict[str, np.ndarray] = {}
    cache: dict[str, tuple[Any, Any, Any]] = {}
    for inst in main_insts:
        delisted = pd.Timestamp(inst.de_listed_date)
        eff_end = min(end_dt, delisted.to_pydatetime()) if delisted.year < 2999 else end_dt
        bp = src.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="post",
            adjust_orig=eff_end,
        )
        br = src.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="none",
        )
        if bp is None or br is None or len(bp) < 125 or len(br) != len(bp):
            continue
        c_p = pd.Series(bp["close"].astype(float))
        v60 = (
            c_p.pct_change().rolling(60, min_periods=60).std() * np.sqrt(252.0)
        ).to_numpy(dtype=np.float32)
        v60[:60] = np.nan
        dts = (bp["datetime"] // 1000000).astype(np.int64)
        mask = np.isin(dts, list(cal_set))
        if not mask.any():
            continue
        idxs = np.searchsorted(cal_ints, dts[mask])
        arr = np.full(n_days, np.nan, dtype=np.float32)
        arr[idxs] = v60[mask]
        vol60_cols[inst.order_book_id] = arr
        cache[inst.order_book_id] = (inst, bp, br)

    vol60_df = pd.DataFrame(vol60_cols, index=cal)
    med_vol60 = vol60_df.median(axis=1)
    fin_table = _load_pit_financial_table_202611()

    cands: dict[str, list[dict[str, Any]]] = {}
    stats = {
        "tech_raw": 0,
        "qc_filtered": 0,
        "dv_filtered": 0,
        "lowvol_filtered": 0,
        "qualified": 0,
    }

    for ob, (inst, bp, br) in cache.items():
        ts_c = rq_to_ts(ob)
        listed_dt = pd.Timestamp(inst.listed_date).normalize()
        dts = (bp["datetime"] // 1000000).astype(np.int64)
        c_p = pd.Series(bp["close"].astype(float))
        l_p = pd.Series(bp["low"].astype(float))
        c_r = pd.Series(br["close"].astype(float))
        o_r = pd.Series(br["open"].astype(float))
        h_r = pd.Series(br["high"].astype(float))
        l_r = pd.Series(br["low"].astype(float))
        v_r = pd.Series(br["volume"].astype(float))
        amt_ma20 = pd.Series(br["total_turnover"].astype(float)).rolling(20, min_periods=20).mean()

        ma5 = c_p.rolling(5, min_periods=5).mean()
        ma20 = c_p.rolling(20, min_periods=20).mean()
        ma60 = c_p.rolling(60, min_periods=60).mean()
        bar_dates = pd.to_datetime([str(int(x)) for x in dts])
        listed_days = pd.Series((bar_dates - listed_dt).days)
        low_5 = l_p.rolling(5, min_periods=5).min()

        hit = (
            (dts >= oos_int)
            & (listed_days >= 250)
            & (c_r > 0.0)
            & (c_r <= 90.0)
            & (h_r > l_r)
            & (v_r > 0.0)
            & (amt_ma20 >= 1.5e8)
            & (c_p > ma60)
            & (ma60 >= ma60.shift(5))
            & (low_5 <= ma20 * 1.02)
            & (low_5 >= ma20 * 0.96)
            & (c_r > o_r)
            & (c_p > c_p.shift(1))
            & (c_p > ma5)
        )
        idxs = np.where(hit.to_numpy())[0]
        if len(idxs) == 0:
            continue
        st_flags = src.is_st_stock(ob, [pd.Timestamp(bar_dates[j]) for j in idxs])
        low_5d_raw = l_r.rolling(5, min_periods=5).min()
        ma20_raw = c_r * (ma20 / c_p)

        for j, is_st in zip(idxs, st_flags, strict=True):
            if is_st:
                continue
            stats["tech_raw"] += 1
            dt_int = int(dts[j])
            dt_ts = pd.Timestamp(bar_dates[j])
            if not _lookup_quality_core(fin_table, ts_c, dt_int, int(dt_ts.value)):
                stats["qc_filtered"] += 1
                continue
            cmv, dv = lookup_exact_circ_and_dv(basic_table, ts_c, dt_int)
            if cmv is None or cmv < MIN_CIRC_MV_WAN or dv is None or dv < 3.5:
                stats["dv_filtered"] += 1
                continue
            v_stock = vol60_df.at[dt_ts, ob] if dt_ts in vol60_df.index else np.nan
            v_med = med_vol60.at[dt_ts] if dt_ts in med_vol60.index else np.nan
            if pd.isna(v_stock) or pd.isna(v_med) or float(v_stock) > float(v_med):
                stats["lowvol_filtered"] += 1
                continue

            ref_c = float(c_r.iloc[j])
            l5 = float(low_5d_raw.iloc[j])
            m20r = float(ma20_raw.iloc[j])
            hard_stop = max(round(ref_c * 0.92, 2), round(min(l5, m20r * 0.97), 2))
            if hard_stop >= ref_c * 0.99:
                hard_stop = round(ref_c * 0.96, 2)
            stats["qualified"] += 1
            cands.setdefault(dt_ts.strftime("%Y-%m-%d"), []).append(
                {
                    "order_book_id": ob,
                    "ref_close_raw": ref_c,
                    "hard_stop_raw": hard_stop,
                    "score": dv - 0.01 * float(v_stock),
                }
            )

    for lst in cands.values():
        lst.sort(key=lambda x: (-x["score"], x["order_book_id"]))
    return cands, stats


def run_standalone_stock_rqalpha(
    cands_by_date: dict[str, list[Any]],
    regime_by_date: dict[str, str],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cash: float,
) -> dict[str, Any]:
    """Native RQAlpha 6.3.0 standalone stock swing evaluation with 5bp one-way slippage drag."""
    from rqalpha.api import history_bars, order_shares, subscribe_event

    closed_trades: list[dict[str, Any]] = []
    open_lots: dict[str, dict[str, Any]] = {}
    pending_sells: dict[str, str] = {}
    pending_buys: list[dict[str, Any]] = []
    slip_cum = [0.0]

    def on_trade(ctx: Any, ev: Any) -> None:
        t = ev.trade
        ob = str(t.order_book_id)
        qty, px = float(t.last_quantity), float(t.last_price)
        notional = qty * px
        slip = notional * 0.0005
        slip_cum[0] += slip
        if t.side.name == "BUY":
            lot = open_lots[ob]
            lot["qty"] += qty
            lot["buy_notional"] += notional
            lot["buy_cost"] += float(t.transaction_cost) + slip
        else:
            lot = open_lots.pop(ob, None)
            if lot:
                gross = notional - lot["buy_notional"]
                frict = lot["buy_cost"] + float(t.transaction_cost) + slip
                closed_trades.append(
                    {
                        "net_ret": (gross - frict) / max(lot["buy_notional"], 1.0),
                        "frict": frict,
                    }
                )

    def init(ctx: Any) -> None:
        env = Environment.get_instance()
        fees = TieredFees(env, set())
        env.set_transaction_cost_decider(INSTRUMENT_TYPE.CS, fees)
        subscribe_event(EVENT.TRADE, on_trade)

    def open_auction(ctx: Any, bar_dict: Any) -> None:
        nonlocal pending_sells, pending_buys
        next_sells: dict[str, str] = {}
        for ob, rsn in pending_sells.items():
            pos = ctx.portfolio.positions.get(ob)
            if not pos or pos.quantity <= 0:
                continue
            b = bar_dict[ob]
            is_ld = (
                np.isfinite(b.limit_down)
                and b.limit_down > 0
                and b.open <= b.limit_down + 1e-4
            )
            if getattr(b, "suspended", False) or np.isnan(b.open) or is_ld:
                next_sells[ob] = rsn
                continue
            order_shares(ob, -int(pos.quantity))
        pending_sells = next_sells

        nav, avail = float(ctx.portfolio.total_value), float(ctx.portfolio.cash)
        occupied = sum(1 for p in ctx.portfolio.positions.values() if p.quantity > 0)
        slots = max(0, 2 - occupied)
        for cand in pending_buys:
            if slots <= 0:
                break
            ob = cand["order_book_id"]
            if ob in open_lots:
                continue
            b = bar_dict[ob]
            px = float(b.open)
            if getattr(b, "suspended", False) or not isfinite(px) or px <= 0:
                continue
            if np.isfinite(b.limit_up) and b.limit_up > 0 and px >= b.limit_up - 1e-4:
                continue
            if np.isfinite(b.prev_close) and b.prev_close > 0 and px > float(b.prev_close) * 1.02:
                continue
            stop_pct = min(0.08, max(0.025, 1.0 - cand["hard_stop_raw"] / cand["ref_close_raw"]))
            risk_per = max(px * stop_pct, px * 0.02)
            raw_sh = min((nav * 0.013) / risk_per, (nav * 0.18) / px, (avail * 0.996) / px)
            shares = int(math.floor(raw_sh / 100.0) * 100)
            if shares < 100 or shares * px < 8000.0:
                continue
            avail -= shares * px + max(5.0, shares * px * 0.00025)
            slots -= 1
            open_lots[ob] = {
                "entry_date": str(ctx.now.date()),
                "qty": 0.0,
                "buy_notional": 0.0,
                "buy_cost": 0.0,
                "stop_pct": stop_pct,
                "peak_px": px,
                "armed": False,
            }
            order_shares(ob, shares)
        pending_buys = []

    def handle_bar(ctx: Any, bar_dict: Any) -> None:
        nonlocal pending_buys
        cur_d = str(ctx.now.date())
        for ob in list(open_lots.keys()):
            if open_lots[ob]["qty"] <= 0:
                open_lots.pop(ob, None)
        for ob, lot in list(open_lots.items()):
            if lot["entry_date"] >= cur_d or ob in pending_sells:
                continue
            c = float(bar_dict[ob].close)
            if not isfinite(c) or c <= 0:
                continue
            pos = ctx.portfolio.positions.get(ob)
            eff_q = float(pos.quantity) if pos and pos.quantity > 0 else lot["qty"]
            eff_e = lot["buy_notional"] / max(eff_q, 1.0)
            lot["peak_px"] = max(lot["peak_px"], c)
            if lot["peak_px"] >= eff_e * 1.15:
                lot["armed"] = True
            stop_px = max(eff_e * (1.0 - lot["stop_pct"]), eff_e if lot["armed"] else 0.0)
            h20 = history_bars(ob, 20, "1d", "close")
            ma20 = float(np.mean(h20)) if h20 is not None and len(h20) == 20 else np.nan
            if c <= stop_px:
                pending_sells[ob] = "STOP"
            elif np.isfinite(ma20) and c < ma20:
                pending_sells[ob] = "MA20"
        if regime_by_date.get(cur_d, "STRUCTURAL") == "DEFENSIVE":
            pending_buys = []
            return
        pending_buys = [
            c for c in cands_by_date.get(cur_d, []) if c["order_book_id"] not in open_lots
        ][:2]

    cfg = build_rqalpha_config(
        str(start.date()),
        str(end.date()),
        initial_cash=cash,
        fees=0.00025,
        slippage=0,
        bundle_path=data.BUNDLE_PATH_202611,
        rqalpha_major_version=6,
    )
    cfg["mod"]["sys_accounts"] = {"stock_t1": True, "auto_switch_order_value": False}
    raw = run_func(
        init=init, open_auction=open_auction, handle_bar=handle_bar, config=cfg
    )["sys_analyser"]
    eq_raw = raw["portfolio"]["total_value"].astype(float)
    # Apply explicit 5bp slippage total monotonically to final net return metrics
    eq_adj = (eq_raw - slip_cum[0] * np.linspace(0.0, 1.0, len(eq_raw))).clip(lower=1.0)
    rets = [t["net_ret"] for t in closed_trades]
    return {
        "net_metrics": metrics(eq_adj),
        "closed_trades": len(closed_trades),
        "win_rate": round(float(np.mean([r > 0 for r in rets])), 4) if rets else 0.0,
        "net_expectancy_pct": round(float(np.mean(rets)) * 100.0, 3) if rets else 0.0,
        "total_friction_yuan": round(float(sum(t["frict"] for t in closed_trades)), 2),
    }


def main() -> int:
    reserve(STEM)
    report: dict[str, Any] = {
        "started": utc(),
        "runner_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "versions": {k: version(k) for k in ("rqalpha", "vectorbt")},
        "protocol_sha256": data.sha256_file(PROTOCOL),
        "line_10a_vbt": {},
        "line_10a_rqa": {},
        "line_10b_status": "BOUNDED_SHORT_WINDOW_PRE_STUDY",
        "line_10b_audit": {},
        "line_10b_rqa": {},
        "gates": {},
    }
    try:
        prov = data.verify_v3_202611_provenance(verify_content=True)
        p = data.load_stitched_panels_202611(prov)
        reg = data.compute_v3_regime_series_202611(prov, p.index_close, p.calendar, use_cache=True)

        wl = json.loads(data.base_v3.WHITELIST_PATH.read_text(encoding="utf-8"))
        sector_super = tuple(
            str(e["ts_code"]) for e in wl["entries"] if e["category"] == "industry_theme"
        )
        require(
            len(sector_super) == 23,
            f"expected 23 industry_theme super ETFs, got {len(sector_super)}",
        )

        # Line 10A
        arms_10a = [
            ("10A_CHASSIS_NO_PIONEER", 0, "ret60", True, True),
            ("10A_TOP1_RET60_MA60", 1, "ret60", True, True),
            ("10A_TOP1_BLEND_MA60", 1, "blend", True, True),
            ("10A_TOP2_RET60_MA60", 2, "ret60", True, True),
            ("10A_TOP2_BLEND_MA60", 2, "blend", True, False),
            ("10A_UNFILTERED_TOP1_CTRL", 1, "ret60", False, True),
        ]
        w10a: dict[str, pd.DataFrame] = {}
        for name, tk, rm, tf, _ in arms_10a:
            w, events = build_sector_pioneer_weights(
                p, reg, sector_super, top_k=tk, rank_mode=rm, trend_filter=tf, end=VBT_END
            )
            w10a[name] = w
            prices, mask, targets_df = (
                f.loc[:VBT_END] for f in (p.etf_adj_close, p.etf_tradability_mask, w)
            )
            validate_execution_targets(targets_df, prices, mask, p.etf_lifetimes)
            rates = np.array(
                [SUPER if c in prov.super_etf_codes else NORMAL for c in w.columns]
            )[None, :]
            eq = run_target_weights(
                prices,
                targets_df,
                fees=rates,
                slippage=0.0002,
                initial_cash=100000.0,
                metric_start=START,
                tradability_mask=mask,
                lifetimes=p.etf_lifetimes,
            ).equity.loc[START:VBT_END]
            report["line_10a_vbt"][name] = {
                "events": len(events),
                "full_2018_20261126": metrics(eq),
                "is_2018_2023": metrics(eq.loc[: data.IS_END]),
                "oos_2024_20261126": metrics(eq.loc[data.IS_END :]),
            }

        for cash in CASH:
            for name, _, _, _, rqa_on in arms_10a:
                if not rqa_on:
                    continue
                label = f"{name}_{cash}"
                print(utc(), label, flush=True)
                eq, run = replay(
                    w10a[name], cash, prov.super_etf_codes, True, start=START, end=RQA_END
                )
                fees = sum(float(f["commission"]) for f in run["fills"])
                report["line_10a_rqa"][label] = {
                    "full": metrics(eq),
                    "oos": metrics(eq.loc[data.IS_END :]),
                    "commission_yuan": round(fees, 2),
                    "trade_count": len(run["fills"]),
                    "dates_pass": run["dates_pass"],
                    "fill_capture_pass": run["fill_capture_pass"],
                    "fees_pass": run["commission_audit"]["fees_pass"],
                    "illegal_non_lot_fills": len(run["commission_audit"]["illegal_non_lot_fills"]),
                }

        # Line 10B: Bounded Short-Window Pre-Study (2024-02-01..2026-10-30)
        basic_tbl, dv_audit = load_pit_basic_tables()
        hd_cands, hd_stats = build_high_div_lowvol_candidates(
            basic_table=basic_tbl, oos_start=OOS_10B_START, bundle_end=RQA_END
        )
        bp1_raw, bp1_stats = build_causal_bp1_candidates_202611(
            oos_start=OOS_10B_START, bundle_end=RQA_END
        )
        bp1_cands = {
            d: [
                {
                    "order_book_id": c.order_book_id,
                    "ref_close_raw": c.ref_close_raw,
                    "hard_stop_raw": c.hard_stop_raw,
                    "score": c.score,
                }
                for c in lst
            ]
            for d, lst in bp1_raw.items()
        }
        reg_by_date = {str(dt.date()): str(row["confirmed_regime"]) for dt, row in reg.iterrows()}
        report["line_10b_audit"] = {
            "dv_coverage": dv_audit,
            "hd_lowvol_stats": hd_stats,
            "bp1_stats": bp1_stats,
        }

        for cash in CASH:
            report["line_10b_rqa"][f"BP1_REF_{cash}"] = run_standalone_stock_rqalpha(
                bp1_cands, reg_by_date, start=OOS_10B_START, end=RQA_END, cash=float(cash)
            )
            report["line_10b_rqa"][f"HIGH_DIV_LOWVOL_{cash}"] = run_standalone_stock_rqalpha(
                hd_cands, reg_by_date, start=OOS_10B_START, end=RQA_END, cash=float(cash)
            )

        rqa_list = list(report["line_10a_rqa"].values())
        report["gates"] = {
            "order_dates": all(r["dates_pass"] for r in rqa_list),
            "lots_and_capture": all(
                r["fill_capture_pass"] and r["illegal_non_lot_fills"] == 0 for r in rqa_list
            ),
            "commissions": all(r["fees_pass"] for r in rqa_list),
        }
        require(all(report["gates"].values()), "10A integrity gate failed")
        base10a = report["line_10a_rqa"]["10A_CHASSIS_NO_PIONEER_100000"]["full"]
        top1_10a = report["line_10a_rqa"]["10A_TOP1_RET60_MA60_100000"]["full"]
        report["verdict"] = (
            "SECTOR_PIONEER_ADDS_VALUE_10B_PRE_STUDY"
            if top1_10a["calmar"] > base10a["calmar"] and top1_10a["cagr"] > base10a["cagr"]
            else "SECTOR_PIONEER_NO_EDGE_10B_PRE_STUDY"
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
        "# EXP-V3-10：23 只超级行业 ETF 动量先导（10A）与短窗高股息低波 pre-study（10B）",
        "",
        f"裁决：`{report['verdict']}`。10B 状态：`{report['line_10b_status']}`。",
        "",
        "## 1. Line 10A RQAlpha 6.3.0 原生回放（2018-01-02..2026-10-30）",
        "",
        "| 回放 | CAGR | MaxDD | Sharpe | Calmar | OOS CAGR | 成交 | 佣金(元) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, r in report["line_10a_rqa"].items():
        m, om = r["full"], r["oos"]
        lines.append(
            f"| {label} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {m['sharpe']:.3f} "
            f"| {m['calmar']:.3f} | {om['cagr']:.2%} | {r['trade_count']} "
            f"| {r['commission_yuan']:.2f} |"
        )
    lines += [
        "",
        "## 2. Line 10B BOUNDED_SHORT_WINDOW_PRE_STUDY"
        "（2024-02-01..2026-10-30，含 5bp 滑点与全额税费）",
        "",
        "| Arm | CAGR | MaxDD | Sharpe | 成交笔数 | 胜率 | 单笔净期望 | 总摩擦(元) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, r in report["line_10b_rqa"].items():
        m = r["net_metrics"]
        lines.append(
            f"| {label} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {m['sharpe']:.3f} "
            f"| {r['closed_trades']} | {r['win_rate']:.2%} | {r['net_expectancy_pct']:.3f}% "
            f"| {r['total_friction_yuan']:.2f} |"
        )
    with STEM.with_suffix(".md").open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(report["verdict"], flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
