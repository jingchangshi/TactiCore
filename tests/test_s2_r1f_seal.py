"""Synthetic manual S2_R1F clocks, input refusal and month-end decisions; no real quotes."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from research.shadow.s2_r1f import manual as m


def test_clock_boundary(monkeypatch):
    for hour in (14, 15):
        monkeypatch.setattr(m, "clock", lambda h=hour: datetime(2026, 11, 30, h, 0, tzinfo=m.SH))
        if hour == 14:
            with pytest.raises(ValueError):
                m.today("2026-11-30")
        else:
            assert m.today("2026-11-30").hour == 15
    for wrong in ("2026-11-29", "2026-12-01"):
        with pytest.raises(ValueError):
            m.today(wrong)


def test_manual_chain(tmp_path, monkeypatch):
    day = "2026-11-30"
    monkeypatch.setattr(m, "clock", lambda: datetime(2026, 11, 30, 16, tzinfo=m.SH))
    monkeypatch.setattr(m, "OUT", tmp_path / "out")
    monkeypatch.setattr(m, "BASE", tmp_path / "base")
    m.BASE.mkdir()
    cal = tmp_path / "dates.npy"
    np.save(cal, [20261125, 20261130, 20261201, 20271231])
    meta = {
        "candidate_id": "S2_R1F",
        "eligible_since": "2026-11-25",
        "calendar": {"path": str(cal), "sha256": m.sha(cal), "trusted_year": 2026},
    }
    monkeypatch.setattr(m, "identity", lambda: meta)
    assert not m.is_month_end("2026-11-25", meta)
    with pytest.raises(ValueError):
        m.is_month_end("2027-12-31", meta)
    with pytest.raises(FileNotFoundError):
        m.seal(day)
    assert not m.vintage(day).exists()
    real_root = m.ROOT
    syms = pd.read_csv(real_root / m.v2.UNIVERSE).symbol
    dates = pd.date_range("2025-11-30", day)
    prices = pd.DataFrame({s: np.arange(len(dates)) + 1.0 for s in syms}, index=dates)
    prices.index.name = "date"
    prices.loc[: m.v2.CUTOFF].to_csv(m.BASE / "etf_adjusted_close.csv", float_format="%.8f")
    source = m.source_dir(day)
    source.mkdir(parents=True)
    m.v2.write(source / "manifest.json", {"synthetic": True})
    monkeypatch.setattr(m, "verified_prices", lambda *a: prices)
    m.seal(day)
    p = m.vintage(day) / "seal.json"
    before = m.sha(p)
    with pytest.raises(FileExistsError):
        m.seal(day)
    assert before == m.sha(p)
    m.decide(day)
    record = m.OUT / "decisions" / f"{day}.json"
    assert record.is_file()
    old = m.sha(record)
    with pytest.raises(FileExistsError):
        m.decide(day)
    assert old == m.sha(record)
    (m.vintage(day) / "etf_adjusted_close.csv").write_text("wrong")
    with pytest.raises(ValueError, match="seal"):
        m.decide(day)
