"""EXP-V3-09 runner: Drawdown control comparison on V3 ETF chassis and concentrated replay.

External Evidence Gate:
- Canonical mapping: DRAWDOWN_CONTROL (E3_MIXED_CONDITIONAL).
- External conclusion: Black & Jones (1987) CPPI scales exposure cleanly by cushion m*(NAV-F);
  step locks risk re-lock loops around fixed HWM unless working peak re-anchors after cooldown.
- Relevant contradictions: Re-anchoring must never hide true un-reanchored all-time peak drawdown
  and redline (-15%) breaches; must be reported on both dual metrics.
- Upstream implementation: VectorBT (2018-01-02..2026-11-26) + RQAlpha 6.3.0 (chassis ..2026-10-30
  & concentrated account replay 2024-07-01..2026-10-30 at ¥69k / ¥100k).
- Remaining local gap: Fixing HEAVY70_69000's 20x re-lock loop and comparing net Calmar/breaches.
- Research action: LOCAL_ADJUDICATION.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rqalpha import run_func
from rqalpha.const import INSTRUMENT_TYPE
from rqalpha.core.events import EVENT
from rqalpha.environment import Environment
from rqalpha.mod.rqalpha_mod_sys_accounts.trade_utils import get_amount_from_value
from rqalpha.mod.utils import round_order_quantity

from research.ashare import v3_data_202611 as data
from research.ashare.experiments import exp_v3_01_regime_super_etf as e1
from research.batches.v3_account_replay_v2.native import TieredFees, opening_block
from research.batches.v3_account_replay_v2.policy import BUDGET, FOCUS, Plan, exit_reason, targets
from research.batches.v3_account_replay_v2.run import END as RQA_END
from research.batches.v3_account_replay_v2.run import (
    OOS_CONC_START,
    _build_etf_features,
    _series_metrics,
)
from research.batches.v3_complexity_hurdle_v2.native import NORMAL, SUPER, replay
from research.batches.v3_complexity_hurdle_v2.run import metrics, require, reserve, utc
from tacticore.engines.rqalpha_adapter import build_rqalpha_config
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/EXP_V3_09_DRAWDOWN_CONTROL_V2"
PROTOCOL = ROOT / "research/batches/exp_v3_09_drawdown_control/PROTOCOL_V2.md"

START = data.EXP_START
VBT_END = data.EXP_END_202611
CASH = (69000, 100000)


@dataclass
class DrawdownController:
    """Unified state machine for C0/C1/C2(CPPI)/C3(gradual) drawdown control."""

    init_nav: float
    mode: str  # "c0_hard" | "c1_reanchor" | "c2_cppi" | "c3_gradual"
    floor_dd: float = 0.15
    cppi_m: float = 5.0
    cooldown_days: int = 15
    ramp_days: int = 10

    def __post_init__(self) -> None:
        self.true_peak = float(self.init_nav)
        self.work_peak = float(self.init_nav)
        self.until = -1000
        self.ramp_until = -1000
        self.lock_ceiling = 0.15
        self.locks = 0
        self.relock_loops = 0
        self.last_unlock_day = -1000

    def step(self, i: int, nav: float, concentrated: bool, base_eq_budget: float) -> dict[str, Any]:
        self.true_peak = max(self.true_peak, nav)
        self.work_peak = max(self.work_peak, nav)
        true_dd = 1.0 - nav / self.true_peak
        work_dd = 1.0 - nav / self.work_peak
        breach = max(0.0, true_dd - 0.15)
        l1 = work_dd + 1e-12 >= 0.10

        trigger = False
        locked = False
        ctrl_cap: float | None = None
        buy_cap = base_eq_budget

        if self.mode == "c0_hard":
            th, cap = (0.12, 0.0) if concentrated else (0.15, 0.15)
            if i > self.until and work_dd + 1e-12 >= th:
                trigger = True
                self.locks += 1
                if i <= self.last_unlock_day + 5:
                    self.relock_loops += 1
                self.until, self.lock_ceiling = i + self.cooldown_days, cap
            if i <= self.until:
                locked = True
                ctrl_cap = self.lock_ceiling
                buy_cap = min(buy_cap, self.lock_ceiling)
            elif i == self.until + 1:
                self.last_unlock_day = i

        elif self.mode == "c1_reanchor":
            th, cap = (0.12, 0.0) if concentrated else (0.15, 0.15)
            if i == self.until + 1:
                self.last_unlock_day = i
                # Re-anchor control peak at unlock completion; true_peak remains untouched!
                self.work_peak = nav
                self.ramp_until = i + self.ramp_days
                work_dd = 0.0
            if i > self.until and work_dd + 1e-12 >= th:
                trigger = True
                self.locks += 1
                if i <= self.last_unlock_day + 5:
                    self.relock_loops += 1
                self.until, self.lock_ceiling = i + self.cooldown_days, cap
            if i <= self.until:
                locked = True
                ctrl_cap = self.lock_ceiling
                buy_cap = min(buy_cap, self.lock_ceiling)
            elif i <= self.ramp_until:
                prog = 0.5 + 0.5 * (1.0 - (self.ramp_until - i) / max(1, self.ramp_days))
                buy_cap = min(buy_cap, base_eq_budget * prog)

        elif self.mode == "c2_cppi":
            if i == self.until + 1:
                self.work_peak = nav
            floor_nav = self.work_peak * (1.0 - self.floor_dd)
            cushion_frac = max(0.0, (nav - floor_nav) / max(nav, 1.0))
            if cushion_frac <= 1e-6 and i > self.until:
                trigger = True
                self.locks += 1
                self.until = i + self.cooldown_days
            if i <= self.until:
                locked = True
                ctrl_cap = 0.0 if concentrated else 0.10
                buy_cap = min(buy_cap, ctrl_cap)
            else:
                cppi_limit = min(1.0, self.cppi_m * cushion_frac)
                ctrl_cap = cppi_limit
                buy_cap = min(buy_cap, cppi_limit)

        elif self.mode == "c3_gradual":
            if i == self.until + 1:
                self.last_unlock_day = i
                self.work_peak = nav
                self.ramp_until = i + self.ramp_days
                work_dd = 0.0
            if i <= self.until:
                locked = True
                ctrl_cap = 0.0 if concentrated else 0.10
                buy_cap = min(buy_cap, ctrl_cap)
            else:
                if work_dd + 1e-12 >= 0.135:
                    trigger = True
                    self.locks += 1
                    self.until = i + 10
                    locked = True
                    ctrl_cap = 0.0 if concentrated else 0.10
                    buy_cap = min(buy_cap, ctrl_cap)
                elif work_dd + 1e-12 >= 0.11:
                    ctrl_cap = 0.25
                    buy_cap = min(buy_cap, 0.25)
                elif work_dd + 1e-12 >= 0.08:
                    ctrl_cap = 0.50
                    buy_cap = min(buy_cap, 0.50)
                if not locked and i <= self.ramp_until:
                    prog = 0.5 + 0.5 * (1.0 - (self.ramp_until - i) / max(1, self.ramp_days))
                    buy_cap = min(buy_cap, base_eq_budget * prog)

        return {
            "true_dd": true_dd,
            "work_dd": work_dd,
            "breach": breach,
            "l1": l1,
            "trigger": trigger,
            "locked": locked,
            "ctrl_cap": ctrl_cap,
            "buy_cap": buy_cap,
        }


def simulate_chassis_overlay(
    panels: Any,
    regime_df: pd.DataFrame,
    base_weights: pd.DataFrame,
    *,
    mode: str,
    floor_dd: float = 0.15,
    cppi_m: float = 5.0,
    end: pd.Timestamp = VBT_END,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply causal daily drawdown multiplier onto V3 ETF base weights and emit schedule."""
    cal = panels.calendar[(panels.calendar >= START) & (panels.calendar <= end)]
    adj = panels.etf_adj_close.loc[cal].ffill()
    cols = list(panels.etf_adj_close.columns)
    base_full = base_weights.loc[cal].ffill().fillna(0.0)
    mask = panels.etf_tradability_mask

    # Daily asset simple returns for causal NAV proxy driving the controller
    rets = adj.pct_change(fill_method=None).fillna(0.0)
    ctrl = DrawdownController(init_nav=1.0, mode=mode, floor_dd=floor_dd, cppi_m=cppi_m)

    nav = 1.0
    prev_w = pd.Series(0.0, index=cols, dtype=float)
    out_w = pd.DataFrame(np.nan, index=panels.calendar, columns=cols, dtype=float)
    max_true_dd = 0.0
    breach_days = 0

    for pos in range(len(cal) - 1):
        sig_dt = cal[pos]
        exec_dt = cal[pos + 1]
        if pos > 0:
            port_ret = float((prev_w * rets.loc[sig_dt]).sum())
            nav *= 1.0 + port_ret
        base_row = base_full.loc[exec_dt].copy()
        eq_cols = [c for c in cols if c != "511010.SH"]
        base_eq = float(base_row[eq_cols].sum())
        st = ctrl.step(pos, nav, concentrated=False, base_eq_budget=base_eq)
        max_true_dd = max(max_true_dd, float(st["true_dd"]))
        if st["breach"] > 0:
            breach_days += 1

        scale = (st["buy_cap"] / base_eq) if base_eq > 1e-9 else 1.0
        scale = min(1.0, max(0.0, scale))
        cand = pd.Series(0.0, index=cols, dtype=float)
        for c in eq_cols:
            if base_row[c] > 0:
                cand[c] = float(base_row[c]) * scale
        rem = max(0.0, 1.0 - float(cand.sum()))
        if rem > 1e-6 and bool(mask.at[exec_dt, "511010.SH"]):
            cand["511010.SH"] = rem

        if pos == 0 or float((cand - prev_w).abs().sum()) >= 0.06:
            cand_row = pd.Series(np.nan, index=cols, dtype=float)
            for sym in cols:
                if cand[sym] > 0:
                    cand_row[sym] = cand[sym]
                elif prev_w[sym] > 0:
                    cand_row[sym] = 0.0
            out_w.loc[exec_dt] = cand_row
            prev_w = cand

    return out_w, {
        "locks": ctrl.locks,
        "relock_loops": ctrl.relock_loops,
        "breach_days": breach_days,
        "proxy_max_true_dd": max_true_dd,
    }


