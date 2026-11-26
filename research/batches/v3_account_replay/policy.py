"""Pure decision rules for EXP-V3-05; never value a portfolio or match an order."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from research.ashare.experiments.exp_v3_04_bottom_grind_cost_reduction import _compute_rsi14

FOCUS = "159558.XSHE"
GOLD = "518880.XSHG"
SECTORS = ("512480.XSHG", "159994.XSHE", "515790.XSHG")
VALUE = ("159330.XSHE", "530050.XSHG", "510140.XSHG", "510300.XSHG")
GROWTH = (
    "159205.XSHE",
    "159337.XSHE",
    "589850.XSHG",
    "159290.XSHE",
    "589060.XSHG",
    "589330.XSHG",
    "510500.XSHG",
)
BUDGET = {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "DEFENSIVE": 0.15}


def indicators(close, raw):
    f = pd.DataFrame({"c": close, "prev": close.shift(), "raw": raw, "prev_raw": raw.shift()})
    for n in (5, 10, 20, 60):
        f[f"ma{n}"] = close.rolling(n).mean()
    f["slope"] = f.ma60 / f.ma60.shift(10) - 1
    f["peak60"] = close.rolling(60).max()
    f["rsi"] = _compute_rsi14(close)
    f["min_rsi"] = f.rsi.rolling(3).min()
    f["min_bias"] = (close / f.ma20 - 1).rolling(3).min()
    f["ret20"] = close / close.shift(20) - 1
    return f


@dataclass
class Risk:
    peak: float
    until: int = -1
    ceiling: float = 0.15

    def observe(self, i, nav, concentrated, lock_enabled):
        self.peak = max(self.peak, nav)
        dd = 1 - nav / self.peak
        threshold, cap = (0.12, 0.0) if concentrated else (0.15, 0.15)
        hit = dd + 1e-12 >= threshold
        trigger = lock_enabled and i > self.until and hit
        if trigger:
            self.until, self.ceiling = i + 15, cap
        locked = lock_enabled and i <= self.until
        return dict(
            dd=dd,
            hwm=self.peak,
            threshold=threshold,
            shadow_hit=hit,
            trigger=trigger,
            locked=locked,
            cap=self.ceiling if locked else None,
            l1=dd + 1e-12 >= 0.10,
            breach=max(0, dd - 0.15),
        )


@dataclass
class Plan:
    batches: list[int] = field(default_factory=list)
    anchor: float = 0.0
    last_sale: float = 0.0
    sale_day: int = -1000
    last_fill: int = -1000
    slot: int = 0
    slot_px: float = 0.0

    def seed(self, quantity, keep_lots, px, i):
        lots = max(0, quantity // 100 - keep_lots)
        self.batches = [100 * (lots // 4 + int(j < lots % 4)) for j in range(4)]
        self.anchor, self.last_fill = px, i

    def sell(self, quantity, px, i):
        self.last_sale, self.last_fill, self.sale_day = px, i, i
        used = min(self.slot, quantity)
        self.slot -= used
        quantity -= used
        for j, n in enumerate(self.batches):
            used = min(n, quantity)
            self.batches[j] -= used
            quantity -= used

    def gates(self, r, i):
        return (
            r.slope >= 0,
            (i - self.sale_day <= 90 and self.last_sale > 0 and r.raw <= self.last_sale * 0.93)
            or r.c <= r.peak60 * 0.85,
            r.min_rsi <= 36 or r.min_bias <= -0.065,
            r.c > r.prev and r.c >= r.ma5 * 0.995,
        )

    def decision(self, r, i, w, regime, l1, risk_room):
        pending = [n for n in self.batches if n]
        if pending:
            if regime != "OFFENSIVE" and (
                (r.raw < 0.780 and r.prev_raw < 0.780) or r.raw < 0.780 * 0.96
            ):
                return "SUPPORT", -sum(pending[: (len(pending) + 1) // 2]), None
            if r.raw >= (self.last_sale or self.anchor) * 1.08:
                return "REBOUND", -pending[0], None
        if self.slot:
            if r.c <= r.ma60 * 1.01:
                take = r.raw >= self.slot_px * 1.075
            else:
                take = (r.raw >= self.slot_px * 1.15 and r.c < r.ma5) or (
                    r.raw >= self.slot_px * 1.04 and r.c < r.ma20
                )
            if take:
                return "TAKE", -self.slot, None
        if w >= 0.34 and ((r.rsi >= 68 and r.c < r.ma5) or (r.c >= r.ma20 * 1.10 and r.c < r.prev)):
            return "HARVEST", None, 0.25
        if (
            not pending
            and not self.slot
            and 0 < w < 0.30
            and i - self.last_fill >= 3
            and not l1
            and regime != "DEFENSIVE"
            and risk_room > 0
            and all(self.gates(r, i))
        ):
            return "SLOT", None, min(0.35, w + min(0.10, risk_room))
        return None


def exit_reason(close, cost, ma20, ma10, armed, l1, stock=False, structural_stop=0.0):
    armed = armed or close >= cost * 1.15
    if stock and close <= max(cost * 0.92, structural_stop, cost if armed else 0):
        return armed, "STOCK_STOP"
    if (stock or armed) and close < (ma10 if l1 else ma20):
        return armed, "MA_EXIT"
    return armed, None


def targets(regime, style, focus_weight, features):
    """Features provided at the signal close only. Never fill unallocated capacity."""

    def valid(c):
        return c in features and pd.notna(features[c].ma20) and features[c].raw > 0

    room = max(0.0, BUDGET[regime] - focus_weight)
    base = min(room, {"OFFENSIVE": 0.40, "STRUCTURAL": 0.25, "DEFENSIVE": 0.10}[regime])
    gold = min(base, 0.10)
    out = {GOLD: gold} if valid(GOLD) else {}
    growth = {"GROWTH_LEADING": 0.65, "VALUE_LEADING": 0.35}.get(style, 0.5)
    for group, share in ((VALUE, 1 - growth), (GROWTH, growth)):
        c = next((c for c in group if valid(c)), None)
        if c and base > gold:
            out[c] = (base - gold) * share
    sector_budget = min(
        0.20,
        room - base,
        max(0.0, {"OFFENSIVE": 0.50, "STRUCTURAL": 0.35, "DEFENSIVE": 0}[regime] - focus_weight),
    )
    pool = [
        c
        for c in SECTORS
        if valid(c) and features[c].c > features[c].ma20 and pd.notna(features[c].ret20)
    ]
    if pool and sector_budget > 0:
        out[min(pool, key=lambda c: (-features[c].ret20, c))] = sector_budget
    return {c: w for c, w in out.items() if w > 0}
