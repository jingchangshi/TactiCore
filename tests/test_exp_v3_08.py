"""Synthetic tests for EXP-V3-08."""

from types import SimpleNamespace

import numpy as np
import pandas as pd

from research.batches.exp_v3_08_icepoint_recovery.run import compute_recovery_overlay_series


def test_m1_triggers_only_after_icepoint_and_stops_on_false_breakout():
    cal = pd.bdate_range("2024-01-02", periods=45)
    hs = pd.Series(np.linspace(100.0, 90.0, 45), index=cal)
    c500 = pd.Series(np.linspace(100.0, 90.0, 45), index=cal)
    cyb = pd.Series(np.linspace(100.0, 90.0, 45), index=cal)
    # Two-day bounce over MA20 near index 28-29, then break below pre-trigger 5d low at index 33
    hs.iloc[27:30] = [97.0, 98.5, 99.0]
    hs.iloc[33:] = 85.0
    c500.iloc[33:] = 85.0
    panels = SimpleNamespace(
        calendar=cal,
        index_close=pd.DataFrame({"000300.SH": hs, "000905.SH": c500, "399006.SZ": cyb}),
    )
    reg = pd.DataFrame(
        {
            "confirmed_regime": "DEFENSIVE",
            "pct_above_ma60": 0.10,
            "pct_above_ma20": 0.10,
            "amount_vs_ma20": 1.15,
            "crash_override": False,
        },
        index=cal,
    )
    eff_reg, eff_w, stats = compute_recovery_overlay_series(
        panels, reg, mode="m1_ma20", ice_th=0.15, recovery_weight=0.35
    )
    assert stats["recovery_entries"] >= 1
    assert stats["false_breakout_stops"] >= 1
    assert (eff_reg == "RECOVERY").any()
    assert float(eff_w.max()) == 0.35
    assert eff_reg.iloc[-1] == "DEFENSIVE"
