"""共享前瞻证据原语的纯验证测试：as-of 语义、temporal seal、文件身份与 append-only。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from conftest import write_observations_header

from research.experiments import prospective_evidence as pe

SIGNAL = pd.Timestamp("2026-09-30")


def _calendar(dates: list[str]) -> pd.DataFrame:
    index = pd.DatetimeIndex(pd.to_datetime(dates), name="date")
    return pd.DataFrame({"sse_open": 1, "szse_open": 1}, index=index).astype(int)


# --- instant and as-of semantics ----------------------------------------------------------


def test_signal_close_is_1500_asia_shanghai() -> None:
    close = pe.signal_close_instant(SIGNAL)

    assert close == pd.Timestamp("2026-09-30T15:00:00+08:00")
    assert close.tz_convert("UTC") == pd.Timestamp("2026-09-30T07:00:00+00:00")


def test_next_boundary_uses_the_published_exchange_calendar() -> None:
    calendar = _calendar(["2026-09-29", "2026-09-30", "2026-10-09"])

    boundary = pe.next_canonical_execution_boundary(calendar, SIGNAL)

    assert boundary == pd.Timestamp("2026-10-09T00:00:00+08:00")


def test_next_boundary_falls_back_to_the_next_calendar_day() -> None:
    calendar = _calendar(["2026-09-29", "2026-09-30"])

    boundary = pe.next_canonical_execution_boundary(calendar, SIGNAL)

    assert boundary == pd.Timestamp("2026-10-01T00:00:00+08:00")


def test_signal_day_seal_accepts_a_legal_instant_chain() -> None:
    calendar = _calendar(["2026-09-29", "2026-09-30", "2026-10-09"])

    pe.verify_signal_day_seal(
        signal_date=SIGNAL,
        download_timestamp="2026-09-30T07:30:00+00:00",
        decision_seal_time="2026-09-30T08:00:00+00:00",
        calendar=calendar,
    )


@pytest.mark.parametrize(
    ("download", "seal", "match"),
    [
        ("2026-09-30T06:00:00+00:00", "2026-09-30T08:00:00+00:00", "signal_close"),
        ("2026-09-30T07:30:00+00:00", "2026-09-30T06:30:00+00:00", "signal_close"),
        ("2026-09-30T07:30:00+00:00", "2026-09-30T07:15:00+00:00", "download_timestamp"),
        ("2026-09-30T07:30:00+00:00", "2026-09-30T16:00:00+00:00", "signal_date"),
        ("2026-09-30T07:30:00+00:00", "2026-10-09T00:30:00+00:00", "signal_date"),
    ],
)
def test_signal_day_seal_rejects_illegal_instant_chains(
    download: str, seal: str, match: str
) -> None:
    calendar = _calendar(["2026-09-29", "2026-09-30", "2026-10-09"])

    with pytest.raises(ValueError, match=match):
        pe.verify_signal_day_seal(
            signal_date=SIGNAL,
            download_timestamp=download,
            decision_seal_time=seal,
            calendar=calendar,
        )


@pytest.mark.parametrize("value", ["2026-09-30T08:00:00", "", "not-a-timestamp", None])
def test_naive_or_unparseable_instants_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="必须带时区|不可解析"):
        pe.require_timezone_aware_instant(value, label="decision_seal_time")


# --- canonical vintage location ------------------------------------------------------------


def test_canonical_vintage_location_is_the_as_of_directory(tmp_path: Path) -> None:
    parent = tmp_path / "vintages"
    resolved = pe.verify_canonical_vintage_location(
        parent / "2026-09-30", SIGNAL, canonical_parent=parent
    )

    assert resolved == (parent / "2026-09-30").resolve()
    assert pe.resolve_canonical_vintage_dir(parent, SIGNAL) == parent / "2026-09-30"


@pytest.mark.parametrize("name", ["2026-09-29", "2026-09-30-extra", "not-a-date"])
def test_non_as_of_vintage_directory_names_are_rejected(tmp_path: Path, name: str) -> None:
    parent = tmp_path / "vintages"

    with pytest.raises(ValueError, match="目录名必须等于 --as-of"):
        pe.verify_canonical_vintage_location(parent / name, SIGNAL, canonical_parent=parent)


def test_parent_traversal_vintage_path_is_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "vintages"

    with pytest.raises(ValueError, match="vintages"):
        pe.verify_canonical_vintage_location(parent / "..", SIGNAL, canonical_parent=parent)


def test_external_vintage_parent_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="vintages"):
        pe.verify_canonical_vintage_location(
            tmp_path / "elsewhere/2026-09-30",
            SIGNAL,
            canonical_parent=tmp_path / "vintages",
        )


# --- parsed fields -------------------------------------------------------------------------


def test_parse_weight_vector_requires_full_coverage_and_unit_sum() -> None:
    weights = pe.parse_weight_vector(
        json.dumps({"A": 0.25, "B": 0.75}), expected_symbols=["A", "B"], label="desired_targets"
    )

    assert weights == {"A": 0.25, "B": 0.75}
    with pytest.raises(ValueError, match="完整覆盖"):
        pe.parse_weight_vector('{"A": 1.0}', expected_symbols=["A", "B"], label="desired_targets")
    with pytest.raises(ValueError, match="合计必须为一"):
        pe.parse_weight_vector(
            '{"A": 0.25, "B": 0.25}', expected_symbols=["A", "B"], label="desired_targets"
        )
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        pe.parse_weight_vector(
            '{"A": 1.25, "B": -0.25}', expected_symbols=["A", "B"], label="desired_targets"
        )


def test_realized_weights_may_leave_cash_unallocated() -> None:
    weights = pe.parse_weight_vector(
        json.dumps({"A": 0.4, "B": 0.5}),
        expected_symbols=["A", "B"],
        label="realized_weights",
        require_total_one=False,
    )

    assert sum(weights.values()) == pytest.approx(0.9)


@pytest.mark.parametrize(
    ("raw", "label", "match"),
    [
        ("", "x", "JSON"),
        ("[]", "x", "JSON object"),
        ("{bad", "x", "JSON"),
    ],
)
def test_parse_json_object_rejects_malformed_fields(raw: str, label: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        pe.parse_json_object(raw, label=label)


@pytest.mark.parametrize("raw", ["", "abc", "nan", "inf"])
def test_parse_finite_float_rejects_non_finite_values(raw: str) -> None:
    with pytest.raises(ValueError, match="数值"):
        pe.parse_finite_float(raw, label="turnover")


def test_parse_iso_date_rejects_timestamps_and_naive_datetimes() -> None:
    assert pe.parse_iso_date("2026-09-30", label="signal_date") == SIGNAL
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        pe.parse_iso_date("2026-09-30 12:00", label="signal_date")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        pe.parse_iso_date("2026-09-30T00:00:00+08:00", label="signal_date")
    with pytest.raises(ValueError, match="非空"):
        pe.parse_iso_date("", label="signal_date")


def test_verify_hex_digest_requires_lowercase_sha256() -> None:
    assert pe.verify_hex_digest("a" * 64, label="x") == "a" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        pe.verify_hex_digest("A" * 64, label="x")
    with pytest.raises(ValueError, match="SHA-256"):
        pe.verify_hex_digest("abc", label="x")


# --- RQAlpha evidence binding --------------------------------------------------------------


def _evidence(root: Path, relative: str = "research/results/fixture.json") -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fixture": True}), encoding="utf-8")
    return pe.build_rqalpha_evidence_identity(
        evidence_path=relative, root=root, expected_framework_version="6.3.0"
    )


def test_rqalpha_evidence_identity_is_hash_bound(tmp_path: Path) -> None:
    identity = _evidence(tmp_path)

    payload = pe.verify_rqalpha_evidence_identity(
        identity, root=tmp_path, expected_framework_version="6.3.0"
    )

    assert payload["framework"] == "rqalpha"
    assert payload["evidence_path"] == "research/results/fixture.json"
    assert payload["evidence_sha256"] == pe.sha256_file(tmp_path / "research/results/fixture.json")


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        ({"evidence_sha256": "0" * 64}, "SHA-256"),
        ({"framework": "vectorbt"}, "RQAlpha"),
        ({"framework_version": "6.2.0"}, "framework_version"),
        ({"evidence_path": "/etc/passwd"}, "research/"),
        ({"evidence_path": "research/../secrets.json"}, "上级目录"),
        ({"evidence_path": "docs/goal.md"}, "research/"),
        ({"extra": "field"}, "schema"),
    ],
)
def test_rqalpha_evidence_identity_rejects_drift(
    tmp_path: Path, mutate: dict[str, str], match: str
) -> None:
    payload = json.loads(_evidence(tmp_path))
    payload.update(mutate)

    with pytest.raises(ValueError, match=match):
        pe.verify_rqalpha_evidence_identity(
            json.dumps(payload), root=tmp_path, expected_framework_version="6.3.0"
        )


def test_rqalpha_evidence_must_exist(tmp_path: Path) -> None:
    identity = _evidence(tmp_path)
    (tmp_path / "research/results/fixture.json").unlink()

    with pytest.raises(ValueError, match="不存在"):
        pe.verify_rqalpha_evidence_identity(
            identity, root=tmp_path, expected_framework_version="6.3.0"
        )


# --- append-only event table ---------------------------------------------------------------


def _rows(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    return pe.read_event_rows(path, fields)


FIELDS = ("record_type", "candidate_id", "signal_date", "execution_status")


def test_append_event_row_appends_once_and_rejects_duplicates(tmp_path: Path) -> None:
    path = write_observations_header(tmp_path / "observations.csv", FIELDS)
    record = dict.fromkeys(FIELDS, "")
    record.update({"record_type": "decision", "candidate_id": "X_R1", "signal_date": "2026-09-30"})

    pe.append_event_row(record, path=path, fields=FIELDS)

    assert len(_rows(path, FIELDS)) == 1
    before = path.read_bytes()
    with pytest.raises(ValueError, match="append-only"):
        pe.append_event_row(record, path=path, fields=FIELDS)
    assert path.read_bytes() == before


def test_append_event_row_rejects_schema_drift_before_writing(tmp_path: Path) -> None:
    path = write_observations_header(tmp_path / "observations.csv", FIELDS)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="字段集合"):
        pe.append_event_row({"record_type": "decision"}, path=path, fields=FIELDS)

    assert path.read_bytes() == before


def test_read_event_rows_requires_the_frozen_header(tmp_path: Path) -> None:
    path = tmp_path / "observations.csv"
    path.write_text("record_type,candidate_id\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="schema 与冻结协议不一致"):
        pe.read_event_rows(path, FIELDS)
