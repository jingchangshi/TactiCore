"""Synthetic tests for EXP-V3-06."""

from types import SimpleNamespace

import numpy as np
import pandas as pd

from research.ashare.experiments import exp_v3_01_regime_super_etf as e1
from research.batches.exp_v3_06_defensive_rotation.run import (
    build_defensive_weights,
    select_bond_reserve,
)


def test_select_bond_reserve_pit_fallback():
    cal = pd.bdate_range("2022-01-03", periods=30)
    cols = ["159649.SZ", "511260.SH", "511010.SH"]
    adj = pd.DataFrame(100.0, index=cal, columns=cols)
    adj.loc[:, "159649.SZ"] = np.nan
    mask = adj.notna()
    assert select_bond_reserve(cal[-1], mask, adj, tuple(cols)) == "511260.SH"
    # Once 159649 has >=20 valid obs, it is selected
    adj.iloc[:25, 0] = 100.0
    mask = adj.notna()
    assert select_bond_reserve(cal[24], mask, adj, tuple(cols)) == "159649.SZ"


def test_defensive_trend_filter_collapses_to_bond_reserve():
    cal = pd.bdate_range("2022-01-03", periods=80)
    cols = sorted(
        {
            *e1.DEFENSIVE_SUPER_ETFS,
            *e1.DEFENSIVE_FALLBACKS,
            *e1.VALUE_SUPER_ETFS,
            *e1.VALUE_FALLBACKS,
            *e1.GROWTH_SUPER_ETFS,
            *e1.GROWTH_FALLBACKS,
            "518880.SH",
            "511260.SH",
            "159649.SZ",
            "511010.SH",
        }
    )
    adj = pd.DataFrame(100.0, index=cal, columns=cols)
    # Downtrend in gold and dividend fallback
    adj["518880.SH"] = np.linspace(100.0, 70.0, len(cal))
    adj["512890.SH"] = np.linspace(100.0, 80.0, len(cal))
    adj["159549.SZ"] = np.nan
    adj["159207.SZ"] = np.nan
    mask = adj.notna()
    panels = SimpleNamespace(calendar=cal, etf_adj_close=adj, etf_tradability_mask=mask)
    reg = pd.DataFrame({"confirmed_regime": "DEFENSIVE", "style": "BALANCED"}, index=cal)
    w, _ = build_defensive_weights(
        panels, reg, reserve_mode="low_ticket", gold_weight=0.10, trend_ma_window=40, end=cal[-1]
    )
    # After 40d warmup + 1, downtrending dividend & gold both collapse into bond reserve
    last_valid = w.dropna(how="all").iloc[-1].fillna(0.0)
    assert last_valid.get("518880.SH", 0.0) == 0.0
    assert last_valid.get("159649.SZ", 0.0) + last_valid.get("511260.SH", 0.0) == 1.0
