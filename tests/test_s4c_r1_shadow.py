"""S4C R1 前瞻影子 runner 的 activation、边界与 append-only 契约测试。

全部使用 fixtures / `tmp_path` / synthetic data；不修改系统时间，不运行真实 future observation。
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from research.experiments import run_s4c_r1_shadow as shadow
from research.experiments import verify_s4c_r1_candidate as candidate
from tacticore.data.prices import load_price_csv

ROOT = Path(__file__).resolve().parents[1]
AS_OF = pd.Timestamp("2026-09-30")
# COMMIT A 之前冻结的 candidate_manifest.json（CRLF 归一化）SHA-256。
FROZEN_MANIFEST_SHA256 = "09469df0ec06d741bee2f176fd1f8334154edafe84afef5b01d889222f6cd908"
GENERATED_AT = "2026-09-30T16:00:00+00:00"


def _activation_payload() -> dict[str, str]:
    return {
        "candidate_id": "S4C_R1",
        "candidate_version": "R1",
        "activation_status": "ACTIVE",
        "activation_decision_timestamp": "2026-09-14T00:00:00+00:00",
        "activation_protocol_version": "V1",
        "candidate_manifest_sha256": shadow.manifest_hash(),
        "historical_cutoff": "2026-08-31",
        "first_eligible_prospective_signal": "2026-09-30",
        "observation_schema_version": "S4C_R1_OBSERVATIONS_V1",
        "decision_record_policy": "APPEND_ONLY_ONE_DECISION_PER_SIGNAL_DATE_BEFORE_EXECUTION",
        "execution_record_policy": "APPEND_ONLY_ONE_EXECUTION_PER_DECISION_AFTER_SIGNAL_DATE",
        "activation_decision_record": (
            "research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md"
        ),
    }


def _write_activation(tmp_path: Path, **overrides: str) -> Path:
    payload = _activation_payload()
    payload.update(overrides)
    path = tmp_path / "activation.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_vintage(
    tmp_path: Path,
    *,
    overlap_multiplier: float = 1.0,
    beyond_as_of: bool = False,
) -> Path:
    historical_prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    historical_calendar = shadow.load_calendar(ROOT / "data/canonical/trading_calendar.csv")
    overlap_date = historical_prices.index[-1]
    future_dates = pd.bdate_range("2026-09-01", "2026-09-30")
    if beyond_as_of:
        future_dates = future_dates.append(pd.DatetimeIndex([pd.Timestamp("2026-10-01")]))
    prospective_prices = pd.DataFrame(
        [historical_prices.iloc[-1].to_numpy()] * len(future_dates),
        index=future_dates,
        columns=historical_prices.columns,
    )
    prospective_prices = prospective_prices * (
        1.0 + 0.001 * pd.Series(range(len(future_dates)), index=future_dates).to_numpy()[:, None]
    )
    prices = pd.concat(
        [historical_prices.loc[[overlap_date]] * overlap_multiplier, prospective_prices]
    )
    calendar = pd.concat(
        [
            historical_calendar.loc[[overlap_date]],
            pd.DataFrame(1, index=future_dates, columns=["sse_open", "szse_open"]).astype(int),
        ]
    )
    vintage = tmp_path / "2026-09-30"
    vintage.mkdir(exist_ok=True)
    prices.to_csv(vintage / "etf_adjusted_close.csv", index_label="date")
    calendar.to_csv(vintage / "trading_calendar.csv", index_label="date")
    (vintage / "provenance.json").write_text(
        json.dumps({"vintage": vintage.name}), encoding="utf-8"
    )
    return vintage


def _write_header(path: Path) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=shadow.RECORD_FIELDS).writeheader()
    return path


def _decision_record(tmp_path: Path) -> dict[str, str]:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path)
    prices, _, vintage_hash = shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)
    return shadow.build_decision_record(
        prices,
        manifest,
        as_of=AS_OF,
        vintage_identifier=vintage.name,
        prospective_data_hash=vintage_hash,
        historical_manifest_hash=shadow.manifest_hash(),
        generated_at=GENERATED_AT,
    )


# --- candidate identity -----------------------------------------------------------------


def test_candidate_manifest_is_unchanged_by_activation_work() -> None:
    manifest = shadow.load_manifest()

    assert manifest["candidate_id"] == "S4C_R1"
    assert manifest["prospective_activation"] == "NOT_ACTIVE"
    assert manifest["historical_cutoff"] == "2026-08-31"
    assert manifest["first_eligible_prospective_signal"] == "2026-09-30"
    assert shadow.manifest_hash() == FROZEN_MANIFEST_SHA256


def test_frozen_semantics_still_reproduce_the_committed_schedule() -> None:
    manifest = shadow.load_manifest()

    shadow.verify_semantics_reproduce_frozen_schedule(manifest)


def test_framework_version_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = shadow.load_manifest()

    def frozen_version_except_numpy(package: str) -> str:
        if package == "numpy":
            return "0.0.0"
        return manifest["framework_versions"][package]

    monkeypatch.setattr(candidate, "version", frozen_version_except_numpy)

    with pytest.raises(ValueError, match="当前框架版本不一致: numpy"):
        shadow.verify_candidate_shadow(manifest)


# --- activation lifecycle artifact ------------------------------------------------------


def test_runner_refuses_to_write_without_an_activation_artifact(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    missing = tmp_path / "activation.json"

    assert shadow.activation_status(missing) == "NOT_ACTIVE"
    with pytest.raises(ValueError, match="未激活"):
        shadow.require_activation(missing, manifest)


def test_activation_requires_the_correct_candidate_id(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    activation = shadow.load_activation(_write_activation(tmp_path, candidate_id="S4C_R2"))

    with pytest.raises(ValueError, match="candidate_id"):
        shadow.verify_activation(activation, manifest)  # type: ignore[arg-type]


def test_activation_artifact_manifest_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    activation = shadow.load_activation(
        _write_activation(tmp_path, candidate_manifest_sha256="0" * 64)
    )

    with pytest.raises(ValueError, match="manifest hash 不一致"):
        shadow.verify_activation(activation, manifest)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("historical_cutoff", "2026-09-30"),
        ("first_eligible_prospective_signal", "2026-09-29"),
        ("observation_schema_version", "S4C_R1_OBSERVATIONS_V2"),
        ("activation_protocol_version", "V2"),
        ("activation_status", "NOT_ACTIVE"),
    ],
)
def test_activation_artifact_mismatch_is_rejected(tmp_path: Path, field: str, value: str) -> None:
    manifest = shadow.load_manifest()
    activation = shadow.load_activation(_write_activation(tmp_path, **{field: value}))

    with pytest.raises(ValueError):
        shadow.verify_activation(activation, manifest)  # type: ignore[arg-type]


def test_activation_schema_drift_is_rejected(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    payload = _activation_payload()
    payload["activation_commit"] = "self-referential"
    path = tmp_path / "activation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="字段集合与冻结 schema 不一致"):
        shadow.verify_activation(shadow.load_activation(path), manifest)  # type: ignore[arg-type]


# --- historical / prospective boundary ---------------------------------------------------


def test_historical_cutoff_cannot_be_prospective(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path)
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv")

    with pytest.raises(ValueError, match="严格晚于 historical_data_cutoff"):
        shadow.validate_month_end(calendar, pd.Timestamp("2026-08-31"), manifest)


@pytest.mark.parametrize(
    "as_of",
    ["2026-09-01", "2026-09-13", "2026-09-29"],
)
def test_pre_eligible_signal_is_rejected(tmp_path: Path, as_of: str) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path)
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv")

    with pytest.raises(ValueError, match="first_eligible_prospective_signal"):
        shadow.validate_month_end(calendar, pd.Timestamp(as_of), manifest)


def test_first_eligible_signal_is_accepted_by_pure_validation(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path)
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv")

    shadow.validate_month_end(calendar, AS_OF, manifest)

    prices, _, _ = shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)
    target, diagnostics = shadow.derive_target(prices, manifest, AS_OF)

    assert diagnostics["regime"] in {"RISK", "FALLBACK"}
    assert float(target.sum()) == pytest.approx(1.0)


def test_incomplete_signal_month_cannot_fabricate_a_month_end_decision(
    tmp_path: Path,
) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path)
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv").loc[:"2026-09-29"]

    with pytest.raises(ValueError, match="未覆盖完整 signal 月"):
        shadow.validate_month_end(calendar, AS_OF, manifest)


def test_as_of_must_be_the_last_canonical_trading_day(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path)
    calendar = shadow.load_calendar(vintage / "trading_calendar.csv")
    calendar.loc[pd.Timestamp("2026-09-30")] = 0

    with pytest.raises(ValueError, match="最后一个 canonical 交易日"):
        shadow.validate_month_end(calendar, AS_OF, manifest)


def test_vintage_after_as_of_is_rejected_instead_of_leaking(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, beyond_as_of=True)

    with pytest.raises(ValueError, match="as-of 之后"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_vintage_cannot_overwrite_different_historical_data(tmp_path: Path) -> None:
    manifest = shadow.load_manifest()
    vintage = _write_vintage(tmp_path, overlap_multiplier=1.01)

    with pytest.raises(ValueError, match="重叠但内容不同"):
        shadow.load_prospective_inputs(vintage, manifest, as_of=AS_OF)


def test_explicit_as_of_is_required(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["run_s4c_r1_shadow", "--vintage-dir", str(tmp_path)])

    with pytest.raises(SystemExit):
        shadow.main()


# --- decision / execution separation -----------------------------------------------------


def test_decision_record_carries_no_execution_evidence(tmp_path: Path) -> None:
    record = _decision_record(tmp_path)

    assert record["record_type"] == "decision"
    assert record["signal_date"] == "2026-09-30"
    assert record["data_as_of"] == "2026-09-30"
    assert record["execution_status"] == shadow.PENDING_EXECUTION_STATUS
    assert record["action_required"] == "true"
    assert json.loads(record["desired_targets"])
    for field in shadow.EXECUTION_ONLY_FIELDS:
        assert record[field] == ""


def test_decision_record_with_execution_evidence_is_rejected(tmp_path: Path) -> None:
    record = _decision_record(tmp_path)
    record["execution_date"] = "2026-10-09"

    with pytest.raises(ValueError, match="不得包含执行结果字段"):
        shadow.verify_decision_row_is_fixed_before_execution(record)


def test_decision_generated_before_the_signal_date_is_rejected(tmp_path: Path) -> None:
    record = _decision_record(tmp_path)
    record["record_generated_at"] = "2026-09-13T16:00:00+00:00"

    with pytest.raises(ValueError, match="不得早于 signal_date"):
        shadow.verify_record_generation_time(record)


def test_execution_must_follow_the_decision(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(tmp_path)
    shadow.append_decision_record(record, path)

    execution = dict.fromkeys(shadow.RECORD_FIELDS, "")
    execution.update(
        {
            "record_type": "execution",
            "candidate_id": "S4C_R1",
            "signal_date": "2026-09-30",
            "execution_date": "2026-09-30",
            "execution_status": "EXECUTED",
        }
    )
    with pytest.raises(ValueError, match="决策必须先于执行"):
        shadow.append_execution_record(execution, path)

    execution["execution_date"] = "2026-10-09"
    shadow.append_execution_record(execution, path)
    assert shadow.observation_record_count(path) == 2


def test_execution_without_a_decision_is_rejected(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    execution = dict.fromkeys(shadow.RECORD_FIELDS, "")
    execution.update(
        {
            "record_type": "execution",
            "candidate_id": "S4C_R1",
            "signal_date": "2026-09-30",
            "execution_date": "2026-10-09",
        }
    )

    with pytest.raises(ValueError, match="只能追加在唯一对应的 decision 行之后"):
        shadow.append_execution_record(execution, path)


# --- append-only and idempotency ---------------------------------------------------------


def test_duplicate_decision_is_rejected(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(tmp_path)

    shadow.append_decision_record(record, path)
    with pytest.raises(ValueError, match="append-only"):
        shadow.append_decision_record(record, path)

    assert shadow.decision_record_count(path) == 1


def test_duplicate_execution_is_rejected(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(tmp_path)
    shadow.append_decision_record(record, path)

    execution = dict.fromkeys(shadow.RECORD_FIELDS, "")
    execution.update(
        {
            "record_type": "execution",
            "candidate_id": "S4C_R1",
            "signal_date": "2026-09-30",
            "execution_date": "2026-10-09",
        }
    )
    shadow.append_execution_record(execution, path)

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_execution_record(execution, path)

    assert shadow.observation_record_count(path) == 2


def test_append_only_preserves_the_existing_decision_row(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(tmp_path)
    shadow.append_decision_record(record, path)
    before = path.read_text(encoding="utf-8").splitlines()

    execution = dict.fromkeys(shadow.RECORD_FIELDS, "")
    execution.update(
        {
            "record_type": "execution",
            "candidate_id": "S4C_R1",
            "signal_date": "2026-09-30",
            "execution_date": "2026-10-09",
        }
    )
    shadow.append_execution_record(execution, path)

    after = path.read_text(encoding="utf-8").splitlines()
    assert after[: len(before)] == before
    assert len(after) == len(before) + 1


def test_rejected_duplicate_append_leaves_the_file_bytes_unchanged(tmp_path: Path) -> None:
    path = _write_header(tmp_path / "observations.csv")
    record = _decision_record(tmp_path)
    shadow.append_decision_record(record, path)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="append-only"):
        shadow.append_decision_record(record, path)

    assert path.read_bytes() == before


def test_observation_schema_drift_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "observations.csv"
    path.write_text("record_type,candidate_id\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="schema 与冻结协议不一致"):
        shadow.read_observation_rows(path)


def test_frozen_observation_scaffold_is_still_header_only() -> None:
    rows = candidate.OBSERVATIONS_PATH.read_text(encoding="utf-8").splitlines()

    assert rows == [",".join(candidate.RECORD_FIELDS)]
    assert observation_records_are_zero()


def observation_records_are_zero() -> bool:
    return shadow.observation_record_count(candidate.OBSERVATIONS_PATH) == 0


# --- end-to-end CLI behaviour ------------------------------------------------------------


def _run_cli(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["run_s4c_r1_shadow", *argv])
    shadow.main()


@pytest.fixture
def frozen_record_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 record 生成时间可确定，避免测试依赖运行机器时钟。"""
    monkeypatch.setattr(shadow, "_now_utc_iso", lambda: GENERATED_AT)


