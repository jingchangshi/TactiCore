"""V3 2026-11 扩展研究数据加载器（严格只读、不修改冻结基线 `v3_data.py`）。

数据边界：
1. 主快照：`/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_snapshot_20261126`
   （经 `load_snapshot_manifest(..., verify_content=True)` 全量 SHA-256 校验）；
2. 附属导出：`/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_aux_20261126`
   （含 `index_daily.csv`、`daily_basic_pit.csv` 与 `aux_manifest.json`）；
3. RQAlpha 隔离数据包：`/home/jcshi/.rqalpha/bundle_202611_root/bundle`（截至 `2026-10-30`），
   在重叠窗 `2026-08-01 .. 2026-10-30` 与快照核对后，以 `close / pre_close` 链式拼接至
   `2026-11-26`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.ashare import v3_data as base_v3
from research.ashare.data.contract import load_snapshot_manifest, sha256_file
from research.ashare.engines.bundle_source import bundle_calendar, open_bundle_source
from tacticore.data.tradability import AssetLifetime, build_tradability_mask

SNAPSHOT_DIR_202611 = Path(
    "/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_snapshot_20261126"
)
AUX_DIR_202611 = Path("/home/jcshi/.local/share/finance-mcp-ashare/exports/v3_aux_20261126")
BUNDLE_PATH_202611 = Path("/home/jcshi/.rqalpha/bundle_202611_root/bundle")
REGIME_CACHE_PATH_202611 = AUX_DIR_202611 / "v3_regime_daily_20261126.csv"

WARMUP_START = pd.Timestamp("2017-01-03")
EXP_START = pd.Timestamp("2018-01-02")
IS_END = pd.Timestamp("2023-12-29")
OOS_START = pd.Timestamp("2024-01-02")
BUNDLE_CUTOFF_202611 = pd.Timestamp("2026-10-30")
EXP_END_202611 = pd.Timestamp("2026-11-26")

REGIME_CACHE_VERSION_202611 = "v3_regime_breadth_202611_v1"

EXTENDED_RESEARCH_ETFS: tuple[str, ...] = (
    # Bond / Money market / Gold / Dividend fallbacks
    "511010.SH",
    "511260.SH",
    "511360.SH",
    "511880.SH",
    "159649.SZ",
    "518880.SH",
    "510880.SH",
    "512890.SH",
    # Sector & industry PIT proxies
    "512480.SH",
    "515790.SH",
    "512170.SH",
    "159558.SZ",
    "512880.SH",
    "515030.SH",
    "512660.SH",
    "512400.SH",
    "512800.SH",
    "159928.SZ",
    "512690.SH",
)


def verify_v3_202611_provenance(verify_content: bool = True) -> base_v3.SnapshotProvenance:
    """校验 `v3_snapshot_20261126`、`v3_aux_20261126` 及东财超级 ETF 白名单哈希。"""
    manifest = load_snapshot_manifest(SNAPSHOT_DIR_202611, verify_content=verify_content)
    aux_manifest_path = AUX_DIR_202611 / "aux_manifest.json"
    if not aux_manifest_path.is_file():
        raise FileNotFoundError(f"缺少附属导出 manifest: {aux_manifest_path}")
    aux_raw = json.loads(aux_manifest_path.read_text(encoding="utf-8"))
    if aux_raw.get("linked_snapshot_id") != manifest.snapshot_id:
        raise ValueError(
            "aux_manifest.json linked_snapshot_id 与主快照不一致: "
            f"{aux_raw.get('linked_snapshot_id')} != {manifest.snapshot_id}"
        )
    aux_hashes: dict[str, str] = {}
    for filename, meta in dict(aux_raw.get("files", {})).items():
        fpath = AUX_DIR_202611 / filename
        expected_sha = str(meta["sha256"])
        if verify_content:
            actual_sha = sha256_file(fpath)
            if actual_sha != expected_sha:
                raise ValueError(
                    f"附属文件哈希校验失败 {filename}: {actual_sha} != {expected_sha}"
                )
        aux_hashes[filename] = expected_sha

    wl_raw = json.loads(base_v3.WHITELIST_PATH.read_text(encoding="utf-8"))
    wl_sha = sha256_file(base_v3.WHITELIST_PATH)
    entries = list(wl_raw["entries"])
    return base_v3.SnapshotProvenance(
        snapshot_id=manifest.snapshot_id,
        as_of_trade_date=manifest.as_of_trade_date,
        manifest=manifest,
        dataset_hashes=dict(manifest.content_hashes),
        aux_hashes=aux_hashes,
        whitelist_sha256=wl_sha,
        super_etf_codes=tuple(str(item["ts_code"]) for item in entries),
        super_etf_names={str(item["ts_code"]): str(item["name"]) for item in entries},
        super_etf_categories={str(item["ts_code"]): str(item["category"]) for item in entries},
    )


def build_unified_calendar_202611(
    source: Any,
    *,
    start: pd.Timestamp = WARMUP_START,
    end: pd.Timestamp = EXP_END_202611,
) -> pd.DatetimeIndex:
    """拼接 RQAlpha 2026-10-30 交易日历与快照日历至 2026-11-26。"""
    cal_hist = bundle_calendar(source, start, min(end, BUNDLE_CUTOFF_202611))
    if end <= BUNDLE_CUTOFF_202611:
        return cal_hist
    tc_df = pd.read_csv(SNAPSHOT_DIR_202611 / "trade_calendar.csv", dtype=str)
    open_df = tc_df[tc_df["is_open"] == "1"].copy()
    open_dates = pd.DatetimeIndex(sorted(pd.to_datetime(open_df["cal_date"]).unique()))
    tail = open_dates[(open_dates > BUNDLE_CUTOFF_202611) & (open_dates <= end)]
    return pd.DatetimeIndex(sorted(set(cal_hist).union(set(tail))))


def load_stitched_panels_202611(
    provenance: base_v3.SnapshotProvenance,
    *,
    start: pd.Timestamp = WARMUP_START,
    end: pd.Timestamp = EXP_END_202611,
    extra_etfs: tuple[str, ...] = (),
) -> base_v3.V3StitchedPanels:
    """加载 2017–2026-11-26 指数与扩展 ETF 全收益面板并执行重叠窗审计。"""
    source = open_bundle_source(BUNDLE_PATH_202611)
    calendar = build_unified_calendar_202611(source, start=start, end=end)

    idx_df = pd.read_csv(
        AUX_DIR_202611 / "index_daily.csv",
        dtype={"ts_code": str, "trade_date": str},
    )
    idx_df["dt"] = pd.to_datetime(idx_df["trade_date"])
    idx_cols: dict[str, pd.Series] = {}
    idx_overlap: dict[str, dict[str, float]] = {}
    ov_start = pd.Timestamp("2026-08-01")
    for code in base_v3.INDEX_CODES:
        s_bundle = base_v3._read_bundle_index_series(
            source, base_v3.ts_to_rq(code), min(end, BUNDLE_CUTOFF_202611)
        )
        sub = idx_df[idx_df["ts_code"] == code].set_index("dt")["close"].astype(float).sort_index()
        common = s_bundle.index.intersection(sub.index)
        common_ov = common[(common >= ov_start) & (common <= BUNDLE_CUTOFF_202611)]
        if len(common_ov) > 0:
            max_close_diff = float((s_bundle.loc[common_ov] - sub.loc[common_ov]).abs().max())
            ret_b = s_bundle.pct_change().reindex(common_ov)
            ret_s = sub.pct_change().reindex(common_ov)
            max_ret_diff = float((ret_b - ret_s).abs().max())
            idx_overlap[code] = {
                "common_days": float(len(common_ov)),
                "max_abs_close_diff": round(max_close_diff, 8),
                "max_abs_ret_diff": round(max_ret_diff, 10),
            }
        tail = sub.loc[sub.index > BUNDLE_CUTOFF_202611]
        stitched = pd.concat([s_bundle, tail]).sort_index()
        idx_cols[code] = stitched.reindex(calendar)
    index_close = pd.DataFrame(idx_cols, index=calendar)

    all_etfs = sorted(
        set(provenance.super_etf_codes)
        | set(base_v3.FALLBACK_ETFS)
        | set(EXTENDED_RESEARCH_ETFS)
        | set(extra_etfs)
    )
    fb_df = pd.read_csv(
        SNAPSHOT_DIR_202611 / "fund_daily_bars.csv",
        dtype={"ts_code": str, "trade_date": str},
    )
    fb_df["dt"] = pd.to_datetime(fb_df["trade_date"])
    fa_df = pd.read_csv(
        SNAPSHOT_DIR_202611 / "fund_adj_factor.csv",
        dtype={"ts_code": str, "trade_date": str},
    )
    fbasic_df = pd.read_csv(
        SNAPSHOT_DIR_202611 / "fund_basic.csv",
        dtype={"ts_code": str, "list_date": str, "delist_date": str},
    ).set_index("ts_code")

    fa_codes_complete = set(
        fa_df.groupby("ts_code")["trade_date"].count().loc[lambda s: s >= 190].index
    )
    missing_adj = tuple(sorted(c for c in all_etfs if c not in fa_codes_complete))

    adj_cols: dict[str, pd.Series] = {}
    raw_cols: dict[str, pd.Series] = {}
    lifetimes: dict[str, AssetLifetime] = {}
    etf_overlap: dict[str, dict[str, float]] = {}

    for code in all_etfs:
        sub_fb = (
            fb_df[fb_df["ts_code"] == code].sort_values("dt").drop_duplicates("dt").set_index("dt")
        )
        rq_id = base_v3.ts_to_rq(code)
        try:
            b_raw, b_post, listed, delisted = base_v3._read_bundle_etf_series(
                source, rq_id, min(end, BUNDLE_CUTOFF_202611)
            )
            in_bundle = True
        except KeyError:
            in_bundle = False
            meta = fbasic_df.loc[code]
            listed = pd.to_datetime(str(meta["list_date"])).normalize()
            delist_val = meta["delist_date"]
            delisted = (
                pd.to_datetime(str(delist_val)).normalize()
                if pd.notna(delist_val) and str(delist_val).strip() not in ("", "nan", "None")
                else None
            )

        if in_bundle:
            common = b_raw.index.intersection(sub_fb.index)
            common_ov = common[(common >= ov_start) & (common <= BUNDLE_CUTOFF_202611)]
            if len(common_ov) > 1:
                ov_close = sub_fb.loc[common_ov, "close"]
                max_raw_diff = float((b_raw.loc[common_ov] - ov_close).abs().max())
                ret_post = b_post.pct_change().reindex(common_ov)
                raw_ratio = sub_fb["close"].astype(float) / sub_fb["pre_close"].astype(float) - 1.0
                ret_preclose = raw_ratio.reindex(common_ov)
                max_ret_diff = float((ret_post - ret_preclose).abs().max())
                etf_overlap[code] = {
                    "common_days": float(len(common_ov)),
                    "max_abs_raw_close_diff": round(max_raw_diff, 8),
                    "max_abs_adj_ret_diff": round(max_ret_diff, 10),
                }

            tail_fb = sub_fb[sub_fb.index > BUNDLE_CUTOFF_202611]
            if not tail_fb.empty and not b_post.empty:
                last_post = float(b_post.iloc[-1])
                daily_mult = (
                    tail_fb["close"].astype(float) / tail_fb["pre_close"].astype(float)
                ).replace([np.inf, -np.inf], np.nan)
                tail_post = last_post * daily_mult.cumprod()
                stitched_adj = pd.concat([b_post, tail_post]).sort_index()
                stitched_raw = pd.concat([b_raw, tail_fb["close"].astype(float)]).sort_index()
            else:
                stitched_adj = b_post
                stitched_raw = b_raw
        else:
            if sub_fb.empty:
                stitched_adj = pd.Series(dtype=float)
                stitched_raw = pd.Series(dtype=float)
            else:
                daily_mult = (
                    (sub_fb["close"].astype(float) / sub_fb["pre_close"].astype(float))
                    .replace([np.inf, -np.inf], np.nan)
                    .fillna(1.0)
                    .copy()
                )
                daily_mult.iloc[0] = 1.0
                first_close = float(sub_fb["close"].iloc[0])
                stitched_adj = first_close * daily_mult.cumprod()
                stitched_raw = sub_fb["close"].astype(float)

        mask_life = (calendar >= listed) & (calendar <= delisted if delisted is not None else True)
        adj_s = stitched_adj.reindex(calendar)
        raw_s = stitched_raw.reindex(calendar)
        adj_s[~mask_life] = np.nan
        raw_s[~mask_life] = np.nan
        adj_cols[code] = adj_s
        raw_cols[code] = raw_s
        lifetimes[code] = AssetLifetime(symbol=code, listed_date=listed, delisted_date=delisted)

    etf_adj_close = pd.DataFrame(adj_cols, index=calendar)
    etf_raw_close = pd.DataFrame(raw_cols, index=calendar)
    tradability_mask = build_tradability_mask(calendar, all_etfs, lifetimes, etf_adj_close)

    max_etf_ret_diff = max((v["max_abs_adj_ret_diff"] for v in etf_overlap.values()), default=0.0)
    max_idx_ret_diff = max((v["max_abs_ret_diff"] for v in idx_overlap.values()), default=0.0)
    disclosure = (
        f"raw_close_no_adj_factor_for={len(missing_adj)}/{len(all_etfs)} ETFs in snapshot "
        f"(close/pre_close chained onto RQAlpha 2026-10-30 post-adjusted bundle; "
        f"max 2026-08..10 overlap adj_ret diff={max_etf_ret_diff:.2e})"
    )

    return base_v3.V3StitchedPanels(
        calendar=calendar,
        index_close=index_close,
        etf_adj_close=etf_adj_close,
        etf_raw_close=etf_raw_close,
        etf_lifetimes=lifetimes,
        etf_tradability_mask=tradability_mask,
        overlap_audit={
            "window": "2026-08-01..2026-10-30",
            "max_index_ret_diff": max_idx_ret_diff,
            "max_etf_adj_ret_diff": max_etf_ret_diff,
            "indices": idx_overlap,
            "etfs_audited": len(etf_overlap),
        },
        missing_fund_adj_factor_codes=missing_adj,
        adjustment_disclosure=disclosure,
    )


def _compute_bundle_breadth_202611(
    cal_hist: pd.DatetimeIndex,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """从 2026-11 RQAlpha bundle 读取历史全市场非北交 CS 宽度（含 MA60 与 MA20 占比）。"""
    source = open_bundle_source(BUNDLE_PATH_202611)
    all_cs = [
        inst
        for inst in source.get_instruments(types=["CS"])
        if not inst.order_book_id.endswith(".BJ")
    ]
    cal_ints = np.array([int(d.strftime("%Y%m%d")) for d in cal_hist], dtype=np.int64)
    n_days = len(cal_ints)
    above60_num = np.zeros(n_days, dtype=np.int32)
    above60_den = np.zeros(n_days, dtype=np.int32)
    above20_num = np.zeros(n_days, dtype=np.int32)
    above20_den = np.zeros(n_days, dtype=np.int32)
    mkt_amt_yuan = np.zeros(n_days, dtype=np.float64)
    limit_dn = np.zeros(n_days, dtype=np.int32)

    end_dt = cutoff.to_pydatetime()
    start_int = int(cal_hist[0].strftime("%Y%m%d"))

    for inst in all_cs:
        listed = pd.Timestamp(inst.listed_date)
        delisted = pd.Timestamp(inst.de_listed_date)
        if listed > cutoff or delisted < cal_hist[0]:
            continue
        eff_end = min(end_dt, delisted.to_pydatetime()) if delisted.year < 2999 else end_dt
        bars_raw = source.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="none",
        )
        if bars_raw is None or len(bars_raw) == 0:
            continue
        bars_adj = source.history_bars(
            inst,
            None,
            "1d",
            None,
            eff_end,
            skip_suspended=True,
            include_now=True,
            adjust_type="pre",
            adjust_orig=eff_end,
        )
        if bars_adj is None or len(bars_adj) != len(bars_raw):
            bars_adj = bars_raw

        dts = (bars_adj["datetime"] // 1000000).astype(np.int64)
        mask = dts >= start_int
        if not mask.any():
            continue

        c_adj = bars_adj["close"].astype(np.float64)
        ma60 = pd.Series(c_adj).rolling(60, min_periods=60).mean().to_numpy()
        ma20 = pd.Series(c_adj).rolling(20, min_periods=20).mean().to_numpy()

        dts_w = dts[mask]
        idxs = np.searchsorted(cal_ints, dts_w)
        in_cal = (idxs < n_days) & (cal_ints[np.minimum(idxs, n_days - 1)] == dts_w)
        if not in_cal.any():
            continue
        idxs = idxs[in_cal]

        c_w = c_adj[mask][in_cal]
        m60_w = ma60[mask][in_cal]
        m20_w = ma20[mask][in_cal]
        amt_w = bars_raw["total_turnover"][mask][in_cal].astype(np.float64)
        c_raw_w = bars_raw["close"][mask][in_cal].astype(np.float64)
        ld_w = bars_raw["limit_down"][mask][in_cal].astype(np.float64)

        v60 = ~np.isnan(m60_w)
        if v60.any():
            np.add.at(above60_den, idxs[v60], 1)
            np.add.at(above60_num, idxs[v60], (c_w[v60] > m60_w[v60]).astype(np.int32))
        v20 = ~np.isnan(m20_w)
        if v20.any():
            np.add.at(above20_den, idxs[v20], 1)
            np.add.at(above20_num, idxs[v20], (c_w[v20] > m20_w[v20]).astype(np.int32))
        np.add.at(mkt_amt_yuan, idxs, np.nan_to_num(amt_w, 0.0))
        is_ld = np.isfinite(ld_w) & (ld_w > 0) & (c_raw_w <= ld_w + 1e-4)
        np.add.at(limit_dn, idxs, is_ld.astype(np.int32))

    return pd.DataFrame(
        {
            "pct_above_ma60": np.where(above60_den > 0, above60_num / above60_den, np.nan),
            "pct_above_ma20": np.where(above20_den > 0, above20_num / above20_den, np.nan),
            "amount_yi": mkt_amt_yuan / 1e8,
            "limit_down": limit_dn,
        },
        index=cal_hist,
    )


def _compute_snapshot_breadth_202611() -> pd.DataFrame:
    """从 `v3_snapshot_20261126` 计算 2024-01-02..2026-11-26 全市场宽度指标（含 MA60 与 MA20）。"""
    sb = pd.read_csv(SNAPSHOT_DIR_202611 / "stock_basic.csv", usecols=["ts_code"], dtype=str)
    valid_codes = set(sb[~sb["ts_code"].str.endswith(".BJ")]["ts_code"])

    daily = pd.read_csv(
        SNAPSHOT_DIR_202611 / "daily_bars.csv",
        usecols=["ts_code", "trade_date", "close", "amount"],
        dtype={"ts_code": str, "trade_date": str, "close": float, "amount": float},
    )
    daily = daily[daily["ts_code"].isin(valid_codes)].copy()

    adj = pd.read_csv(
        SNAPSHOT_DIR_202611 / "adj_factor.csv",
        usecols=["ts_code", "trade_date", "adj_factor"],
        dtype={"ts_code": str, "trade_date": str, "adj_factor": float},
    )
    pl = pd.read_csv(
        SNAPSHOT_DIR_202611 / "price_limit.csv",
        usecols=["ts_code", "trade_date", "down_limit"],
        dtype={"ts_code": str, "trade_date": str, "down_limit": float},
    )

    merged = daily.merge(adj, on=["ts_code", "trade_date"], how="left")
    merged = merged.merge(pl, on=["ts_code", "trade_date"], how="left")
    merged = merged.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    merged["adj_close"] = merged["close"] * merged["adj_factor"]
    grp = merged.groupby("ts_code", sort=False)["adj_close"]
    merged["ma60"] = grp.rolling(60, min_periods=60).mean().reset_index(level=0, drop=True)
    merged["ma20"] = grp.rolling(20, min_periods=20).mean().reset_index(level=0, drop=True)
    merged["valid_60"] = merged["ma60"].notna().astype(np.int32)
    merged["above_60"] = (merged["ma60"].notna() & (merged["adj_close"] > merged["ma60"])).astype(
        np.int32
    )
    merged["valid_20"] = merged["ma20"].notna().astype(np.int32)
    merged["above_20"] = (merged["ma20"].notna() & (merged["adj_close"] > merged["ma20"])).astype(
        np.int32
    )
    merged["is_ld"] = (
        merged["down_limit"].notna()
        & (merged["down_limit"] > 0)
        & (merged["close"] <= merged["down_limit"] + 1e-4)
    ).astype(np.int32)

    agg = merged.groupby("trade_date", sort=True).agg(
        above60_num=("above_60", "sum"),
        above60_den=("valid_60", "sum"),
        above20_num=("above_20", "sum"),
        above20_den=("valid_20", "sum"),
        amount_k=("amount", "sum"),
        limit_down=("is_ld", "sum"),
    )
    agg.index = pd.to_datetime(agg.index)
    return pd.DataFrame(
        {
            "pct_above_ma60": np.where(
                agg["above60_den"] > 0, agg["above60_num"] / agg["above60_den"], np.nan
            ),
            "pct_above_ma20": np.where(
                agg["above20_den"] > 0, agg["above20_num"] / agg["above20_den"], np.nan
            ),
            "amount_yi": agg["amount_k"] / 1e5,
            "limit_down": agg["limit_down"].astype(int),
        },
        index=agg.index.sort_values(),
    )


def compute_v3_regime_series_202611(
    provenance: base_v3.SnapshotProvenance,
    index_close: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    *,
    pct_above_ma60_off: float = 0.45,
    style_spread_threshold: float = 0.03,
    use_cache: bool = True,
) -> pd.DataFrame:
    """计算 2017–2026-11-26 逐日双锚三档状态与风格（附带 `pct_above_ma20`）。"""
    breadth: pd.DataFrame | None = None
    if use_cache and REGIME_CACHE_PATH_202611.is_file():
        cached = pd.read_csv(
            REGIME_CACHE_PATH_202611, dtype={"trade_date": str, "snapshot_id": str}
        )
        if (
            not cached.empty
            and str(cached["snapshot_id"].iloc[0]) == provenance.snapshot_id
            and str(cached.get("cache_version", pd.Series([""])).iloc[0])
            == REGIME_CACHE_VERSION_202611
        ):
            cached["dt"] = pd.to_datetime(cached["trade_date"])
            cached = cached.set_index("dt")[
                ["pct_above_ma60", "pct_above_ma20", "amount_yi", "limit_down"]
            ]
            if set(calendar).issubset(set(cached.index)):
                breadth = cached.reindex(calendar)

    if breadth is None:
        stitch_split = pd.Timestamp("2024-06-30")
        cal_hist = calendar[calendar <= BUNDLE_CUTOFF_202611]
        b_hist = _compute_bundle_breadth_202611(cal_hist, BUNDLE_CUTOFF_202611)
        b_snap = _compute_snapshot_breadth_202611()
        ov = b_hist.index.intersection(b_snap.index)
        ov = ov[ov > stitch_split]
        max_pct_diff = (
            float((b_hist.loc[ov, "pct_above_ma60"] - b_snap.loc[ov, "pct_above_ma60"]).abs().max())
            if len(ov) > 0
            else 0.0
        )
        amt_ratio = (
            float((b_snap.loc[ov, "amount_yi"] / b_hist.loc[ov, "amount_yi"]).median())
            if len(ov) > 0
            else 1.0
        )
        breadth = (
            pd.concat(
                [b_hist.loc[b_hist.index <= stitch_split], b_snap.loc[b_snap.index > stitch_split]]
            )
            .sort_index()
            .reindex(calendar)
        )
        if use_cache:
            out_cache = breadth.copy()
            out_cache.insert(0, "trade_date", out_cache.index.strftime("%Y%m%d"))
            out_cache["snapshot_id"] = provenance.snapshot_id
            out_cache["cache_version"] = REGIME_CACHE_VERSION_202611
            out_cache["seam_max_pct_diff"] = round(max_pct_diff, 6)
            out_cache["seam_amt_ratio"] = round(amt_ratio, 6)
            out_cache.to_csv(REGIME_CACHE_PATH_202611, index=False)

    amount_ma20 = breadth["amount_yi"].rolling(20, min_periods=20).mean()
    amount_vs_ma20 = (breadth["amount_yi"] / amount_ma20).round(3)

    val_state, val_pct_chg, val_ret20 = base_v3._anchor_states(index_close["000300.SH"])
    csi500_state, csi500_pct_chg, csi500_ret20 = base_v3._anchor_states(index_close["000905.SH"])
    chinext_state, chinext_pct_chg, chinext_ret20 = base_v3._anchor_states(index_close["399006.SZ"])

    rows: list[dict[str, Any]] = []
    confirmed = "STRUCTURAL"
    prev_raw = "STRUCTURAL"
    target_bps_map = {"OFFENSIVE": 8500, "STRUCTURAL": 6000, "DEFENSIVE": 1500}
    thresh_pct = style_spread_threshold * 100.0

    for i, _dt in enumerate(calendar):
        vs = str(val_state.iloc[i])
        g1 = str(csi500_state.iloc[i])
        g2 = str(chinext_state.iloc[i])
        if g1 == "BEAR" and g2 == "BEAR":
            gs = "BEAR"
        elif (g1 == "BULL" or g2 == "BULL") and g1 != "BEAR" and g2 != "BEAR":
            gs = "BULL"
        else:
            gs = "RANGE"

        pct_ab60 = breadth["pct_above_ma60"].iloc[i]
        pct_ab20 = breadth["pct_above_ma20"].iloc[i]
        amt_ratio = amount_vs_ma20.iloc[i]
        ld = int(breadth["limit_down"].iloc[i]) if pd.notna(breadth["limit_down"].iloc[i]) else 0

        off_breadth = pd.notna(pct_ab60) and float(pct_ab60) >= pct_above_ma60_off
        off_vol = pd.notna(amt_ratio) and float(amt_ratio) >= 0.85
        def_breadth = pd.notna(pct_ab60) and float(pct_ab60) < 0.30

        is_bull_pair = (vs == "BULL" or gs == "BULL") and vs != "BEAR" and gs != "BEAR"
        if is_bull_pair and off_breadth and off_vol:
            raw = "OFFENSIVE"
        elif (vs == "BEAR" and gs == "BEAR") or ((vs == "BEAR" or gs == "BEAR") and def_breadth):
            raw = "DEFENSIVE"
        else:
            raw = "STRUCTURAL"

        v_chg = val_pct_chg.iloc[i]
        g_chgs = [x for x in (csi500_pct_chg.iloc[i], chinext_pct_chg.iloc[i]) if pd.notna(x)]
        g_chg = float(np.mean(g_chgs)) if g_chgs else np.nan
        crash = (
            pd.notna(v_chg)
            and float(v_chg) < -3.5
            and pd.notna(g_chg)
            and float(g_chg) < -3.5
            and ld > 80
        )

        if i == 0:
            confirmed = "DEFENSIVE" if crash else raw
        elif crash:
            confirmed = "DEFENSIVE"
        elif raw == prev_raw:
            confirmed = raw
        prev_raw = raw

        v_r20 = val_ret20.iloc[i]
        g_r20s = [x for x in (csi500_ret20.iloc[i], chinext_ret20.iloc[i]) if pd.notna(x)]
        g_r20 = float(np.mean(g_r20s)) if g_r20s else np.nan
        spread = float(g_r20 - v_r20) if pd.notna(v_r20) and pd.notna(g_r20) else 0.0
        if spread > thresh_pct:
            style = "GROWTH_LEADING"
        elif spread < -thresh_pct:
            style = "VALUE_LEADING"
        else:
            style = "BALANCED"

        rows.append(
            {
                "value_state": vs,
                "growth_state": gs,
                "pct_above_ma60": float(pct_ab60) if pd.notna(pct_ab60) else np.nan,
                "pct_above_ma20": float(pct_ab20) if pd.notna(pct_ab20) else np.nan,
                "amount_yi": float(breadth["amount_yi"].iloc[i]),
                "amount_vs_ma20": float(amt_ratio) if pd.notna(amt_ratio) else np.nan,
                "limit_down": ld,
                "crash_override": bool(crash),
                "raw_regime": raw,
                "confirmed_regime": confirmed,
                "target_equity_bps": target_bps_map[confirmed],
                "style": style,
                "style_spread_pct": spread,
            }
        )

    return pd.DataFrame(rows, index=calendar)
