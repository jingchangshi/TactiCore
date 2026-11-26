"""Synthetic-only V2 boundary checks: no quote connections or committed schedules."""

from __future__ import annotations

import pandas as pd
import pytest

from research.batches.free_data_contract_v1 import run_equivalence_v2 as runner
from research.batches.free_data_contract_v1.contract_v2 import adjust, compare


def bar(d, c=10, v=1):
    return {"date": f"2020-01-{d:02}", "close": c, "volume": v}


def split(d, s=2, category=11):
    return {"date": f"2020-01-{d:02}", "category": category, "suogu": s}


def dividend(d, **kwargs):
    return {
        "date": f"2020-01-{d:02}",
        "category": 1,
        "fenhong": 1,
        "peigu": 0,
        "peigujia": 0,
        "songzhuangu": 0,
    } | kwargs


def prices(b, e):
    return adjust("S", b, e, "2020-01-02", "2020-01-08")


@pytest.mark.parametrize("post", [4.75, 5.25, 5.0])
@pytest.mark.parametrize("cat", [11, 12])
def test_exact_five_percent_and_direction(post, cat):
    s, events = prices([bar(2), bar(3, 0), bar(4, 3, 0), bar(5, post)], [split(4, category=cat)])
    assert s.tolist() == [10, post * 2] and events[0]["post"] == "2020-01-05"


@pytest.mark.parametrize("post", [4.749, 5.251])
def test_strictly_outside_five_percent(post):
    with pytest.raises(ValueError, match="exceeds"):
        prices([bar(2), bar(5, post)], [split(4)])


def test_window_crop_and_dividend_compounding():
    s, events = prices(
        [bar(1), bar(2), bar(3, 9.9), bar(8, 4.95), bar(9)],
        [split(1), dividend(3), split(8), split(9, category=88)],
    )
    assert s.tolist() == pytest.approx([10, 10, 10])
    assert len(events) == 2


@pytest.mark.parametrize(
    "events,reason",
    [
        ([split(2)], "missing"),
        ([split(8)], "missing"),
        ([split(3), split(4)], "multiple"),
        ([dividend(3), split(4)], "multiple"),
        ([dividend(3), dividend(3)], "multiple"),
        ([split(3, category=8)], "unknown"),
        ([split(3, float("nan"))], "invalid split"),
        ([split(3, -1)], "invalid split"),
        ([dividend(3, songzhuangu=-10)], "denominator"),
        ([dividend(3, fenhong=101)], "reference"),
    ],
)
def test_ambiguous_or_invalid_events(events, reason):
    with pytest.raises(ValueError, match=reason):
        prices([bar(2), bar(4, 5)], events)


def test_invalid_date_no_valid_bar_and_outside_pre():
    with pytest.raises(ValueError):
        prices([bar(32)], [])
    with pytest.raises(ValueError):
        prices([bar(2, float("nan")), bar(4, 1, float("inf"))], [])
    with pytest.raises(ValueError, match="missing"):
        prices([bar(1), bar(2, 5)], [split(2)])


def schedule(erc):
    dates = list(pd.date_range("2013-04-01", periods=161 if erc else 103))
    dates[-1] = pd.Timestamp("2026-08-03")
    return pd.DataFrame({"A": 0.75, "B": 0.25, "C": 0.0}, index=dates)


@pytest.mark.parametrize("name", ["S4C_R1", "S2_R1"])
def test_axis_identity_before_common_diagnostics(name):
    f = schedule(name == "S4C_R1")
    assert compare(name, f, f)["passed"]
    for other in [
        f.iloc[::-1],
        f[["B", "A", "C"]],
        f.drop(f.index[12]),
        f.rename(columns={"B": "D"}),
    ]:
        r = compare(name, f, other)
        assert not r["passed"] and r["first_difference"]
    g = f.copy()
    g.iloc[4, 0] += 0.01
    r = compare(name, f, g)
    assert not r["passed"] and r["largest_common_weight_difference"]["asset"] == "A"


def test_erc_independent_invariants():
    f = schedule(True)
    g = f.copy()
    g.iloc[6] = [0.75, 0.25 - 1e-12, 1e-12]
    assert not compare("S4C_R1", f, g)["checks"]["positive_support"]
    g = f.copy()
    g.iloc[3, 0] += 3e-9
    assert not compare("S4C_R1", f, g)["checks"]["row_sum"]
    f.iloc[2] = [0.5 + 1e-6, 0.5 - 1e-6, 0]
    g = f.copy()
    g.iloc[2] = [0.5 - 1e-6, 0.5 + 1e-6, 0]
    assert not compare("S4C_R1", f, g)["checks"]["max_asset"]


def test_one_failed_control_skips_both_free_arms():
    refs = {k: schedule(k == "S4C_R1") for k in runner.REF}
    info = {"verdicts": dict.fromkeys(refs, "NOT_COMPARED")}
    calls = []

    def gen(k, source):
        calls.append((k, source))
        return refs[k] if k == "S4C_R1" else refs[k].iloc[::-1]

    runner.adjudicate(info, "CANON", "FREE", refs, gen)
    assert (
        info["stage"] == "BLOCKED_CONTROL"
        and len(calls) == 2
        and all(src == "CANON" for _, src in calls)
    )


def test_arm_generation_failure_is_not_an_observed_difference():
    refs = {k: schedule(k == "S4C_R1") for k in runner.REF}
    info = {"verdicts": dict.fromkeys(refs, "NOT_COMPARED")}

    def gen(k, src):
        if src == "FREE" and k == "S4C_R1":
            raise ValueError("synthetic failure")
        return refs[k] if src == "CANON" else refs[k].iloc[:-1]

    runner.adjudicate(info, "CANON", "FREE", refs, gen)
    assert info["verdicts"] == {"S2_R1": "NOT_EQUIVALENT", "S4C_R1": "NOT_COMPARED"}


def test_existing_attempt_refused_even_when_empty(tmp_path):
    target = tmp_path / "once"
    runner.claim(target)
    assert (target / "ATTEMPT_V2.json").exists()
    with pytest.raises(FileExistsError):
        runner.claim(target)


def test_short_xdxr_and_wrong_event_owner(tmp_path, monkeypatch):
    s = object.__new__(runner.ArchiveSession)
    s.directory = tmp_path
    packet = bytes(14) + b"\x01510300"
    payload = b"X" * 9 + b"\x01\x00" + b"\x00510300" + bytes(22)
    monkeypatch.setattr(runner.tdx.TdxSession, "request", lambda *args: payload)
    with pytest.raises(ValueError, match="ownership"):
        s.request(packet)
    assert (tmp_path / "xdxr.bin").read_bytes() == payload
