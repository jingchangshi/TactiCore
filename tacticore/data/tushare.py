from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

SOURCE = "Tushare Pro"
ADJUSTMENT_TYPE = "后复权（原始收盘价 × fund_adj 复权因子，将因子变化视为分红再投资）"
DAILY_PAGE_SIZE = 5000
ADJUSTMENT_PAGE_SIZE = 2000


@dataclass(frozen=True)
class TushareDataset:
    prices: pd.DataFrame
    calendar: pd.DataFrame
    provenance: dict[str, Any]


def _require_columns(frame: pd.DataFrame, required: set[str], endpoint: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{endpoint} 返回缺少字段: {sorted(missing)}")


def _fetch_pages(
    api: Any,
    endpoint: str,
    *,
    page_size: int,
    fields: str,
    parameters: dict[str, str],
) -> pd.DataFrame:
    pages: list[pd.DataFrame] = []
    offset = 0
    while True:
        page = getattr(api, endpoint)(
            **parameters,
            offset=offset,
            limit=page_size,
            fields=fields,
        )
        if page is None:
            raise RuntimeError(f"{endpoint} 未返回数据")
        pages.append(page)
        if len(page) < page_size:
            break
        offset += page_size
    return pd.concat(pages, ignore_index=True)


def adjust_fund_close(daily: pd.DataFrame, adjustments: pd.DataFrame) -> pd.Series:
    """按 Tushare fund_adj 因子生成不随查询截止日缩放的后复权收盘价。"""
    _require_columns(daily, {"trade_date", "close"}, "fund_daily")
    _require_columns(adjustments, {"trade_date", "adj_factor"}, "fund_adj")
    if daily["trade_date"].duplicated().any():
        raise ValueError("fund_daily 返回重复交易日期")
    if adjustments["trade_date"].duplicated().any():
        raise ValueError("fund_adj 返回重复交易日期")

    merged = daily[["trade_date", "close"]].merge(
        adjustments[["trade_date", "adj_factor"]],
        on="trade_date",
        how="left",
        validate="one_to_one",
    )
    merged["close"] = pd.to_numeric(merged["close"], errors="coerce")
    merged["adj_factor"] = pd.to_numeric(merged["adj_factor"], errors="coerce")
    if merged[["close", "adj_factor"]].isna().any().any():
        raise ValueError("日线收盘价或对应复权因子存在缺失")
    if (merged[["close", "adj_factor"]] <= 0).any().any():
        raise ValueError("日线收盘价和复权因子必须大于零")

    dates = pd.to_datetime(merged["trade_date"], format="%Y%m%d")
    adjusted = pd.Series(
        merged["close"].to_numpy() * merged["adj_factor"].to_numpy(),
        index=pd.DatetimeIndex(dates, name="date"),
        dtype=float,
    )
    return adjusted.sort_index()


def _load_calendar(api: Any, start_date: str, end_date: str) -> pd.DataFrame:
    calendars: dict[str, pd.Series] = {}
    for exchange in ("SSE", "SZSE"):
        frame = api.trade_cal(
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        if frame is None:
            raise RuntimeError(f"trade_cal({exchange}) 未返回数据")
        _require_columns(frame, {"cal_date", "is_open"}, "trade_cal")
        if frame["cal_date"].duplicated().any():
            raise ValueError(f"trade_cal({exchange}) 返回重复日期")
        dates = pd.to_datetime(frame["cal_date"], format="%Y%m%d")
        calendars[exchange.lower() + "_open"] = pd.Series(
            pd.to_numeric(frame["is_open"], errors="raise").astype(int).to_numpy(),
            index=dates,
            dtype=int,
        )

    calendar = pd.DataFrame(calendars).fillna(0).astype(int).sort_index()
    calendar.index.name = "date"
    if calendar.empty or not calendar.isin([0, 1]).all().all():
        raise ValueError("交易日历为空或包含非 0/1 状态")
    return calendar


def download_tushare_dataset(
    api: Any,
    universe: pd.DataFrame,
    start_date: str,
    end_date: str,
    *,
    downloaded_at: str | None = None,
) -> TushareDataset:
    """下载当前标的池所需的 ETF 日线、复权因子、交易日历和基金元数据。"""
    try:
        parsed_start = datetime.strptime(start_date, "%Y%m%d")
        parsed_end = datetime.strptime(end_date, "%Y%m%d")
    except ValueError as error:
        raise ValueError("start_date 和 end_date 必须使用 YYYYMMDD 格式") from error
    if parsed_start > parsed_end:
        raise ValueError("start_date 不得晚于 end_date")
    required_columns = {"symbol", "tushare_symbol", "name", "start_date"}
    missing_columns = required_columns.difference(universe.columns)
    if missing_columns:
        raise ValueError(f"universe 缺少 Tushare 字段: {sorted(missing_columns)}")

    calendar = _load_calendar(api, start_date, end_date)
    metadata_request = {
        "market": "E",
        "status": "L",
        "fields": "ts_code,name,management,fund_type,list_date,delist_date",
    }
    metadata = api.fund_basic(**metadata_request)
    if metadata is None:
        raise RuntimeError("fund_basic 未返回数据")
    _require_columns(
        metadata,
        {"ts_code", "name", "management", "fund_type", "list_date", "delist_date"},
        "fund_basic",
    )
    if metadata["ts_code"].duplicated().any():
        raise ValueError("fund_basic 返回重复基金代码")
    metadata_by_code = metadata.set_index("ts_code")

    adjusted_series: dict[str, pd.Series] = {}
    records: list[dict[str, Any]] = []
    quality_by_symbol: dict[str, dict[str, Any]] = {}
    timestamp = downloaded_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for row in universe.itertuples(index=False):
        symbol = str(row.symbol)
        tushare_symbol = str(row.tushare_symbol)
        request_parameters = {
            "ts_code": tushare_symbol,
            "start_date": start_date,
            "end_date": end_date,
        }
        daily = _fetch_pages(
            api,
            "fund_daily",
            page_size=DAILY_PAGE_SIZE,
            fields="ts_code,trade_date,close",
            parameters=request_parameters,
        )
        adjustments = _fetch_pages(
            api,
            "fund_adj",
            page_size=ADJUSTMENT_PAGE_SIZE,
            fields="ts_code,trade_date,adj_factor",
            parameters=request_parameters,
        )
        if daily.empty:
            raise ValueError(f"{tushare_symbol} 没有日线数据")
        if adjustments.empty:
            raise ValueError(f"{tushare_symbol} 没有复权因子")
        if set(daily["ts_code"]) != {tushare_symbol}:
            raise ValueError(f"fund_daily 返回了非请求标的: {tushare_symbol}")
        if set(adjustments["ts_code"]) != {tushare_symbol}:
            raise ValueError(f"fund_adj 返回了非请求标的: {tushare_symbol}")
        if tushare_symbol not in metadata_by_code.index:
            raise ValueError(f"fund_basic 缺少当前上市基金: {tushare_symbol}")
        source_metadata = metadata_by_code.loc[tushare_symbol]
        configured_list_date = pd.to_datetime(str(row.start_date)).strftime("%Y%m%d")
        if str(source_metadata["list_date"]) != configured_list_date:
            raise ValueError(
                f"{tushare_symbol} 上市日期不一致: "
                f"config={configured_list_date}, Tushare={source_metadata['list_date']}"
            )

        adjusted = adjust_fund_close(daily, adjustments)
        if (
            configured_list_date >= start_date
            and adjusted.index.min().strftime("%Y%m%d") != configured_list_date
        ):
            raise ValueError(f"{tushare_symbol} 首个行情日与上市日期不一致")
        exchange_column = "sse_open" if tushare_symbol.endswith(".SH") else "szse_open"
        open_dates = calendar.index[calendar[exchange_column] == 1]
        misaligned = adjusted.index.difference(open_dates)
        if len(misaligned):
            raise ValueError(f"{tushare_symbol} 有 {len(misaligned)} 个行情日期不在交易日历中")
        adjusted_series[symbol] = adjusted.rename(symbol)

        active_open_dates = open_dates[open_dates >= adjusted.index.min()]
        missing_dates = active_open_dates.difference(adjusted.index)
        factors = (
            adjustments.assign(
                trade_date=pd.to_datetime(adjustments["trade_date"], format="%Y%m%d")
            )
            .sort_values("trade_date")["adj_factor"]
            .astype(float)
        )
        factor_changes = int(factors.ne(factors.shift()).sum() - 1)
        quality_by_symbol[symbol] = {
            "日线重复日期": 0,
            "复权因子重复日期": 0,
            "非交易日行情": 0,
            "上市后区间缺失观测": len(missing_dates),
            "上市后区间缺失日期": [date.date().isoformat() for date in missing_dates],
            "非正复权价格": 0,
            "复权因子变化次数": factor_changes,
        }
        records.append(
            {
                "symbol": symbol,
                "tushare_symbol": tushare_symbol,
                "source": SOURCE,
                "request_parameters": {
                    "fund_daily": {
                        **request_parameters,
                        "fields": "ts_code,trade_date,close",
                        "page_size": DAILY_PAGE_SIZE,
                    },
                    "fund_adj": {
                        **request_parameters,
                        "fields": "ts_code,trade_date,adj_factor",
                        "page_size": ADJUSTMENT_PAGE_SIZE,
                    },
                },
                "adjustment_type": ADJUSTMENT_TYPE,
                "data_timestamp": adjusted.index.max().date().isoformat(),
                "download_timestamp": timestamp,
                "rows": len(adjusted),
                "first_observation": adjusted.index.min().date().isoformat(),
                "metadata": {
                    "name": source_metadata["name"],
                    "management": source_metadata["management"],
                    "fund_type": source_metadata["fund_type"],
                    "list_date": source_metadata["list_date"],
                    "delist_date": source_metadata["delist_date"],
                },
            }
        )

    prices = pd.concat(adjusted_series.values(), axis=1).sort_index()
    prices.index.name = "date"
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("规范化价格日期必须唯一且递增")
    if (prices <= 0).any().any():
        raise ValueError("规范化价格中的有效值必须大于零")

    provenance: dict[str, Any] = {
        "dataset": "TactiCore S1 ETF 后复权收盘价",
        "source": SOURCE,
        "start_date": start_date,
        "end_date": end_date,
        "adjustment_type": ADJUSTMENT_TYPE,
        "download_timestamp": timestamp,
        "calendar_requests": [
            {
                "exchange": exchange,
                "start_date": start_date,
                "end_date": end_date,
                "fields": "exchange,cal_date,is_open,pretrade_date",
            }
            for exchange in ("SSE", "SZSE")
        ],
        "metadata_request": metadata_request,
        "lookahead_control": {
            "data_availability": "trade_date 收盘价只在该交易日收盘后可用",
            "strategy_execution": "月末收盘生成信号，下一交易日执行",
        },
        "symbols": records,
        "quality_checks": {
            "日期唯一且递增": True,
            "有效价格均为正数": True,
            "行情日期均属于对应交易所交易日": True,
            "配置上市日期与 Tushare 元数据一致": True,
            "缺失值未填零或猜测": True,
            "逐标的结果": quality_by_symbol,
        },
    }
    return TushareDataset(prices=prices, calendar=calendar, provenance=provenance)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_tushare_dataset(dataset: TushareDataset, output_dir: str | Path) -> None:
    """按稳定排序和固定精度写出 canonical CSV 与来源清单。"""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    prices_path = destination / "etf_adjusted_close.csv"
    calendar_path = destination / "trading_calendar.csv"
    provenance_path = destination / "provenance.json"

    dataset.prices.to_csv(
        prices_path,
        date_format="%Y-%m-%d",
        float_format="%.8f",
        na_rep="",
        lineterminator="\n",
    )
    dataset.calendar.to_csv(calendar_path, date_format="%Y-%m-%d", lineterminator="\n")
    provenance = dict(dataset.provenance)
    provenance["files"] = {
        prices_path.name: {"sha256": _sha256(prices_path), "rows": len(dataset.prices)},
        calendar_path.name: {"sha256": _sha256(calendar_path), "rows": len(dataset.calendar)},
    }
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
