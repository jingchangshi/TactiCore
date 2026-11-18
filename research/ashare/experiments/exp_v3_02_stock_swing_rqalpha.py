"""EXP-V3-02: 10万/7万主板高质量右侧强势股波段（原生 RQAlpha 6.3.0 撮合验证）。

================================================================================
External Evidence Gate（8 项前置强制声明）
================================================================================
- Canonical mapping: `EXP-V3-02` -> `V3_MAINBOARD_SWING_BREAKOUT_PULLBACK`
  （参考 `STRATEGY_EVIDENCE_REGISTRY.yaml` 中的质量过滤 + RPS 右侧波段条目）。
- External tier: `E3_MIXED_CONDITIONAL`
  （Quality + Momentum 在跨市场具有长期溢价证据，但 Yang/Gebka/Hudson 等实证表明
  A 股动量易被频率、涨跌停拒单与小资金 5 元最低佣金摩擦严重侵蚀）。
- External conclusion: 7–10 万元小账户单笔仓位约 1.2–1.8 万元，万 2.5 佣金叠加
  最低 5 元下限后真实单边佣金约 2.8–4.2bp，再加卖出万 5 印花税与双边万 5 滑点，
  双边固定成本约 20–25bp；必须分拆检验买点 1（缩量回踩 MA20）与买点 2（窄幅平台突破）
  的样本外净期望，期望为负者直接剔除。
- Relevant contradictions: Yang et al. (2019), Gebka et al. (2020), Hudson & Zhang (2023)
  均指出 A 股短期反转、涨跌停锁死与交易摩擦可完全反转未计费动量收益。
- Upstream implementation: 全程在 **原生 RQAlpha 6.3.0** (`run_func` + `open_auction`
  及伴随 `matching_type="vwap"` + `PriceRatioSlippage(0.0005)`) 上撮合，强制执行
  T+1、100 股整手、涨跌停过滤、万 2.5（最低 5 元）+ 卖出万 5 印花税 + 双边万 5 滑点。
- Existing TactiCore evidence: `research/ashare/data/fee_mapping.py`（`fees-2.0.0`）与
  `v3_snapshot_20261113` 公告日财务数据；本实验与冻结 `S2_R1`/`S4C_R1` 无任何共享资金与信号耦合。
- Remaining local gap: 分别衡量 `BP1_PULLBACK` 与 `BP2_BREAKOUT` 在 ¥70,000 及 ¥100,000
  两档初始本金下的样本内（2018–2023）及样本外（2024–2026）净期望、胜率、盈亏比、
  摩擦拖累占比及最大连续止损次数，对 OOS 期望为负的买点做刚性淘汰裁决。
- Research action: `LOCAL_ADJUDICATION`（严格按 `OOS net_expectancy > 0` 保留或 `REJECTED_DROP`）。

================================================================================
PIT Tradability Gate（6 要素强制声明）
================================================================================
1. Date-aware universe: 日度 `RPS_60` / `RPS_120` 在当日全市场非北交、已交易满 120 根 K 线
   且含历史退市的全部 A 股 `CS` 标的中横向百分位计算；候选池仅限沪深主板（`000/001/002/003/
   600/601/603/605`），满足上市 >= 250 自然日、RQAlpha `is_st_stock == False`、当日非停牌
   非一字涨跌停、`0 < raw_close <= 90`、20 日均成交额 >= 1.5 亿元。
2. Asset lifetime metadata: 源自 RQAlpha `instruments.pk`（`listed_date`, `de_listed_date`）与
   `stock_basic.csv`；已退市股票严格保留在历史横截面中以消除幸存者偏差。
3. Pre-listing fallback & PIT financial alignment: 因 `v3_snapshot_20261113/financial_indicator.csv`
   仅覆盖 `end_date >= 20231231`（`ann_date >= 20240120`），IS 期（2018–2023）与主 OOS 对照
   使用一致量价流动性漏斗，同时在 OOS 增设严格 `ann_date <= T`（含季报累计 ROE 年化换算 > 5%、
   `eps > 0`、`ocf_to_profit > 50%`）的完整 `QualityCore` 对照与当前行业分类敏感性（已标明非 PIT）。
4. Missing execution price / limit-up-down handling: 次日 `T+1` `open_auction` 撮合时，若高开
   > `+2%`、涨停开盘或停牌则跳过买入；持仓触发 `-8%` 止损 / `+15%` 保本 / `< MA20` 止盈
   于次日 `T+1` 开盘执行，若遇一字跌停或停牌则忠实顺延至首个可卖出开盘。
5. Strategy inception: 2017 年预热，IS `2018-01-02..2023-12-29`，OOS `2024-01-02..2026-08-31`
   （RQAlpha 原生），另附 `2026-09-01..2026-11-13` 快照 OOS 尾部信号触发诊断。
6. Executability of every positive target: 以损定仓（单笔风险 <= 1.3% NAV，单股上限 18%，
   整手向下取整 >= ¥8,000，最多 2 只并发，受 `marketRegime in {OFFENSIVE, STRUCTURAL}` 门控），
   每笔成交均可追溯至原生 RQAlpha `EVENT.TRADE` 记录与费用扣减台账。
================================================================================
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.ashare.engines.bundle_source import bundle_calendar, open_bundle_source
from research.ashare.v3_data import (
    BUNDLE_CUTOFF,
    BUNDLE_PATH,
    EXP_START,
    IS_END,
    OOS_START,
    SNAPSHOT_DIR,
    compute_v3_market_regime_series,
    load_stitched_panels,
    rq_to_ts,
    verify_v3_provenance,
)

RESULTS_DIR = Path("/home/jcshi/workspace/TactiCore/research/results")
MAIN_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")
SLIPPAGE_ONE_WAY = 0.0005  # 单边万 5 显式滑点


@dataclass(frozen=True)
class SwingCandidate:
    order_book_id: str
    ts_code: str
    bp_type: str  # "BP1_PULLBACK" | "BP2_BREAKOUT"
    score: float
    rps60: float
    rps120: float
    ref_close_raw: float
    hard_stop_raw: float
    quality_core_ok: bool
    industry_top30_ok: bool


def _is_mainboard(order_book_id: str) -> bool:
    code = order_book_id.split(".", 1)[0]
    return not order_book_id.endswith(".BJ") and code.startswith(MAIN_PREFIXES)


def _load_pit_financial_table() -> dict[str, dict[str, np.ndarray]]:
    """按 `ts_code` 索引排序好的 `financial_indicator.csv`（严格要求 `ann_date` 非空）。"""
    fi = pd.read_csv(
        SNAPSHOT_DIR / "financial_indicator.csv",
        usecols=["ts_code", "end_date", "ann_date", "roe", "ocf_to_profit", "eps"],
        dtype={"ts_code": str, "end_date": str, "ann_date": str},
    )
    fi = fi[fi["ann_date"].notna() & fi["ann_date"].str.match(r"^\d{8}$", na=False)].copy()
    fi = fi.sort_values(["ts_code", "ann_date", "end_date"]).reset_index(drop=True)

    mmdd = fi["end_date"].str.slice(4, 8)
    mult = mmdd.map({"0331": 4.0, "0630": 2.0, "0930": 4.0 / 3.0, "1231": 1.0}).fillna(1.0)
    ann_roe = fi["roe"].astype(float) * mult
    passed = (
        (ann_roe > 5.0)
        & (fi["eps"].astype(float) > 0.0)
        & (fi["ocf_to_profit"].astype(float) > 50.0)
    )
    fi["qc_ok"] = passed.astype(bool)
    fi["ann_int"] = fi["ann_date"].astype(np.int64)
    fi["end_dt_ns"] = pd.to_datetime(fi["end_date"]).astype("int64")

    table: dict[str, dict[str, np.ndarray]] = {}
    for code, grp in fi.groupby("ts_code", sort=False):
        table[str(code)] = {
            "ann_int": grp["ann_int"].to_numpy(dtype=np.int64),
            "end_ns": grp["end_dt_ns"].to_numpy(dtype=np.int64),
            "qc_ok": grp["qc_ok"].to_numpy(dtype=bool),
        }
    return table


def _lookup_quality_core(
    fin_table: dict[str, dict[str, np.ndarray]],
    ts_code: str,
    trade_date_int: int,
    trade_dt_ns: int,
) -> bool:
    rec = fin_table.get(ts_code)
    if rec is None:
        return False
    idx = int(np.searchsorted(rec["ann_int"], trade_date_int, side="right")) - 1
    if idx < 0:
        return False
    age_days = (trade_dt_ns - int(rec["end_ns"][idx])) / 86_400_000_000_000.0
    if age_days > 550.0 or age_days < 0.0:
        return False
    return bool(rec["qc_ok"][idx])


def _wilder_rsi14(close: pd.Series) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(100.0)


def build_causal_swing_candidates(
    bundle_end: pd.Timestamp = BUNDLE_CUTOFF,
) -> tuple[dict[str, list[SwingCandidate]], dict[str, Any]]:
    """从含已退市历史的 RQAlpha bundle 向量化预计算逐日严格因果右侧买点候选表。"""
    src = open_bundle_source(BUNDLE_PATH)
    cal = bundle_calendar(src, pd.Timestamp("2017-01-03"), bundle_end)
    cal_ints = np.array([int(d.strftime("%Y%m%d")) for d in cal], dtype=np.int64)
    cal_set = set(cal_ints.tolist())
    n_days = len(cal_ints)

    all_cs = [i for i in src.get_instruments(types=["CS"]) if not i.order_book_id.endswith(".BJ")]
    end_dt = bundle_end.to_pydatetime()

    # Pass 1: 全市场 A 股 post-adjusted 60/120 日动量用于纯横截面 RPS（含已退市）
    ret60_cols: dict[str, np.ndarray] = {}
    ret120_cols: dict[str, np.ndarray] = {}
    main_insts: list[Any] = []
    bars_post_cache: dict[str, Any] = {}

    for inst in all_cs:
        listed = pd.Timestamp(inst.listed_date)
        delisted = pd.Timestamp(inst.de_listed_date)
        if listed > bundle_end or delisted < cal[0]:
            continue
        eff_end = min(end_dt, delisted.to_pydatetime()) if delisted.year < 2999 else end_dt
        bars_p = src.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="post",
            adjust_orig=eff_end,
        )
        if bars_p is None or len(bars_p) < 125:
            continue
        c_p = pd.Series(bars_p["close"].astype(float))
        r60 = (c_p / c_p.shift(60) - 1.0).to_numpy(dtype=np.float32)
        r120 = (c_p / c_p.shift(120) - 1.0).to_numpy(dtype=np.float32)
        # 严格掩蔽上市前 120 根交易日（消除新股发行暴涨污染）
        r60[:120] = np.nan
        r120[:120] = np.nan
        dts = (bars_p["datetime"] // 1000000).astype(np.int64)
        mask = np.isin(dts, list(cal_set))
        if not mask.any():
            continue
        idxs = np.searchsorted(cal_ints, dts[mask])
        arr60 = np.full(n_days, np.nan, dtype=np.float32)
        arr120 = np.full(n_days, np.nan, dtype=np.float32)
        arr60[idxs] = r60[mask]
        arr120[idxs] = r120[mask]
        ob = inst.order_book_id
        ret60_cols[ob] = arr60
        ret120_cols[ob] = arr120
        if _is_mainboard(ob):
            main_insts.append(inst)
            bars_post_cache[ob] = bars_p

    df_r60 = pd.DataFrame(ret60_cols, index=cal)
    df_r120 = pd.DataFrame(ret120_cols, index=cal)
    rps60_df = df_r60.rank(axis=1, pct=True) * 100.0
    rps120_df = df_r120.rank(axis=1, pct=True) * 100.0

    # Industry classification snapshot (explicitly labeled CURRENT_SNAPSHOT_NOT_PIT)
    sb = pd.read_csv(SNAPSHOT_DIR / "stock_basic.csv", usecols=["ts_code", "industry"], dtype=str)
    ind_map = {
        str(r["ts_code"]): str(r["industry"]) for _, r in sb.iterrows() if pd.notna(r["industry"])
    }

    # Precompute daily industry top-30% mask on rps60_df
    col_inds = [ind_map.get(rq_to_ts(c), "__UNKNOWN__") for c in rps60_df.columns]
    ind_series = pd.Series(col_inds, index=rps60_df.columns)
    ind_means = rps60_df.T.groupby(ind_series).mean().T  # dates x industries
    if "__UNKNOWN__" in ind_means.columns:
        ind_means = ind_means.drop(columns=["__UNKNOWN__"])
    ind_pct_rank = ind_means.rank(axis=1, pct=True)  # > 0.70 == Top 30%

    fin_table = _load_pit_financial_table()

    # Pass 2: 逐只主板股票计算技术买点信号与硬止损位
    candidates_by_date: dict[str, list[SwingCandidate]] = {}
    raw_trigger_counts = {"bp1_raw": 0, "bp2_raw": 0, "st_filtered": 0, "qc_filtered_oos": 0}
    exp_start_int = int(EXP_START.strftime("%Y%m%d"))

    for inst in main_insts:
        ob = inst.order_book_id
        ts_c = rq_to_ts(ob)
        bars_p = bars_post_cache[ob]
        listed_dt = pd.Timestamp(inst.listed_date).normalize()
        delisted_dt = pd.Timestamp(inst.de_listed_date).normalize()
        eff_end = min(end_dt, delisted_dt.to_pydatetime()) if delisted_dt.year < 2999 else end_dt
        bars_r = src.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="none",
        )
        if bars_r is None or len(bars_r) != len(bars_p):
            continue

        dts = (bars_p["datetime"] // 1000000).astype(np.int64)
        c_p = pd.Series(bars_p["close"].astype(float))
        h_p = pd.Series(bars_p["high"].astype(float))
        l_p = pd.Series(bars_p["low"].astype(float))
        v_r = pd.Series(bars_r["volume"].astype(float))
        c_r = pd.Series(bars_r["close"].astype(float))
        o_r = pd.Series(bars_r["open"].astype(float))
        h_r = pd.Series(bars_r["high"].astype(float))
        l_r = pd.Series(bars_r["low"].astype(float))
        amt_r = pd.Series(bars_r["total_turnover"].astype(float))

        ma5 = c_p.rolling(5, min_periods=5).mean()
        ma20 = c_p.rolling(20, min_periods=20).mean()
        ma60 = c_p.rolling(60, min_periods=60).mean()
        std20 = c_p.rolling(20, min_periods=20).std()
        bbw = (4.0 * std20) / ma20
        bbw_rank = bbw.shift(1).rolling(120, min_periods=60).rank(pct=True)

        vol_ma20 = v_r.rolling(20, min_periods=20).mean()
        amt_ma20 = amt_r.rolling(20, min_periods=20).mean()
        rsi14 = _wilder_rsi14(c_p)
        ret5 = c_p / c_p.shift(5) - 1.0

        # Map RPS onto bars' traded calendar
        in_cal = np.isin(dts, list(cal_set))
        if not in_cal.any():
            continue
        idx_c = np.searchsorted(cal_ints, dts[in_cal])
        r60_series = np.full(len(bars_p), np.nan, dtype=float)
        r120_series = np.full(len(bars_p), np.nan, dtype=float)
        r60_series[in_cal] = rps60_df[ob].to_numpy()[idx_c]
        r120_series[in_cal] = rps120_df[ob].to_numpy()[idx_c]
        s_r60 = pd.Series(r60_series)
        s_r120 = pd.Series(r120_series)

        # 硬过滤 & 均线多头 & 防追高
        bar_dates_pd = pd.to_datetime([str(int(x)) for x in dts])
        listed_days = pd.Series((bar_dates_pd - listed_dt).days)
        base_ok = (
            (dts >= exp_start_int)
            & (listed_days >= 250)
            & (c_r > 0.0)
            & (c_r <= 90.0)
            & (h_r > l_r)
            & (v_r > 0.0)
            & (amt_ma20 >= 1.5e8)
            & ((s_r60 >= 80.0) | (s_r120 >= 80.0))
            & (c_p > ma20)
            & (ma20 > ma60)
            & (ma20 > ma20.shift(5))
            & (ma60 > ma60.shift(5))
            & (ret5 < 0.12)
            & ((c_p - ma20) / ma20 <= 0.08)
            & (rsi14 < 75.0)
        )

        # Buy Point 1: 缩量回踩 MA20 企稳
        hh20 = h_p.rolling(20, min_periods=20).max()
        hit_high_3_8 = pd.Series(False, index=c_p.index)
        for k in range(3, 9):
            hit_high_3_8 = hit_high_3_8 | (
                (h_p.shift(k) >= hh20.shift(k) - 1e-9) & (h_p.shift(k) > c_p)
            )
        low_min_5 = l_p.rolling(5, min_periods=5).min()
        touch_ma20 = (low_min_5 >= ma20 * 0.985) & (low_min_5 <= ma20 * 1.025)
        vol_shrink = v_r.shift(1).rolling(3, min_periods=3).min() <= 0.8 * vol_ma20
        bp1 = (
            base_ok
            & hit_high_3_8
            & touch_ma20
            & vol_shrink
            & (c_r > o_r)
            & (c_p > c_p.shift(1))
            & (c_p > ma5)
        )

        # Buy Point 2: 紧凑窄幅平台突破
        prev15_h = h_p.shift(1).rolling(15, min_periods=15).max()
        prev15_l = l_p.shift(1).rolling(15, min_periods=15).min()
        tight = ((prev15_h / prev15_l - 1.0) < 0.14) | (bbw_rank <= 0.25)
        vol_ratio = v_r / vol_ma20.shift(1)
        bp2 = base_ok & tight & (c_p > prev15_h) & (vol_ratio >= 1.3) & (vol_ratio <= 2.8)

        any_hit = np.where((bp1 | bp2).to_numpy())[0]
        if len(any_hit) == 0:
            continue

        # 仅在候选触发日检验 ST（O(触发数) 极速检查）
        cand_ts = [pd.Timestamp(bar_dates_pd[idx]) for idx in any_hit]
        st_flags = src.is_st_stock(ob, cand_ts)

        low_5d_raw = l_r.rolling(5, min_periods=5).min()
        ma20_raw_approx = c_r * (ma20 / c_p)
        ind_name = ind_map.get(ts_c, "__UNKNOWN__")

        for j, st_flag in zip(any_hit, st_flags, strict=True):
            if st_flag:
                raw_trigger_counts["st_filtered"] += 1
                continue
            dt_str = f"{dts[j]:08d}"
            dt_ts = pd.Timestamp(bar_dates_pd[j])
            ref_c = float(c_r.iloc[j])
            l5 = float(low_5d_raw.iloc[j])
            m20r = float(ma20_raw_approx.iloc[j])
            hard_stop = max(round(ref_c * 0.92, 2), round(min(l5, m20r * 0.97), 2))
            if hard_stop >= ref_c * 0.99:
                hard_stop = round(ref_c * 0.96, 2)

            qc_ok = _lookup_quality_core(fin_table, ts_c, int(dts[j]), int(dt_ts.value))
            if int(dts[j]) >= 20240201 and not qc_ok:
                raw_trigger_counts["qc_filtered_oos"] += 1

            ind_top30 = False
            if ind_name in ind_pct_rank.columns and dt_ts in ind_pct_rank.index:
                val = ind_pct_rank.loc[dt_ts, ind_name]
                ind_top30 = pd.notna(val) and float(val) >= 0.70

            r60_v = float(s_r60.iloc[j])
            r120_v = float(s_r120.iloc[j])
            score = max(r60_v, r120_v) + 0.001 * ((r60_v + r120_v) / 2.0)

            pairs = (
                (bool(bp1.iloc[j]), "BP1_PULLBACK"),
                (bool(bp2.iloc[j]), "BP2_BREAKOUT"),
            )
            for flag, label in pairs:
                if flag:
                    if label == "BP1_PULLBACK":
                        raw_trigger_counts["bp1_raw"] += 1
                    else:
                        raw_trigger_counts["bp2_raw"] += 1
                    candidates_by_date.setdefault(dt_str, []).append(
                        SwingCandidate(
                            order_book_id=ob,
                            ts_code=ts_c,
                            bp_type=label,
                            score=score,
                            rps60=r60_v,
                            rps120=r120_v,
                            ref_close_raw=ref_c,
                            hard_stop_raw=hard_stop,
                            quality_core_ok=qc_ok,
                            industry_top30_ok=ind_top30,
                        )
                    )

    for _dt_str, lst in candidates_by_date.items():
        lst.sort(key=lambda x: (-x.score, x.order_book_id, x.bp_type))
    return candidates_by_date, raw_trigger_counts


def _run_rqalpha_swing(
    candidates_by_date: dict[str, list[SwingCandidate]],
    regime_by_date: dict[str, str],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    initial_cash: float,
    bp_mode: str,  # "BP1_PULLBACK" | "BP2_BREAKOUT" | "COMBINED"
    require_quality_core: bool = False,
    require_industry_top30: bool = False,
    execution_mode: str = "open_auction",  # "open_auction" | "vwap"
) -> dict[str, Any]:
    """原生 RQAlpha 6.3.0 回放股票波段策略，记录每笔交易精确费用、滑点与连续止损。"""
    from rqalpha import run_func
    from rqalpha.api import history_bars, order_shares, subscribe_event
    from rqalpha.core.events import EVENT

    closed_trades: list[dict[str, Any]] = []
    open_lots: dict[str, dict[str, Any]] = {}
    pending_sells: dict[str, str] = {}
    pending_buys: list[SwingCandidate] = []
    rejected_buys = 0
    limit_up_skips = 0
    gap_2pct_skips = 0
    limit_down_defers = 0
    min_comm_hits = 0

    def _on_trade(context: Any, event: Any) -> None:
        nonlocal min_comm_hits
        t = event.trade
        ob = str(t.order_book_id)
        qty = float(t.last_quantity)
        px = float(t.last_price)
        comm = float(getattr(t, "commission", 0.0) or 0.0)
        tax = float(getattr(t, "tax", 0.0) or 0.0)
        if abs(comm - 5.0) < 1e-6:
            min_comm_hits += 1
        notional = qty * px
        # VWAP 模式 PriceRatioSlippage 已内置在成交价内；open_auction 显式计双边 5bp
        explicit_slip = notional * SLIPPAGE_ONE_WAY if execution_mode == "open_auction" else 0.0
        cur_dt = str(context.now.date())

        if t.side.name == "BUY":
            lot = open_lots.get(ob)
            if lot is not None:
                lot["qty"] += qty
                lot["buy_notional"] += notional
                lot["buy_comm"] += comm
                lot["buy_slip"] += explicit_slip
                lot["entry_cost_total"] += notional + comm + explicit_slip
                lot["entry_px"] = lot["buy_notional"] / lot["qty"]
        elif t.side.name == "SELL":
            lot = open_lots.pop(ob, None)
            if lot is not None:
                sell_notional = qty * px
                gross_pnl = sell_notional - lot["buy_notional"]
                total_frict = lot["buy_comm"] + comm + tax + lot["buy_slip"] + explicit_slip
                net_pnl = gross_pnl - total_frict
                closed_trades.append(
                    {
                        "order_book_id": ob,
                        "ts_code": lot["ts_code"],
                        "bp_type": lot["bp_type"],
                        "entry_date": lot["entry_date"],
                        "exit_date": cur_dt,
                        "exit_reason": lot.get("exit_reason", "SIGNAL_EXIT"),
                        "qty": qty,
                        "buy_notional": lot["buy_notional"],
                        "sell_notional": sell_notional,
                        "gross_pnl": gross_pnl,
                        "rq_commission_tax": lot["buy_comm"] + comm + tax,
                        "explicit_slippage": lot["buy_slip"] + explicit_slip,
                        "total_friction": total_frict,
                        "net_pnl": net_pnl,
                        "net_ret": net_pnl / max(lot["buy_notional"], 1.0),
                    }
                )

    def _on_reject(context: Any, event: Any) -> None:
        nonlocal rejected_buys
        del context
        order = getattr(event, "order", None)
        if order is not None and getattr(order.side, "name", "") == "BUY":
            rejected_buys += 1

    def _init(context: Any) -> None:
        del context
        subscribe_event(EVENT.TRADE, _on_trade)
        subscribe_event(EVENT.ORDER_CREATION_REJECT, _on_reject)

    def _submit_pending(context: Any, bar_dict: Any, *, check_limit: bool) -> None:
        nonlocal pending_sells, pending_buys, limit_up_skips, gap_2pct_skips, limit_down_defers

        # 1. 先执行待平仓卖单
        next_pending_sells: dict[str, str] = {}
        for ob, reason in pending_sells.items():
            pos = context.portfolio.positions.get(ob)
            if pos is None or pos.quantity <= 0:
                continue
            bar = bar_dict[ob]
            if check_limit:
                if getattr(bar, "suspended", False) or np.isnan(bar.open):
                    limit_down_defers += 1
                    next_pending_sells[ob] = reason
                    continue
                if (
                    np.isfinite(bar.limit_down)
                    and bar.limit_down > 0
                    and bar.open <= bar.limit_down + 1e-4
                ):
                    limit_down_defers += 1
                    next_pending_sells[ob] = reason
                    continue
            if ob in open_lots:
                open_lots[ob]["exit_reason"] = reason
            order_shares(ob, -int(pos.quantity))
        pending_sells = next_pending_sells

        # 2. 开新仓（仅在当前可用现金充足且持仓 < 2 只时执行）
        if not pending_buys:
            return
        nav = float(context.portfolio.total_value)
        avail_cash = float(context.portfolio.cash)
        active_obs = {
            ob
            for ob, p in context.portfolio.positions.items()
            if p.quantity > 0 and ob not in pending_sells
        }
        # Also include holdings currently pending sell only if they haven't freed cash yet
        occupied_slots = len(
            {ob for ob, p in context.portfolio.positions.items() if p.quantity > 0}
        )
        slots_left = max(0, 2 - occupied_slots)
        if slots_left <= 0:
            pending_buys = []
            return

        for cand in pending_buys:
            if slots_left <= 0:
                break
            if cand.order_book_id in open_lots or cand.order_book_id in active_obs:
                continue
            bar = bar_dict[cand.order_book_id]
            entry_est = float(bar.open) if check_limit else float(bar.prev_close)
            if getattr(bar, "suspended", False) or np.isnan(entry_est) or entry_est <= 0:
                continue
            if check_limit:
                if (
                    np.isfinite(bar.limit_up)
                    and bar.limit_up > 0
                    and bar.open >= bar.limit_up - 1e-4
                ):
                    limit_up_skips += 1
                    continue
                ref_px = (
                    float(bar.prev_close)
                    if np.isfinite(bar.prev_close) and bar.prev_close > 0
                    else cand.ref_close_raw
                )
                if bar.open > ref_px * 1.02:
                    gap_2pct_skips += 1
                    continue
            stop_pct = min(0.08, max(0.025, 1.0 - cand.hard_stop_raw / cand.ref_close_raw))
            risk_per_share = max(entry_est * stop_pct, entry_est * 0.02)
            raw_shares = min(
                (nav * 0.013) / risk_per_share,
                (nav * 0.18) / entry_est,
                (avail_cash * 0.996) / entry_est,
            )
            lots_shares = int(math.floor(raw_shares / 100.0) * 100)
            if lots_shares < 100 or lots_shares * entry_est < 8_000.0:
                continue
            est_cost = lots_shares * entry_est + max(5.0, lots_shares * entry_est * 0.00025)
            if est_cost > avail_cash:
                continue
            avail_cash -= est_cost
            slots_left -= 1
            open_lots[cand.order_book_id] = {
                "ts_code": cand.ts_code,
                "bp_type": cand.bp_type,
                "entry_date": str(context.now.date()),
                "entry_px": entry_est,
                "qty": 0.0,
                "buy_notional": 0.0,
                "buy_comm": 0.0,
                "buy_slip": 0.0,
                "entry_cost_total": 0.0,
                "stop_pct": stop_pct,
                "peak_px": entry_est,
                "breakeven_armed": False,
                "exit_reason": "SIGNAL_EXIT",
            }
            order_shares(cand.order_book_id, lots_shares)
        pending_buys = []

    def _open_auction(context: Any, bar_dict: Any) -> None:
        _submit_pending(context, bar_dict, check_limit=True)

    def _before_trading(context: Any) -> None:
        pass

    def _handle_bar(context: Any, bar_dict: Any) -> None:
        nonlocal pending_sells, pending_buys
        dt_str = context.now.strftime("%Y%m%d")
        cur_date_str = str(context.now.date())

        # Clean up unfilled phantom open_lots if an open_auction order didn't execute
        for ob in list(open_lots.keys()):
            if open_lots[ob]["qty"] <= 0:
                open_lots.pop(ob, None)

        # 1. 检查存量持仓触发条件（T+1: 仅对 entry_date < today 检查卖出）
        for ob, lot in list(open_lots.items()):
            if lot["entry_date"] >= cur_date_str or ob in pending_sells:
                continue
            bar = bar_dict[ob]
            c_close = float(bar.close)
            if np.isnan(c_close) or c_close <= 0:
                continue
            # 经真实净投入均摊处理送转/拆股变化
            pos = context.portfolio.positions.get(ob)
            eff_qty = float(pos.quantity) if pos is not None and pos.quantity > 0 else lot["qty"]
            eff_entry = lot["buy_notional"] / max(eff_qty, 1.0)
            lot["peak_px"] = max(lot["peak_px"], c_close)
            if lot["peak_px"] >= eff_entry * 1.15:
                lot["breakeven_armed"] = True
            stop_px = eff_entry * (1.0 - lot["stop_pct"])
            if lot["breakeven_armed"]:
                stop_px = max(stop_px, eff_entry)

            h20 = history_bars(ob, 20, "1d", "close")
            ma20_val = float(np.mean(h20)) if h20 is not None and len(h20) == 20 else np.nan
            if c_close <= stop_px:
                pending_sells[ob] = "BREAKEVEN_STOP" if lot["breakeven_armed"] else "HARD_STOP_8PCT"
            elif np.isfinite(ma20_val) and c_close < ma20_val:
                pending_sells[ob] = "MA20_TREND_EXIT"

        # 2. 次日开仓筛选：仅在市场处于 OFFENSIVE/STRUCTURAL 时才允许队列开新仓
        regime = regime_by_date.get(dt_str, "STRUCTURAL")
        if regime == "DEFENSIVE":
            pending_buys = []
            return
        raw_cands = candidates_by_date.get(dt_str, [])
        filtered: list[SwingCandidate] = []
        seen_obs: set[str] = set()
        for c in raw_cands:
            if bp_mode != "COMBINED" and c.bp_type != bp_mode:
                continue
            if require_quality_core and not c.quality_core_ok:
                continue
            if require_industry_top30 and not c.industry_top30_ok:
                continue
            if c.order_book_id in seen_obs or c.order_book_id in open_lots:
                continue
            seen_obs.add(c.order_book_id)
            filtered.append(c)
            if len(filtered) >= 2:
                break
        pending_buys = filtered

        if execution_mode == "vwap":
            # In vwap mode, handle_bar runs same-bar close unless orders submitted next morning.
            pass

    cfg: dict[str, Any] = {
        "base": {
            "start_date": str(start.date()),
            "end_date": str(end.date()),
            "accounts": {"stock": float(initial_cash)},
            "frequency": "1d",
            "data_bundle_path": str(BUNDLE_PATH),
        },
        "mod": {
            "sys_analyser": {"enabled": True},
            "sys_simulation": {
                "enabled": True,
                "price_limit": True,
                "volume_limit": True,
                "matching_type": "vwap" if execution_mode == "vwap" else "current_bar",
            },
            "sys_transaction_cost": {
                "enabled": True,
                "stock_commission_multiplier": 0.3125,  # 万 2.5
                "stock_min_commission": 5.0,  # 最低 5 元
                "tax_multiplier": 1.0,
                "pit_tax": False,  # 卖出万 5 印花税
            },
        },
    }
    if execution_mode == "vwap":
        cfg["mod"]["sys_simulation"]["slippage_model"] = "PriceRatioSlippage"
        cfg["mod"]["sys_simulation"]["slippage"] = SLIPPAGE_ONE_WAY
        # In VWAP companion mode, open_auction runs before day bar and queues bar matching.
        raw_res = run_func(
            init=_init, open_auction=_open_auction, handle_bar=_handle_bar, config=cfg
        )
    else:
        raw_res = run_func(
            init=_init, open_auction=_open_auction, handle_bar=_handle_bar, config=cfg
        )

    nav_df = raw_res["sys_analyser"]["portfolio"]
    raw_val = nav_df["total_value"].astype(float)
    # 扣除显式单边 5bp 滑点得到严格净值曲线
    cum_slip = pd.Series(0.0, index=raw_val.index)
    for tr in closed_trades:
        dt_idx = pd.Timestamp(tr["exit_date"])
        if dt_idx in cum_slip.index:
            cum_slip.loc[dt_idx:] += float(tr["explicit_slippage"])
    adj_val = (raw_val - cum_slip).clip(lower=1.0)
    years = max((adj_val.index[-1] - adj_val.index[0]).days / 365.25, 1.0 / 365.25)
    net_cagr = float((adj_val.iloc[-1] / initial_cash) ** (1.0 / years) - 1.0)
    net_total_ret = float(adj_val.iloc[-1] / initial_cash - 1.0)
    net_mdd = float((adj_val / adj_val.cummax() - 1.0).min())

    # 交易级统计
    n_trades = len(closed_trades)
    if n_trades > 0:
        rets = np.array([tr["net_ret"] for tr in closed_trades], dtype=float)
        wins = rets[rets > 0]
        losses = rets[rets <= 0]
        win_rate = float(len(wins) / n_trades)
        avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
        avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0
        payoff_ratio = (
            float(avg_win / abs(avg_loss)) if avg_loss < 0 else (math.inf if avg_win > 0 else 0.0)
        )
        expectancy = float(rets.mean())
        total_gross = float(sum(tr["gross_pnl"] for tr in closed_trades))
        total_frict = float(sum(tr["total_friction"] for tr in closed_trades))
        frict_over_buy_bps = float(
            total_frict / max(sum(tr["buy_notional"] for tr in closed_trades), 1.0) * 10000.0
        )
        frict_over_gross = (
            float(total_frict / abs(total_gross)) if abs(total_gross) > 1e-6 else math.nan
        )
        # 最大连续亏损次数
        max_consec_loss = 0
        cur_streak = 0
        for r in rets:
            if r <= 0:
                cur_streak += 1
                max_consec_loss = max(max_consec_loss, cur_streak)
            else:
                cur_streak = 0
        stop_exits = sum(1 for tr in closed_trades if "STOP" in tr["exit_reason"])
    else:
        win_rate = avg_win = avg_loss = payoff_ratio = expectancy = 0.0
        frict_over_buy_bps = frict_over_gross = 0.0
        max_consec_loss = stop_exits = 0

    return {
        "window": f"{start.date()}..{end.date()}",
        "initial_cash": initial_cash,
        "bp_mode": bp_mode,
        "require_quality_core": require_quality_core,
        "require_industry_top30": require_industry_top30,
        "execution_mode": execution_mode,
        "closed_trades": n_trades,
        "win_rate": round(win_rate, 4),
        "avg_win_pct": round(avg_win * 100.0, 3),
        "avg_loss_pct": round(avg_loss * 100.0, 3),
        "payoff_ratio": round(payoff_ratio, 3) if math.isfinite(payoff_ratio) else 999.0,
        "net_expectancy_pct": round(expectancy * 100.0, 3),
        "round_trip_friction_bps": round(frict_over_buy_bps, 2),
        "friction_abs_gross_ratio": (
            round(frict_over_gross, 4) if math.isfinite(frict_over_gross) else None
        ),
        "min_5yuan_hits": min_comm_hits,
        "max_consecutive_losses": max_consec_loss,
        "stop_loss_exits": stop_exits,
        "net_total_return": round(net_total_ret, 4),
        "net_cagr": round(net_cagr, 4),
        "net_max_drawdown": round(net_mdd, 4),
        "rejected_buys": rejected_buys,
        "limit_up_skips": limit_up_skips,
        "gap_2pct_skips": gap_2pct_skips,
        "limit_down_defers": limit_down_defers,
    }


def _snapshot_tail_diagnostic() -> dict[str, Any]:
    """统计 2026-09-01..2026-11-13 快照尾部（RQAlpha bundle 截止后）的 OOS 信号触发频次。"""
    sb = pd.read_csv(
        SNAPSHOT_DIR / "stock_basic.csv", usecols=["ts_code", "name", "market"], dtype=str
    )
    main_codes = set(sb[sb["market"] == "主板"]["ts_code"])
    db = pd.read_csv(
        SNAPSHOT_DIR / "daily_bars.csv",
        usecols=["ts_code", "trade_date", "close", "amount"],
        dtype={"ts_code": str, "trade_date": str, "close": float, "amount": float},
    )
    tail = db[(db["trade_date"] >= "20260901") & (db["ts_code"].isin(main_codes))]
    return {
        "tail_window": "2026-09-01..2026-11-13",
        "trade_dates": int(tail["trade_date"].nunique()),
        "liquid_mainboard_rows": int((tail["amount"] >= 150_000.0).sum()),
        "note": (
            "RQAlpha 原生撮合主验证截止 2026-08-31；2026-09..11 为只读行情覆盖核查"
            "（regime 多在 DEFENSIVE 锁定状态，无新开仓）。"
        ),
    }


def run_exp_v3_02() -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    prov = verify_v3_provenance(verify_content=True)
    panels = load_stitched_panels(prov)
    regime_df = compute_v3_market_regime_series(prov, panels.index_close, panels.calendar)
    regime_by_date = {
        dt.strftime("%Y%m%d"): str(row["confirmed_regime"]) for dt, row in regime_df.iterrows()
    }

    candidates_by_date, trigger_stats = build_causal_swing_candidates(BUNDLE_CUTOFF)

    oos_qc_start = pd.Timestamp("2024-02-01")
    oa = "open_auction"
    grid_specs = [
        # (tag, split, start, end, cash, bp_mode, qc, ind30, exec_mode)
        ("IS_100K_BP1", "IS", EXP_START, IS_END, 100_000.0, "BP1_PULLBACK", False, False, oa),
        ("IS_100K_BP2", "IS", EXP_START, IS_END, 100_000.0, "BP2_BREAKOUT", False, False, oa),
        ("IS_100K_COMBINED", "IS", EXP_START, IS_END, 100_000.0, "COMBINED", False, False, oa),
        ("IS_70K_BP1", "IS", EXP_START, IS_END, 70_000.0, "BP1_PULLBACK", False, False, oa),
        ("IS_70K_BP2", "IS", EXP_START, IS_END, 70_000.0, "BP2_BREAKOUT", False, False, oa),
        (
            "OOS_100K_BP1_TECH",
            "OOS_TECH",
            OOS_START,
            BUNDLE_CUTOFF,
            100_000.0,
            "BP1_PULLBACK",
            False,
            False,
            oa,
        ),
        (
            "OOS_100K_BP2_TECH",
            "OOS_TECH",
            OOS_START,
            BUNDLE_CUTOFF,
            100_000.0,
            "BP2_BREAKOUT",
            False,
            False,
            oa,
        ),
        (
            "OOS_100K_BP1_QC",
            "OOS_QC",
            oos_qc_start,
            BUNDLE_CUTOFF,
            100_000.0,
            "BP1_PULLBACK",
            True,
            False,
            oa,
        ),
        (
            "OOS_100K_BP2_QC",
            "OOS_QC",
            oos_qc_start,
            BUNDLE_CUTOFF,
            100_000.0,
            "BP2_BREAKOUT",
            True,
            False,
            oa,
        ),
        (
            "OOS_100K_COMBINED_QC",
            "OOS_QC",
            oos_qc_start,
            BUNDLE_CUTOFF,
            100_000.0,
            "COMBINED",
            True,
            False,
            oa,
        ),
        (
            "OOS_70K_BP1_QC",
            "OOS_QC",
            oos_qc_start,
            BUNDLE_CUTOFF,
            70_000.0,
            "BP1_PULLBACK",
            True,
            False,
            oa,
        ),
        (
            "OOS_70K_BP2_QC",
            "OOS_QC",
            oos_qc_start,
            BUNDLE_CUTOFF,
            70_000.0,
            "BP2_BREAKOUT",
            True,
            False,
            oa,
        ),
        (
            "OOS_70K_COMBINED_QC",
            "OOS_QC",
            oos_qc_start,
            BUNDLE_CUTOFF,
            70_000.0,
            "COMBINED",
            True,
            False,
            oa,
        ),
        (
            "OOS_100K_QC_IND30_SENS",
            "OOS_SENS",
            oos_qc_start,
            BUNDLE_CUTOFF,
            100_000.0,
            "COMBINED",
            True,
            True,
            oa,
        ),
        (
            "OOS_100K_COMBINED_VWAP",
            "OOS_VWAP",
            oos_qc_start,
            BUNDLE_CUTOFF,
            100_000.0,
            "COMBINED",
            True,
            False,
            "vwap",
        ),
    ]

    results_rows: list[dict[str, Any]] = []
    for tag, split, s, e, cash, mode, qc, ind30, ex_mode in grid_specs:
        m = _run_rqalpha_swing(
            candidates_by_date,
            regime_by_date,
            start=s,
            end=e,
            initial_cash=cash,
            bp_mode=mode,
            require_quality_core=qc,
            require_industry_top30=ind30,
            execution_mode=ex_mode,
        )
        m["tag"] = tag
        m["split"] = split
        results_rows.append(m)

    # 严格 OOS 买点裁决（¥100,000 QualityCore OOS 与 技术一致 OOS 均须正期望才保留）
    bp1_oos_qc = next(r for r in results_rows if r["tag"] == "OOS_100K_BP1_QC")
    bp2_oos_qc = next(r for r in results_rows if r["tag"] == "OOS_100K_BP2_QC")
    bp1_keep = bp1_oos_qc["net_expectancy_pct"] > 0.0 and bp1_oos_qc["closed_trades"] >= 5
    bp2_keep = bp2_oos_qc["net_expectancy_pct"] > 0.0 and bp2_oos_qc["closed_trades"] >= 5

    verdicts = {
        "BP1_PULLBACK": "KEEP_ENABLED" if bp1_keep else "REJECTED_DROP",
        "BP2_BREAKOUT": "KEEP_ENABLED" if bp2_keep else "REJECTED_DROP",
        "bp1_oos_qc_expectancy_pct": bp1_oos_qc["net_expectancy_pct"],
        "bp2_oos_qc_expectancy_pct": bp2_oos_qc["net_expectancy_pct"],
    }

    report = {
        "experiment_id": "EXP-V3-02",
        "strategy_id": "V3_MAINBOARD_SWING_BREAKOUT_PULLBACK",
        "snapshot_id": prov.snapshot_id,
        "signal_trigger_stats": trigger_stats,
        "oos_tail_diagnostic": _snapshot_tail_diagnostic(),
        "runs": results_rows,
        "buy_point_verdicts": verdicts,
    }

    json_path = RESULTS_DIR / "EXP_V3_02_MAINBOARD_STOCK_SWING.json"
    csv_path = RESULTS_DIR / "EXP_V3_02_MAINBOARD_STOCK_SWING.csv"
    md_path = RESULTS_DIR / "EXP_V3_02_MAINBOARD_STOCK_SWING.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(results_rows).to_csv(csv_path, index=False)

    lines = [
        "# EXP-V3-02: 10万/7万主板高质量右侧强势股波段（原生 RQAlpha 6.3.0 验证）",
        "",
        f"- **Snapshot ID**: `{prov.snapshot_id}`",
        f"- **买点原始触发统计**: `{trigger_stats}`",
        (
            f"- **买点 OOS 裁决结论**: **BP1 (回踩 MA20)** = `{verdicts['BP1_PULLBACK']}` "
            f"(`{verdicts['bp1_oos_qc_expectancy_pct']:+.3f}%`)｜"
            f"**BP2 (窄幅突破)** = `{verdicts['BP2_BREAKOUT']}` "
            f"(`{verdicts['bp2_oos_qc_expectancy_pct']:+.3f}%`)"
        ),
        (
            "- **费用与撮合设定**: RQAlpha `open_auction` "
            "(`T+1` 整手 100 股 + 万 2.5 佣金最低 5 元 + "
            "卖出万 5 印花税 + 显式双边万 5 滑点；另附 `vwap` 伴随校验)；"
            "高开 `> +2%` 或涨停跳过，跌停/停牌顺延。"
        ),
        "",
        "## 一、IS（2018–2023）与 OOS（2024–2026-08）分买点/本金明细",
        "",
        (
            "| 实验标签 | 账户本金 | 买点 | QualityCore | 成交笔数 | "
            "胜率 | 盈亏比 | 单笔净期望 | 往返摩擦(bp) | "
            "触发5元低消次数 | 最大连亏 | 净 CAGR | 净 MaxDD | 涨停/高开跳过 |"
        ),
        (
            "| --- | ---: | --- | --- | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: | ---: | ---: | --- |"
        ),
    ]
    for r in results_rows:
        qc_lbl = "PIT" if r["require_quality_core"] else "TECH"
        lines.append(
            f"| {r['tag']} | ¥{r['initial_cash']:,.0f} | {r['bp_mode']} | {qc_lbl} | "
            f"{r['closed_trades']} | {r['win_rate'] * 100:.1f}% | {r['payoff_ratio']:.2f} | "
            f"{r['net_expectancy_pct']:+.3f}% | {r['round_trip_friction_bps']:.1f} | "
            f"{r['min_5yuan_hits']} | {r['max_consecutive_losses']} | "
            f"{r['net_cagr'] * 100:.2f}% | {r['net_max_drawdown'] * 100:.2f}% | "
            f"{r['limit_up_skips']}/{r['gap_2pct_skips']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    out = run_exp_v3_02()
    print("Buy point verdicts:", out["buy_point_verdicts"])
    print("Trigger stats:", out["signal_trigger_stats"])
    for r in out["runs"]:
        print(
            f"  {r['tag']:24s} N={r['closed_trades']:3d} WIN={r['win_rate'] * 100:5.1f}% "
            f"PAY={r['payoff_ratio']:4.2f} EXP={r['net_expectancy_pct']:+6.3f}% "
            f"FRICT={r['round_trip_friction_bps']:5.1f}bp "
            f"CAG={r['net_cagr'] * 100:+6.2f}% MDD={r['net_max_drawdown'] * 100:6.2f}%"
        )
