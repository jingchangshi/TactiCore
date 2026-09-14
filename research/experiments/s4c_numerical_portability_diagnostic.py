#!/usr/bin/env python3
# ruff: noqa: E501
"""S4C 冻结语义跨环境数值可移植性只读诊断。

它比较「committed 冻结目标 artifact」与「由冻结语义重新推导的日程」，并记录环境指纹与逐值差异
统计，供独立分类使用：

    NUMERICALLY_EQUIVALENT / MATERIAL_SOLVER_DIVERGENCE / UNRESOLVED

本诊断是只读的：不修改 candidate、冻结目标 artifact、historical canonical data 或任何 evidence
bytes，也不产生任何宽松容差。它只测量，不裁决，不修改 verifier 行为。
"""

from __future__ import annotations

import json
import platform
import sys
from argparse import ArgumentParser
from hashlib import sha256
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.experiments import run_s4c_rqalpha_execution_review as review

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("numpy", "pandas", "scipy", "cvxpy", "cvxpy-base", "skfolio")
DELTA_THRESHOLDS = (1e-12, 1e-10, 1e-8, 1e-6, 1e-5, 1e-4, 1e-2)
PERCENTILES = (0.50, 0.90, 0.95, 0.99, 1.00)
TOP_DIFFERENCES = 10
DEFAULT_OUTPUT = ROOT / "research/results/S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LOCAL_V1.json"
PENDING = "PENDING_INDEPENDENT_REVIEW"


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def blas_lapack_fingerprint() -> dict[str, Any]:
    try:
        config = np.show_config(mode="dicts")
    except (TypeError, AttributeError) as error:  # pragma: no cover - numpy < 1.26
        return {"available": False, "reason": str(error)}
    dependencies = config.get("Build Dependencies", {})
    blas = (dependencies.get("blas") or {}).get("name")
    lapack = (dependencies.get("lapack") or {}).get("name")
    return {"available": True, "blas": blas, "lapack": lapack}


def _problem_attributes(model: object) -> dict[str, Any]:
    """尽量读出 skfolio 内部 cvxpy problem 的 solver/status（不可得则显式记录）。"""
    for attribute in ("problem_", "problem", "_problem"):
        problem = getattr(model, attribute, None)
        if problem is None:
            continue
        stats = getattr(problem, "solver_stats", None)
        return {
            "problem_attribute": attribute,
            "solver_name": getattr(stats, "solver_name", None),
            "num_iters": getattr(stats, "num_iters", None),
            "solve_time": getattr(stats, "solve_time", None),
            "status": getattr(problem, "status", None),
        }
    return {
        "problem_attribute": None,
        "solver_name": None,
        "num_iters": None,
        "solve_time": None,
        "status": None,
    }


def _capture_solver_usage(fit: Any) -> dict[str, Any]:
    """在一次只在内存中的 fit 期间捕获 cvxpy 实际使用的 solver / status（只读 instrumentation）。"""
    import cvxpy

    calls: list[dict[str, Any]] = []
    original = cvxpy.Problem.solve

    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        stats = getattr(self, "solver_stats", None)
        calls.append(
            {
                "solver_name": getattr(stats, "solver_name", None),
                "status": getattr(self, "status", None),
                "num_iters": getattr(stats, "num_iters", None),
                "solve_time": getattr(stats, "solve_time", None),
                "solve_kwargs": {key: str(value) for key, value in kwargs.items()},
            }
        )
        return result

    cvxpy.Problem.solve = wrapper  # type: ignore[method-assign]
    try:
        fit()
    finally:
        cvxpy.Problem.solve = original  # type: ignore[method-assign]
    return {"solve_calls": len(calls), "captured": calls}


