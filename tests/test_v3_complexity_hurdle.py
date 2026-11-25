"""Synthetic-only contracts; never run a historical engine or touch production files."""

import hashlib
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from research.batches.v3_complexity_hurdle import run_v3_complexity_hurdle as h
from research.batches.v3_complexity_hurdle.native import audit_fills


@pytest.mark.parametrize("prior", [".md", ".json", ".attempt", None])
def test_single_attempt(tmp_path, prior):
    stem = tmp_path / "result"
    if prior:
        stem.with_suffix(prior).touch()
    else:
        h.reserve(stem)
    with pytest.raises(FileExistsError):
        h.reserve(stem)


@pytest.mark.parametrize("bad", ["snapshot", "version", "date", "sha", None])
def test_cache_guard(tmp_path, monkeypatch, bad):
    cal = pd.date_range("2020-01-01", periods=2)
    path = tmp_path / "original.csv"
    pd.DataFrame(
        dict(
            trade_date=["20200101", "20200102" if bad != "date" else "20200101"],
            snapshot_id=["s", "s" if bad != "snapshot" else "x"],
            cache_version=[
                h.data.REGIME_CACHE_VERSION,
                h.data.REGIME_CACHE_VERSION if bad != "version" else "x",
            ],
        )
    ).to_csv(path, index=False)
    blob = path.read_bytes()
    monkeypatch.setattr(h.data, "REGIME_CACHE_PATH", path)
    monkeypatch.setattr(h, "CACHE_HASH", hashlib.sha256(blob).hexdigest() if bad != "sha" else "x")
    calls = []

    def upstream(*args):
        assert h.data.REGIME_CACHE_PATH != path
        assert h.data.REGIME_CACHE_PATH.read_bytes() == blob
        calls.append(True)

    monkeypatch.setattr(h.data, "compute_v3_market_regime_series", upstream)
    args = SimpleNamespace(snapshot_id="s"), SimpleNamespace(calendar=cal, index_close=None), {}
    if bad:
        with pytest.raises(h.InvalidRun):
            h.guarded_regime(*args)
        assert not calls
    else:
        h.guarded_regime(*args)
        assert calls
    assert path.read_bytes() == blob


def test_four_sleeves_signals_and_code_switch(monkeypatch):
    cal = pd.bdate_range("2017-01-02", "2019-01-03")
    prices = pd.DataFrame(1.0, index=cal, columns=[*h.RISK, *h.PRIMARY])
    prices.loc[:"2018-01-05", list(h.PRIMARY)] = np.nan
    p = SimpleNamespace(calendar=cal, etf_adj_close=prices, etf_tradability_mask=prices.notna())
    w = h.four_sleeves(p, False).dropna(how="all")
    assert list(w.index) == [pd.Timestamp("2018-01-03"), pd.Timestamp("2019-01-01")]
    assert w.iloc[0][list(h.RISK)].eq(0.25).all()
    assert w.iloc[-1][list(h.PRIMARY)].eq(0.25).all() and w.iloc[-1][list(h.RISK[:2])].eq(0).all()
    dates = []

    def solver(hist):
        assert len(hist) == 60 and list(hist.columns) == list(h.RISK)
        dates.append(hist.index[-1])
        return pd.Series([0.1, 0.2, 0.3, 0.4], index=h.RISK)

    monkeypatch.setattr(h, "erc_weights", solver)
    c = h.four_sleeves(p, True).dropna(how="all")
    assert all(
        cal[cal.get_loc(sig) + 1] == execution
        for sig, execution in zip(dates, c.index, strict=True)
    )
    assert c.loc["2018-02-01", h.RISK[0]] == 0.1  # listed but fewer than 20 observed prices
    assert c.loc["2018-03-01", h.PRIMARY[0]] == 0.1 and c.loc["2018-03-01", h.RISK[0]] == 0


def test_fee_audit_partial_fill_and_super_relative_tolerance():
    fills = [
        dict(order_id=i, code=s, quantity=100, notional=1000, commission=c)
        for i, s, c in [(1, "N", 3), (1, "N", 2), (2, "S", 0.05)]
    ]
    result = audit_fills(fills, {"S"}, True)
    assert result["fees_pass"] and result["normal_orders"] == 1 and result["super_rate_fills"] == 1
    fills[2]["commission"] = 0.050001
    fills[1]["commission"] = 1.99
    assert audit_fills(fills, {"S"}, True)["bad_normal"] == [1]
    assert audit_fills(fills, {"S"}, True)["bad_super"] == [2]


def test_two_capitals_two_comparators_edge_and_veto():
    runs = {
        f"{arm}_{cash}": {"full": dict(sharpe=0.5, calmar=0.5, max_drawdown=-0.2)}
        for arm in "ABC"
        for cash in h.CASH
    }
    assert h.verdict(runs, {"a": True}) == h.OVERLAY
    for cash in h.CASH:
        runs[f"A_{cash}"]["full"].update(sharpe=0.6, calmar=0.6)
    assert h.verdict(runs, {"a": True}) == h.CLEAR
    runs["C_69000"]["full"]["sharpe"] = 0.51
    assert h.verdict(runs, {"a": True}) == "MIXED"
    assert h.verdict(runs, {"a": False}) == "INVALID_RUN"


def test_rolling_resets_peaks_in_each_window():
    equity = pd.Series([8.0, 4.0, 5.0, 4.0], index=pd.bdate_range("2018-01-02", periods=4))
    result = h.rolling(equity, 3)
    assert list(result.index) == list(equity.index[-2:])
    assert result.max_drawdown.tolist() == pytest.approx([-0.5, -0.2])
