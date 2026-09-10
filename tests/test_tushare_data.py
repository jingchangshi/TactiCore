import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tacticore.data.tushare import (
    ADJUSTMENT_TYPE,
    adjust_fund_close,
    download_tushare_dataset,
    write_tushare_dataset,
)


class FakeTushareApi:
    def trade_cal(self, **kwargs: Any) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "exchange": [kwargs["exchange"], kwargs["exchange"]],
                "cal_date": ["20240102", "20240103"],
                "is_open": [1, 1],
                "pretrade_date": ["20231229", "20240102"],
            }
        )

    def fund_basic(self, **kwargs: Any) -> pd.DataFrame:
        del kwargs
        return pd.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "name": ["沪深300ETF"],
                "management": ["测试基金公司"],
                "fund_type": ["股票型"],
                "list_date": ["20120528"],
                "delist_date": [None],
            }
        )

    def fund_daily(self, **kwargs: Any) -> pd.DataFrame:
        if kwargs["offset"]:
            return pd.DataFrame(columns=["ts_code", "trade_date", "close"])
        return pd.DataFrame(
            {
                "ts_code": [kwargs["ts_code"], kwargs["ts_code"]],
                "trade_date": ["20240103", "20240102"],
                "close": [11.0, 10.0],
            }
        )

    def fund_adj(self, **kwargs: Any) -> pd.DataFrame:
        if kwargs["offset"]:
            return pd.DataFrame(columns=["ts_code", "trade_date", "adj_factor"])
        return pd.DataFrame(
            {
                "ts_code": [kwargs["ts_code"], kwargs["ts_code"]],
                "trade_date": ["20240103", "20240102"],
                "adj_factor": [2.0, 1.0],
            }
        )


def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["510300.SS"],
            "tushare_symbol": ["510300.SH"],
            "name": ["沪深300ETF"],
            "start_date": [pd.Timestamp("2012-05-28")],
        }
    )


def test_adjust_fund_close_uses_factor_and_sorts_dates() -> None:
    daily = pd.DataFrame({"trade_date": ["20240103", "20240102"], "close": [11.0, 10.0]})
    adjustments = pd.DataFrame({"trade_date": ["20240103", "20240102"], "adj_factor": [2.0, 1.0]})

    adjusted = adjust_fund_close(daily, adjustments)

    assert adjusted.to_dict() == {
        pd.Timestamp("2024-01-02"): 10.0,
        pd.Timestamp("2024-01-03"): 22.0,
    }
    assert adjusted.index.is_monotonic_increasing


def test_adjust_fund_close_rejects_duplicate_dates() -> None:
    daily = pd.DataFrame({"trade_date": ["20240102", "20240102"], "close": [10.0, 10.0]})
    adjustments = pd.DataFrame({"trade_date": ["20240102"], "adj_factor": [1.0]})

    with pytest.raises(ValueError, match="重复交易日期"):
        adjust_fund_close(daily, adjustments)


def test_download_and_write_records_provenance_and_quality(tmp_path: Path) -> None:
    dataset = download_tushare_dataset(
        FakeTushareApi(),
        _universe(),
        "20240102",
        "20240103",
        downloaded_at="2024-01-04T00:00:00+00:00",
    )

    assert list(dataset.prices.columns) == ["510300.SS"]
    assert dataset.prices.loc["2024-01-03", "510300.SS"] == 22.0
    record = dataset.provenance["symbols"][0]
    assert record["source"] == "Tushare Pro"
    assert record["request_parameters"]["fund_daily"]["ts_code"] == "510300.SH"
    assert record["request_parameters"]["fund_adj"]["page_size"] == 2000
    assert record["adjustment_type"] == ADJUSTMENT_TYPE
    assert record["data_timestamp"] == "2024-01-03"
    assert record["download_timestamp"] == "2024-01-04T00:00:00+00:00"
    assert dataset.provenance["quality_checks"]["缺失值未填零或猜测"] is True
    assert dataset.provenance["quality_checks"]["配置上市日期与 Tushare 元数据一致"] is True
    assert (
        dataset.provenance["quality_checks"]["逐标的结果"]["510300.SS"]["上市后区间缺失日期"] == []
    )

    write_tushare_dataset(dataset, tmp_path)

    prices = (tmp_path / "etf_adjusted_close.csv").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "provenance.json").read_text(encoding="utf-8"))
    assert prices == "date,510300.SS\n2024-01-02,10.00000000\n2024-01-03,22.00000000\n"
    assert len(manifest["files"]["etf_adjusted_close.csv"]["sha256"]) == 64


def test_download_rejects_configured_listing_date_mismatch() -> None:
    universe = _universe()
    universe.loc[0, "start_date"] = pd.Timestamp("2012-05-29")

    with pytest.raises(ValueError, match="上市日期不一致"):
        download_tushare_dataset(
            FakeTushareApi(),
            universe,
            "20240102",
            "20240103",
            downloaded_at="2024-01-04T00:00:00+00:00",
        )


def test_download_rejects_invalid_request_dates() -> None:
    with pytest.raises(ValueError, match="YYYYMMDD"):
        download_tushare_dataset(FakeTushareApi(), _universe(), "2024-01-02", "20240103")
