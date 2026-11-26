"""Unit tests for EXP-V3-11 analytics, allocation invariants, and BP1 gating."""

from __future__ import annotations

import pandas as pd

from research.batches.exp_v3_11_v330_integration.analytics import (
    compute_calendar_stats,
    compute_roundtrip_stats,
)
from research.batches.exp_v3_11_v330_integration.run import (
    load_sector_pioneer_pool,
    select_v330_targets,
)


def _row(c: float, ma20: float, ma60: float, ret20: float, ret60: float) -> pd.Series:
    return pd.Series(
        {"c": c, "raw": c, "ma20": ma20, "ma60": ma60, "ret20": ret20, "ret60": ret60}
    )


def test_fifo_roundtrip_stats_and_calendar_win_rates() -> None:
    fills = [
        {
            "date": "2024-01-02",
            "code": "510300.XSHG",
            "side": "BUY",
            "qty": 200,
            "price": 4.0,
            "commission": 2.0,
            "tax": 0.0,
            "other": 0.0,
            "stock_slip_5bp": 0.0,
            "order": 1,
        },
        {
            "date": "2024-01-10",
            "code": "510300.XSHG",
            "side": "SELL",
            "qty": 100,
            "price": 4.4,
            "commission": 1.0,
            "tax": 0.0,
            "other": 0.0,
            "stock_slip_5bp": 0.0,
            "order": 2,
        },
        {
            "date": "2024-01-20",
            "code": "510300.XSHG",
            "side": "SELL",
            "qty": 100,
            "price": 3.8,
            "commission": 1.0,
            "tax": 0.0,
            "other": 0.0,
            "stock_slip_5bp": 0.0,
            "order": 3,
        },
    ]
    rt = compute_roundtrip_stats(fills, lambda _: "chassis")
    ov = rt["overall"]
    assert ov["closed_trades"] == 2
    assert ov["wins"] == 1
    assert ov["losses"] == 1
    assert ov["win_rate"] == 0.5
    # Trade 1: sell 440 - 1 = 439, buy 400 + 1 = 401 -> pnl = +38
    # Trade 2: sell 380 - 1 = 379, buy 400 + 1 = 401 -> pnl = -22
    assert abs(ov["total_realized_pnl_yuan"] - 16.0) < 1e-6
    assert ov["payoff_ratio"] > 1.5
    assert abs(ov["profit_factor"] - (38.0 / 22.0)) < 1e-2
    assert ov["max_consecutive_losses"] == 1

    idx = pd.date_range("2024-01-01", "2024-03-31", freq="B")
    eq = pd.Series([100.0 + i * 0.5 for i in range(len(idx))], index=idx)
    cal = compute_calendar_stats(eq)
    assert cal["monthly_win_rate"] == 1.0
    assert cal["annual_win_rate"] == 1.0
    assert cal["total_return"] > 0


def test_v330_target_allocation_and_bp1_gating_invariants() -> None:
    pool = load_sector_pioneer_pool()
    assert len(pool) >= 20
    assert "159549.SZ" not in pool and "159207.SZ" not in pool and "159321.SZ" not in pool

    feats = {
        "159330.XSHE": _row(1.1, 1.0, 1.0, 0.05, 0.08),
        "159205.XSHE": _row(1.2, 1.1, 1.0, 0.12, 0.18),
        "159549.XSHE": _row(1.05, 1.0, 1.0, 0.02, 0.04),
        "159207.XSHE": _row(1.04, 1.0, 1.0, 0.01, 0.03),
        "512480.XSHG": _row(1.3, 1.2, 1.1, 0.15, 0.25),
        "515790.XSHG": _row(0.9, 1.0, 1.1, -0.05, -0.10),
    }

    # Gated OFFENSIVE: 65% chassis (30% of 65% = 19.5% low-vol) + 20% top-1 sector pioneer
    off_gated = select_v330_targets(
        regime="OFFENSIVE",
        style="BALANCED",
        occupied_weight=0.0,
        features=feats,
        sector_pool_rq=("512480.XSHG", "515790.XSHG"),
        use_lowvol_core=True,
        use_sector_pioneer=True,
        bp1_active_budget=False,
    )
    assert abs(sum(off_gated.values()) - 0.85) < 1e-9
    assert abs(off_gated["512480.XSHG"] - 0.20) < 1e-9
    assert abs(off_gated["159549.XSHE"] + off_gated["159207.XSHE"] - 0.65 * 0.30) < 1e-9

    # RECOVERY: 40% pure chassis, 0% sector pioneer
    rec = select_v330_targets(
        regime="RECOVERY",
        style="GROWTH_LEADING",
        occupied_weight=0.0,
        features=feats,
        sector_pool_rq=("512480.XSHG", "515790.XSHG"),
        use_lowvol_core=True,
        use_sector_pioneer=True,
        bp1_active_budget=True,
    )
    assert abs(sum(rec.values()) - 0.40) < 1e-9
    assert "512480.XSHG" not in rec

    # DEFENSIVE: 15% low-vol only
    def_w = select_v330_targets(
        regime="DEFENSIVE",
        style="BALANCED",
        occupied_weight=0.0,
        features=feats,
        sector_pool_rq=("512480.XSHG",),
        use_lowvol_core=True,
        use_sector_pioneer=True,
        bp1_active_budget=False,
    )
    assert abs(def_w["159549.XSHE"] + def_w["159207.XSHE"] - 0.15) < 1e-9
