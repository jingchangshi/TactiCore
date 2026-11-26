"""Synthetic tests for EXP-V3-09 drawdown controllers."""

import pytest

from research.batches.exp_v3_09_drawdown_control.run import DrawdownController


def test_c0_relocks_without_reanchor_whereas_c1_reanchors_while_tracking_true_dd():
    c0 = DrawdownController(init_nav=100.0, mode="c0_hard", cooldown_days=2, ramp_days=2)
    c1 = DrawdownController(init_nav=100.0, mode="c1_reanchor", cooldown_days=2, ramp_days=2)
    # Day 0: zero-DD under DEFENSIVE (0.15) must NOT impose forced ctrl_cap!
    d0 = DrawdownController(init_nav=100.0, mode="c0_hard").step(0, 100.0, True, 0.15)
    d1 = DrawdownController(init_nav=100.0, mode="c1_reanchor").step(0, 100.0, True, 0.15)
    assert d0["ctrl_cap"] is None and d1["ctrl_cap"] is None
    assert d0["buy_cap"] == pytest.approx(0.15)

    # Drop -13% under concentrated=True
    s0 = c0.step(0, 87.0, True, 0.85)
    s1 = c1.step(0, 87.0, True, 0.85)
    assert s0["trigger"] and s1["trigger"]
    assert s0["ctrl_cap"] == 0.0 and s1["ctrl_cap"] == 0.0
    assert c0.step(1, 87.0, True, 0.85)["locked"]
    assert c0.step(2, 87.0, True, 0.85)["locked"]
    assert c1.step(1, 87.0, True, 0.85)["locked"]
    assert c1.step(2, 87.0, True, 0.85)["locked"]

    # Day 3: unlock at nav=86 (-14% true DD)
    u0 = c0.step(3, 86.0, True, 0.85)
    u1 = c1.step(3, 86.0, True, 0.85)
    assert u0["trigger"] and u0["locked"]
    assert not u1["trigger"] and not u1["locked"]
    assert u1["ctrl_cap"] is None and u1["buy_cap"] < 0.85
    assert u1["true_dd"] == pytest.approx(0.14)
    assert u1["work_dd"] == pytest.approx(0.0)


def test_cppi_scales_exposure_linearly_with_cushion():
    c2 = DrawdownController(init_nav=100.0, mode="c2_cppi", floor_dd=0.15, cppi_m=5.0)
    # Day 0 at DD=0 -> m*cushion = 0.75 (> 0.70, no Day-1 HEAVY70 forced dump!)
    d0 = c2.step(0, 100.0, True, 0.15)
    assert d0["ctrl_cap"] == pytest.approx(0.75) and d0["buy_cap"] == pytest.approx(0.15)
    # At -5% DD -> cushion = 10/95 -> m*cushion
    st = c2.step(1, 95.0, False, 0.85)
    assert st["ctrl_cap"] == pytest.approx(5.0 * (95.0 - 85.0) / 95.0)
    assert st["buy_cap"] == pytest.approx(5.0 * (95.0 - 85.0) / 95.0)
