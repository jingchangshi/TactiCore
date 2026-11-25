"""Development tests only: synthetic inputs; no historical data/engine runs."""

from types import SimpleNamespace as NS

import pytest
from rqalpha.const import INSTRUMENT_TYPE, SIDE

from research.batches.v3_account_replay.native import TieredFees, opening_block
from research.batches.v3_account_replay.policy import GOLD, Plan, Risk, exit_reason, targets
from research.batches.v3_account_replay.run import PREFIX, claim, compare


def bar(**values):
    base = dict(
        c=0.9,
        prev=0.89,
        raw=0.9,
        prev_raw=0.89,
        ma5=0.90,
        ma20=0.95,
        ma60=0.96,
        slope=0.0,
        peak60=1.10,
        min_rsi=36,
        min_bias=-0.06,
        rsi=45,
        ret20=0.0,
    )
    return NS(**(base | values))


@pytest.mark.parametrize(
    "change", [dict(slope=-0.001), dict(peak60=0.95), dict(min_rsi=37), dict(prev=0.91)]
)
def test_four_gates_individually_binding(change):
    p = Plan()
    assert p.decision(bar(), 10, 0.25, "STRUCTURAL", False, 0.10)[0] == "SLOT"
    assert p.decision(bar(**change), 10, 0.25, "STRUCTURAL", False, 0.10) is None


def test_discount_either_path_and_no_expired_sale():
    p = Plan(last_sale=1.0, sale_day=0)
    assert all(p.gates(bar(peak60=0.95), 90))
    assert not all(p.gates(bar(peak60=0.95), 91))
    assert all(p.gates(bar(), 91))
    assert p.decision(bar(), 10, 0.25, "OFFENSIVE", True, 0.2) is None
    assert p.decision(bar(), 10, 0.25, "OFFENSIVE", False, 0) is None


def test_tranche_state_requires_fill_and_consumes_partial():
    p = Plan()
    p.seed(7000, 25, 1.0, 0)
    assert p.batches == [1200, 1100, 1100, 1100]
    assert p.decision(bar(raw=0.77, prev_raw=0.79), 5, 0.7, "STRUCTURAL", False, 0) is None
    assert p.decision(bar(raw=0.77, prev_raw=0.77), 5, 0.7, "STRUCTURAL", False, 0)[:2] == (
        "SUPPORT",
        -2300,
    )
    assert p.decision(bar(raw=1.081), 5, 0.7, "OFFENSIVE", False, 0)[:2] == ("REBOUND", -1200)
    assert p.batches[0] == 1200
    p.sell(1100, 1.09, 6)
    assert p.batches[0] == 100
    p.sell(5900, 1.0, 7)
    assert not any(p.batches)


def test_slot_exit_and_no_noise_stop():
    p = Plan(slot=200, slot_px=1.0)
    assert p.decision(bar(raw=0.90), 10, 0.28, "STRUCTURAL", False, 0.10) is None
    assert p.decision(bar(raw=1.08, c=1.08, ma60=1.10), 10, 0.28, "STRUCTURAL", False, 0.1)[:2] == (
        "TAKE",
        -200,
    )


def test_dynamic_redline_cooldown_counterfactual():
    r = Risk(100.0)
    assert not r.observe(0, 90, True, True)["locked"]
    assert r.observe(1, 88, True, True)["cap"] == 0
    assert r.observe(16, 94, False, True)["locked"]
    assert not r.observe(17, 94, False, True)["locked"]
    assert r.observe(18, 85, False, True)["cap"] == 0.15
    r = Risk(100.0)
    row = r.observe(1, 83, False, False)
    assert row["shadow_hit"] and not row["locked"] and row["breach"] == pytest.approx(0.02)


def test_stock_stop_hard_ma20_and_armed_etf():
    assert exit_reason(9.2, 10, 9, 9, False, False, True)[1] == "STOCK_STOP"
    assert exit_reason(9.9, 10, 10, 9, False, False, True)[1] == "MA_EXIT"
    assert exit_reason(9.9, 10, 10, 9, False, False, False)[1] is None
    assert exit_reason(10, 10, 9, 9, True, False, True)[1] == "STOCK_STOP"


def test_same_cash_priority_missing_fallback():
    f = {GOLD: bar(), "510300.XSHG": bar(), "512480.XSHG": bar(c=1.0, ret20=0.1)}
    assert targets("DEFENSIVE", "BALANCED", 0.70, f) == {}
    assert targets("OFFENSIVE", "BALANCED", 0.70, f).get("512480.XSHG") is None
    assert targets("OFFENSIVE", "BALANCED", 0, f)["512480.XSHG"] == 0.20
    assert targets("DEFENSIVE", "BALANCED", 0, f) == {GOLD: 0.10}
    assert targets("OFFENSIVE", "BALANCED", 0, {}) == {}


def test_next_open_limits_and_missing():
    assert opening_block(11.0, 11.0, True, False) == "LIMIT_UP"
    assert opening_block(9.0, 9.0, False, False) == "LIMIT_DOWN"
    assert opening_block(float("nan"), 11.0, True, False) == "SUSPENDED_OR_MISSING_OPEN"
    assert opening_block(10.0, 11.0, True, False) is None


@pytest.mark.parametrize(
    ("sym", "typ", "side", "commission", "tax", "other"),
    [
        ("white", INSTRUMENT_TYPE.ETF, SIDE.BUY, 0.40, 0, 0),
        ("normal", INSTRUMENT_TYPE.ETF, SIDE.SELL, 5, 0, 0),
        ("stock", INSTRUMENT_TYPE.CS, SIDE.SELL, 5, 4, 0.08),
        ("stock", INSTRUMENT_TYPE.CS, SIDE.BUY, 5, 0, 0.08),
    ],
)
def test_actual_native_fee_decider(monkeypatch, sym, typ, side, commission, tax, other):
    from rqalpha.environment import Environment

    env = NS(event_bus=None)
    monkeypatch.setattr(Environment, "get_instance", classmethod(lambda cls: env))
    fees = TieredFees(env, {"white"})
    a = NS(
        instrument=NS(order_book_id=sym, type=typ), price=8.0, quantity=1000, side=side, order_id=1
    )
    assert tuple(fees.calc(a)) == pytest.approx((commission, tax, other))


def test_claim_fails_closed_on_partial_or_claim(tmp_path):
    p = claim(tmp_path)
    with pytest.raises(FileExistsError):
        claim(tmp_path)
    p.unlink()
    (tmp_path / (PREFIX + "_only_one_cell.json.gz")).touch()
    with pytest.raises(FileExistsError):
        claim(tmp_path)


def test_lock_cost_direction_and_identification():
    def rows(n1, n2, lock):
        return [
            dict(nav=n1, dd=0.12, locked=lock, trigger=lock),
            dict(nav=n2, dd=0.18, locked=lock, trigger=False),
        ]

    assert compare(rows(88, 88, True), rows(88, 95, False), 100)["locked_sessions_pnl_gap"] == 7
    assert compare(rows(88, 88, False), rows(88, 88, False), 100)["final_gap_yuan"] is None
