"""离线 fixture 测试：不联网、不使用真实 TUSHARE_TOKEN、不运行真实下载。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import fetch_transfer_data as ftd
import pandas as pd
import pytest

FIXED_TIME = "2026-11-14T00:00:00+00:00"


class FakeTushare:
    """按协议资产生成确定性的假 Tushare 响应。"""

    def __init__(
        self,
        *,
        list_dates: dict[str, str] | None = None,
        missing_daily: dict[str, tuple[str, ...]] | None = None,
        extra_daily: dict[str, tuple[str, ...]] | None = None,
        retain_adj: bool = False,
    ) -> None:
        self.specs = {spec.tushare_code: spec for spec in ftd.ASSETS}
        self.list_dates = {
            spec.tushare_code: list_dates.get(spec.tushare_code, spec.claim or "2013-05-15")
            if list_dates
            else (spec.claim or "2013-05-15")
            for spec in ftd.ASSETS
        }
        self.missing_daily = missing_daily or {}
        self.extra_daily = extra_daily or {}
        self.retain_adj = retain_adj

    def _open_dates(self, start: str, end: str) -> pd.DatetimeIndex:
        dates = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")
        return pd.DatetimeIndex(dates[dates.dayofweek < 5])

    def trade_cal(self, **kwargs: Any) -> pd.DataFrame:
        dates = pd.date_range(pd.Timestamp(kwargs["start_date"]), pd.Timestamp(kwargs["end_date"]))
        return pd.DataFrame(
            {
                "exchange": kwargs["exchange"],
                "cal_date": dates.strftime("%Y%m%d"),
                "is_open": (dates.dayofweek < 5).astype(int),
                "pretrade_date": (dates - pd.Timedelta(days=1)).strftime("%Y%m%d"),
            }
        )

    def fund_basic(self, **kwargs: Any) -> pd.DataFrame:
        columns = ["ts_code", "name", "management", "fund_type", "list_date", "delist_date"]
        if kwargs["status"] != "L":
            return pd.DataFrame(columns=columns)
        return pd.DataFrame(
            [
                {
                    "ts_code": code,
                    "name": f"fixture-{code}",
                    "management": "fixture",
                    "fund_type": "ETF",
                    "list_date": pd.Timestamp(self.list_dates[code]).strftime("%Y%m%d"),
                    "delist_date": None,
                }
                for code in self.specs
            ],
            columns=columns,
        )

    def _page(self, frame: pd.DataFrame, kwargs: dict[str, Any]) -> pd.DataFrame:
        offset, limit = int(kwargs.get("offset", 0)), int(kwargs.get("limit", len(frame) or 1))
        return frame.iloc[offset : offset + limit].reset_index(drop=True)

    def _dates(self, code: str, start: str, end: str) -> pd.DatetimeIndex:
        dates = self._open_dates(start, end)
        listed = pd.Timestamp(self.list_dates[code])
        dates = dates[dates >= listed]
        extra = pd.DatetimeIndex([pd.Timestamp(x) for x in self.extra_daily.get(code, ())])
        missing = {pd.Timestamp(x) for x in self.missing_daily.get(code, ())}
        return pd.DatetimeIndex(sorted((set(dates) | set(extra)) - missing))

    def fund_daily(self, **kwargs: Any) -> pd.DataFrame:
        code = kwargs["ts_code"]
        dates = self._dates(code, kwargs["start_date"], kwargs["end_date"])
        frame = pd.DataFrame(
            {
                "ts_code": code,
                "trade_date": dates.strftime("%Y%m%d"),
                "close": 10.0 + pd.Series(range(len(dates)), dtype=float) / 100.0,
            }
        )
        return self._page(frame, kwargs)

    def fund_adj(self, **kwargs: Any) -> pd.DataFrame:
        code = kwargs["ts_code"]
        dates = self._dates(code, kwargs["start_date"], kwargs["end_date"])
        if self.retain_adj:
            dates = dates.union(
                pd.DatetimeIndex([pd.Timestamp(x) for x in self.missing_daily.get(code, ())])
            )
        frame = pd.DataFrame(
            {"ts_code": code, "trade_date": dates.strftime("%Y%m%d"), "adj_factor": 2.0}
        )
        return self._page(frame, kwargs)


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakeTushare, name: str = "snap"):
    monkeypatch.setattr(ftd, "WARMUP", 3)
    return ftd.run_audit(
        fake,
        output_dir=tmp_path / name,
        start_date="20240101",
        end_date="20240112",
        downloaded_at=FIXED_TIME,
    )


def test_pass_snapshot_provenance_and_adjusted_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(tmp_path, monkeypatch, FakeTushare())

    assert result["decision"] == "PASS"
    snapshot = tmp_path / "snap"
    provenance = json.loads((snapshot / "provenance.json").read_text("utf-8"))
    assert provenance["source"] == "Tushare Pro"
    assert provenance["download_timestamp"] == FIXED_TIME
    assert provenance["token_handling"].startswith("TUSHARE_TOKEN")
    assert provenance["endpoints"]["fund_daily"]["fields"] == ftd.DAILY_FIELDS
    assert len(provenance["code_mapping"]) == 8
    assert {spec.tushare_code for spec in ftd.ASSETS if spec.requirement == "MAIN"} == {
        "512890.SH",
        "515450.SH",
        "511360.SH",
        "511010.SH",
        "518880.SH",
    }
    assert set(provenance["missing_and_lifecycle_audit"]) == {
        spec.tushare_code for spec in ftd.ASSETS
    }
    for name, info in {**provenance["files"], **provenance["raw_files"]}.items():
        path = snapshot / name
        assert path.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == info["sha256"]
    adjusted = pd.read_csv(snapshot / "etf_adjusted_close.csv")
    assert adjusted.loc[0, "512890.SS"] == pytest.approx(20.0)
    audit = json.loads((snapshot / "ACCOUNT_TRANSFER_DATA_AUDIT_V1.json").read_text("utf-8"))
    assert audit["decision"] == "PASS"
    assert audit["provenance_sha256"] == result["provenance_sha256"]


def test_missing_day_is_no_backtest_and_remains_blank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(tmp_path, monkeypatch, FakeTushare(missing_daily={"512890.SH": ("20240104",)}))

    assert result["decision"] == "NO_BACKTEST"
    assert any(item["code"] == "MISSING_DAILY_OBSERVATIONS" for item in result["blockers"])
    asset = next(item for item in result["assets"] if item["tushare_code"] == "512890.SH")
    assert "2024-01-04" in asset["lifecycle"]["missing_daily_dates"]
    adjusted = pd.read_csv(tmp_path / "snap/etf_adjusted_close.csv", index_col="date")
    value = adjusted.loc["2024-01-04", "512890.SS"]
    assert pd.isna(value)


@pytest.mark.parametrize("code", ["512890.SH", "513100.SH"])
def test_isolated_missing_daily_with_factor_warns_without_filling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    monkeypatch.setattr(ftd, "WARMUP", 3)
    result = ftd.run_audit(
        FakeTushare(missing_daily={code: ("20240201",)}, retain_adj=True),
        output_dir=tmp_path / "snap",
        start_date="20240101",
        end_date="20241231",
        downloaded_at=FIXED_TIME,
    )
    assert result["decision"] == "PASS"
    assert any(
        w["code"] == "SUSPECTED_SUSPENSION_UNVERIFIED" and w["asset"] == code
        for w in result["warnings"]
    )
    symbol = next(s.symbol for s in ftd.ASSETS if s.tushare_code == code)
    prices = pd.read_csv(tmp_path / "snap/etf_adjusted_close.csv", index_col="date")
    assert pd.isna(prices.loc["2024-02-01", symbol])


def test_consecutive_missing_main_is_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ftd, "WARMUP", 3)
    result = ftd.run_audit(
        FakeTushare(missing_daily={"512890.SH": ("20240201", "20240202")}, retain_adj=True),
        output_dir=tmp_path / "snap",
        start_date="20240101",
        end_date="20241231",
        downloaded_at=FIXED_TIME,
    )
    assert result["decision"] == "NO_BACKTEST"
    assert any(b["code"] == "MISSING_DAILY_OBSERVATIONS" for b in result["blockers"])


def test_non_main_blocker_does_not_block_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(tmp_path, monkeypatch, FakeTushare(missing_daily={"513100.SH": ("20240104",)}))
    assert result["decision"] == "PASS"
    assert any(b["asset"] == "513100.SH" for b in result["blockers"])
    assert (
        next(a for a in result["assets"] if a["tushare_code"] == "513100.SH")["status"]
        == "NO_BACKTEST"
    )


def test_non_main_invalid_rows_are_reported_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DuplicateApi(FakeTushare):
        def fund_daily(self, **kwargs: Any) -> pd.DataFrame:
            frame = super().fund_daily(**kwargs)
            if kwargs["ts_code"] == "513100.SH" and not frame.empty:
                return pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
            return frame

    result = _run(tmp_path, monkeypatch, DuplicateApi())
    assert result["decision"] == "PASS"
    assert any(
        b["asset"] == "513100.SH" and b["code"] == "ASSET_AUDIT_FAILED" for b in result["blockers"]
    )


def test_claim_mismatch_is_no_backtest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(tmp_path, monkeypatch, FakeTushare(list_dates={"512890.SH": "2019-01-17"}))

    assert result["decision"] == "NO_BACKTEST"
    assert any(item["code"] == "LIST_DATE_CLAIM_MISMATCH" for item in result["blockers"])


def test_observation_outside_lifecycle_is_no_backtest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ftd, "WARMUP", 3)
    result = ftd.run_audit(
        FakeTushare(extra_daily={"512890.SH": ("20190117",)}),
        output_dir=tmp_path / "snap",
        start_date="20190101",
        end_date="20190131",
        downloaded_at=FIXED_TIME,
    )

    assert result["decision"] == "NO_BACKTEST"
    assert any(item["code"] == "OBSERVATION_OUTSIDE_LIFECYCLE" for item in result["blockers"])


def test_token_missing_makes_no_network_or_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    code = ftd.main(["--output-dir", str(tmp_path / "snap")])

    assert code == 1
    assert not (tmp_path / "snap").exists()
    output = capsys.readouterr().out
    assert "TUSHARE_TOKEN_MISSING" in output
    assert json.loads(output)["decision"] == "NO_BACKTEST"


def test_main_pass_does_not_write_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "never-print-this-token"
    monkeypatch.setattr(ftd, "WARMUP", 3)
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    target = tmp_path / "snap"

    code = ftd.main(["--output-dir", str(target)], api_factory=lambda token: FakeTushare())

    assert code == 0
    output = capsys.readouterr().out
    assert secret not in output
    assert json.loads(output)["decision"] == "PASS"
    for path in target.rglob("*"):
        if path.is_file():
            assert secret not in path.read_bytes().decode("utf-8", errors="ignore")


def test_api_error_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "unit-test-secret-token"

    class Exploding:
        def __getattr__(self, name: str):
            def fail(**kwargs: Any) -> pd.DataFrame:
                raise RuntimeError(f"auth failed for {secret}")

            return fail

    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    code = ftd.main(["--output-dir", str(tmp_path / "snap")], api_factory=lambda token: Exploding())

    assert code == 1
    output = capsys.readouterr().out
    assert secret not in output
    assert "[REDACTED]" in output


def test_refuses_canonical_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy")
    code = ftd.main(
        ["--output-dir", str(ftd.CANONICAL_DIR)], api_factory=lambda token: FakeTushare()
    )

    assert code == 1
    assert json.loads(capsys.readouterr().out)["blockers"][0]["code"] == "OUTPUT_IS_CANONICAL"


def test_refuses_nonempty_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "snap"
    target.mkdir()
    (target / "existing.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy")
    code = ftd.main(["--output-dir", str(target)], api_factory=lambda token: FakeTushare())

    assert code == 1
    assert json.loads(capsys.readouterr().out)["blockers"][0]["code"] == "OUTPUT_DIR_NOT_EMPTY"
    assert (target / "existing.txt").read_text("utf-8") == "keep"


def test_snapshot_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ftd, "WARMUP", 3)
    first = ftd.run_audit(
        FakeTushare(),
        output_dir=tmp_path / "a",
        start_date="20240101",
        end_date="20240112",
        downloaded_at=FIXED_TIME,
    )
    second = ftd.run_audit(
        FakeTushare(),
        output_dir=tmp_path / "b",
        start_date="20240101",
        end_date="20240112",
        downloaded_at=FIXED_TIME,
    )

    assert first["files"] == second["files"]
    assert first["provenance_sha256"] == second["provenance_sha256"]
