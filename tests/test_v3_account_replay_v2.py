"""Synthetic-only tests for EXP-V3-05B (v3_account_replay_v2)."""

from types import SimpleNamespace as NS

import numpy as np

from research.batches.v3_account_replay_v2.policy import BUDGET, FOCUS, Plan, exit_reason, targets
from research.batches.v3_account_replay_v2.stock_signals import (
    MIN_CIRC_MV_WAN,
    lookup_exact_circ_mv,
)


def test_circ_mv_unit_is_wan_yuan_50_yi():
    assert MIN_CIRC_MV_WAN == 500_000.0
    table = {
        "600519.SH": (
            np.array([20261125, 20261126], dtype=np.int64),
            np.array([184_367_000.0, 183_637_000.0]),
        ),
        "000001.SZ": (np.array([20261125], dtype=np.int64), np.array([499_999.0])),
    }
    assert lookup_exact_circ_mv(table, "600519.SH", 20261126) >= MIN_CIRC_MV_WAN
    # Exact date lookup: no forward fill to 20261126 when missing
    assert lookup_exact_circ_mv(table, "000001.SZ", 20261126) is None
    assert lookup_exact_circ_mv(table, "000001.SZ", 20261125) < MIN_CIRC_MV_WAN


def test_v321_stock_exits_and_breakeven_arm():
    # Hard stop at -8% or structural stop
    armed, reason = exit_reason(9.2, 10.0, 9.5, 9.5, False, False, stock=True, structural_stop=9.3)
    assert not armed and reason == "STOCK_STOP"
    # +15% arms breakeven floor
    armed2, reason2 = exit_reason(
        11.6, 10.0, 10.5, 11.0, False, False, stock=True, structural_stop=9.2
    )
    assert armed2 and reason2 is None
    # Armed breakeven triggered at cost
    _, reason3 = exit_reason(9.99, 10.0, 10.5, 10.5, True, False, stock=True, structural_stop=9.2)
    assert reason3 == "STOCK_STOP"
    # Close < MA20 exits unconditionally for stocks
    _, reason4 = exit_reason(9.8, 10.0, 10.0, 9.7, False, False, stock=True, structural_stop=9.2)
    assert reason4 == "MA_EXIT"


def test_occupied_budget_respects_focus_plus_stock_room():
    f = {
        "518880.XSHG": NS(c=1.0, raw=1.0, ma20=1.0, ret20=0.02),
        "510300.XSHG": NS(c=1.0, raw=1.0, ma20=1.0, ret20=0.02),
        "510500.XSHG": NS(c=1.0, raw=1.0, ma20=1.0, ret20=0.02),
        "512480.XSHG": NS(c=1.0, raw=1.0, ma20=0.95, ret20=0.10),
    }
    w = targets("OFFENSIVE", "BALANCED", 0.36, f)
    assert sum(w.values()) <= BUDGET["OFFENSIVE"] - 0.36 + 1e-12
    assert FOCUS not in w and isinstance(Plan(), Plan)
