"""One real run only: python -I research/batches/free_data_contract_v1/run_equivalence_v2.py"""

# ruff: noqa: E402 -- isolated interpreter, explicit trusted import root
from __future__ import annotations

import hashlib
import json
import os
import platform
import struct
import subprocess
import sys
import traceback
from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))  # Trusted worktree only; never import from the private data dir.
import pandas as pd

from research.batches.free_data_contract_v1 import fetch_tdx_history as tdx
from research.batches.free_data_contract_v1.contract_v2 import CUTOFF, adjust, compare, iso
from tacticore.data.prices import load_price_csv

BATCH = Path(__file__).resolve().parent
PRIVATE = Path("/home/jcshi/workspace/free-v2-private")
PROTOCOL = "d3258a2398e23389b01d08107385dc7608a0bb97"
BASE = "6bc99b8d7c2f6ffee3e5110815878f5c8de696c6"
PROTOCOL_SHA = "c74833f4194521c22920cceeb828dcda48ff089f7b9bbdd4b499f782aab62591"
CANON = "data/canonical/etf_adjusted_close.csv"
UNIVERSE = "config/universe.csv"
STRATEGY = "config/strategy.toml"
REF = {
    "S2_R1": "research/results/s2_v2_frozen_targets.csv",
    "S4C_R1": "research/results/s4c_pit_corrected_frozen_targets_v1.csv",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def write(path, payload):
    with path.open("x", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        f.write("\n")


def claim(directory):
    directory.mkdir(mode=0o700, exist_ok=False)
    write(
        directory / "ATTEMPT_V2.json",
        {
            "started_utc": now(),
            "protocol_commit": PROTOCOL,
            "runner_commit": git("rev-parse", "HEAD").decode().strip(),
        },
    )


class ArchiveSession(tdx.TdxSession):
    """Retain each received payload before decoding. No probe, reconnect or second request."""

    directory: Path

    def request(self, packet):
        body = super().request(packet)
        if packet in (tdx.HELLO1, tdx.HELLO2):
            return body
        if len(packet) == 38:
            start = struct.unpack_from("<H", packet, 24)[0]
            name = f"bars_{start}.bin"
        else:
            name = "xdxr.bin"
        with (self.directory / name).open("xb") as f:
            f.write(body)
        if name == "xdxr.bin":
            # The response may explicitly report zero securities, or carry a count and 29-byte rows.
            if body == b"\x00\x00":
                return body
            if len(body) < 11 or len(body) != 11 + 29 * int.from_bytes(body[9:11], "little"):
                raise ValueError(f"{self.directory.name}: truncated/ambiguous xdxr")
            for i in range(11, len(body), 29):
                if body[i : i + 7] != packet[14:21]:
                    raise ValueError(
                        f"{self.directory.name}: ambiguous xdxr ownership (row {(i - 11) // 29})"
                    )
        elif len(body) < 2:
            raise ValueError(f"{self.directory.name}: truncated daily page")
        return body


def snapshot(directory, info):
    started = now()
    info["stage"] = "CONNECT"
    errors = {}
    for host in tdx.DEFAULT_HOSTS:
        try:
            session = ArchiveSession(host)
            break
        except (OSError, EOFError) as e:
            errors[host] = str(e)
    else:
        raise ConnectionError(f"no handshake: {errors}")
    info["selected_host"] = host
    info["stage"] = "SNAPSHOT"
    series = []
    records = []
    with closing(session):
        for row in pd.read_csv(ROOT / UNIVERSE, dtype=str).itertuples():
            sym = row.symbol
            asset = directory / sym
            asset.mkdir(mode=0o700)
            session.directory = asset
            print(now(), sym, flush=True)
            bars, events = tdx.fetch_symbol(session, sym)
            write(asset / "daily.json", bars)
            write(asset / "xdxr.json", events)
            s, applied = adjust(sym, bars, events, row.start_date)
            series.append(s)
            records.append(
                dict(
                    symbol=sym,
                    list_date=row.start_date,
                    raw_rows=len(bars),
                    raw_first=bars[0]["date"],
                    raw_last=bars[-1]["date"],
                    rows=len(s),
                    first=iso(s.index[0]),
                    last=iso(s.index[-1]),
                    all_events=events,
                    applied=applied,
                )
            )
    path = directory / "etf_adjusted_close.csv"
    pd.concat(series, axis=1).sort_index().to_csv(
        path, date_format="%Y-%m-%d", float_format="%.8f", lineterminator="\n", mode="x"
    )
    prices = load_price_csv(path)  # Validate serialized (not just in-memory) prices.
    manifest = dict(
        contract="FREE_DATA_CONTRACT_V2",
        protocol_sha256=PROTOCOL_SHA,
        protocol_commit=PROTOCOL,
        runner_commit=info["runner_commit"],
        inputs=info["inputs"],
        started_utc=started,
        ended_utc=now(),
        host=host,
        source=tdx.SOURCE,
        request=dict(category=9, page=800, xdxr="get_xdxr_info", port=tdx.PORT),
        cutoff=CUTOFF,
        availability="Current vendor view; closes after Shanghai 15:00, not vintage data",
        records=records,
        files={
            str(p.relative_to(directory)): tdx.sha256(p)
            for p in sorted(directory.rglob("*"))
            if p.is_file()
        },
    )
    write(directory / "manifest.json", manifest)
    info["snapshot_sha256"] = tdx.sha256(directory / "manifest.json")
    info["coverage"] = [
        {k: v for k, v in r.items() if k not in ("all_events", "applied")}
        | {"applied_events": len(r["applied"])}
        for r in records
    ]
    return prices


def derive(candidate, prices):
    from research.experiments.run_s2_rqalpha_validation import (
        build_frozen_target_schedule,
        load_trend_config,
    )
    from research.experiments.run_s4c_rqalpha_execution_review import (
        S4CConfig,
        build_frozen_schedule,
        load_tradability_inputs,
    )

    strategy = load_trend_config(ROOT / STRATEGY)
    if candidate == "S2_R1":
        return build_frozen_target_schedule(prices, strategy)
    mask, life = load_tradability_inputs(prices, str(ROOT / UNIVERSE))
    cfg = S4CConfig(
        strategy.fallback_symbol, strategy.fees, strategy.slippage, strategy.initial_cash
    )
    return build_frozen_schedule(prices, tuple(strategy.risk_symbols), mask, life, cfg)[0]


def adjudicate(info, canonical, free, refs, generate=derive):
    for key, prices in [("controls", canonical), ("comparisons", free)]:
        info["stage"] = key.upper()
        out = info[key] = {}
        for name, reference in refs.items():
            try:
                out[name] = compare(name, reference, generate(name, prices))
            except Exception as e:
                traceback.print_exc()
                out[name] = {"error_type": type(e).__name__, "passed": False}
                continue
            if key == "comparisons":
                info["verdicts"][name] = "EQUIVALENT" if out[name]["passed"] else "NOT_EQUIVALENT"
        if key == "controls" and not all(r["passed"] for r in out.values()):
            info["stage"] = "BLOCKED_CONTROL"
            return
    info["stage"] = (
        "COMPARED" if "NOT_COMPARED" not in info["verdicts"].values() else "COMPARISON_INCOMPLETE"
    )


def price_diagnostics(canon, free):
    diagnostics = {}
    for symbol in free:
        a, b = canon[symbol].align(free[symbol], join="outer")
        ret = (a.pct_change(fill_method=None) - b.pct_change(fill_method=None)).dropna().abs()
        diagnostics[symbol] = {
            "canonical_only_valid": int((a.notna() & b.isna()).sum()),
            "free_only_valid": int((a.isna() & b.notna()).sum()),
            "common_adjacent_returns": len(ret),
            "max_abs_return_delta": float(ret.max()) if len(ret) else None,
            "mean_abs_return_delta": float(ret.mean()) if len(ret) else None,
            "canonical_factor_events": "UNKNOWN: frozen input is adjusted closes only",
        }
    return diagnostics


def main():
    os.umask(0o077)
    result = BATCH / "EQUIVALENCE_RESULT_V2.json"
    if result.exists() or PRIVATE.exists() or PRIVATE.is_symlink():
        raise SystemExit("attempt or result exists; NEVER rerun")
    if (
        tdx.sha256(BATCH / "PROTOCOL_V2.md") != PROTOCOL_SHA
        or git("rev-parse", PROTOCOL + "^").decode().strip() != BASE
    ):
        raise SystemExit("protocol identity mismatch")
    if (
        git("status", "--porcelain")
        or git("rev-parse", "--abbrev-ref", "HEAD").strip() != b"feat/drop-tushare"
    ):
        raise SystemExit("runner must be committed on the designated clean branch")
    git("merge-base", "--is-ancestor", PROTOCOL, "HEAD")
    hashes = {}
    for name in (CANON, UNIVERSE, STRATEGY, *REF.values()):
        hashes[name] = tdx.sha256(ROOT / name)
        if hashes[name] != hashlib.sha256(git("show", BASE + ":" + name)).hexdigest():
            raise SystemExit("input drift: " + name)
    claim(PRIVATE)
    marker = PRIVATE / "ATTEMPT_V2.json"
    attempt = json.loads(marker.read_text())
    data = PRIVATE / "snapshot"
    data.mkdir(mode=0o700)
    info = dict(
        attempt,
        contract="FREE_DATA_CONTRACT_V2",
        protocol_sha256=PROTOCOL_SHA,
        input_commit=BASE,
        inputs=hashes,
        snapshot_sha256=None,
        stage="START",
        verdicts=dict.fromkeys(REF, "NOT_COMPARED"),
        environment={
            "platform": platform.platform(),
            "python": sys.version,
            "packages": {
                k: version(k)
                for k in ("numpy", "pandas", "skfolio", "scipy", "clarabel", "cvxpy-base")
            },
        },
        private_root=str(PRIVATE),
    )
    log = PRIVATE / "run.log"
    with log.open("x") as f, redirect_stdout(f), redirect_stderr(f):
        try:
            free = snapshot(data, info)
            info["stage"] = "CONTROL_INPUTS"
            canonical = load_price_csv(ROOT / CANON).loc[:CUTOFF]
            refs = {
                k: pd.read_csv(ROOT / v, index_col="execution_date", parse_dates=["execution_date"])
                for k, v in REF.items()
            }
            adjudicate(info, canonical, free, refs)
            if "comparisons" in info:
                info["price_diagnostics"] = price_diagnostics(canonical, free)
        except Exception as e:
            traceback.print_exc()
            info["error"] = {"type": type(e).__name__, "reason": str(e)}
        print(now(), info["stage"], info["verdicts"], flush=True)
    info.update(ended_utc=now(), log_sha256=tdx.sha256(log), attempt_sha256=tdx.sha256(marker))
    # Even when acquisition stopped early, identify every partial data file.
    inventory = PRIVATE / "file_hashes.json"
    write(
        inventory,
        {
            str(p.relative_to(PRIVATE)): tdx.sha256(p)
            for p in sorted(PRIVATE.rglob("*"))
            if p.is_file()
        },
    )
    info["private_file_hashes_sha256"] = tdx.sha256(inventory)
    info["returncode"] = 0 if info["stage"] == "COMPARED" else 2
    write(result, info)
    return info["returncode"]


if __name__ == "__main__":
    sys.exit(main())
