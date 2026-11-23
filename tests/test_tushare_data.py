import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import tacticore.data.tushare as tushare
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


def test_delisted_fund_metadata_is_accepted_from_status_d() -> None:
    """标的池可以包含已摘牌 ETF：fund_basic 必须查询 status="D" 而不是只查 L。"""

    class DelistedOnly(FakeTushareApi):
        def fund_basic(self, **kwargs: Any) -> pd.DataFrame:
            if kwargs.get("status") != "D":
                return pd.DataFrame(
                    columns=[
                        "ts_code",
                        "name",
                        "management",
                        "fund_type",
                        "list_date",
                        "delist_date",
                    ]
                )
            frame = super().fund_basic(**kwargs)
            frame["delist_date"] = ["20231229"]
            return frame

    dataset = download_tushare_dataset(
        DelistedOnly(),
        _universe(),
        "20240102",
        "20240103",
        downloaded_at="2024-01-04T00:00:00+00:00",
    )

    record = dataset.provenance["symbols"][0]
    assert record["metadata"]["request_status"] == "D"
    assert record["metadata"]["delist_date"] == "20231229"
    assert [request["status"] for request in dataset.provenance["metadata_requests"]] == [
        "L",
        "D",
    ]


def test_conflicting_l_and_d_fund_metadata_is_rejected() -> None:
    class Conflicting(FakeTushareApi):
        def fund_basic(self, **kwargs: Any) -> pd.DataFrame:
            frame = super().fund_basic(**kwargs)
            if kwargs.get("status") == "D":
                frame["list_date"] = "20120529"
                frame["delist_date"] = "20231229"
            return frame

    with pytest.raises(ValueError, match="身份字段不一致"):
        download_tushare_dataset(
            Conflicting(),
            _universe(),
            "20240102",
            "20240103",
            downloaded_at="2024-01-04T00:00:00+00:00",
        )


@pytest.mark.parametrize(
    "problem",
    [
        "missing_one",
        "missing_both",
        "duplicate",
        "extra",
        "wrong_exchange",
        "null_exchange",
        "missing_exchange",
        "fractional",
        "null_state",
        "invalid_date",
    ],
)
def test_calendar_rejects_incomplete_or_invalid_exchange_data(problem: str) -> None:
    class BrokenCalendar(FakeTushareApi):
        def trade_cal(self, **kwargs: Any) -> pd.DataFrame:
            frame = super().trade_cal(**kwargs)
            if problem == "missing_both" or (
                problem == "missing_one" and kwargs["exchange"] == "SSE"
            ):
                return frame.iloc[:1]
            if kwargs["exchange"] != "SSE":
                return frame
            if problem == "duplicate":
                return pd.concat([frame, frame.iloc[:1]], ignore_index=True)
            if problem == "extra":
                frame.loc[1, "cal_date"] = "20240104"
            elif problem == "wrong_exchange":
                frame.loc[0, "exchange"] = "SZSE"
            elif problem == "null_exchange":
                frame.loc[0, "exchange"] = None
            elif problem == "missing_exchange":
                return frame.drop(columns="exchange")
            elif problem == "fractional":
                frame["is_open"] = [0.5, 1.0]
            elif problem == "null_state":
                frame.loc[0, "is_open"] = None
            elif problem == "invalid_date":
                frame.loc[0, "cal_date"] = "2024010x"
            return frame

    with pytest.raises(ValueError):
        download_tushare_dataset(BrokenCalendar(), _universe(), "20240102", "20240103")


def test_download_timestamp_is_after_all_price_and_factor_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    completion = datetime(2024, 1, 3, 7, 0, 0, 123456, tzinfo=timezone.utc)

    class Api(FakeTushareApi):
        def fund_daily(self, **kwargs: Any) -> pd.DataFrame:
            events.append("daily")
            return super().fund_daily(**kwargs)

        def fund_adj(self, **kwargs: Any) -> pd.DataFrame:
            events.append("adjustment")
            return super().fund_adj(**kwargs)

    class Clock:
        @staticmethod
        def now(tz: Any) -> datetime:
            assert tz == timezone.utc
            assert events == ["daily", "adjustment"]
            return completion

    monkeypatch.setattr(tushare, "datetime", Clock)
    # Request date parsing still uses strptime.
    monkeypatch.setattr(Clock, "strptime", staticmethod(datetime.strptime), raising=False)
    dataset = download_tushare_dataset(Api(), _universe(), "20240102", "20240103")
    assert dataset.provenance["download_timestamp"] == completion.isoformat()
    assert dataset.provenance["symbols"][0]["download_timestamp"] == completion.isoformat()


def test_download_rejects_invalid_request_dates() -> None:
    with pytest.raises(ValueError, match="YYYYMMDD"):
        download_tushare_dataset(FakeTushareApi(), _universe(), "2024-01-02", "20240103")
