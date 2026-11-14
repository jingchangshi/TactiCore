"""Offline, account-free strategy feedback contract. No persistence or evidence collection."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_COMMON = {
    "schema_version",
    "event_id",
    "event_type",
    "release_hash",
    "snapshot_hash",
    "occurred_at",
    "recorded_at",
    "coverage",
}
_PAYLOAD = {
    "SIGNAL_EVALUATED": (
        {"signal_id", "result"},
        {"result": {"TRIGGERED", "NOT_TRIGGERED", "UNAVAILABLE"}},
    ),
    "DECISION": (
        {"signal_event_id", "result", "reason_code"},
        {"result": {"ACCEPTED", "REJECTED", "NO_ACTION"}},
    ),
    "OUTCOME": (
        {"decision_event_id", "result", "reason_code"},
        {"result": {"PENDING", "UNAVAILABLE", "OBSERVED", "ACTUAL_FILL"}},
    ),
    "CORRECTION": ({"corrects_event_id", "reason_code"}, {}),
}


def _id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def validate_event(event: Any) -> None:
    if not isinstance(event, dict) or event.get("schema_version") != "strategy-feedback-1":
        raise ValueError("invalid feedback event")
    kind = event.get("event_type")
    if not isinstance(kind, str) or kind not in _PAYLOAD or set(event) != _COMMON | {"payload"}:
        raise ValueError("invalid feedback event")
    if not _id(event["event_id"]) or not all(
        isinstance(event[k], str) and _SHA.fullmatch(event[k])
        for k in ("release_hash", "snapshot_hash")
    ):
        raise ValueError("invalid feedback identity")
    for key in ("occurred_at", "recorded_at"):
        value = event[key]
        if not isinstance(value, str) or not _TIME.fullmatch(value):
            raise ValueError("invalid timestamp")
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError("invalid timestamp") from exc
    if event["occurred_at"] > event["recorded_at"]:
        raise ValueError("recording precedes occurrence")
    coverage = event["coverage"]
    if (
        not isinstance(coverage, dict)
        or set(coverage) != {"universe_id", "period_start", "period_end"}
        or not _id(coverage["universe_id"])
    ):
        raise ValueError("invalid coverage")
    for key in ("period_start", "period_end"):
        value = coverage[key]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("invalid coverage date")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("invalid coverage date") from exc
    if coverage["period_start"] > coverage["period_end"]:
        raise ValueError("invalid coverage range")
    payload = event["payload"]
    keys, enums = _PAYLOAD[kind]
    if not isinstance(payload, dict) or set(payload) != keys:
        raise ValueError("invalid payload")
    for key, value in payload.items():
        if key in enums:
            if not isinstance(value, str) or value not in enums[key]:
                raise ValueError("invalid result")
        elif not _id(value):
            raise ValueError("invalid payload identifier")
    if kind == "CORRECTION" and payload["corrects_event_id"] == event["event_id"]:
        raise ValueError("self correction")


def content_hash(event: Any) -> str:
    validate_event(event)
    encoded = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def append_event(events: list[dict[str, Any]], event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a detached new sequence; caller owns durable, atomic persistence."""
    digest = content_hash(event)
    duplicate = False
    seen: set[str] = set()
    for existing in events:
        old_hash = content_hash(existing)
        if existing["event_id"] in seen:
            raise ValueError("duplicate existing event id")
        seen.add(existing["event_id"])
        if existing["event_id"] == event["event_id"]:
            if old_hash != digest:
                raise ValueError("conflicting event id")
            duplicate = True
    return json.loads(json.dumps(events if duplicate else [*events, event]))
