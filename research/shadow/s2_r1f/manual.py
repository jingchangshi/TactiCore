"""Manual S2_R1F seal/decision; no scheduler, R1 ledger or trading endpoint."""

# ruff: noqa: E402 -- isolated Python, only the trusted worktree enters the import path
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import closing
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd

from research.batches.free_data_contract_v1 import run_equivalence_v2 as v2
from research.batches.free_data_contract_v1.contract_v2 import adjust
from research.experiments.run_s2_r1_shadow import build_decision_record
from tacticore.data.prices import load_price_csv

IDENTITY = Path(__file__).with_name("candidate_manifest.json")
OUT = ROOT / "research/output/s2_r1f"
BASE = v2.PRIVATE / "snapshot"
SH = ZoneInfo("Asia/Shanghai")
sha = v2.tdx.sha256


def clock():
    return datetime.now(SH)


def today(day):
    t = clock()
    if day != t.date().isoformat() or t.time() < time(15):
        raise ValueError("requires today after 15:00 Asia/Shanghai; no backfill or future date")
    return t


def identity():
    if v2.git("diff", "HEAD", "--", str(IDENTITY.parent)):
        raise ValueError("uncommitted candidate code/identity")
    meta = json.loads(IDENTITY.read_bytes())
    for path, digest in meta["files"].items():
        if sha(ROOT / path) != digest:
            raise ValueError("candidate identity drift: " + path)
    if (
        sha(BASE / "manifest.json") != meta["historical_snapshot_sha256"]
        or sha(BASE / "etf_adjusted_close.csv") != meta["historical_prices_sha256"]
    ):
        raise ValueError("historical baseline mismatch")
    return meta


def source_dir(day):
    local = OUT / "inputs" / day
    # Bootstrap once from the authenticated raw payloads of the SAME DAY historical run.
    # No use of old V2 prices as a future vintage.
    if not local.exists() and day == "2026-11-25":
        return BASE
    return local


def collect(day):
    """Future manual same-day TDX raw inputs; distinct from the V2 historical experiment."""
    started = today(day)
    meta = identity()
    dest = OUT / "inputs" / day
    if day == "2026-11-25" or (OUT / "vintages" / day).exists():
        raise ValueError("source already captured")
    dest.mkdir(parents=True, exist_ok=False)
    for host in v2.tdx.DEFAULT_HOSTS:
        try:
            session = v2.ArchiveSession(host)
            break
        except OSError:
            continue
    else:
        raise ValueError("no TDX handshake")
    with closing(session):
        for symbol in pd.read_csv(ROOT / v2.UNIVERSE).symbol:
            sub = dest / symbol
            sub.mkdir()
            session.directory = sub
            bars, events = v2.tdx.fetch_symbol(session, symbol)
            v2.write(sub / "daily.json", bars)
            v2.write(sub / "xdxr.json", events)
    end = today(day)
    v2.write(
        dest / "manifest.json",
        dict(
            candidate=meta["candidate_id"],
            host=host,
            started_utc=started.isoformat(),
            ended_utc=end.isoformat(),
            files={str(p.relative_to(dest)): sha(p) for p in dest.rglob("*") if p.is_file()},
        ),
    )


def verified_prices(src, day, meta):
    manifest = json.loads((src / "manifest.json").read_bytes())
    t = today(day)
    if src == BASE and sha(src / "manifest.json") != meta["historical_snapshot_sha256"]:
        raise ValueError("raw snapshot mismatch")
    if src != BASE and manifest.get("candidate") != "S2_R1F":
        raise ValueError("not a candidate source")
    start = datetime.fromisoformat(manifest["started_utc"])
    end = datetime.fromisoformat(manifest["ended_utc"])
    for instant in [start, end]:
        if (
            instant.tzinfo is None
            or instant.astimezone(SH).date() != t.date()
            or instant.astimezone(SH).time() < time(15)
        ):
            raise ValueError("download not today after close")
    if not start <= end <= t:
        raise ValueError("invalid acquisition clock")
    series = []
    for r in pd.read_csv(ROOT / v2.UNIVERSE, dtype=str).itertuples():
        docs = []
        for file in ("daily.json", "xdxr.json"):
            k = f"{r.symbol}/{file}"
            p = src / k
            if sha(p) != manifest["files"][k]:
                raise ValueError("source file hash mismatch")
            docs.append(json.loads(p.read_bytes()))
        bars, events = docs
        if not bars or any(b["date"] > day for b in bars):
            raise ValueError("empty/future price input")
        s, _ = adjust(r.symbol, bars, events, r.start_date, day)
        series.append(s)
    prices = pd.concat(series, axis=1).sort_index()
    if prices.index[-1] != pd.Timestamp(day):
        raise ValueError("no actual current price")
    return prices