def erc_solver_probe(prices: pd.DataFrame) -> dict[str, Any]:
    """对最后一个 RISK 月重复一次只读 ERC 拟合，以指纹化实际求解后端。"""
    try:
        from skfolio import RiskMeasure
        from skfolio.optimization import RiskBudgeting

        from research.experiments.run_s4c_erc_skfolio_transfer import aligned_window
    except ImportError as error:  # pragma: no cover - research extra missing
        return {"available": False, "reason": f"import failed: {error}"}

    risk_symbols = review.load_review_inputs()[4]
    risk = prices.loc[:, list(risk_symbols)]
    month_ends = pd.DatetimeIndex(prices.index).to_period("M")
    ends = list(prices.groupby(month_ends).tail(1).index)
    for date in reversed(ends):
        window = aligned_window(risk, pd.Timestamp(date), review.PRICE_WINDOW)
        if len(window) != review.PRICE_WINDOW:
            continue
        returns = window.pct_change(fill_method=None).dropna(how="any")
        model = RiskBudgeting(risk_measure=RiskMeasure.VARIANCE, min_weights=0.0, max_weights=1.0)

        def fit_probe(probe_model: Any = model, probe_returns: pd.DataFrame = returns) -> None:
            probe_model.fit(probe_returns)

        try:
            captured = _capture_solver_usage(fit_probe)
        except Exception as error:  # noqa: BLE001 - diagnostic must not fail the probe
            return {"available": False, "reason": f"probe fit failed: {error}"}
        report = {"available": True, "probe_signal_date": str(pd.Timestamp(date).date())}
        report.update(captured)
        report.update(_problem_attributes(model))
        return report
    return {"available": False, "reason": "no RISK month available for probing"}


def environment_fingerprint(
    label: str, repository_head: str | None, prices: pd.DataFrame
) -> dict[str, Any]:
    import os

    try:
        import cvxpy

        installed_solvers: list[str] | None = sorted(cvxpy.installed_solvers())
    except ImportError:  # pragma: no cover - cvxpy comes with the research extra
        installed_solvers = None
    return {
        "environment_label": label,
        "repository_head": repository_head,
        "github_actions": os.environ.get("GITHUB_ACTIONS"),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "package_versions": package_versions(),
        "installed_cvxpy_solvers": installed_solvers,
        "blas_lapack": blas_lapack_fingerprint(),
        "erc_solver_probe": erc_solver_probe(prices),
    }


def _support(column: pd.Series) -> tuple[str, ...]:
    return tuple(sorted(column.index[column > 0.0]))


def _support_changes(committed: pd.DataFrame, derived: pd.DataFrame) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for date in committed.index:
        expected = _support(committed.loc[date])
        observed = _support(derived.loc[date])
        if expected != observed:
            changes.append(
                {
                    "execution_date": str(pd.Timestamp(date).date()),
                    "committed_support": list(expected),
                    "derived_support": list(observed),
                }
            )
    return changes


