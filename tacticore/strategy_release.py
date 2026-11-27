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


def _validate_v340_parameters(parameters: dict[str, str]) -> None:
    """Enforce v3.4.0 Tri-Pillar schema invariants and reject B2/style_tilt regressions."""
    for key in parameters:
        if "style_tilt" in key.lower():
            _fail()
    required = {
        "lowvol_core_mode": "CORE_40",
        "lowvol_core_permanent_share_bps": "1500",
        "gold_core_etf": "518880.SH",
        "gold_core_share_bps": "1000",
        "gold_core_drift_band_bps": "400",
        "gold_core_min_trade_cny": "5000",
        "strategic_bond_core_share_bps": "1500",
        "defensive_bond_reservoir_etf": "159649.SZ",
        "defensive_bond_reservoir_drift_band_bps": "1000",
        "defensive_equity_bps": "2500",
        "ice10_floor_enabled": "true",
        "ice10_equity_bps": "3500",
        "ice10_window_trade_days": "15",
        "ice10_disable_on_p0_lock": "true",
        "fundamental_envelope_enabled": "true",
        "fundamental_envelope_mode": "B1_PIT_ERP_BP_DUAL_756D",
        "align_trigger_mode": "REGIME_ONLY",
        "equity_align_drift_band_bps": "1000",
        "quality_core_version": "v2",
        "fvo_enabled": "true",
        "fvo_scalar_only": "true",
        "fvo_equity_delta_default_bps": "0",
        "fvo_max_abs_delta_bps": "1000",
        "fvo_max_ttl_trade_days": "20",
        "fvo_zero_positive_on_l1_or_bubble": "true",
        "fvo_60d_attribution_halve_trigger_bps": "-150",
        "fvo_60d_attribution_halved_cap_bps": "500",
    }
    for key, expected in required.items():
        if parameters.get(key) != expected:
            _fail()


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
        key_lower = key.lower()
        if (
            key_lower == "implied_expectation_tilt"
            or key_lower.startswith("b2_")
            or key_lower == "l2_lock_allow_m2_early_release"
        ):
            _fail()
        _text(val)
    if strategy["version"] == "3.4.0":
        _validate_v340_parameters(parameters)
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
