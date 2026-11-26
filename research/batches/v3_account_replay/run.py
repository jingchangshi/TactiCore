"""EXP-V3-05 only. External Evidence Gate: GTAA/BP1/concentration, E3/E4,
non-transferability of sleeve returns, lock/rebound contradiction, native RQAlpha,
EXP-01..04B, remaining single-account gap, LOCAL_ADJUDICATION. PIT: dated
life, no pre-listing proxy for 159558, listed broad fallback, next-open only,
2018 IS/July 2024 OOS, positive orders require usable auction price. Protocol owns details.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from research.ashare import v3_data as vd
from research.ashare.data.contract import sha256_file
from research.ashare.engines.bundle_source import bundle_calendar, open_bundle_source

from .native import replay
from .policy import FOCUS, GOLD, GROWTH, SECTORS, VALUE, indicators

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESULTS = ROOT / "research/results"
PREFIX = "EXP_V3_05_ACCOUNT_REPLAY"
PROTOCOL_SHA = "b293a2d9b8178f9b25a47d24bf368b4c8f001dacc6c5b71dfb27bb2dd13c0ea2"
CACHE_SHA = "e3127d6bd13517b6762386f5886e161548e8489de781875223cedd82ea48bbfa"
SNAPSHOT_ID = "ca43f6393393056d6b318bba792c3f6c70c7c5d786f72a7ec6beab366d5b5a78"
WINDOWS = {
    "IS_CASH": ("2018-01-02", "2023-12-29", 0.0),
    "OOS_CORE25": ("2024-07-01", "2026-08-31", 0.25),
    "OOS_HEAVY70": ("2024-07-01", "2026-08-31", 0.70),
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def claim(directory):
    if list(directory.glob(PREFIX + "*")):
        raise FileExistsError("An EXP-V3-05 artifact exists; do not retry")
    path = directory / (PREFIX + ".attempt")
    with path.open("x") as f:
        json.dump(dict(start=utc(), argv=sys.argv, cwd=str(Path.cwd())), f)
    return path


def prepare():
    if version("rqalpha") != "6.3.0" or sha256_file(HERE / "PROTOCOL_V1.md") != PROTOCOL_SHA:
        raise ValueError("protocol or engine version mismatch")
    prov = vd.verify_v3_provenance(verify_content=True)
    if prov.snapshot_id != SNAPSHOT_ID or sha256_file(vd.REGIME_CACHE_PATH) != CACHE_SHA:
        raise ValueError("unexpected snapshot/cache")
    if prov.whitelist_sha256 != "d0c30ecc2c4f18de21827b02bff1db78cc29b853fe40481a17ad8d9facbb07c0":
        raise ValueError("unexpected whitelist")
    src = open_bundle_source(vd.BUNDLE_PATH)
    cal = bundle_calendar(src, vd.WARMUP_START, vd.BUNDLE_CUTOFF)
    idx = pd.DataFrame(
        {
            c: vd._read_bundle_index_series(src, vd.ts_to_rq(c), vd.BUNDLE_CUTOFF)
            for c in vd.INDEX_CODES
        }
    ).reindex(cal)
    with TemporaryDirectory() as tmp:
        copy = Path(tmp) / "breadth.csv"
        copy.write_bytes(vd.REGIME_CACHE_PATH.read_bytes())
        cached = pd.read_csv(copy, dtype={"trade_date": str})
        if not (
            cached.snapshot_id.eq(SNAPSHOT_ID).all()
            and cached.cache_version.eq(vd.REGIME_CACHE_VERSION).all()
            and not cached.trade_date.duplicated().any()
            and set(cal.strftime("%Y%m%d")) <= set(cached.trade_date)
        ):
            raise ValueError("incomplete sealed breadth cache")
        with patch.object(vd, "REGIME_CACHE_PATH", copy):
            reg = vd.compute_v3_market_regime_series(prov, idx, cal)
        if sha256_file(copy) != CACHE_SHA:
            raise ValueError("cache regenerated")
    market = {str(d.date()): (r.confirmed_regime, r["style"]) for d, r in reg.iterrows()}
    features = {d: {} for d in market}
    for sym in sorted(set(VALUE + GROWTH + SECTORS + (FOCUS, GOLD))):
        raw, adj, listed, delisted = vd._read_bundle_etf_series(src, sym, vd.BUNDLE_CUTOFF)
        bars = indicators(adj, raw)
        for r in bars.itertuples():
            d = str(r.Index.date())
            if (
                d in features
                and r.Index >= listed
                and (delisted is None or r.Index <= delisted)
                and r.raw > 0
            ):
                features[d][sym] = r
    files = [
        vd.SNAPSHOT_DIR / "manifest.json",
        vd.AUX_DIR / "aux_manifest.json",
        vd.REGIME_CACHE_PATH,
        *sorted(vd.WHITELIST_PATH.parent.glob("*.json")),
        *sorted(HERE.glob("*.py")),
        HERE / "PROTOCOL_V1.md",
        ROOT / "tests/test_v3_account_replay.py",
        Path(vd.__file__),
    ]
    hashed = dict(
        snapshot_id=prov.snapshot_id,
        datasets=prov.dataset_hashes,
        auxiliary=prov.aux_hashes,
        files={str(p): sha256_file(p) for p in files},
        bundle={p.name: sha256_file(p) for p in sorted(vd.BUNDLE_PATH.iterdir()) if p.is_file()},
    )
    return market, features, {vd.ts_to_rq(c) for c in prov.super_etf_codes}, hashed


def summarize(res, capital):
    rows, fills, orders = res["daily"], res["fills"], res["orders"]
    last = rows[-1]["nav"]
    breach = [r for r in rows if r["breach"] > 1e-12]
    triggers = []
    for i, r in enumerate(rows):
        if r["trigger"]:
            reached = next(
                (j for j in range(i + 1, len(rows)) if rows[j]["risk"] <= r["cap"] + 1e-10), None
            )
            triggers.append(
                dict(
                    date=r["date"],
                    cap=r["cap"],
                    dd=r["dd"],
                    first_compliant_close=rows[reached]["date"] if reached is not None else None,
                    lag_sessions=reached - i if reached is not None else None,
                )
            )
    by_stage, by_symbol, by_group = {}, {}, Counter()
    for f in fills:
        for table, k in ((by_stage, f["reason"]), (by_symbol, f["code"])):
            bucket = table.setdefault(k, dict(fills=0, notional=0.0, fee=0.0))
            bucket["fills"] += 1
            bucket["notional"] += f["notional"]
            bucket["fee"] += f["commission"] + f["tax"] + f["other"]
    for r in rows:
        by_group.update(r["pnl"])
    return dict(
        nav=last,
        net_return=last / capital - 1,
        max_drawdown=max(r["dd"] for r in rows),
        crossed_15_dates=[r["date"] for r in breach],
        max_over15_pp=100 * max((r["breach"] for r in rows), default=0.0),
        max_over15_yuan=max((r["breach"] * r["hwm"] for r in rows), default=0.0),
        shadow_hit_days=sum(r["shadow_hit"] for r in rows),
        triggers=triggers,
        locked_days=sum(r["locked"] for r in rows),
        fills=len(fills),
        rejected_events=len(res["rejects"]),
        statuses=dict(Counter(o["status"] for o in orders)),
        odd_lot_liquidations=sum(f["qty"] % 100 != 0 for f in fills),
        fees=sum(b["fee"] for b in by_stage.values()),
        conflicts=len(res["conflicts"]),
        holdings_over_regime_cap=sum(
            r["risk"]
            > {"OFFENSIVE": 0.85, "STRUCTURAL": 0.60, "DEFENSIVE": 0.15}[r["regime"]] + 1e-9
            for r in rows
        ),
        reasons=by_stage,
        symbols=by_symbol,
        group_native_daily_pnl=dict(by_group),
        pnl_residual=last - capital - sum(by_group.values()),
        violations=res["violations"],
    )


def compare(locked, never, capital):
    trigger = any(r["trigger"] for r in locked)
    if not trigger:
        return dict(
            identified=False,
            final_gap_yuan=None,
            final_gap_pp=None,
            mdd_gap_pp=None,
            locked_sessions_pnl_gap=None,
        )
    gap = never[-1]["nav"] - locked[-1]["nav"]
    # Decision at prior close binds the following session, including its opening trade.
    realized = sum(
        (never[i]["nav"] - never[i - 1]["nav"]) - (locked[i]["nav"] - locked[i - 1]["nav"])
        for i in range(1, len(locked))
        if locked[i - 1]["locked"]
    )
    return dict(
        identified=True,
        final_gap_yuan=gap,
        final_gap_pp=100 * gap / capital,
        mdd_gap_pp=100 * (max(r["dd"] for r in never) - max(r["dd"] for r in locked)),
        locked_sessions_pnl_gap=realized,
    )


def main():
    if Path.cwd().resolve() != ROOT or ROOT.name != "v3e-05":
        raise SystemExit("run only in designated worktree")
    claim(RESULTS)
    report = dict(
        start=utc(),
        engine=version("rqalpha"),
        commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        cells={},
        pairs={},
        files={},
        coverage="PARTIAL_DATA",
        stock="IS: no PIT financials; both: no PIT float cap",
    )
    try:
        market, features, white, report["inputs"] = prepare()
        for name, (start, end, seed) in WINDOWS.items():
            days = sorted(d for d in market if start <= d <= end)
            if (days[0], days[-1]) != (start, end):
                raise ValueError("incomplete window endpoints")
            for capital in (69000, 100000):
                pair = {}
                for enabled, arm in ((True, "LOCK"), (False, "NEVER_L2")):
                    key = f"{name}_{capital}_{arm}"
                    res = replay(days, market, features, white, capital, seed, enabled)
                    p = RESULTS / f"{PREFIX}_{key}.json.gz"
                    with p.open("xb") as f:
                        f.write(gzip.compress(dump(res), mtime=0))
                    report["files"][p.name] = sha256_file(p)
                    report["cells"][key] = summarize(res, capital)
                    pair[arm] = res["daily"]
                    print("sealed", key, "violations", len(res["violations"]), flush=True)
                report["pairs"][f"{name}_{capital}"] = compare(
                    pair["LOCK"], pair["NEVER_L2"], capital
                )
        cells = report["cells"]
        if len(cells) != 12 or any(r["violations"] for r in cells.values()):
            raise ValueError("integrity failure; no economic adjudication")
        report["verdict"] = (
            "REDLINE_BREACHED"
            if any(
                r["max_drawdown"] > 0.15 + 1e-12 for k, r in cells.items() if k.endswith("_LOCK")
            )
            else "NO_OBSERVED_BREACH"
        )
        rc = 0
    except Exception:
        report.update(verdict="INVALID_RUN", error=traceback.format_exc())
        rc = 1
    report["end"], report["exit_code"] = utc(), rc
    with (RESULTS / (PREFIX + ".json")).open("xb") as out:
        out.write(dump(report))
    print(report["verdict"], report.get("error", ""), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
