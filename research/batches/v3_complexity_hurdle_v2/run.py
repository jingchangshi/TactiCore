"""V3_COMPLEXITY_HURDLE_V2: Same-window complexity hurdle on bundle_202611 + v3_snapshot_20261126.

External Evidence Gate:
- Canonical mapping: A -> V3_DUAL_ANCHOR_SUPER_ETF; B -> STATIC_DIVERSIFICATION (S30 style);
  C -> ERC_RISK_PARITY (skfolio RiskBudgeting); D -> STATIC_60_40.
- External tier: A=E3_MIXED_CONDITIONAL; B=E1_MATURE; C=E2_ESTABLISHED_METHOD.
- External conclusion: 1/N & ERC lower estimation/commission drag in small accounts.
- Relevant contradictions: Kim/Tse/Wald (2016), Cederburg et al. (2020), RL-053,
  HURDLE_V1 4.52% fee drag.
- Upstream implementation: RQAlpha 6.3.0 (2018-01-02..2026-10-30) + VectorBT (..2026-11-26).
- Existing TactiCore evidence: EXP_V3_01_REGIME_SUPER_ETF.*, V3_COMPLEXITY_HURDLE_V1.json.
- Remaining local gap: §8 verdict after legalizing corporate-action full-close odd lots
  & 2026-H2 bear/gold crash.
- Research action: LOCAL_ADJUDICATION.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.ashare import v3_data_202611 as data
from research.ashare.experiments import exp_v3_01_regime_super_etf as exp
from research.batches.v3_complexity_hurdle_v2.native import NORMAL, SUPER, replay
from tacticore.engines.vectorbt_adapter import run_target_weights, validate_execution_targets

ROOT = Path("/home/jcshi/workspace/TactiCore")
STEM = ROOT / "research/results/V3_COMPLEXITY_HURDLE_V2"
PROTOCOL = ROOT / "research/batches/v3_complexity_hurdle_v2/PROTOCOL_V2.md"

START = data.EXP_START
RQA_END = data.BUNDLE_CUTOFF_202611
VBT_END = data.EXP_END_202611
STRESS_START = pd.Timestamp("2026-07-01")
CASH = (69000, 100000)

RISK = ("510300.SH", "510500.SH", "518880.SH", "511010.SH")
PRIMARY = ("159330.SZ", "159337.SZ", "518880.SH", "511010.SH")
CLEAR = "V3_REGIME_CLEARS_HURDLE"
OVERLAY = "V3_REGIME_IS_RISK_OVERLAY_NOT_RETURN_SOURCE"


class InvalidRun(RuntimeError):
    pass


class SolverFailure(RuntimeError):
    pass


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise InvalidRun(msg)


def utc() -> str:
    return pd.Timestamp.now("UTC").isoformat()


def erc_weights(returns: pd.DataFrame) -> pd.Series:
    """Upstream long-only variance equal-risk-budget solver via skfolio."""
    from skfolio import RiskMeasure
    from skfolio.optimization import RiskBudgeting

    model = RiskBudgeting(risk_measure=RiskMeasure.VARIANCE, min_weights=0.0, max_weights=1.0)
    try:
        model.fit(returns)
    except Exception as error:
        raise SolverFailure(f"skfolio RiskBudgeting failed: {error}") from error
    weights = pd.Series(model.weights_, index=returns.columns, dtype=float)
    if (
        not np.isfinite(weights).all()
        or (weights < -1e-12).any()
        or not np.isclose(weights.sum(), 1.0)
    ):
        raise SolverFailure("skfolio RiskBudgeting returned invalid weights")
    return weights.clip(lower=0.0) / weights.clip(lower=0.0).sum()


def four_sleeves(
    p: Any,
    erc: bool,
    *,
    start: pd.Timestamp = START,
    end: pd.Timestamp = VBT_END,
) -> pd.DataFrame:
    """Build causal four-sleeve weights (S30 static 25%x4 annual or S4C monthly skfolio ERC)."""
    cal = p.calendar[(p.calendar >= start) & (p.calendar <= end)]
    period = cal.to_period("M" if erc else "Y")
    w = pd.DataFrame(np.nan, index=p.calendar, columns=p.etf_adj_close.columns)
    counts = p.etf_adj_close[list(PRIMARY)].notna().cumsum()
    previous: set[str] = set()
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
            w.at[execution, sym] = 0.0
        w.loc[execution, codes] = allocation
        previous = set(codes)
    return w


def metrics(s: pd.Series) -> dict[str, Any]:
    ret = s.pct_change(fill_method=None).iloc[1:]
    years = max((s.index[-1] - s.index[0]).days / 365.25, 1.0 / 365.25)
    growth = float((s.iloc[-1] / s.iloc[0]) ** (1.0 / years) - 1.0)
    total_ret = float(s.iloc[-1] / s.iloc[0] - 1.0)
    dd = float((s / s.cummax() - 1.0).min())
    return {
        "total_return": total_ret,
        "cagr": growth,
        "max_drawdown": dd,
        "sharpe": float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() else None,
        "calmar": growth / abs(dd) if dd < 0 else None,
    }


def rolling(s: pd.Series, n: int = 756) -> pd.DataFrame:
    a = np.lib.stride_tricks.sliding_window_view(s.to_numpy(), n)
    years = (s.index[n - 1 :] - s.index[: len(a)]).days.to_numpy() / 365.25
    g = (a[:, -1] / a[:, 0]) ** (1.0 / years) - 1.0
    dd = np.min(a / np.maximum.accumulate(a, axis=1) - 1.0, axis=1)
    return pd.DataFrame(
        {
            "cagr": g,
            "max_drawdown": dd,
            "calmar": np.divide(g, -dd, out=np.full_like(g, np.nan), where=dd < 0),
        },
        index=s.index[n - 1 :],
    )


def statistics(eq: pd.Series, run: dict[str, Any], cash: float) -> pd.DataFrame:
    ret = eq.pct_change(fill_method=None).iloc[1:]
    annual = {int(k): float(v) for k, v in ((1 + ret).groupby(ret.index.year).prod() - 1).items()}
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    roll = rolling(eq)
    fees = sum(float(f["commission"]) for f in run["fills"])
    run.update(
        full=metrics(eq),
        IS=metrics(eq.loc[: data.IS_END]),
        OOS=metrics(eq.loc[data.IS_END :]),
        cvar5=float(ret.nsmallest(math.ceil(len(ret) * 0.05)).mean()),
        by_year=annual,
        worst_year=min(range(2018, 2026), key=annual.__getitem__),
        ytd_2026=annual[2026],
        worst_year_return=min(annual[y] for y in range(2018, 2026)),
        annual_one_way_turnover=sum(float(f["notional"]) for f in run["fills"])
        / (2.0 * float(eq.mean()) * years),
        trade_count=len(run["fills"]),
        reject_count=len(run["rejects"]),
        commission=fees,
        commission_to_initial=fees / cash,
        rolling={
            "windows": len(roll),
            "cagr_min": float(roll.cagr.min()),
            "cagr_median": float(roll.cagr.median()),
            "worst_max_drawdown": float(roll.max_drawdown.min()),
        },
        daily_total_value={str(k.date()): float(v) for k, v in eq.items()},
    )
    return roll


def verdict(runs: dict[str, Any], gates: dict[str, Any]) -> str:
    if not gates or not all(gates.values()):
        return "INVALID_RUN"
    clears, overlays = [], []
    for cash in CASH:
        a, b, c = (runs[f"{arm}_{cash}"]["full"] for arm in "ABC")

        def beats(x: dict[str, Any], m: str, candidate: dict[str, Any] = a) -> bool:
            return candidate[m] is not None and x[m] is not None and candidate[m] >= x[m] + 0.10

        clears.append(all(beats(x, m) for x in (b, c) for m in ("sharpe", "calmar")))
        overlays.append(
            not beats(b, "sharpe")
            and not beats(b, "calmar")
            and a["max_drawdown"] < b["max_drawdown"] + 0.05
        )
    return CLEAR if all(clears) else OVERLAY if all(overlays) else "MIXED"


def guarded_regime(prov: Any, p: Any, cache_info: dict[str, Any]) -> pd.DataFrame:
    cache_path = data.REGIME_CACHE_PATH_202611
    require(cache_path.is_file(), f"missing regime cache {cache_path}")
    before = data.sha256_file(cache_path)
    cache_info["before"] = before
    df = pd.read_csv(cache_path, dtype={"trade_date": str, "snapshot_id": str})
    require(
        set(df["snapshot_id"]) == {prov.snapshot_id}
        and set(df["cache_version"]) == {data.REGIME_CACHE_VERSION_202611}
        and list(pd.to_datetime(df["trade_date"])) == list(p.calendar),
        "regime cache contract mismatch",
    )
    return data.compute_v3_regime_series_202611(
        prov, p.index_close, p.calendar, use_cache=True
    )


def research(report: dict[str, Any]) -> None:
    gates = report["gates"]
    prov = data.verify_v3_202611_provenance(verify_content=True)
    report["inputs"].update(
        snapshot_id=prov.snapshot_id,
        datasets=prov.dataset_hashes,
        auxiliary=prov.aux_hashes,
        whitelist=prov.whitelist_sha256,
        bundle={
            p.name: data.sha256_file(p)
            for p in sorted(data.BUNDLE_PATH_202611.iterdir())
            if p.is_file()
        },
        protocol_sha256=data.sha256_file(PROTOCOL),
    )
    gates["provenance"] = bool(prov.snapshot_id and prov.whitelist_sha256)
    require(gates["provenance"], "missing provenance")

    p = data.load_stitched_panels_202611(prov)
    require(
        p.etf_lifetimes["518880.SH"].listed_date == pd.Timestamp("2013-07-29"),
        "unexpected gold listing date",
    )
    reg = guarded_regime(prov, p, report["inputs"]["regime_cache"])

    a_w, events = exp.build_v3_execution_weights(p, reg, include_bond_reserve=True)
    weights = {
        "A": a_w,
        "B": four_sleeves(p, False, start=START, end=VBT_END),
        "C": four_sleeves(p, True, start=START, end=VBT_END),
        "D": exp.build_benchmark_weights(p, "STATIC_60_40"),
    }
    report["v3_event_count"] = len(events)

    def vbt(label: str, w: pd.DataFrame, end: pd.Timestamp, fees: Any) -> pd.Series:
        prices, mask, targets = (f.loc[:end] for f in (p.etf_adj_close, p.etf_tradability_mask, w))
        validate_execution_targets(targets, prices, mask, p.etf_lifetimes)
        report["validated_targets"].append(label)
        return run_target_weights(
            prices,
            targets,
            fees=fees,
            slippage=0.0002,
            initial_cash=100000.0,
            metric_start=START,
            tradability_mask=mask,
            lifetimes=p.etf_lifetimes,
        ).equity.loc[START:end]

    for arm, w in weights.items():
        rates = np.array([SUPER if c in prov.super_etf_codes else NORMAL for c in w.columns])[
            None, :
        ]
        eq_vbt = vbt(arm, w, VBT_END, rates)
        report["vbt"][arm] = {
            "full_2018_20261126": metrics(eq_vbt),
            "oos_2024_20261126": metrics(eq_vbt.loc[data.IS_END :]),
            "stress_202607_20261126": metrics(eq_vbt.loc[STRESS_START:VBT_END]),
        }
    gates["validate_execution_targets"] = len(report["validated_targets"]) == 4

    rolls: dict[str, pd.DataFrame] = {}
    for cash in CASH:
        for arm in "ABCD":
            label = f"{arm}_{cash}"
            print(utc(), label, flush=True)
            started = utc()
            eq, run = replay(
                weights[arm], cash, prov.super_etf_codes, True, start=START, end=RQA_END
            )
            run.update(started=started, finished=utc(), initial_cash=cash, tiered=True)
            report["runs"][label] = run
            require(
                eq.index.equals(p.calendar[(p.calendar >= START) & (p.calendar <= RQA_END)])
                and eq.notna().all()
                and eq.iloc[0] == cash,
                f"native equity coverage/initial cash failed for {label}",
            )
            rolls[label] = statistics(eq, run, cash)

    for cash in CASH:
        aa, bb = (rolls[f"{arm}_{cash}"] for arm in "AB")
        report["rolling_A_vs_B"][str(cash)] = {
            m: float((aa[m] > bb[m]).mean()) for m in ("cagr", "calmar")
        }

    runs = list(report["runs"].values())
    gates["order_dates"] = all(r["dates_pass"] for r in runs)
    gates["lots_and_capture"] = all(
        r["fill_capture_pass"] and not r["commission_audit"]["illegal_non_lot_fills"]
        for r in runs
    )
    gates["commissions"] = all(r["commission_audit"]["fees_pass"] for r in runs)


def reserve(stem: Path) -> None:
    markers = [stem.with_suffix(ext) for ext in (".md", ".json", ".attempt")]
    if any(p.exists() for p in markers):
        raise FileExistsError("prior result/attempt; no rerun")
    with markers[-1].open("x", encoding="utf-8") as f:
        f.write(utc() + "\n")


def markdown(r: dict[str, Any]) -> str:
    lines = [
        "# V3 同窗口复杂度门槛 V2（2018-01-02..2026-10-30 原生 / ..2026-11-26 VBT）",
        "",
        f"裁决：`{r['verdict']}`。仅为历史诊断，不修改已签发 `v3.2.1` release。",
        "",
        "## 1. RQAlpha 6.3.0 原生全窗回放（2018-01-02..2026-10-30，真实分层费率）",
        "",
        (
            "| 回放 | CAGR | MaxDD | Sharpe | Calmar | CVaR5 | 年换手 | 成交 | 拒单 "
            "| 佣金(元) | 佣金占比 | 公司行动全清零股 | 非法零股 |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k, v in r["runs"].items():
        if "full" not in v:
            continue
        m = v["full"]
        ca = v["commission_audit"]
        n_corp = len(ca["corporate_action_full_close_odd_lots"])
        n_ill = len(ca["illegal_non_lot_fills"])
        lines.append(
            f"| {k} | {m['cagr']:.2%} | {m['max_drawdown']:.2%} | {m['sharpe']:.3f} | "
            f"{m['calmar']:.3f} | {v['cvar5']:.2%} | {v['annual_one_way_turnover']:.2f} | "
            f"{v['trade_count']} | {v['reject_count']} | {v['commission']:.2f} | "
            f"{v['commission_to_initial']:.2%} | {n_corp} | {n_ill} |"
        )
    lines += [
        "",
        "## 2. VectorBT 全窗与 2026-07..11-26 深熊/黄金冲击切片",
        "",
        (
            "| Arm | 全窗 CAGR | 全窗 MaxDD | 全窗 Sharpe | 全窗 Calmar "
            "| 2026-07..11-26 收益 | 2026-07..11-26 MaxDD |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, blk in r["vbt"].items():
        f_m = blk["full_2018_20261126"]
        s_m = blk["stress_202607_20261126"]
        lines.append(
            f"| {arm} | {f_m['cagr']:.2%} | {f_m['max_drawdown']:.2%} | {f_m['sharpe']:.3f} | "
            f"{f_m['calmar']:.3f} | {s_m['total_return']:.2%} | {s_m['max_drawdown']:.2%} |"
        )
    lines += ["", "## 3. 完整性门槛", *(f"- {k}: `{v}`" for k, v in r["gates"].items())]
    if "error" in r:
        lines += ["", f"错误：`{r['error']}`"]
    return "\n".join(lines) + "\n"


def main() -> int:
    reserve(STEM)
    report: dict[str, Any] = {
        "started": utc(),
        "runner_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "versions": {k: version(k) for k in ("rqalpha", "vectorbt", "skfolio")},
        "inputs": {"regime_cache": {}},
        "runs": {},
        "vbt": {},
        "validated_targets": [],
        "rolling_A_vs_B": {},
        "gates": {},
    }
    try:
        require(
            report["versions"]["rqalpha"] == "6.3.0" and report["versions"]["skfolio"] == "1.0.6",
            "engine versions mismatch",
        )
        research(report)
    except Exception as exc:
        import traceback

        traceback.print_exc()
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["gates"]["completed"] = False

    cache = report["inputs"]["regime_cache"]
    after = (
        data.sha256_file(data.REGIME_CACHE_PATH_202611)
        if data.REGIME_CACHE_PATH_202611.is_file()
        else None
    )
    cache["after"] = after
    report["gates"]["regime_cache"] = bool(after and after == cache.get("before"))
    report["verdict"] = verdict(report["runs"], report["gates"])
    code = int(report["verdict"] == "INVALID_RUN")
    report.update(finished=utc(), exit_code=code)
    with STEM.with_suffix(".json").open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, allow_nan=False, indent=1)
        f.write("\n")
    with STEM.with_suffix(".md").open("x", encoding="utf-8") as f:
        f.write(markdown(report))
    print(report["verdict"], flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
