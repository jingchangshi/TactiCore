"""V3.4 阶段 2 PIT 财报与估值底座单元测试：零前视、TTM 公式、送转股除权、股息率与因果分位。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.ashare.pit_fundamental_builder import (
    QUARTERS_40,
    _build_cumulative_split_matrix,
    _build_pit_dividend_matrix,
    _build_pit_fundamental_matrices,
    causal_rolling_percentile,
    compute_pit_ttm_eps,
)


def test_quarters_40_exact_coverage() -> None:
    assert len(QUARTERS_40) == 40
    assert QUARTERS_40[0] == "2016-12-31"
    assert QUARTERS_40[-1] == "2026-09-30"


def test_ttm_eps_formula_and_fallback() -> None:
    # 完整 Q3 TTM = 2024Q3(1.5) + 2023FY(2.0) - 2023Q3(1.2) = 2.3
    reports = [
        {
            "end_date": "20230930",
            "ann_date": "20231028",
            "basic_eps": 1.2,
            "bps": 10.0,
            "parent_netprofit": 120.0,
        },
        {
            "end_date": "20231231",
            "ann_date": "20240320",
            "basic_eps": 2.0,
            "bps": 10.5,
            "parent_netprofit": 200.0,
        },
        {
            "end_date": "20240930",
            "ann_date": "20241029",
            "basic_eps": 1.5,
            "bps": 11.2,
            "parent_netprofit": 150.0,
        },
    ]
    eps_ttm, bps = compute_pit_ttm_eps(reports)
    assert np.isclose(eps_ttm, 2.3)
    assert np.isclose(bps, 11.2)

    # 缺上年同季 -> 回退上年年报
    reports_no_prev_q = [reports[1], reports[2]]
    eps_fb, bps_fb = compute_pit_ttm_eps(reports_no_prev_q)
    assert np.isclose(eps_fb, 2.0)
    assert np.isclose(bps_fb, 11.2)

    # 仅新股 2024Q2 -> 季报年化
    reports_new = [
        {
            "end_date": "20240630",
            "ann_date": "20240825",
            "basic_eps": 0.6,
            "bps": 8.0,
            "parent_netprofit": 60.0,
        }
    ]
    eps_ann, bps_ann = compute_pit_ttm_eps(reports_new)
    assert np.isclose(eps_ann, 1.2)
    assert np.isclose(bps_ann, 8.0)


def test_zero_lookahead_ann_date_and_split_adjustment() -> None:
    cal = ["20240425", "20240426", "20240606", "20240607", "20240829"]
    cal_ints = np.array([int(d) for d in cal], dtype=np.int64)
    all_codes = ["000001.SZ"]
    # 20240607 发生 10 转 4（1.4 倍送转）
    splits = {"000001.SZ": [(20240607, 1.4)]}
    cum_split = _build_cumulative_split_matrix(cal_ints, all_codes, splits)

    # 2023FY 与 2024Q1 均在 20240426 公告；2024Q2 在 20240829 公告
    fina_df = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "end_date": "20230331",
                "ann_date": "20230426",
                "basic_eps": 0.40,
                "bps": 9.0,
                "parent_netprofit": 40.0,
                "dt_netprofit_yoy": 5.0,
                "roe_dt": 3.0,
            },
            {
                "ts_code": "000001.SZ",
                "end_date": "20231231",
                "ann_date": "20240426",
                "basic_eps": 1.40,
                "bps": 10.0,
                "parent_netprofit": 140.0,
                "dt_netprofit_yoy": 10.0,
                "roe_dt": 12.0,
            },
            {
                "ts_code": "000001.SZ",
                "end_date": "20240331",
                "ann_date": "20240426",
                "basic_eps": 0.50,
                "bps": 10.5,
                "parent_netprofit": 50.0,
                "dt_netprofit_yoy": 15.0,
                "roe_dt": 4.0,
            },
            {
                "ts_code": "000001.SZ",
                "end_date": "20240630",
                "ann_date": "20240829",
                "basic_eps": 0.70,
                "bps": 8.0,
                "parent_netprofit": 98.0,
                "dt_netprofit_yoy": 12.0,
                "roe_dt": 6.0,
            },
        ]
    )

    eps_dir, eps_np, bps_mat, edi_mat = _build_pit_fundamental_matrices(
        fina_df, cal, cal_ints, all_codes, splits, cum_split
    )

    # 20240425: 2023FY/2024Q1 尚未公告 -> 只能见到 20230331 (严禁前视 20240426 财报)
    assert np.isclose(bps_mat[0, 0], 9.0)
    assert np.isnan(edi_mat[0, 0])  # 仅一期可见，不能计算改善

    # 20240426: 2024Q1 公告，尚未送转 -> EPS_TTM = 0.50 + 1.40 - 0.40 = 1.50, BPS = 10.5
    assert np.isclose(eps_dir[1, 0], 1.50)
    assert np.isclose(eps_np[1, 0], 1.50)
    assert np.isclose(bps_mat[1, 0], 10.5)
    assert edi_mat[1, 0] == 1.0  # 15.0 > 10.0

    # 20240606 (送转前一日): 仍未除权
    assert np.isclose(bps_mat[2, 0], 10.5)

    # 20240607 (送转除权日): 按 1.4 倍缩小每股口径
    assert np.isclose(eps_dir[3, 0], 1.50 / 1.4)
    assert np.isclose(eps_np[3, 0], 1.50 / 1.4)
    assert np.isclose(bps_mat[3, 0], 10.5 / 1.4)

    # 20240829 (送转后首份财报 2024Q2): latest_ed=20240630 已在送转后，不再重复除 1.4
    assert np.isclose(bps_mat[4, 0], 8.0)
    assert edi_mat[4, 0] == 0.0  # 12.0 < 15.0

    # 截断未来公告检验：删除 20240829 报告后，0..3 日数值逐位一致
    fina_trunc = fina_df[fina_df["ann_date"] <= "20240607"].copy()
    eps_dir_t, eps_np_t, bps_t, edi_t = _build_pit_fundamental_matrices(
        fina_trunc, cal, cal_ints, all_codes, splits, cum_split
    )
    np.testing.assert_allclose(eps_dir_t[:4], eps_dir[:4], equal_nan=True)
    np.testing.assert_allclose(eps_np_t[:4], eps_np[:4], equal_nan=True)
    np.testing.assert_allclose(bps_t[:4], bps_mat[:4], equal_nan=True)
    np.testing.assert_allclose(edi_t[:4], edi_mat[:4], equal_nan=True)


def test_pit_dividend_yield_window_and_split_dilution() -> None:
    cal = ["20240606", "20240607", "20250606", "20250607"]
    cal_ints = np.array([int(d) for d in cal], dtype=np.int64)
    all_codes = ["000001.SZ"]
    splits = {"000001.SZ": [(20240607, 1.4)]}
    # 20240607 当日除权除息: 派现 0.28 元/股（按送转前股本），送转后相当于 0.20 元/股
    divs = {"000001.SZ": [(20240607, 0.28)]}
    cum_split = _build_cumulative_split_matrix(cal_ints, all_codes, splits)
    close_mat = np.array([[14.0], [10.0], [10.0], [10.0]], dtype=np.float64)

    dv_mat = _build_pit_dividend_matrix(
        cal, cal_ints, all_codes, divs, splits, cum_split, close_mat
    )
    assert np.isnan(dv_mat[0, 0])  # ex_date > T 严禁前视
    assert np.isclose(dv_mat[1, 0], 0.20 / 10.0)  # ex_date == T 计入并按 1.4 稀释
    assert np.isclose(dv_mat[2, 0], 0.20 / 10.0)  # 第 364 天仍在滚动窗口内
    assert np.isnan(dv_mat[3, 0])  # 第 365 天 (T - 365d == ex_date) 滚出


def test_causal_rolling_percentile_prefix_invariance() -> None:
    rng = np.random.default_rng(42)
    full = rng.normal(loc=300.0, scale=80.0, size=200)
    full[15] = np.nan
    pct_full = causal_rolling_percentile(full, window=60, min_periods=20)
    for cut in (30, 80, 150):
        pct_prefix = causal_rolling_percentile(full[:cut], window=60, min_periods=20)
        np.testing.assert_allclose(pct_prefix, pct_full[:cut], equal_nan=True)
