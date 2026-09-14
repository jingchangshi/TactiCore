"""共享 fixture：策略配置、合成前瞻 vintage 与最小 candidate repo 布局。

所有前瞻相关 fixture 都只使用 synthetic / historical fixture 数据；不下载、不查看任何真实
2026-09 市场数据，也不运行真实 observation。
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from tacticore.data.prices import load_price_csv
from tacticore.data.tushare import ADJUSTMENT_TYPE, SOURCE, TushareDataset, write_tushare_dataset
from tacticore.strategies.global_dual_momentum import GlobalDualMomentumConfig

CANONICAL_ROOT = Path(__file__).resolve().parents[1]
SHADOW_DIRS = {"S2_R1": "research/shadow/s2_r1", "S4C_R1": "research/shadow/s4c_r1"}
DEFAULT_AS_OF = "2026-09-30"
# 15:30 Asia/Shanghai（收盘后）与 16:00 Asia/Shanghai（signal-day seal 窗口内）。
DEFAULT_DOWNLOAD_TIMESTAMP = "2026-09-30T07:30:00+00:00"
DEFAULT_DECISION_SEAL = "2026-09-30T08:00:00+00:00"


def canonical_prices(root: Path = CANONICAL_ROOT) -> pd.DataFrame:
    return load_price_csv(root / "data/canonical/etf_adjusted_close.csv")


def canonical_calendar(root: Path = CANONICAL_ROOT) -> pd.DataFrame:
    return pd.read_csv(
        root / "data/canonical/trading_calendar.csv", index_col="date", parse_dates=["date"]
    ).astype(int)


def tushare_symbol_map(root: Path = CANONICAL_ROOT) -> dict[str, str]:
    universe = pd.read_csv(root / "config/universe.csv")
    return dict(zip(universe["symbol"], universe["tushare_symbol"], strict=True))


def _synthetic_provenance(
    prices: pd.DataFrame,
    *,
    as_of: str,
    download_timestamp: str,
    symbols: dict[str, str],
) -> dict[str, Any]:
    as_of_token = pd.Timestamp(as_of).strftime("%Y%m%d")
    records: list[dict[str, Any]] = []
    for symbol in prices.columns:
        observed = prices[symbol].dropna()
        records.append(
            {
                "symbol": symbol,
                "tushare_symbol": symbols[symbol],
                "source": SOURCE,
                "request_parameters": {
                    "fund_daily": {
                        "ts_code": symbols[symbol],
                        "start_date": "20120101",
                        "end_date": as_of_token,
                        "fields": "ts_code,trade_date,close",
                        "page_size": 5000,
                    },
                    "fund_adj": {
                        "ts_code": symbols[symbol],
                        "start_date": "20120101",
                        "end_date": as_of_token,
                        "fields": "ts_code,trade_date,adj_factor",
                        "page_size": 2000,
                    },
                },
                "adjustment_type": ADJUSTMENT_TYPE,
                "data_timestamp": observed.index.max().date().isoformat(),
                "download_timestamp": download_timestamp,
                "rows": len(observed),
                "first_observation": observed.index.min().date().isoformat(),
                "metadata": {
                    "name": symbol,
                    "management": "fixture",
                    "fund_type": "ETF",
                    "list_date": "20130101",
                    "delist_date": "",
                },
            }
        )
    return {
        "dataset": "TactiCore S1 ETF 后复权收盘价",
        "source": SOURCE,
        "start_date": "20120101",
        "end_date": as_of_token,
        "adjustment_type": ADJUSTMENT_TYPE,
        "download_timestamp": download_timestamp,
        "calendar_requests": [
            {
                "exchange": exchange,
                "start_date": "20120101",
                "end_date": as_of_token,
                "fields": "exchange,cal_date,is_open,pretrade_date",
            }
            for exchange in ("SSE", "SZSE")
        ],
        "metadata_request": {
            "market": "E",
            "status": "L",
            "fields": "ts_code,name,management,fund_type,list_date,delist_date",
        },
        "lookahead_control": {
            "data_availability": "trade_date 收盘价只在该交易日收盘后可用",
            "strategy_execution": "月末收盘生成信号，下一交易日执行",
        },
        "symbols": records,
        "quality_checks": {"fixture": True},
    }


def write_prospective_vintage(
    destination: Path,
    *,
    as_of: str = DEFAULT_AS_OF,
    download_timestamp: str = DEFAULT_DOWNLOAD_TIMESTAMP,
    overlap_multiplier: float = 1.0,
    beyond_as_of: bool = False,
    extra_calendar_dates: tuple[str, ...] = (),
    provenance_overrides: dict[str, Any] | None = None,
) -> Path:
    """用一个 synthetic as-of 快照写出 candidate vintage（provenance 与 hash 均为真值）。"""
    historical_prices = canonical_prices()
    historical_calendar = canonical_calendar()
    overlap_date = historical_prices.index[-1]
    as_of_day = pd.Timestamp(as_of)
    future_dates = pd.bdate_range(as_of_day.replace(day=1), as_of_day)
    if beyond_as_of:
        future_dates = future_dates.append(pd.DatetimeIndex([as_of_day + pd.Timedelta(days=1)]))
    prospective_prices = pd.DataFrame(
        [historical_prices.iloc[-1].to_numpy()] * len(future_dates),
        index=future_dates,
        columns=historical_prices.columns,
    )
    drift = 1.0 + 0.001 * np.arange(len(future_dates), dtype=float)
    prospective_prices = prospective_prices.mul(drift, axis=0)
    prices = pd.concat(
        [historical_prices.loc[[overlap_date]] * overlap_multiplier, prospective_prices]
    )
    prices.index.name = "date"
    calendar_dates = pd.DatetimeIndex([overlap_date, *future_dates.tolist()])
    if extra_calendar_dates:
        calendar_dates = calendar_dates.append(pd.DatetimeIndex(extra_calendar_dates))
    calendar_dates = calendar_dates.sort_values().unique()
    calendar = pd.DataFrame(
        {
            "sse_open": [
                int(historical_calendar.at[date, "sse_open"])
                if date in historical_calendar.index
                else 1
                for date in calendar_dates
            ],
            "szse_open": [
                int(historical_calendar.at[date, "szse_open"])
                if date in historical_calendar.index
                else 1
                for date in calendar_dates
            ],
        },
        index=pd.DatetimeIndex(calendar_dates, name="date"),
    )
    provenance = _synthetic_provenance(
        prices, as_of=as_of, download_timestamp=download_timestamp, symbols=tushare_symbol_map()
    )
    if provenance_overrides:
        provenance.update(provenance_overrides)
    destination.mkdir(parents=True, exist_ok=True)
    write_tushare_dataset(
        TushareDataset(prices=prices, calendar=calendar, provenance=provenance), destination
    )
    return destination


def write_observations_header(path: Path, fields: tuple[str, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=list(fields)).writeheader()
    return path


def build_candidate_repo(root: Path, candidate_id: str) -> Path:
    """最小 candidate repo 布局：真实 manifest 身份 + 冻结输入 + 空 observation 表。"""
    shadow_dir = SHADOW_DIRS[candidate_id]
    manifest = json.loads(
        (CANONICAL_ROOT / shadow_dir / "candidate_manifest.json").read_text("utf-8")
    )
    copied: set[str] = set()
    for key in ("file_hashes", "frozen_identity_artifacts"):
        for relative_path in manifest.get(key, {}):
            copied.add(relative_path)
    for relative_path in sorted(copied):
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CANONICAL_ROOT / relative_path, target)
    for relative_path in ("config/universe.csv", "config/strategy.toml"):
        target = root / relative_path
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CANONICAL_ROOT / relative_path, target)
    for name in ("etf_adjusted_close.csv", "trading_calendar.csv", "provenance.json"):
        target = root / "data/canonical" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CANONICAL_ROOT / "data/canonical" / name, target)
    (root / shadow_dir / "candidate_manifest.json").parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        CANONICAL_ROOT / shadow_dir / "candidate_manifest.json",
        root / shadow_dir / "candidate_manifest.json",
    )
    if candidate_id == "S4C_R1":
        for relative_path in (
            "research/shadow/s4c_r1/activation.json",
            "research/batches/s4c_activation/PROTOCOL.md",
            "research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md",
        ):
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CANONICAL_ROOT / relative_path, target)
    return root


@pytest.fixture
def strategy_config() -> GlobalDualMomentumConfig:
    return GlobalDualMomentumConfig(
        lookback_trading_days=3,
        top_k=2,
        absolute_momentum_threshold=0.0,
        fallback_symbol="BOND",
        risk_symbols=("A", "B", "C"),
        fees=0.0,
        slippage=0.0,
        initial_cash=100_000.0,
    )


@pytest.fixture
def simple_prices() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-22", "2024-02-09")
    step = np.arange(len(dates), dtype=float)
    return pd.DataFrame(
        {
            "A": 100.0 + step * 3.0,
            "B": 100.0 + step * 2.0,
            "C": 100.0 - step,
            "BOND": 100.0 + step * 0.1,
        },
        index=dates,
    )


@pytest.fixture
def one_asset_config(strategy_config: GlobalDualMomentumConfig) -> GlobalDualMomentumConfig:
    return replace(strategy_config, top_k=1)


@pytest.fixture
def make_prospective_vintage() -> Any:
    """Factory: 在给定目录写出一个 provenance/hash 均为真值的 synthetic vintage。"""
    return write_prospective_vintage


@pytest.fixture
def make_candidate_repo() -> Any:
    """Factory: 构造只含真实冻结身份输入与空 observation 表的最小 candidate repo。"""
    return build_candidate_repo