def _maximum_weight_identity_changes(
    committed: pd.DataFrame, derived: pd.DataFrame
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for date in committed.index:
        expected_symbol = str(committed.loc[date].idxmax())
        observed_symbol = str(derived.loc[date].idxmax())
        if expected_symbol != observed_symbol:
            changes.append(
                {
                    "execution_date": str(pd.Timestamp(date).date()),
                    "committed_maximum_weight_symbol": expected_symbol,
                    "derived_maximum_weight_symbol": observed_symbol,
                    "committed_maximum_weight": float(committed.loc[date].max()),
                    "derived_maximum_weight": float(derived.loc[date].max()),
                }
            )
    return changes


def _top_differences(committed: pd.DataFrame, derived: pd.DataFrame) -> list[dict[str, Any]]:
    delta = (derived - committed).abs()
    stacked = delta.stack().sort_values(ascending=False).head(TOP_DIFFERENCES)
    rows = []
    for key, value in stacked.items():
        date, symbol = key
        rows.append(
            {
                "execution_date": str(pd.Timestamp(date).date()),
                "symbol": str(symbol),
                "committed_weight": float(committed.loc[date, symbol]),
                "derived_weight": float(derived.loc[date, symbol]),
                "absolute_delta": float(value),
            }
        )
    return rows


def comparison_report(committed: pd.DataFrame, derived: pd.DataFrame) -> dict[str, Any]:
    index_identical = bool(committed.index.equals(derived.index))
    columns_identical = list(committed.columns) == list(derived.columns)
    report: dict[str, Any] = {
        "committed_rows": int(len(committed)),
        "derived_rows": int(len(derived)),
        "execution_date_index_identical": index_identical,
        "asset_columns_identical": columns_identical,
        "committed_columns": [str(column) for column in committed.columns],
    }
    if not index_identical or not columns_identical:
        report["comparable"] = False
        report["comparison_blocked_by"] = "index or column identity mismatch"
        return report

    support_changes = _support_changes(committed, derived)
    identity_changes = _maximum_weight_identity_changes(committed, derived)
    delta = (derived - committed).abs()
    values = delta.to_numpy(dtype=float)
    flattened = values.reshape(-1)
    per_month_maximum = delta.max(axis=1)
    report.update(
        {
            "comparable": True,
            "elements_compared": int(flattened.size),
            "maximum_absolute_delta": float(flattened.max()),
            "mean_absolute_delta": float(flattened.mean()),
            "absolute_delta_percentiles": {
                f"p{int(percentile * 100):02d}": float(np.quantile(flattened, percentile))
                for percentile in PERCENTILES
            },
            "count_above_threshold": {
                f"{threshold:.0e}": int((flattened > threshold).sum())
                for threshold in DELTA_THRESHOLDS
            },
            "maximum_row_weight_sum_difference": float(
                (derived.sum(axis=1) - committed.sum(axis=1)).abs().max()
            ),
            "per_month_maximum_weight_delta": {
                "median": float(per_month_maximum.median()),
                "maximum": float(per_month_maximum.max()),
            },
            "largest_differing_dates_assets": _top_differences(committed, derived),
            "support_change_count": len(support_changes),
            "support_changes": support_changes[:TOP_DIFFERENCES],
            "maximum_weight_identity_change_count": len(identity_changes),
            "maximum_weight_identity_changes": identity_changes[:TOP_DIFFERENCES],
            "committed_row_weight_sum_bounds": [
                float(committed.sum(axis=1).min()),
                float(committed.sum(axis=1).max()),
            ],
            "derived_row_weight_sum_bounds": [
                float(derived.sum(axis=1).min()),
                float(derived.sum(axis=1).max()),
            ],
            "nonnegative_committed": bool(committed.ge(0).all().all()),
            "nonnegative_derived": bool(derived.ge(0).all().all()),
        }
    )
    return report


def schedule_shape(schedule: pd.DataFrame) -> dict[str, Any]:
    """冻结日程的结构形状：support 宽度、集中度与有效资产数，用于结构一致性比对。"""
    nonzero = (schedule > 0.0).sum(axis=1)
    maximum_weight = schedule.max(axis=1)
    effective = 1.0 / (schedule**2).sum(axis=1)
    return {
        "rows": int(len(schedule)),
        "first_execution_date": str(pd.Timestamp(schedule.index[0]).date()),
        "last_execution_date": str(pd.Timestamp(schedule.index[-1]).date()),
        "single_asset_rows": int(nonzero.eq(1).sum()),
        "multi_asset_rows": int(nonzero.gt(1).sum()),
        "maximum_weight_median": float(maximum_weight.median()),
        "maximum_weight_p95": float(maximum_weight.quantile(0.95)),
        "maximum_weight_maximum": float(maximum_weight.max()),
        "effective_number_assets_minimum": float(effective.min()),
    }


def return_window_provenance(prices: pd.DataFrame) -> dict[str, Any]:
    """对每个 RISK 月的 aligned returns window 做逐值指纹。

    若该指纹跨环境一致，则差异只能来自数值求解器/BLAS，而不是数据对齐、复权或 pandas 语义。
    """
    from hashlib import sha256

    from research.experiments.run_s4c_erc_skfolio_transfer import aligned_window

    risk_symbols = review.load_review_inputs()[4]
    risk = prices.loc[:, list(risk_symbols)]
    month_ends = pd.DatetimeIndex(prices.index).to_period("M")
    ends = list(prices.groupby(month_ends).tail(1).index)
    digest = sha256()
    risk_windows = 0
    fallback_windows = 0
    for date in ends:
        window = aligned_window(risk, pd.Timestamp(date), review.PRICE_WINDOW)
        if len(window) != review.PRICE_WINDOW:
            fallback_windows += 1
            continue
        returns = window.pct_change(fill_method=None).dropna(how="any")
        digest.update(returns.to_csv(float_format="%.17g", lineterminator="\n").encode())
        risk_windows += 1
    return {
        "risk_windows": risk_windows,
        "fallback_windows": fallback_windows,
        "returns_window_sha256": digest.hexdigest(),
        "note": "指纹覆盖逐月 aligned returns window 的全部数值与资产列，用于隔离 solver 与数据路径。",
    }


def economic_materiality(
    committed: pd.DataFrame,
    derived: pd.DataFrame,
    prices: pd.DataFrame,
    mask: pd.DataFrame,
    lifetimes: dict,
    config: Any,
) -> dict[str, Any]:
    """用同一 VectorBT 路径重放两份日程，比较冻结的 V2 指标是否出现经济实质差异。"""
    from research.experiments.frozen_target_replay import replay_vectorbt

    def metrics(schedule: pd.DataFrame) -> dict[str, float]:
        return dict(
            replay_vectorbt(
                prices,
                schedule,
                fees=config.fees,
                slippage=config.slippage,
                initial_cash=config.initial_cash,
                tradability_mask=mask,
                lifetimes=lifetimes,
            ).metrics
        )

    expected = metrics(committed)
    observed = metrics(derived)
    per_metric: dict[str, Any] = {}
    for key in review.REPRODUCED_METRICS:
        baseline = float(expected[key])
        delta = float(observed[key]) - baseline
        tolerance = review.metric_tolerance(baseline)
        per_metric[key] = {
            "committed": baseline,
            "derived": float(observed[key]),
            "absolute_delta": delta,
            "frozen_v2_metric_tolerance": tolerance,
            "within_frozen_v2_metric_tolerance": abs(delta) <= tolerance,
        }
    return {
        "per_metric": per_metric,
        "all_within_frozen_v2_metric_tolerance": all(
            entry["within_frozen_v2_metric_tolerance"] for entry in per_metric.values()
        ),
        "note": (
            "Protocol V2 的指标级容差只作为参照尺度引用；它不构成本次 schedule 级 "
            "portability 分类裁决，也不替代独立分类。"
        ),
    }


def build_report(label: str, repository_head: str | None) -> dict[str, Any]:
    prices, mask, lifetimes, config, risk_symbols = review.load_review_inputs()
    committed = review.load_committed_schedule()
    derived, diagnostics, start = review.build_frozen_schedule(
        prices, risk_symbols, mask, lifetimes, config
    )
    derived_sha256, serialized = review.schedule_sha256(derived)
    committed_text = review.read_normalized_text(review.FROZEN_TARGETS)
    return {
        "diagnostic": "S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_V1",
        "purpose": "measure committed vs re-derived frozen S4C targets across environments",
        "read_only": True,
        "artifacts_modified": [],
        "classification": PENDING,
        "frozen_target_artifact": {
            "path": str(review.FROZEN_TARGETS.relative_to(ROOT)).replace("\\", "/"),
            "committed_sha256": review.FROZEN_TARGET_SHA256,
            "observed_normalized_sha256": sha256(committed_text.encode()).hexdigest(),
            "expected_rows": review.FROZEN_TARGET_ROWS,
            "first_date": str(review.FROZEN_FIRST_DATE.date()),
            "last_date": str(review.FROZEN_LAST_DATE.date()),
        },
        "derivation": {
            "returns_window": review.RETURNS_WINDOW,
            "price_window": review.PRICE_WINDOW,
            "derived_rows": int(len(derived)),
            "derived_first_date": str(pd.Timestamp(start).date()),
            "derived_sha256": derived_sha256,
            "derived_serialized_matches_committed": serialized == committed_text,
            "serialized_line_differences": sum(
                1
                for expected, observed in zip(
                    committed_text.split("\n"), serialized.split("\n"), strict=False
                )
                if expected != observed
            ),
            "risk_regime_months": int(
                (diagnostics["regime"] == "RISK").sum() if diagnostics is not None else 0
            ),
        },
        "environment": environment_fingerprint(label, repository_head, prices),
        "comparison": comparison_report(committed, derived),
        "inputs": return_window_provenance(prices),
        "structure": {
            "committed": schedule_shape(committed),
            "derived": schedule_shape(derived),
        },
        "economic_materiality": economic_materiality(
            committed, derived, prices, mask, lifetimes, config
        ),
    }


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--environment-label", default="local_windows_development")
    parser.add_argument("--repository-head", default=None)
    args = parser.parse_args()

    report = build_report(args.environment_label, args.repository_head)
    serialized = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized + "\n", encoding="utf-8", newline="\n")
    print(serialized)


if __name__ == "__main__":
    main()
