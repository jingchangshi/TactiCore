"""Offline StrategyRelease validation across NOT_APPROVED and APPROVED_FOR_ACCOUNT tiers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Any

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_STATUSES = {"DRAFT", "RESEARCH_PUBLISHED", "FROZEN", "PROSPECTIVE_SHADOW_ACTIVE", "REJECTED"}
_ADMISSIONS = {"NOT_APPROVED", "APPROVED_FOR_ACCOUNT"}


def _fail() -> None:
    raise ValueError("invalid_strategy_release")


def _object(value: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail()
    return value


def _text(value: Any) -> None:
    if (
        not isinstance(value, str)
        or not value.strip(" \t\r\n")
        or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    ):
        _fail()


def _date(value: Any) -> None:
    _text(value)
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        _fail()
    try:
        date.fromisoformat(value)
    except ValueError:
        _fail()


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        _fail()
    return value


def validate_strategy_release(value: Any) -> str:
    """Check every field and the canonical content hash; raise ValueError on failure."""
    root = _object(
        value,
        {
            "schema_version",
            "research_status",
            "production_admission",
            "strategy",
            "applicability",
            "execution_assumptions",
            "inputs",
            "rules",
            "parameters",
            "evidence",
            "content_hash",
        },
    )
    if (
        root["schema_version"] != "strategy-release-1"
        or not isinstance(root["research_status"], str)
        or root["research_status"] not in _STATUSES
        or not isinstance(root["production_admission"], str)
        or root["production_admission"] not in _ADMISSIONS
    ):
        _fail()
    strategy = _object(root["strategy"], {"id", "version", "implementation_sha256"})
    _text(strategy["id"])
    _text(strategy["version"])
    _text(strategy["implementation_sha256"])
    if strategy["implementation_sha256"] != "UNKNOWN" and not _SHA.fullmatch(
        strategy["implementation_sha256"]
    ):
        _fail()
    applicability = _object(root["applicability"], {"market", "environment"})
    for value in applicability.values():
        _text(value)
    execution = _object(
        root["execution_assumptions"],
        {"signal_timing", "earliest_execution", "exit", "fees", "lot_size"},
    )
    for value in execution.values():
        _text(value)
    inputs = _object(root["inputs"], {"source", "snapshot", "start_date", "end_date", "assets"})
    _text(inputs["source"])
    _text(inputs["snapshot"])
    _date(inputs["start_date"])
    _date(inputs["end_date"])
    if inputs["start_date"] > inputs["end_date"]:
        _fail()
    assets = _list(inputs["assets"])
    for asset in assets:
        _text(asset)
    if len(set(assets)) != len(assets):
        _fail()
    for rule in _list(root["rules"]):
        _text(rule)
    parameters = root["parameters"]
    if not isinstance(parameters, dict) or not parameters:
        _fail()
    for key, val in parameters.items():
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            _fail()
        _text(val)
    for item in _list(root["evidence"]):
        evidence = _object(item, {"reference", "sha256"})
        _text(evidence["reference"])
        _text(evidence["sha256"])
        if not _SHA.fullmatch(evidence["sha256"]):
            _fail()
    _text(root["content_hash"])
    if not _SHA.fullmatch(root["content_hash"]):
        _fail()
    payload = {key: val for key, val in root.items() if key != "content_hash"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if digest != root["content_hash"]:
        _fail()
    return digest