def vintage(day):
    return OUT / "vintages" / day


def seal(day):
    today(day)
    dest = vintage(day)
    if dest.exists():
        raise FileExistsError("vintage exists; no overwrite")
    meta = identity()
    src = source_dir(day)
    prices = verified_prices(src, day, meta)
    text = prices.to_csv(date_format="%Y-%m-%d", float_format="%.8f", lineterminator="\n")
    base = load_price_csv(BASE / "etf_adjusted_close.csv")
    from io import StringIO

    parsed = pd.read_csv(StringIO(text), index_col="date", parse_dates=["date"])
    if not parsed.loc[: v2.CUTOFF].equals(base):
        raise ValueError("vendor revision to frozen historical prices")
    # Bind overlapping previously sealed prospective vintages as well; never silently revise.
    for prior in sorted(dest.parent.glob("*/seal.json")):
        previous = json.loads(prior.read_bytes())
        p = prior.with_name("etf_adjusted_close.csv")
        if sha(p) != previous["prices_sha256"] or not parsed.loc[: previous["as_of"]].equals(
            load_price_csv(p)
        ):
            raise ValueError("overlap with prior vintage changed")
    today(day)
    dest.mkdir(parents=True, exist_ok=False)
    p = dest / "etf_adjusted_close.csv"
    with p.open("x") as f:
        f.write(text)
    v2.write(
        dest / "seal.json",
        dict(
            candidate="S2_R1F",
            as_of=day,
            sealed_at=today(day).isoformat(),
            prices_sha256=sha(p),
            source_sha256=sha(src / "manifest.json"),
            identity_sha256=sha(IDENTITY),
            kind="VINTAGE_ONLY_NOT_OBSERVATION",
            runner_commit=v2.git("rev-parse", "HEAD").decode().strip(),
        ),
    )


def is_month_end(day, meta):
    cal = meta["calendar"]
    asof = date.fromisoformat(day)
    if asof.year != cal["trusted_year"] or day < meta["eligible_since"]:
        raise ValueError("outside trusted candidate/calendar dates")
    path = Path(cal["path"])
    if sha(path) != cal["sha256"]:
        raise ValueError("calendar identity mismatch")
    days = [
        str(int(x))
        for x in np.load(path, allow_pickle=False)
        if str(int(x)).startswith(asof.strftime("%Y%m"))
    ]
    if not days:
        raise ValueError("calendar unavailable")
    return max(days) == asof.strftime("%Y%m%d")


def decide(day):
    today(day)
    meta = identity()
    dest = vintage(day)
    sealfile = dest / "seal.json"
    evidence = json.loads(sealfile.read_bytes())
    p = dest / "etf_adjusted_close.csv"
    stamp = datetime.fromisoformat(evidence["sealed_at"])
    if not (
        evidence["as_of"] == day
        and evidence["candidate"] == "S2_R1F"
        and stamp.tzinfo
        and stamp.astimezone(SH).date().isoformat() == day
        and time(15) <= stamp.astimezone(SH).time()
        and stamp <= today(day)
        and evidence["identity_sha256"] == sha(IDENTITY)
        and evidence["prices_sha256"] == sha(p)
        and evidence["source_sha256"] == sha(source_dir(day) / "manifest.json")
    ):
        raise ValueError("invalid vintage seal")
    if not is_month_end(day, meta):
        print("NOT_MONTH_END: vintage only; no observation")
        return
    prices = load_price_csv(p)
    if prices.index[-1] != pd.Timestamp(day):
        raise ValueError("not a same-day vintage")
    record = build_decision_record(
        prices,
        meta,
        as_of=pd.Timestamp(day),
        vintage_identifier=day,
        prospective_data_hash=sha(sealfile),
        manifest_hash=sha(IDENTITY),
        decision_seal_time=today(day).isoformat(),
        root=ROOT,
    )
    if record is None:
        raise ValueError("no eligible decision")
    target = OUT / "decisions" / f"{day}.json"
    target.parent.mkdir(exist_ok=True, parents=True)
    today(day)
    v2.write(target, dict(record, calendar_sha256=meta["calendar"]["sha256"]))
    print("SEALED_RESEARCH_DECISION_NO_EXECUTION")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["collect", "seal", "decide"])
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    try:
        {"seal": seal, "collect": collect, "decide": decide}[args.action](args.as_of)
    except (ValueError, OSError, KeyError) as e:
        print(type(e).__name__ + ":", e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
