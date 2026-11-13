"""前瞻 vintage snapshot 编排的 fail-closed 守卫测试（不联网、不接触真实 2026-09 数据）。"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from conftest import (
    MockTushareApi,
    build_candidate_repo,
    canonical_calendar,
    canonical_prices,
    write_observations_header,
    write_prospective_vintage,
)

from research.experiments import freeze_prospective_vintage as freeze
from research.experiments import prospective_evidence as pe
from research.experiments import run_s2_r1_shadow as s2
from research.experiments import run_s4c_r1_shadow as s4c
from tacticore.data.tushare import ADJUSTMENT_TYPE, SOURCE

AS_OF = pd.Timestamp("2026-09-30")
SEAL = "2026-09-30T08:00:00+00:00"


class _UnusedApi:
    """守卫在下载之前就会失败；任何 API 调用都说明顺序错误。"""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"守卫失败前不得调用 Tushare endpoint: {name}")


def test_unknown_candidate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="未知 candidate"):
        freeze.freeze_vintage(_UnusedApi(), candidate_id="X_R9", as_of="2026-09-30", root=tmp_path)


def test_pre_cutoff_as_of_is_rejected_before_download(tmp_path: Path) -> None:
    root = build_candidate_repo(tmp_path / "repo", "S2_R1")

    with pytest.raises(ValueError, match="historical_cutoff"):
        freeze.freeze_vintage(_UnusedApi(), candidate_id="S2_R1", as_of="2026-08-31", root=root)


def test_existing_vintage_directory_refuses_overwrite(tmp_path: Path) -> None:
    root = build_candidate_repo(tmp_path / "repo", "S2_R1")
    write_prospective_vintage(
        root / "research/shadow/s2_r1/vintages/2026-09-30", as_of="2026-09-30"
    )

    with pytest.raises(ValueError, match="拒绝覆盖"):
        freeze.freeze_vintage(_UnusedApi(), candidate_id="S2_R1", as_of="2026-09-30", root=root)


def test_snapshot_target_is_the_candidate_canonical_vintage_path() -> None:
    assert freeze.CANDIDATES == {
        "S2_R1": "research/shadow/s2_r1",
        "S4C_R1": "research/shadow/s4c_r1",
    }


# --- production CLI authorization ----------------------------------------------------------


def test_production_cli_exposes_only_candidate_and_as_of() -> None:
    options = {
        option
        for action in freeze.build_parser()._actions
        for option in action.option_strings
        if option.startswith("--")
    }

    assert {"--candidate", "--as-of"} <= options
    assert {"--universe", "--start-date", "--output-dir"}.isdisjoint(options)


@pytest.mark.parametrize("option", ["--universe", "--start-date"])
def test_production_cli_rejects_universe_and_start_date_overrides(
    monkeypatch: pytest.MonkeyPatch, option: str
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "unused-in-this-test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "freeze_prospective_vintage",
            "--candidate",
            "S2_R1",
            "--as-of",
            "2026-09-30",
            option,
            "x",
        ],
    )

    with pytest.raises(SystemExit):
        freeze.main()


def test_snapshot_entry_point_has_no_universe_or_start_override() -> None:
    """不允许存在第二个生产注入面：callable 参数同样不得暴露 universe / start date。"""
    parameters = set(inspect.signature(freeze.freeze_vintage).parameters)

    assert "universe_path" not in parameters
    assert "start_date" not in parameters
    assert "universe" not in parameters
    assert parameters == {"api", "candidate_id", "as_of", "root", "downloaded_at"}


# --- frozen universe provenance attacks ----------------------------------------------------


def _repo(tmp_path: Path, candidate_id: str = "S2_R1") -> Path:
    return build_candidate_repo(tmp_path / "repo", candidate_id)


def _frozen_vintage(root: Path, candidate_id: str = "S2_R1") -> Path:
    shadow_dir = freeze.CANDIDATES[candidate_id]
    return write_prospective_vintage(
        root / shadow_dir / "vintages" / AS_OF.date().isoformat(), as_of=AS_OF.date().isoformat()
    )


def _load(root: Path, vintage_dir: Path, candidate_id: str = "S2_R1") -> pe.ProspectiveVintage:
    shadow_dir = freeze.CANDIDATES[candidate_id]
    manifest = json.loads((root / shadow_dir / "candidate_manifest.json").read_text("utf-8"))
    return pe.load_prospective_vintage(
        vintage_dir,
        as_of=AS_OF,
        historical_cutoff=pd.Timestamp(manifest["historical_cutoff"]),
        historical_prices=canonical_prices(root),
        historical_calendar=canonical_calendar(root),
        expected_source=SOURCE,
        expected_adjustment_type=ADJUSTMENT_TYPE,
        frozen_universe=pe.load_frozen_universe(root),
    )


def _mutate_provenance(vintage_dir: Path, mutate: Any) -> None:
    path = vintage_dir / "provenance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_intact_synthetic_vintage_passes_the_frozen_universe_gate(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    vintage = _load(root, _frozen_vintage(root))

    assert vintage.provenance.price_as_of == AS_OF


def test_provider_identity_swap_between_two_valid_members_is_rejected(tmp_path: Path) -> None:
    """symbol 集合不变，只把两个合法标的的 Tushare 代码对调，也必须被拒绝。"""
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def swap(payload: dict[str, Any]) -> None:
        first, second = payload["symbols"][0], payload["symbols"][1]
        first["tushare_symbol"], second["tushare_symbol"] = (
            second["tushare_symbol"],
            first["tushare_symbol"],
        )

    _mutate_provenance(vintage_dir, swap)

    with pytest.raises(ValueError, match="tushare_symbol 与冻结 universe 不一致"):
        _load(root, vintage_dir)


@pytest.mark.parametrize("endpoint", ["fund_daily", "fund_adj"])
def test_price_endpoint_ts_code_mismatch_is_rejected(tmp_path: Path, endpoint: str) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["symbols"][0]["request_parameters"][endpoint]["ts_code"] = "159915.SZ"

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="request ts_code 与冻结 universe"):
        _load(root, vintage_dir)


def test_frozen_start_date_drift_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["symbols"][0]["request_parameters"]["fund_daily"]["start_date"] = "20130101"

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="request start_date"):
        _load(root, vintage_dir)


def test_snapshot_start_date_override_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["start_date"] = "20130101"

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="canonical 起点"):
        _load(root, vintage_dir)


def test_frozen_universe_sha_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["universe"]["sha256"] = "0" * 64

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="SHA-256 与冻结 repository universe 不一致"):
        _load(root, vintage_dir)


def test_universe_mapping_list_date_drift_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["universe"]["symbols"][0]["list_date"] = "20120101"

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="list_date 与配置起点不一致"):
        _load(root, vintage_dir)


def test_per_symbol_configured_list_date_drift_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["symbols"][0]["metadata"]["list_date"] = "20120101"

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="list_date 与冻结 universe 配置起点不一致"):
        _load(root, vintage_dir)


def test_missing_universe_symbol_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["universe"]["symbols"].pop()

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="symbol 集合与冻结 universe 不一致"):
        _load(root, vintage_dir)


def test_unexpected_universe_symbol_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["universe"]["symbols"].append(
            {"symbol": "999999.SS", "tushare_symbol": "999999.SH", "list_date": "20120101"}
        )

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="symbol 集合与冻结 universe 不一致"):
        _load(root, vintage_dir)


def test_duplicate_universe_mapping_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        payload["universe"]["symbols"].append(dict(payload["universe"]["symbols"][0]))

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="标的映射重复"):
        _load(root, vintage_dir)


def test_provenance_record_outside_the_frozen_universe_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    vintage_dir = _frozen_vintage(root)

    def retarget(payload: dict[str, Any]) -> None:
        extra = dict(payload["symbols"][0])
        extra["symbol"] = "999999.SS"
        payload["symbols"].append(extra)

    _mutate_provenance(vintage_dir, retarget)

    with pytest.raises(ValueError, match="冻结 universe 之外的 symbol"):
        _load(root, vintage_dir)


# --- mocked end-to-end snapshot success path ----------------------------------------------


@pytest.mark.parametrize("candidate_id", ["S2_R1", "S4C_R1"])
@pytest.mark.parametrize(
    "relative_path",
    ["config/universe.csv", "data/canonical/provenance.json"],
)
def test_manifest_frozen_identity_drift_is_rejected_before_any_download(
    tmp_path: Path, candidate_id: str, relative_path: str
) -> None:
    """结构仍然合法、但已不等于 manifest 冻结身份的 repository 契约必须先被拒绝。"""
    root = _repo(tmp_path, candidate_id)
    target = root / relative_path
    if relative_path.endswith(".csv"):
        text = target.read_text(encoding="utf-8")
        assert "510300.SS" in text
        target.write_text(text.replace("510300.SS", "510301.SS", 1), encoding="utf-8")
    else:
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["start_date"] = "20130101"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="与 candidate manifest 冻结身份不一致"):
        freeze.freeze_vintage(_UnusedApi(), candidate_id=candidate_id, as_of=AS_OF, root=root)

    shadow_dir = freeze.CANDIDATES[candidate_id]
    assert not (root / shadow_dir / "vintages").exists()


def test_snapshot_requires_both_repository_identity_hashes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    manifest = freeze.candidate_manifest("research/shadow/s2_r1", root)
    manifest.pop("file_hashes")

    with pytest.raises(ValueError, match="未冻结"):
        freeze.require_frozen_repository_identity(manifest, root)


def test_mocked_tushare_snapshot_publishes_and_feeds_both_decisions(tmp_path: Path) -> None:
    """真实 downloader 的成功路径：mock Tushare → freeze → validate → publish → decision。"""
    root = _repo(tmp_path, "S2_R1")
    build_candidate_repo(root, "S4C_R1")
    write_observations_header(root / "research/shadow/s2_r1/observations.csv", s2.RECORD_FIELDS)
    write_observations_header(root / "research/shadow/s4c_r1/observations.csv", s4c.RECORD_FIELDS)
    api = MockTushareApi()

    download_time = "2026-09-30T07:30:00+00:00"
    s2_vintage = freeze.freeze_vintage(
        api, candidate_id="S2_R1", as_of=AS_OF, root=root, downloaded_at=download_time
    )
    s4c_vintage = freeze.freeze_vintage(
        api, candidate_id="S4C_R1", as_of=AS_OF, root=root, downloaded_at=download_time
    )

    assert s2_vintage == root / "research/shadow/s2_r1/vintages/2026-09-30"
    assert s4c_vintage == root / "research/shadow/s4c_r1/vintages/2026-09-30"
    provenance = json.loads((s2_vintage / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["universe"]["sha256"] == pe.load_frozen_universe(root).sha256

    s2_record = s2.run_decision(AS_OF, root=root, decision_seal_time=SEAL)
    s4c_record = s4c.run_decision(AS_OF, root=root, decision_seal_time=SEAL)

    assert s2_record["record_type"] == "decision"
    assert s4c_record["record_type"] == "decision"
    assert s2_record["vintage_identifier"] == "2026-09-30"
    assert s4c_record["vintage_identifier"] == "2026-09-30"
    assert s2.decision_record_count(s2.canonical_observations_path(root)) == 1
    assert s4c.decision_record_count(s4c.canonical_observations_path(root)) == 1


class _MonthEndApi(MockTushareApi):
    def __init__(self, *, missing: bool = False, future_open: bool = False) -> None:
        super().__init__(as_of="2026-10-30")
        self.missing = missing
        self.future_open = future_open
        self.requests: list[dict[str, Any]] = []

    def trade_cal(self, **kwargs: Any) -> pd.DataFrame:
        self.requests.append(kwargs.copy())
        if kwargs["start_date"] == "20261031":
            if self.missing:
                return pd.DataFrame(columns=["exchange", "cal_date", "is_open", "pretrade_date"])
            return pd.DataFrame(
                [
                    {
                        "exchange": kwargs["exchange"],
                        "cal_date": "20261031",
                        "is_open": int(self.future_open),
                        "pretrade_date": "20261030",
                    }
                ]
            )
        return super().trade_cal(**kwargs)


@pytest.mark.parametrize("candidate_id", ["S2_R1", "S4C_R1"])
def test_snapshot_extends_calendar_not_prices_for_weekend_month_end(
    tmp_path: Path, candidate_id: str
) -> None:
    root = _repo(tmp_path, candidate_id)
    api = _MonthEndApi()
    vintage = freeze.freeze_vintage(
        api,
        candidate_id=candidate_id,
        as_of="2026-10-30",
        root=root,
        downloaded_at="2026-10-30T07:30:00+00:00",
    )
    prices = pd.read_csv(vintage / "etf_adjusted_close.csv", index_col=0, parse_dates=True)
    calendar = pd.read_csv(vintage / "trading_calendar.csv", index_col=0, parse_dates=True)
    provenance = json.loads((vintage / "provenance.json").read_text())
    assert prices.index.max() == pd.Timestamp("2026-10-30")
    assert calendar.index.max() == pd.Timestamp("2026-10-31")
    assert not calendar.loc["2026-10-31"].any()
    assert provenance["end_date"] == "20261030"
    assert all(
        r["end_date"] == "20261030"
        for symbol in provenance["symbols"]
        for r in symbol["request_parameters"].values()
    )
    assert [r for r in provenance["calendar_requests"] if r["end_date"] == "20261031"] == [
        r for r in api.requests if r["start_date"] == "20261031"
    ]
    if candidate_id == "S2_R1":
        s2.validate_month_end_review(calendar, "2026-10-30")
        write_observations_header(
            root / freeze.CANDIDATES[candidate_id] / "observations.csv", s2.RECORD_FIELDS
        )
        record = s2.run_decision(
            "2026-10-30", root=root, decision_seal_time="2026-10-30T08:00:00+00:00"
        )
    else:
        manifest = freeze.candidate_manifest(freeze.CANDIDATES[candidate_id], root)
        s4c.validate_month_end(calendar, "2026-10-30", manifest)
        write_observations_header(
            root / freeze.CANDIDATES[candidate_id] / "observations.csv", s4c.RECORD_FIELDS
        )
        record = s4c.run_decision(
            "2026-10-30", root=root, decision_seal_time="2026-10-30T08:00:00+00:00"
        )
    assert record["record_type"] == "decision"


@pytest.mark.parametrize("before_close", [True, False])
def test_calendar_timestamp_cannot_replace_price_download_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, before_close: bool
) -> None:
    root = _repo(tmp_path)
    price_time = "2026-10-30T06:59:00+00:00" if before_close else "2026-10-30T07:30:00+00:00"
    original_download = freeze.download_tushare_dataset

    def download(*args: Any, **kwargs: Any) -> Any:
        kwargs["downloaded_at"] = price_time
        return original_download(*args, **kwargs)

    class Clock:
        @staticmethod
        def now(tz: Any) -> Any:
            return pd.Timestamp("2026-10-30T08:00:00+00:00").to_pydatetime()

    monkeypatch.setattr(freeze, "download_tushare_dataset", download)
    monkeypatch.setattr(freeze, "datetime", Clock)
    if before_close:
        with pytest.raises(ValueError, match="早于 signal_close"):
            freeze.freeze_vintage(
                _MonthEndApi(), candidate_id="S2_R1", as_of="2026-10-30", root=root
            )
        assert not (root / "research/shadow/s2_r1/vintages/2026-10-30").exists()
    else:
        vintage = freeze.freeze_vintage(
            _MonthEndApi(), candidate_id="S2_R1", as_of="2026-10-30", root=root
        )
        provenance = json.loads((vintage / "provenance.json").read_text())
        assert provenance["download_timestamp"] == price_time
        assert provenance["calendar_extension_download_timestamp"] == "2026-10-30T08:00:00+00:00"


@pytest.mark.parametrize("api", [_MonthEndApi(missing=True), _MonthEndApi(future_open=True)])
def test_snapshot_rejects_incomplete_or_later_open_calendar_before_publish(
    tmp_path: Path, api: _MonthEndApi
) -> None:
    root = _repo(tmp_path)
    with pytest.raises(ValueError, match="逐日覆盖|最后一个 canonical"):
        freeze.freeze_vintage(
            api,
            candidate_id="S2_R1",
            as_of="2026-10-30",
            root=root,
            downloaded_at="2026-10-30T07:30:00+00:00",
        )
    assert not (root / "research/shadow/s2_r1/vintages/2026-10-30").exists()


def test_failed_mocked_snapshot_leaves_no_canonical_vintage(tmp_path: Path) -> None:
    """snapshot 失败不得留下 staging 或半成品 canonical vintage。"""
    root = _repo(tmp_path)

    class _DriftedApi(MockTushareApi):
        def fund_daily(self, **kwargs: Any) -> pd.DataFrame:
            frame = super().fund_daily(**kwargs)
            frame["ts_code"] = "159915.SZ"
            return frame

    with pytest.raises(ValueError, match="非请求标的"):
        freeze.freeze_vintage(_DriftedApi(), candidate_id="S2_R1", as_of=AS_OF, root=root)

    parent = root / "research/shadow/s2_r1/vintages"
    assert not parent.exists() or not list(parent.iterdir())
