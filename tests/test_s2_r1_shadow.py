import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from research.experiments import run_s2_r1_shadow as shadow
from tacticore.data.prices import load_price_csv

ROOT = Path(__file__).resolve().parents[1]


def _write_vintage(
    tmp_path: Path, *, overlap_multiplier: float = 1.0, future: bool = False
) -> Path:
    historical_prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    historical_calendar = shadow.load_calendar(ROOT / "data/canonical/trading_calendar.csv")
    overlap_date = historical_prices.index[-1]
    future_dates = pd.to_datetime(["2026-09-29", "2026-09-30"])
    if future:
        future_dates = future_dates.append(pd.DatetimeIndex([pd.Timestamp("2026-10-01")]))
    prospective_prices = pd.DataFrame(
        [historical_prices.iloc[-1].to_numpy()] * len(future_dates),
        index=future_dates,
        columns=historical_prices.columns,
    )
    prospective_prices.iloc[-1] *= 1.01
    prices = pd.concat(
        [historical_prices.loc[[overlap_date]] * overlap_multiplier, prospective_prices]
    )
    calendar = pd.concat(
        [historical_calendar.loc[[overlap_date]], historical_calendar.reindex(future_dates)]
    )
    calendar = calendar.fillna(1).astype(int)
    vintage = tmp_path / "2026-09-30"
    vintage.mkdir()
    prices.to_csv(vintage / "etf_adjusted_close.csv", index_label="date")
    calendar.to_csv(vintage / "trading_calendar.csv", index_label="date")
    (vintage / "provenance.json").write_text(
        json.dumps({"vintage": vintage.name}), encoding="utf-8"
    )
    return vintage


def test_candidate_manifest_matches_frozen_repository_inputs() -> None:
    manifest = shadow.load_manifest()

    shadow.verify_candidate(manifest)

    assert manifest["candidate_id"] == "S2_R1"
    assert manifest["strategy_semantics"]["trend_window"] == 200
    assert pd.Timestamp(manifest["prospective_start"]) > pd.Timestamp(manifest["historical_cutoff"])
    assert shadow.decision_record_count() == 0


def test_shadow_decision_uses_only_as_of_vintage_data(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path)
    as_of = pd.Timestamp("2026-09-30")

    prices, _, vintage_hash = shadow.load_prospective_inputs(vintage, manifest, as_of=as_of)
    record = shadow.build_decision_record(
        prices,
        manifest,
        as_of=as_of,
        vintage_identifier=vintage.name,
        prospective_data_hash=vintage_hash,
        manifest_hash=shadow.sha256_file(shadow.MANIFEST_PATH),
        generated_at="2026-09-30T16:00:00+00:00",
    )

    assert record is not None
    assert record["signal_date"] == "2026-09-30"
    assert record["execution_date"] == ""
    assert record["execution_status"] == "PENDING_NEXT_CANONICAL_OBSERVATION"
    assert record["candidate_id"] == "S2_R1"


def test_vintage_cannot_overwrite_different_historical_data(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, overlap_multiplier=1.01)

    with pytest.raises(ValueError, match="重叠但内容不同"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=pd.Timestamp("2026-09-30"))


def test_vintage_after_as_of_is_rejected_instead_of_leaking(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, future=True)

    with pytest.raises(ValueError, match="as-of 之后"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=pd.Timestamp("2026-09-30"))


def test_mid_month_vintage_cannot_fabricate_a_month_end_decision(tmp_path: Path) -> None:
    vintage = _write_vintage(tmp_path)
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv").loc[:"2026-09-29"]

    with pytest.raises(ValueError, match="未覆盖完整 signal 月"):
        shadow.validate_month_end_review(calendar, pd.Timestamp("2026-09-29"))


def test_observation_append_is_duplicate_safe(tmp_path: Path) -> None:
    observations = tmp_path / "observations.csv"
    with observations.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=shadow.RECORD_FIELDS).writeheader()
    record = {field: "" for field in shadow.RECORD_FIELDS}
    record.update({"candidate_id": "S2_R1", "record_type": "decision", "signal_date": "2026-09-30"})

    shadow.append_decision_record(record, observations)

    assert shadow.decision_record_count(observations) == 1

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_decision_record(record, observations)
