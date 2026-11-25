"""One-shot historical diagnostic. See the preceding frozen PROTOCOL_V1.md."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

from research.ashare import v3_data as data
from research.ashare.experiments import exp_v3_01_regime_super_etf as exp
from research.experiments.run_s4c_erc_skfolio_transfer import erc_weights
from tacticore.data.tradability import (
    AssetLifetime,
    build_tradability_mask,
    validate_execution_targets,
)
from tacticore.engines.vectorbt_adapter import run_target_weights

from .native import NORMAL, SUPER, replay

ROOT = Path(__file__).resolve().parents[3]
STEM = ROOT / "research/results/V3_COMPLEXITY_HURDLE_V1"
PROTOCOL = Path(__file__).with_name("PROTOCOL_V1.md")
CACHE_HASH = "e3127d6bd13517b6762386f5886e161548e8489de781875223cedd82ea48bbfa"
WL_HASH = "d0c30ecc2c4f18de21827b02bff1db78cc29b853fe40481a17ad8d9facbb07c0"
START, END = data.EXP_START, data.BUNDLE_CUTOFF
CASH = (69000, 100000)
RISK = ("510300.SH", "510500.SH", "518880.SH", "511010.SH")
PRIMARY = ("159330.SZ", "159337.SZ")
CLEAR = "V3_REGIME_CLEARS_HURDLE"
OVERLAY = "V3_REGIME_IS_RISK_OVERLAY_NOT_RETURN_SOURCE"


class InvalidRun(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidRun(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def guarded_regime(prov, panels, evidence):
    # Use the SAME verified bytes for identity/coverage and the upstream read.
    # Even a future upstream cache-miss cannot write to the production directory.
    blob = data.REGIME_CACHE_PATH.read_bytes()
    evidence["before"] = hashlib.sha256(blob).hexdigest()
    require(evidence["before"] == CACHE_HASH, "regime cache SHA mismatch")
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "regime.csv"
        path.write_bytes(blob)
        frame = pd.read_csv(path, dtype={"trade_date": str, "snapshot_id": str})
        dates = pd.DatetimeIndex(pd.to_datetime(frame.trade_date))
        evidence.update(
            snapshot_id=prov.snapshot_id,
            cache_version=data.REGIME_CACHE_VERSION,
            rows=len(frame),
            required_days=len(panels.calendar),
            snapshot_match=frame.snapshot_id.eq(prov.snapshot_id).all().item(),
            version_match=frame.cache_version.eq(data.REGIME_CACHE_VERSION).all().item(),
            calendar_match=dates.is_unique and panels.calendar.isin(dates).all().item(),
        )
        require(
            evidence["snapshot_match"] and evidence["version_match"] and evidence["calendar_match"],
            "regime cache identity/version/calendar miss",
        )
        with (
            patch.object(data, "REGIME_CACHE_PATH", path),
            patch.object(
                data,
                "_compute_bundle_breadth",
                side_effect=InvalidRun("unexpected regime cache miss"),
            ),
        ):
            return data.compute_v3_market_regime_series(prov, panels.index_close, panels.calendar)


def with_gold(p):
    gold = RISK[2]
    raw, adj, listed, delisted = data._read_bundle_etf_series(
        data.open_bundle_source(data.BUNDLE_PATH), data.ts_to_rq(gold), END
    )
    require(listed == pd.Timestamp("2013-07-29"), "unexpected gold listing date")
    life = dict(p.etf_lifetimes, **{gold: AssetLifetime(gold, listed, delisted)})
    prices = p.etf_adj_close.assign(**{gold: adj.loc[listed:delisted]})
    mask = build_tradability_mask(p.calendar, [gold], life, prices)
    return replace(
        p,
        etf_adj_close=prices,
        etf_raw_close=p.etf_raw_close.assign(**{gold: raw.loc[listed:delisted]}),
        etf_lifetimes=life,
        etf_tradability_mask=p.etf_tradability_mask.join(mask),
    )


def four_sleeves(p, erc):
    cal = p.calendar[(p.calendar >= START) & (p.calendar <= END)]
    period = cal.to_period("M" if erc else "Y")
    w = pd.DataFrame(np.nan, index=p.calendar, columns=p.etf_adj_close.columns)
    counts = p.etf_adj_close[list(PRIMARY)].notna().cumsum()
    previous = set()
    for i, (signal, execution) in enumerate(zip(cal[:-1], cal[1:], strict=True)):
        if i and period[i] == period[i + 1]:
            continue
        codes = list(RISK)
        for j, primary in enumerate(PRIMARY):
            if (
                p.etf_tradability_mask.at[execution, primary]
                and counts.at[execution, primary] >= 20
            ):
                codes[j] = primary
        if erc:
            hist = p.etf_adj_close.loc[:signal, list(RISK)].dropna().tail(61)
            require(len(hist) == 61, f"insufficient ERC history {signal.date()}")
            allocation = (
                erc_weights(hist.pct_change(fill_method=None).iloc[1:]).loc[list(RISK)].to_numpy()
            )
        else:
            allocation = [0.25] * 4
        for sym in previous.difference(codes):
            w.at[execution, sym] = 0
        w.loc[execution, codes] = allocation
        previous = set(codes)
    return w


def metrics(s):
    ret = s.pct_change(fill_method=None).iloc[1:]
    years = (s.index[-1] - s.index[0]).days / 365.25
    growth = float((s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1)
    dd = float((s / s.cummax() - 1).min())
    return dict(
        cagr=growth,
        max_drawdown=dd,
        sharpe=float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() else None,
        calmar=growth / abs(dd) if dd < 0 else None,
    )


def rolling(s, n=756):
    a = np.lib.stride_tricks.sliding_window_view(s.to_numpy(), n)
    years = (s.index[n - 1 :] - s.index[: len(a)]).days.to_numpy() / 365.25
    g = (a[:, -1] / a[:, 0]) ** (1 / years) - 1
    dd = np.min(a / np.maximum.accumulate(a, axis=1) - 1, axis=1)
    return pd.DataFrame(
        dict(
            cagr=g,
            max_drawdown=dd,
            calmar=np.divide(g, -dd, out=np.full_like(g, np.nan), where=dd < 0),
        ),
        index=s.index[n - 1 :],
    )


def statistics(eq, run, cash):
    ret = eq.pct_change(fill_method=None).iloc[1:]
    annual = ((1 + ret).groupby(ret.index.year).prod() - 1).to_dict()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    roll = rolling(eq)
    fees = sum(f["commission"] for f in run["fills"])
    run.update(
        full=metrics(eq),
        IS=metrics(eq.loc[: data.IS_END]),
        OOS=metrics(eq.loc[data.IS_END :]),
        cvar5=float(ret.nsmallest(math.ceil(len(ret) * 0.05)).mean()),
        by_year=annual,
        worst_year=min(range(2018, 2026), key=annual.__getitem__),
        ytd_2026=annual[2026],
        worst_year_return=min(annual[y] for y in range(2018, 2026)),
        annual_one_way_turnover=sum(f["notional"] for f in run["fills"]) / (2 * eq.mean() * years),
        trade_count=len(run["fills"]),
        reject_count=len(run["rejects"]),
        commission=fees,
        commission_to_initial=fees / cash,
        rolling=dict(
            windows=len(roll),
            cagr_min=roll.cagr.min(),
            cagr_median=roll.cagr.median(),
            worst_max_drawdown=roll.max_drawdown.min(),
        ),
        daily_total_value={str(k.date()): v for k, v in eq.items()},
    )
    return roll


def verdict(runs, gates):
    if not gates or not all(gates.values()):
        return "INVALID_RUN"
    clears, overlays = [], []
    for cash in CASH:
        a, b, c = [runs[f"{arm}_{cash}"]["full"] for arm in "ABC"]

        def beats(x, m, candidate=a):
            return candidate[m] >= x[m] + 0.10

        clears.append(all(beats(x, m) for x in (b, c) for m in ("sharpe", "calmar")))
        overlays.append(
            not beats(b, "sharpe")
            and not beats(b, "calmar")
            and a["max_drawdown"] < b["max_drawdown"] + 0.05
        )
    return CLEAR if all(clears) else OVERLAY if all(overlays) else "MIXED"


def research(report):
    gates = report["gates"]
    prov = data.verify_v3_provenance(verify_content=True)
    inputs = report["inputs"]
    inputs.update(
        snapshot_id=prov.snapshot_id,
        datasets=prov.dataset_hashes,
        auxiliary=prov.aux_hashes,
        whitelist=prov.whitelist_sha256,
        bundle={
            p.name: data.sha256_file(p) for p in sorted(data.BUNDLE_PATH.iterdir()) if p.is_file()
        },
    )
    paths = [
        data.SNAPSHOT_DIR / "manifest.json",
        data.AUX_DIR / "aux_manifest.json",
        PROTOCOL,
        Path(exp.__file__),
        Path(data.__file__),
        data.WHITELIST_PATH.with_name("normal_etf_20261111.json"),
        ROOT / "research/results/EXP_V3_01_REGIME_SUPER_ETF.json",
    ]
    inputs["files"] = {p.name: data.sha256_file(p) for p in paths}
    gates["provenance"] = prov.whitelist_sha256 == WL_HASH
    require(gates["provenance"], "whitelist mismatch")
    p = data.load_stitched_panels(prov)
    reg = guarded_regime(prov, p, inputs["regime_cache"])
    a, events = exp.build_v3_execution_weights(p, reg, include_bond_reserve=True)
    gold = with_gold(p)
    weights = dict(
        A=a,
        B=four_sleeves(gold, False),
        C=four_sleeves(gold, True),
        D=exp.build_benchmark_weights(p, "STATIC_60_40"),
    )
    panels = dict(A=p, B=gold, C=gold, D=p)

    def vbt(label, panel, w, end, fees):
        prices, mask, targets = [
            f.loc[:end] for f in (panel.etf_adj_close, panel.etf_tradability_mask, w)
        ]
        validate_execution_targets(targets, prices, mask, panel.etf_lifetimes)
        report["validated_targets"].append(label)
        return run_target_weights(
            prices,
            targets,
            fees=fees,
            slippage=0.0002,
            initial_cash=100000,
            metric_start=START,
            tradability_mask=mask,
            lifetimes=panel.etf_lifetimes,
        ).equity.loc[START:end]

    check = metrics(vbt("A_reproduction", p, a, data.EXP_END, SUPER))
    report["vbt_reproduction"] = {**check, "events": len(events)}
    gates["vbt_reproduction"] = (
        abs(check["cagr"] - 0.047949955359549046) <= 1e-9
        and abs(check["max_drawdown"] + 0.1379056110690038) <= 1e-9
        and len(events) == 199
    )
    for arm, w in weights.items():
        rates = np.array([SUPER if c in prov.super_etf_codes else NORMAL for c in w.columns])[
            None, :
        ]
        report["vbt"][arm] = metrics(vbt(arm, panels[arm], w, END, rates))
    gates["validate_execution_targets"] = len(report["validated_targets"]) == 5
    rolls = {}
    for label, arm, cash, tiered in [("A_reproduction", "A", 100000, False)] + [
        (f"{arm}_{cash}", arm, cash, True) for cash in CASH for arm in "ABCD"
    ]:
        print(utc(), label, flush=True)
        started = utc()
        eq, run = replay(weights[arm], cash, prov.super_etf_codes, tiered)
        run.update(started=started, finished=utc(), initial_cash=cash, tiered=tiered)
        report["runs"][label] = run
        require(
            eq.index.equals(p.calendar[(p.calendar >= START) & (p.calendar <= END)])
            and eq.notna().all()
            and eq.iloc[0] == cash,
            "native equity coverage/initial cash",
        )
        rolls[label] = statistics(eq, run, cash)
        if not tiered:
            gates["native_reproduction"] = abs(run["summary_cagr"] - 0.04306911643401823) <= 1e-6
    for cash in CASH:
        aa, bb = (rolls[f"{arm}_{cash}"] for arm in "AB")
        report["rolling_A_vs_B"][cash] = {
            m: float((aa[m] > bb[m]).mean()) for m in ("cagr", "calmar")
        }
    runs = list(report["runs"].values())
    gates.update(
        order_dates=all(r["dates_pass"] for r in runs),
        lots_and_capture=all(
            r["fill_capture_pass"] and not r["commission_audit"]["non_lot_fills"] for r in runs
        ),
        commissions=all(r["commission_audit"]["fees_pass"] for r in runs),
    )


def reserve(stem):
    markers = [stem.with_suffix(ext) for ext in (".md", ".json", ".attempt")]
    if any(p.exists() for p in markers):
        raise FileExistsError("prior result/attempt; no rerun")
    marker = markers[-1]
    with marker.open("x") as f:
        f.write(utc() + "\n")


def markdown(r):
    lines = [
        "# V3 同窗口复杂度门槛",
        "",
        f"裁决：`{r['verdict']}`。仅为历史诊断，不创建候选或修改 release。",
        "",
        "权威数据为 RQAlpha 日终总资产；VBT 允许碎股、不含最低佣金，只作粗算。",
        "闲置现金收益按 0，对持现较多的臂不利。",
        "IS 至 2023-12-29；OOS 以该日收盘为基；3Y 为 756 个交易日净值观测。",
        "下单日指原生下单函数调用日，不是成交日。",
        "",
        "| 回放 | CAGR | MaxDD | Sharpe | Calmar | CVaR5 | 年换手 | 成交 | 拒单 | 佣金(元) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k, v in r["runs"].items():
        if "full" not in v:
            continue
        m = v["full"]
        lines.append(
            f"| {k} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {m['sharpe']:.3f} | "
            f"{m['calmar']:.3f} | {v['cvar5']:.2%} | {v['annual_one_way_turnover']:.2f} | "
            f"{v['trade_count']} | {v['reject_count']} | {v['commission']:.2f} |"
        )
    lines += [
        "",
        "完整性门槛：",
        *(f"- {k}: `{v}`" for k, v in r["gates"].items()),
        "",
        "同名 JSON 含 IS/OOS、分年、滚动指标、逐笔费用、下单日、净值、输入哈希和退出码。",
    ]
    if "error" in r:
        lines.append(r["error"])
    return "\n".join(lines) + "\n"


def main():
    reserve(STEM)
    report = dict(
        started=utc(),
        runner_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        versions={k: version(k) for k in ("rqalpha", "vectorbt", "skfolio")},
        inputs={"regime_cache": {}},
        runs={},
        vbt={},
        validated_targets=[],
        rolling_A_vs_B={},
        gates={},
    )
    try:
        require(
            report["versions"]["rqalpha"] == "6.3.0" and report["versions"]["skfolio"] == "1.0.6",
            "engine versions",
        )
        research(report)
    except Exception as exc:
        import traceback

        traceback.print_exc()
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["gates"]["completed"] = False
    after = data.sha256_file(data.REGIME_CACHE_PATH) if data.REGIME_CACHE_PATH.is_file() else None
    cache = report["inputs"]["regime_cache"]
    cache["after"] = after
    report["gates"]["regime_cache"] = after == cache.get("before") == CACHE_HASH
    report["verdict"] = verdict(report["runs"], report["gates"])
    code = int(report["verdict"] == "INVALID_RUN")
    report.update(finished=utc(), exit_code=code)
    with STEM.with_suffix(".json").open("x") as f:
        json.dump(report, f, ensure_ascii=False, allow_nan=False, indent=1)
        f.write("\n")
    with STEM.with_suffix(".md").open("x") as f:
        f.write(markdown(report))
    print(report["verdict"], flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
