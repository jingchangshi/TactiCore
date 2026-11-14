import copy
import json
from pathlib import Path

import pytest

from tacticore.strategy_feedback import append_event, content_hash, validate_event

FIXTURE = json.loads((Path(__file__).parent / "strategy_feedback_fixture.json").read_text())


def test_synthetic_identities_and_append_only_conflict():
    events = []
    for item in FIXTURE:
        assert content_hash(item["event"]) == item["sha256"]
        events = append_event(events, item["event"])
    duplicate = append_event(events, copy.deepcopy(FIXTURE[0]["event"]))
    assert len(duplicate) == len(events)
    duplicate[0]["payload"]["result"] = "TRIGGERED"
    assert events[0]["payload"]["result"] == "NOT_TRIGGERED"
    with pytest.raises(ValueError, match="conflicting"):
        append_event(events, duplicate[0])


def test_invalid_data_rejected():
    mutations = [
        lambda e: e.update(account_id="PRIVATE"),
        lambda e: e["payload"].update(account="PRIVATE"),
        lambda e: e.update(payload={"result|signal_id": "TEST_SIGNAL"}),
        lambda e: e["payload"].update(result="ACTUAL_FILL"),
        lambda e: e.update(occurred_at="2026-02-30T00:00:00Z"),
        lambda e: e.update(recorded_at="2025-01-01T00:00:00Z"),
        lambda e: e.update(release_hash="a" * 64 + "\n"),
        lambda e: e["coverage"].update(period_start="2026-01-03"),
        lambda e: e.update(event_id="bad\n"),
        lambda e: e.update(event_type="toString"),
    ]
    for mutate in mutations:
        event = copy.deepcopy(FIXTURE[0]["event"])
        mutate(event)
        with pytest.raises(ValueError):
            validate_event(event)
    correction = copy.deepcopy(FIXTURE[-1]["event"])
    correction["payload"]["corrects_event_id"] = correction["event_id"]
    with pytest.raises(ValueError):
        validate_event(correction)