def replay_concentrated_with_ctrl(
    days: list[str],
    market: dict[str, tuple[str, str]],
    features: dict[str, dict[str, Any]],
    white: set[str],
    capital: float,
    seed: float,
    *,
    mode: str,
    floor_dd: float = 0.15,
    cppi_m: float = 5.0,
) -> dict[str, Any]:
    """Native RQAlpha replay of concentrated account under C0/C1/C2/C3 risk controller."""
    from rqalpha.api import instruments, order_shares, subscribe_event

    lookup = {d: i for i, d in enumerate(days)}
    rows, fills = [], []
    pending: dict[str, dict[str, Any]] = {}
    retries: dict[str, dict[str, Any]] = {}
    armed: dict[str, bool] = {}
    ctrl = DrawdownController(init_nav=capital, mode=mode, floor_dd=floor_dd, cppi_m=cppi_m)
    plan = Plan()
    state: dict[str, Any] = {"regime": None, "align": -100, "locked": False, "active": None}

    cfg = build_rqalpha_config(
        days[0],
        days[-1],
        initial_cash=capital,
        fees=0.00025,
        slippage=0,
        bundle_path=data.BUNDLE_PATH_202611,
        rqalpha_major_version=6,
    )
    cfg["mod"]["sys_accounts"] = {"stock_t1": True, "auto_switch_order_value": False}

    def merge(book: dict[str, dict[str, Any]], a: dict[str, Any]) -> None:
        sym = a["code"]
        if sym in book:
            old = book[sym]
            key_new = (a["p"], -a.get("sell_est", 0))
            key_old = (old["p"], -old.get("sell_est", 0))
            book[sym] = old if key_new >= key_old else a
        else:
            book[sym] = a

    def on_trade(ctx: Any, ev: Any) -> None:
        a = state["active"]
        if not a:
            return
        t = ev.trade
        q, px = int(t.last_quantity), float(t.last_price)
        d = str(ctx.now.date())
        fills.append(
            {
                "date": d,
                "code": t.order_book_id,
                "side": t.side.name,
                "qty": q,
                "price": px,
                "commission": float(t.commission),
            }
        )
        a["filled"] += q
        if t.order_book_id == FOCUS:
            i = lookup[d]
            if a["reason"] == "SEED":
                plan.seed(a["filled"], int(capital * 0.25 / px / 100), px, i)
            elif a["side"] == "SELL":
                plan.sell(q, px, i)
            elif a["reason"] == "SLOT":
                plan.slot_px = (plan.slot_px * plan.slot + px * q) / (plan.slot + q)
                plan.slot += q
                plan.last_fill = i

    def init(ctx: Any) -> None:
        env = Environment.get_instance()
        fees = TieredFees(env, white)
        for typ in (INSTRUMENT_TYPE.CS, INSTRUMENT_TYPE.ETF):
            env.set_transaction_cost_decider(typ, fees)
        subscribe_event(EVENT.TRADE, on_trade)

    def open_auction(ctx: Any, bars: Any) -> None:
        d = str(ctx.now.date())
        i = lookup[d]
        env = Environment.get_instance()
        if i == 0 and seed:
            pending[FOCUS] = {
                "signal": "INITIAL",
                "code": FOCUS,
                "p": 2,
                "reason": "SEED",
                "side": "BUY",
                "w": seed,
                "qty": None,
            }
        for a in sorted(pending.values(), key=lambda x: (x["p"], x["side"] == "BUY", x["code"])):
            sym, buy = a["code"], a["side"] == "BUY"
            record = dict(a, date=d, filled=0)
            instrument = instruments(sym)
            pos = ctx.portfolio.positions[sym]
            held, sellable = int(pos.quantity), int(pos.sellable)
            bar = bars[sym]
            px = float(bar.open)
            is_susp = not instrument.active_at(ctx.now) or env.data_proxy.is_suspended(
                sym, ctx.now.date()
            )
            why = opening_block(px, bar.limit_up if buy else bar.limit_down, buy, is_susp)
            requested = None
            if not why:
                nav, cash = float(ctx.portfolio.total_value), float(ctx.portfolio.cash)
                if buy:
                    amount = min(max(0.0, a["w"] * nav - held * px), cash)
                    requested = get_amount_from_value(amount, instrument, px, env, cash)
                    minimum = 1000.0 if sym in white else 5000.0
                    why = (
                        "LOT_OR_CASH"
                        if requested == 0
                        else ("BELOW_MIN" if requested * px < minimum else None)
                    )
                else:
                    desired = (
                        min(held, a["qty"])
                        if a["qty"] is not None
                        else (
                            held
                            if a["w"] == 0
                            else int(
                                round_order_quantity(instrument, max(0.0, held - a["w"] * nav / px))
                            )
                        )
                    )
                    requested = min(desired, sellable)
                    if not requested:
                        why = "T1_OR_NONE"
            if not why:
                state["active"] = record
                try:
                    order_shares(sym, requested if buy else -requested)
                finally:
                    state["active"] = None
                if not buy and record["filled"] < desired:
                    rem_q = desired - record["filled"]
                    retries[sym] = dict(a, qty=rem_q, w=None, sell_est=rem_q)
                if not buy and record["filled"] == held:
                    armed.pop(sym, None)
            elif not buy and held and why != "T1_OR_NONE":
                retries[sym] = a.copy()
        pending.clear()

    def close(ctx: Any, bars: Any) -> None:
        del bars
        d = str(ctx.now.date())
        i = lookup[d]
        nav, _ = float(ctx.portfolio.total_value), float(ctx.portfolio.cash)
        pp = ctx.portfolio.positions
        held = {s: pp[s] for s in pp if pp[s].quantity > 0}
        w = {s: float(p.market_value / nav) for s, p in held.items()}
        focus_w = w.get(FOCUS, 0.0)
        regime, style = market[d]
        risk_row = ctrl.step(i, nav, focus_w > 0.30 or any(plan.batches), BUDGET[regime])
        locked, l1 = risk_row["locked"], risk_row["l1"]
        risk_w = sum(w.values())
        rows.append({"date": d, "nav": nav, **risk_row})

        for a in retries.values():
            merge(pending, dict(a, signal=d))
        retries.clear()

        def add(
            p_prio: int,
            sym: str,
            reason: str,
            side: str,
            weight: float | None = None,
            qty: int | None = None,
        ) -> None:
            sell_est = (
                (
                    qty
                    if qty is not None
                    else int(held[sym].quantity * max(0.0, 1.0 - weight / w[sym]))
                )
                if side == "SELL"
                else 0
            )
            merge(
                pending,
                {
                    "signal": d,
                    "code": sym,
                    "p": p_prio,
                    "reason": reason,
                    "side": side,
                    "w": weight,
                    "qty": qty,
                    "sell_est": sell_est,
                },
            )

        # Proportional reduction whenever drawdown controller explicitly imposes ctrl_cap
        cc = risk_row["ctrl_cap"]
        if cc is not None and risk_w > cc + 0.02 and risk_w > 1e-6:
            for s in held:
                add(0, s, "CTRL_REDUCE", "SELL", w[s] * cc / risk_w)

        for s, p in held.items():
            if s != FOCUS and s in features[d]:
                r = features[d][s]
                armed[s], why = exit_reason(
                    r.raw,
                    float(p.avg_price),
                    r.raw * r.ma20 / r.c,
                    r.raw * r.ma10 / r.c,
                    armed.get(s, False),
                    l1,
                )
                if why:
                    add(1, s, why, "SELL", 0.0)

        if FOCUS in held and FOCUS in features[d]:
            dec = plan.decision(
                features[d][FOCUS], i, focus_w, regime, l1 or locked, risk_row["buy_cap"] - risk_w
            )
            if dec:
                reason, qty, wt = dec
                side = "BUY" if reason == "SLOT" else "SELL"
                add(2, FOCUS, reason, side, wt, abs(qty) if qty else None)

        align = (
            regime != state["regime"]
            or (state["locked"] and not locked)
            or i - state["align"] >= 10
        )
        if align and not locked:
            pend_focus = pending.get(FOCUS, {})
            pend_w = (pend_focus.get("w") or 0.0) if pend_focus.get("side") == "BUY" else 0.0
            focus_b = max(focus_w, pend_w)
            raw_t = targets(regime, style, focus_b, features[d])
            tot_t = sum(raw_t.values())
            scale = (
                min(1.0, max(0.0, risk_row["buy_cap"] - focus_b) / max(tot_t, 1e-9))
                if tot_t > 0
                else 1.0
            )
            scaled_t = {k: v * scale for k, v in raw_t.items() if v * scale > 0.01}
            for s in sorted((set(held) | set(scaled_t)) - {FOCUS}):
                wt = scaled_t.get(s, 0.0)
                if abs(wt - w.get(s, 0.0)) * nav >= (1000.0 if s in white else 5000.0):
                    add(3, s, "ALIGN", "BUY" if wt > w.get(s, 0.0) else "SELL", wt)
            state["align"] = i
        state.update(regime=regime, locked=locked)

    run_func(init=init, open_auction=open_auction, handle_bar=close, config=cfg)
    eq = pd.Series([r["nav"] for r in rows], index=pd.to_datetime([r["date"] for r in rows]))
    return {
        "metrics": _series_metrics(eq),
        "true_max_dd": float(max(r["true_dd"] for r in rows)),
        "breach_days": sum(1 for r in rows if r["breach"] > 0),
        "locks": ctrl.locks,
        "relock_loops": ctrl.relock_loops,
        "locked_days": sum(1 for r in rows if r["locked"]),
        "commission_yuan": round(sum(f["commission"] for f in fills), 2),
        "fills": len(fills),
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
        "chassis_vbt": {},
        "chassis_rqa": {},
        "account_replay": {},
        "gates": {},
    }
    try:
        prov = data.verify_v3_202611_provenance(verify_content=True)
        p = data.load_stitched_panels_202611(prov)
        reg = data.compute_v3_regime_series_202611(prov, p.index_close, p.calendar, use_cache=True)
        base_w, _ = e1.build_v3_execution_weights(p, reg, end=VBT_END, include_bond_reserve=True)

        chassis_specs: list[tuple[str, str, float, float, bool]] = [
            ("C0_HARD_STEP_LOCK", "c0_hard", 0.15, 5.0, True),
            ("C1_REANCHOR_15D_RAMP10D", "c1_reanchor", 0.15, 5.0, True),
            ("C2_CPPI_F13_M4", "c2_cppi", 0.13, 4.0, False),
            ("C2_CPPI_F13_M5", "c2_cppi", 0.13, 5.0, False),
            ("C2_CPPI_F15_M4", "c2_cppi", 0.15, 4.0, False),
            ("C2_CPPI_F15_M5", "c2_cppi", 0.15, 5.0, True),
            ("C2_CPPI_F15_M6", "c2_cppi", 0.15, 6.0, False),
            ("C2_CPPI_F17_M5", "c2_cppi", 0.17, 5.0, False),
            ("C2_CPPI_F17_M6", "c2_cppi", 0.17, 6.0, False),
            ("C3_TWO_STAGE_GRADUAL", "c3_gradual", 0.15, 5.0, True),
        ]

        chassis_w: dict[str, pd.DataFrame] = {}
        for name, mode, f_dd, m_val, _ in chassis_specs:
            w, info = simulate_chassis_overlay(
                p, reg, base_w, mode=mode, floor_dd=f_dd, cppi_m=m_val, end=VBT_END
            )
            chassis_w[name] = w
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
            report["chassis_vbt"][name] = {"ctrl": info, "full_2018_20261126": metrics(eq)}

        for cash in CASH:
            for name, _, _, _, rqa_on in chassis_specs:
                if not rqa_on:
                    continue
                label = f"{name}_{cash}"
                print(utc(), label, flush=True)
                eq, run = replay(
                    chassis_w[name], cash, prov.super_etf_codes, True, start=START, end=RQA_END
                )
                fees = sum(float(f["commission"]) for f in run["fills"])
                report["chassis_rqa"][label] = {
                    "full": metrics(eq),
                    "commission_yuan": round(fees, 2),
                    "dates_pass": run["dates_pass"],
                    "fill_capture_pass": run["fill_capture_pass"],
                    "fees_pass": run["commission_audit"]["fees_pass"],
                    "illegal_non_lot_fills": len(
                        run["commission_audit"]["illegal_non_lot_fills"]
                    ),
                }

        features, white_rq = _build_etf_features(p, set(prov.super_etf_codes))
        market = {
            str(dt.date()): (str(r["confirmed_regime"]), str(r["style"]))
            for dt, r in reg.iterrows()
        }
        cal_all = p.calendar[p.calendar <= RQA_END]
        days_conc = [str(d.date()) for d in cal_all[cal_all >= OOS_CONC_START]]

        for scenario, seed in (("CORE25", 0.25), ("HEAVY70", 0.70)):
            for cash in CASH:
                for name, mode, f_dd, m_val, _ in [x for x in chassis_specs if x[4]]:
                    cell = f"{scenario}_{int(cash)}_{name}"
                    print(utc(), cell, flush=True)
                    report["account_replay"][cell] = replay_concentrated_with_ctrl(
                        days_conc,
                        market,
                        features,
                        white_rq,
                        float(cash),
                        seed,
                        mode=mode,
                        floor_dd=f_dd,
                        cppi_m=m_val,
                    )

        rqa_list = list(report["chassis_rqa"].values())
        report["gates"] = {
            "order_dates": all(r["dates_pass"] for r in rqa_list),
            "lots_and_capture": all(
                r["fill_capture_pass"] and r["illegal_non_lot_fills"] == 0 for r in rqa_list
            ),
            "commissions": all(r["fees_pass"] for r in rqa_list),
        }
        require(all(report["gates"].values()), "chassis rqa gate failed")
        h0 = report["account_replay"]["HEAVY70_69000_C0_HARD_STEP_LOCK"]
        h1 = report["account_replay"]["HEAVY70_69000_C1_REANCHOR_15D_RAMP10D"]
        h2 = report["account_replay"]["HEAVY70_69000_C2_CPPI_F15_M5"]
        report["verdict"] = (
            "REANCHOR_OR_CPPI_ELIMINATES_RELOCK_LOOP"
            if min(h1["relock_loops"], h2["relock_loops"]) < h0["relock_loops"]
            or min(h1["locks"], h2["locks"]) < h0["locks"]
            else "DRAWDOWN_CONTROLS_COMPARABLE"
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
        "# EXP-V3-09：回撤控制架构对比（硬锁死 vs 解锁重锚爬坡 vs CPPI vs 两级渐进）",
        "",
        f"裁决：`{report['verdict']}`。",
        "",
        "## 1. 集中账户原生回放（2024-07-01..2026-10-30，双口径报告真实峰值回撤）",
        "",
        "| 场景 | CAGR | 真实Peak MaxDD | 穿-15%天数 | 锁死次数 | 重锁循环 | 锁定天数 | 佣金(元) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell, c in report["account_replay"].items():
        m = c["metrics"]
        lines.append(
            f"| {cell} | {m['cagr']:.2%} | {-c['true_max_dd']:.2%} | {c['breach_days']} | "
            f"{c['locks']} | {c['relock_loops']} | {c['locked_days']} "
            f"| {c['commission_yuan']:.2f} |"
        )
    lines += [
        "",
        "## 2. 全窗 V3 ETF 底盘 RQAlpha 原生对照（2018-01-02..2026-10-30）",
        "",
        "| 回放 | CAGR | MaxDD | Sharpe | Calmar | 佣金(元) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, r in report["chassis_rqa"].items():
        m = r["full"]
        lines.append(
            f"| {label} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {m['sharpe']:.3f} "
            f"| {m['calmar']:.3f} | {r['commission_yuan']:.2f} |"
        )
    with STEM.with_suffix(".md").open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(report["verdict"], flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
