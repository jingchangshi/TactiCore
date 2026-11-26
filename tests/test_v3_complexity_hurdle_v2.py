"""Synthetic-only tests for V3_COMPLEXITY_HURDLE_V2."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from research.batches.v3_complexity_hurdle_v2 import run as h2
from research.batches.v3_complexity_hurdle_v2.native import audit_fills


@pytest.mark.parametrize("prior", [".md", ".json", ".attempt", None])
def test_single_attempt_v2(tmp_path, prior):
    stem = tmp_path / "result"
    if prior:
        stem.with_suffix(prior).touch()
    else:
        h2.reserve(stem)
    with pytest.raises(FileExistsError):
        h2.reserve(stem)


def test_audit_fills_allows_full_close_corp_action_odd_lot_only():
    fills = [
        {
            "order_id": 1,
            "date": "2022-09-06",
            "code": "510500.XSHG",
            "side": "SELL",
            "quantity": 2863,
            "notional": 17984.63,
            "commission": 5.0,
            "full_liquidation": True,
        },
        {
            "order_id": 2,
            "date": "2022-09-07",
            "code": "159330.XSHE",
            "side": "BUY",
            "quantity": 1000,
            "notional": 1000.0,
            "commission": 0.05,
            "full_liquidation": False,
        },
    ]
    res = audit_fills(fills, {"159330.XSHE"}, True)
    assert res["fees_pass"]
    assert len(res["corporate_action_full_close_odd_lots"]) == 1
    assert res["illegal_non_lot_fills"] == []

    # Partial sell or buy odd lot remains strictly illegal
    bad = [
        dict(fills[0], order_id=3, full_liquidation=False),
        dict(fills[1], order_id=4, quantity=150, commission=0.0075),
    ]
    res_bad = audit_fills(bad, {"159330.XSHE"}, True)
    assert len(res_bad["illegal_non_lot_fills"]) == 2


def test_four_sleeves_v2_signals():
    cal = pd.bdate_range("2017-01-02", "2019-01-03")
    cols = list(dict.fromkeys([*h2.RISK, *h2.PRIMARY]))
    prices = pd.DataFrame(1.0, index=cal, columns=cols)
    prices.loc[:"2018-01-05", [c for c in h2.PRIMARY if c not in h2.RISK]] = np.nan
    p = SimpleNamespace(calendar=cal, etf_adj_close=prices, etf_tradability_mask=prices.notna())
    w = h2.four_sleeves(
        p, False, start=pd.Timestamp("2018-01-02"), end=pd.Timestamp("2019-01-03")
    ).dropna(how="all")
    assert list(w.index) == [pd.Timestamp("2018-01-03"), pd.Timestamp("2019-01-01")]
    assert w.iloc[0][list(h2.RISK)].eq(0.25).all()
    assert w.iloc[-1][list(h2.PRIMARY)].eq(0.25).all()