def test_runner_refuses_real_record_before_first_eligible_date(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    activation = _write_activation(tmp_path)
    vintage = _write_vintage(tmp_path)
    record_path = _write_header(tmp_path / "observations.csv")

    with pytest.raises(ValueError, match="first_eligible_prospective_signal"):
        _run_cli(
            monkeypatch,
            [
                "--as-of",
                "2026-09-29",
                "--vintage-dir",
                str(vintage),
                "--activation-path",
                str(activation),
                "--record-path",
                str(record_path),
            ],
        )

    assert shadow.observation_record_count(record_path) == 0


def test_runner_refuses_to_write_when_not_active(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vintage = _write_vintage(tmp_path)
    record_path = _write_header(tmp_path / "observations.csv")

    with pytest.raises(ValueError, match="未激活"):
        _run_cli(
            monkeypatch,
            [
                "--as-of",
                "2026-09-30",
                "--vintage-dir",
                str(vintage),
                "--activation-path",
                str(tmp_path / "absent-activation.json"),
                "--record-path",
                str(record_path),
            ],
        )

    assert shadow.observation_record_count(record_path) == 0


def test_first_eligible_decision_is_appended_once(
    monkeypatch: pytest.MonkeyPatch,
    frozen_record_time: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    activation = _write_activation(tmp_path)
    vintage = _write_vintage(tmp_path)
    record_path = _write_header(tmp_path / "observations.csv")
    argv = [
        "--as-of",
        "2026-09-30",
        "--vintage-dir",
        str(vintage),
        "--activation-path",
        str(activation),
        "--record-path",
        str(record_path),
    ]

    _run_cli(monkeypatch, argv)

    assert "2026-09-30" in capsys.readouterr().out
    assert shadow.decision_record_count(record_path) == 1
    rows = shadow.read_observation_rows(record_path)
    assert rows[0]["candidate_id"] == "S4C_R1"
    assert rows[0]["vintage_identifier"] == "2026-09-30"

    with pytest.raises(ValueError, match="append-only"):
        _run_cli(monkeypatch, argv)

    assert shadow.decision_record_count(record_path) == 1
