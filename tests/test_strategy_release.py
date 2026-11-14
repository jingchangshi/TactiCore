import copy
import hashlib
import json
from pathlib import Path

import pytest

from tacticore.strategy_release import validate_strategy_release

FIXTURE = Path(__file__).parent / "fixtures" / "strategy-release.json"


def _rehash(value):
    payload = {key: val for key, val in value.items() if key != "content_hash"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    value["content_hash"] = hashlib.sha256(encoded.encode()).hexdigest()


def test_shared_fixture():
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert validate_strategy_release(value) == (
        "f174eb2c37e1451d444ac1ea5e0962f39934e3b675ae2b374fc723bf10441555"
    )
    assert value["production_admission"] == "NOT_APPROVED"


def test_unicode_scalars_and_normalization():
    cases = [
        (
            json.loads('"策略 \\ud83d\\ude00"'),
            "c40a8a9e54e32b04ae0d74c0697c0721faa658fe58cf9e947f1cca3d7eba3b55",
        ),
        ("café", "833f0749ad1f0c96ca59ba96f183c2ad64aae5a40d28413fccde241503fdef62"),
        ("café", "ea653e22002647682f824e3e72f402fbe1ab4bfd81da64c260892ee9084ef5d0"),
    ]
    for text, expected in cases:
        value = json.loads(FIXTURE.read_text(encoding="utf-8"))
        value["rules"][0] = text
        _rehash(value)
        assert validate_strategy_release(value) == expected
        assert value["rules"][0] == text
    for text in ("\ud800", "\udc00"):
        value = json.loads(FIXTURE.read_text(encoding="utf-8"))
        value["rules"][0] = text
        with pytest.raises(ValueError):
            validate_strategy_release(value)


@pytest.mark.parametrize(
    ("group", "field"),
    [
        ("strategy", "implementation_sha256"),
        ("applicability", "market"),
        ("applicability", "environment"),
    ]
    + [
        ("execution_assumptions", field)
        for field in ("signal_timing", "earliest_execution", "exit", "fees", "lot_size")
    ],
)
def test_required_frozen_semantics(group, field):
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    altered = copy.deepcopy(value)
    altered[group][field] = "changed"
    with pytest.raises(ValueError):
        validate_strategy_release(altered)
    del value[group][field]
    _rehash(value)
    with pytest.raises(ValueError):
        validate_strategy_release(value)


def test_implementation_hash_format():
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["strategy"]["implementation_sha256"] = "invalid"
    _rehash(value)
    with pytest.raises(ValueError):
        validate_strategy_release(value)
    value["strategy"]["implementation_sha256"] = "b" * 64
    _rehash(value)
    assert validate_strategy_release(value) == value["content_hash"]


@pytest.mark.parametrize(
    "case",
    [
        "tamper",
        "missing",
        "unknown",
        "approved",
        "missing_admission",
        "invalid_date",
        "reverse_dates",
        "number",
        "extra",
        "evidence_hash",
    ],
)
def test_reject_invalid_release(case):
    value = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    if case == "tamper":
        value["rules"][0] += " altered"
    elif case == "missing":
        del value["inputs"]["assets"]
    elif case == "unknown":
        value["research_status"] = "UNKNOWN"
    elif case == "approved":
        value["production_admission"] = "APPROVED"
    elif case == "missing_admission":
        del value["production_admission"]
    elif case == "invalid_date":
        value["inputs"]["end_date"] = "2020-02-30"
    elif case == "reverse_dates":
        value["inputs"]["start_date"] = "2021-01-01"
    elif case == "number":
        value["parameters"]["lookback"] = 200
    elif case == "extra":
        value["extra"] = "ignored?"
    elif case == "evidence_hash":
        value["evidence"][0]["sha256"] = "bad"
    if case != "tamper":
        _rehash(value)
    with pytest.raises(ValueError):
        validate_strategy_release(value)
