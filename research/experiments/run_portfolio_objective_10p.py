#!/usr/bin/env python3
"""10% portfolio-objective feasibility on frozen S2_R1 / S4C_R1 fixed blends.

本模块只做历史诊断：把**已经冻结**的 S2_R1 与 S4C_R1 目标按预注册的粗粒度固定权重合成一个
**派生组合目标**，再交给 VectorBT 原生组合模拟。它不生成候选、不优化权重、不加杠杆、
不修改任何冻结组件身份。

语义边界（必须与结果一起陈述）：

* 组件目标状态 `T_i(t)` 是组件 i 在 t 或之前最后一次冻结提交的意图目标；这里保持的是冻结的
  **目标决定**，不是价格。
* 派生组合目标 `T_blend(t) = w_S2 * T_S2(t) + w_S4C * T_S4C(t)`。
* 在提交日并集上提交 `T_blend` 会形成一个新的**组合层提交政策**
  （`DERIVED_UNION_TARGET_SUBMISSION`）：S4C 的月度提交会把 S2 的贡献重新拉回其当前目标，
  即使 S2_R1 自身因 `SIGNAL_CHANGE_ONLY` 不会提交。因此：
  - 不得把内部 blend 说成"两个候选在同一个账户中原样运行"；
  - 不得声称 blend 保持了 S2 单独运行时的执行政策行为；
  - 组件自身的 anchor 必须单独回放，作为各自候选的正确性参照；
  - 派生的 100/0 端点**不等于** standalone S2_R1，也不得命名为 S2_R1。
"""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from research.experiments.frozen_target_replay import schedule_execution
from research.experiments.run_s1_evidence_closure import (
    annual_returns,
    period_metrics,
    realized_turnover,
    rolling_table,
)
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import (
    AssetLifetime,
    load_tradability_inputs,
    validate_execution_targets,
)
from tacticore.engines.vectorbt_adapter import ResearchResult, run_target_weights
from tacticore.strategies.multi_asset_trend import load_trend_config
from tacticore.strategies.static_strategic_allocation import (
    build_execution_weights as build_static_execution_weights,
)
from tacticore.strategies.static_strategic_allocation import (
    load_static_allocation_config,
)

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "research/results"
S2_FROZEN_TARGETS = RESULTS / "s2_v2_frozen_targets.csv"
S4C_FROZEN_TARGETS = RESULTS / "s4c_pit_corrected_frozen_targets_v1.csv"
S2_FROZEN_SHA256 = "9cc5a8e70751f274cb7c4f900784400bd8de684450833ba6d4034fd75ca70b61"
S4C_FROZEN_SHA256 = "f7bf398d7f8a016933cbe287bfa1cac98b3cccf175d40ef99092b95db1227e47"
S4C_COMPARISON_PATH = RESULTS / "s4c_pit_corrected_comparison_v1.csv"
S2_PLATEAU_PATH = RESULTS / "s2_parameter_plateau_summary.csv"

# 预注册的评估窗口：主窗口是两个冻结组件的共同可评价区间；S30 窗口是对齐 S30 natural
# inception（513500.SS 上市）后，全部序列在同一区间上的公平比较窗口。
PRIMARY_START = pd.Timestamp("2013-04-01")
EVALUATION_END = pd.Timestamp("2026-08-31")
S2_REPRODUCTION_START = pd.Timestamp("2013-03-29")

# 预注册的粗粒度机制配置；禁止增加任何其他权重组合。
BLEND_WEIGHTS: tuple[tuple[float, float], ...] = (
    (1.00, 0.00),
    (0.75, 0.25),
    (0.50, 0.50),
    (0.25, 0.75),
    (0.00, 1.00),
)
BLEND_SERIES_NAMES = tuple(
    f"BLEND_S2_{int(s2_share * 100):02d}_S4C_{int(s4c_share * 100):02d}"
    for s2_share, s4c_share in BLEND_WEIGHTS
)
INTERIOR_BLEND_WEIGHTS = tuple(
    (s2_share, s4c_share)
    for s2_share, s4c_share in BLEND_WEIGHTS
    if s2_share > 0.0 and s4c_share > 0.0
)
INTERIOR_BLEND_SERIES_NAMES = tuple(
    f"BLEND_S2_{int(s2_share * 100):02d}_S4C_{int(s4c_share * 100):02d}"
    for s2_share, s4c_share in INTERIOR_BLEND_WEIGHTS
)
ANCHOR_SERIES_NAMES = ("S2_R1_committed_anchor", "S4C_R1_committed_anchor")
S30_SERIES_NAME = "S30_REFERENCE"

# 主窗口只包含两个真实候选 anchor 与五个派生 blend；S30 只出现在单独标注的共同窗口比较中，
# 并且永远不是第三个策略组件。派生端点不参与可行性裁决。
PRIMARY_SERIES_NAMES = ANCHOR_SERIES_NAMES + BLEND_SERIES_NAMES
COMMON_WINDOW_SERIES_NAMES = PRIMARY_SERIES_NAMES + (S30_SERIES_NAME,)

# 预注册的目标判定阈值；它们只用于把历史诊断分类，不是收益预测或参数搜索。
TARGET_CAGR = 0.10
NEAR_TARGET_CAGR = 0.095
COMPLEXITY_CAGR_MARGIN = 0.005
COMPLEXITY_DRAWDOWN_MARGIN = 0.02

# 已提交冻结日程以 8 位小数保存；S2 的 1/9 sleeve 因此合计为 0.99999999。
# 该容差只吸收已记录的 CSV 定点舍入，不改变任何冻结数值，也不授权重新归一化。
ROW_SUM_TOLERANCE = 1e-7

# S4C 指标复现沿用早于本 Goal 的既有 portability 规则（见
# research/batches/s4c_execution_review/PROTOCOL_V2.md），等价于
# math.isclose(rel_tol=1e-4, abs_tol=1e-4)。S2 不使用任何性能容差：其 correctness 是身份式的。
S4C_PORTABILITY_REL_TOLERANCE = 1e-4
S4C_PORTABILITY_ABS_TOLERANCE = 1e-4
CORRECTNESS_COLUMNS = (
    "series",
    "check",
    "gate",
    "metric",
    "observed",
    "reference",
    "absolute_difference",
    "tolerance",
    "passed",
)
# 冻结 S30 规则的共同窗口起点：由 513500.SS 上市日决定，运行时断言。
S30_COMMON_WINDOW_START = pd.Timestamp("2014-01-15")

PERIODS = (
    ("2013-2016", "2013-04-01", "2016-12-31"),
    ("2017-2019", "2017-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-2026", "2023-01-01", "2026-08-31"),
)

SUMMARY_COLUMNS = (
    "series",
    "series_kind",
    "submission_policy",
    "s2_share",
    "s4c_share",
    "evaluation_start",
    "evaluation_end",
    "cagr",
    "max_drawdown",
    "sharpe",
    "calmar",
    "worst_year",
    "turnover",
    "trade_count",
    "average_holding_days",
    "submission_count",
    "annualized_submission_count",
    "actual_order_days",
    "annualized_action_days",
)
PERIOD_COLUMNS = ("series", "period", "start", "end", "cagr", "max_drawdown", "sharpe", "calmar")
ROLLING_COLUMNS = (
    "series",
    "years",
    "window_count",
    "cagr_min",
    "cagr_median",
    "sharpe_median",
    "positive_cagr_share",
)
ANNUAL_COLUMNS = ("series", "year", "return")
DECISION_TOKENS = (
    "FEASIBLE_WITH_EXISTING_COMPONENTS",
    "FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT",
    "PLAUSIBLE_BUT_PROSPECTIVE_EVIDENCE_INSUFFICIENT",
    "NOT_SUPPORTED_BY_EXISTING_COMPONENTS",
    "BLOCKED_BY_CORRECTNESS",
)

# 派生组合有自己的提交政策；它既不等于 S2_R1 的 SIGNAL_CHANGE_ONLY，也不等于 S4C_R1 的
# 单独回放，因此必须单独命名。
DERIVED_UNION_TARGET_SUBMISSION = "DERIVED_UNION_TARGET_SUBMISSION"
DIVERSIFICATION_COLUMNS = (
    "series",
    "s2_share",
    "s4c_share",
    "cagr",
    "weighted_anchor_cagr",
    "cagr_beyond_weighted_anchor",
    "max_drawdown",
    "best_anchor_max_drawdown",
    "max_drawdown_improves_anchor",
    "sharpe",
    "best_anchor_sharpe",
    "sharpe_improves_anchor",
)


def sha256_frozen_repository_text(path: Path) -> str:
    """Hash frozen repository text consistently across LF and CRLF checkouts."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_frozen_schedule(path: Path, expected_sha256: str, columns: pd.Index) -> pd.DataFrame:
    """读取并逐字节校验一份冻结目标日程，再对齐到 canonical 资产列。"""
    actual = sha256_frozen_repository_text(path)
    if actual != expected_sha256:
        raise ValueError(f"冻结目标 SHA-256 与已记录身份不一致: {path.name} -> {actual}")
    schedule = pd.read_csv(path, index_col="execution_date", parse_dates=["execution_date"])
    schedule.index.name = "execution_date"
    if schedule.index.has_duplicates or not schedule.index.is_monotonic_increasing:
        raise ValueError(f"冻结目标日期必须唯一且递增: {path.name}")
    if not schedule.ge(0).all().all():
        raise ValueError(f"冻结目标不得为负: {path.name}")
    if not schedule.sum(axis=1).sub(1.0).abs().le(ROW_SUM_TOLERANCE).all():
        raise ValueError(f"冻结目标每行必须合计为一: {path.name}")
    if set(schedule.columns).difference(columns):
        raise ValueError(f"冻结目标含 canonical 之外的资产: {path.name}")
    return schedule.reindex(columns=columns).fillna(0.0).astype(float)


def blend_target_schedule(
    s2: pd.DataFrame,
    s4c: pd.DataFrame,
    s2_share: float,
    s4c_share: float,
) -> pd.DataFrame:
    """在冻结组件提交日的并集上，把两个冻结目标按固定权重合成为组合目标。

    组件在提交日之间的"当前意图目标"就是它最近一次冻结提交的权重（组件自身的固定
    target contract），不是任何前向填充的价格。合成不引入新资产、不重设组件语义。
    """
    if (s2_share, s4c_share) not in BLEND_WEIGHTS:
        raise ValueError(f"未预注册的 blend 权重: {s2_share}/{s4c_share}")
    if s2.columns.tolist() != s4c.columns.tolist():
        raise ValueError("两个冻结组件的资产列必须一致")
    index = s2.index.union(s4c.index).sort_values()
    index.name = "execution_date"
    left = s2.reindex(index).ffill().fillna(0.0)
    right = s4c.reindex(index).ffill().fillna(0.0)
    blend = (s2_share * left + s4c_share * right).astype(float)
    if not blend.ge(-1e-12).all().all():
        raise ValueError("合成目标不得为负（无杠杆）")
    if not blend.sum(axis=1).sub(1.0).abs().le(ROW_SUM_TOLERANCE).all():
        raise ValueError("合成目标每行必须合计为一（无杠杆、不留现金）")
    return blend


def replay_schedule(
    prices: pd.DataFrame,
    schedule: pd.DataFrame,
    *,
    metric_start: pd.Timestamp,
    fees: float,
    slippage: float,
    initial_cash: float,
    tradability_mask: pd.DataFrame,
    lifetimes: dict[str, AssetLifetime],
) -> ResearchResult:
    """把冻结/合成目标交给 VectorBT；PIT 校验由 run_target_weights 强制执行。"""
    return run_target_weights(
        prices,
        schedule_execution(prices, schedule),
        fees=fees,
        slippage=slippage,
        initial_cash=initial_cash,
        metric_start=metric_start,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )


def _action_days(result: ResearchResult, start: pd.Timestamp, end: pd.Timestamp) -> int:
    orders = result.portfolio.orders.records_readable
    mask = (orders["Timestamp"] >= start) & (orders["Timestamp"] <= end)
    return int(orders.loc[mask, "Timestamp"].nunique())


def summary_row(
    series: str,
    kind: str,
    policy: str,
    result: ResearchResult,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    s2_share: float | None = None,
    s4c_share: float | None = None,
) -> dict[str, Any]:
    end = min(end, result.equity.index[-1])
    observations = result.equity.loc[start:end]
    metrics = period_metrics(result.equity, result.execution_weights, start, end)
    elapsed_years = (observations.index[-1] - observations.index[0]).days / 365.25
    submissions = result.execution_weights.loc[start:end].dropna(how="all")
    action_days = _action_days(result, start, end)
    return {
        "series": series,
        "series_kind": kind,
        "submission_policy": policy,
        "s2_share": s2_share,
        "s4c_share": s4c_share,
        "evaluation_start": observations.index[0].date().isoformat(),
        "evaluation_end": observations.index[-1].date().isoformat(),
        "cagr": metrics["cagr"],
        "max_drawdown": metrics["max_drawdown"],
        "sharpe": metrics["sharpe"],
        "calmar": metrics["calmar"],
        "worst_year": float(annual_returns(observations).min()),
        "turnover": realized_turnover(result.portfolio, start, end),
        "trade_count": int(result.metrics["trade_count"]),
        "average_holding_days": float(result.metrics["average_holding_days"]),
        "submission_count": int(len(submissions)),
        "annualized_submission_count": float(len(submissions) / elapsed_years),
        "actual_order_days": action_days,
        "annualized_action_days": float(action_days / elapsed_years),
    }


def period_rows(series: str, result: ResearchResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for period, begin, end in PERIODS:
        observations = result.equity.loc[begin:end]
        metrics = period_metrics(
            result.equity, result.execution_weights, observations.index[0], observations.index[-1]
        )
        rows.append(
            {
                "series": series,
                "period": period,
                "start": observations.index[0].date().isoformat(),
                "end": observations.index[-1].date().isoformat(),
                **{name: metrics[name] for name in ("cagr", "max_drawdown", "sharpe", "calmar")},
            }
        )
    return rows


def rolling_rows(series: str, result: ResearchResult) -> list[dict[str, Any]]:
    table = rolling_table(result).rename(columns={"window_years": "years"})
    rows: list[dict[str, Any]] = []
    for years in (3, 5):
        window = table.loc[table["years"].eq(years)]
        rows.append(
            {
                "series": series,
                "years": years,
                "window_count": int(len(window)),
                "cagr_min": float(window["cagr"].min()),
                "cagr_median": float(window["cagr"].median()),
                "sharpe_median": float(window["sharpe"].median()),
                "positive_cagr_share": float(window["cagr"].gt(0).mean()),
            }
        )
    return rows


def annual_rows(
    series_equity: list[tuple[str, pd.Series, pd.Timestamp]],
) -> pd.DataFrame:
    """按每个序列自己的注册起点报告年度收益；不制造 inception 之前的年份。"""
    return pd.DataFrame(
        [
            {"series": name, "year": int(year), "return": float(value)}
            for name, equity, start in series_equity
            for year, value in annual_returns(equity.loc[start:]).items()
        ]
    ).reindex(columns=ANNUAL_COLUMNS)


def assert_s30_inception(actual: pd.Timestamp) -> None:
    """冻结 S30 共同窗口起点；不一致必须失败，而不是静默使用未登记日期。"""
    if pd.Timestamp(actual) != S30_COMMON_WINDOW_START:
        raise ValueError(
            "S30 共同窗口 inception 与预注册值不一致: "
            f"{pd.Timestamp(actual).date()} != {S30_COMMON_WINDOW_START.date()}"
        )


def s4c_portability_tolerance(baseline: float) -> float:
    """既有 S4C Protocol V2 的数值 portability 规则（早于本 Goal，不属于结果驱动调整）。"""
    return max(S4C_PORTABILITY_ABS_TOLERANCE, S4C_PORTABILITY_REL_TOLERANCE * abs(baseline))


def correctness_passed(frame: pd.DataFrame) -> bool:
    """只有 identity 与预注册 portability 行参与判定；描述性行不参与。"""
    gating = frame.loc[frame["gate"].ne("descriptive_only")]
    return bool(gating["passed"].all())


def correlation_row(
    s2_result: ResearchResult,
    s4c_result: ResearchResult,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    """两个冻结机制的日收益相关性与下行相关性；只做描述，不建通用风险平台。"""
    left = s2_result.equity.loc[start:end].pct_change()
    right = s4c_result.equity.loc[start:end].pct_change()
    joined = pd.concat({"s2": left, "s4c": right}, axis=1).dropna()
    downside = joined.loc[(joined["s2"] < 0) | (joined["s4c"] < 0)]
    return {
        "evaluation_start": joined.index[0].date().isoformat(),
        "evaluation_end": joined.index[-1].date().isoformat(),
        "observation_count": int(len(joined)),
        "daily_return_correlation": float(joined["s2"].corr(joined["s4c"])),
        "downside_return_correlation": float(downside["s2"].corr(downside["s4c"])),
    }


def objective_feasibility_decision(summary: pd.DataFrame, *, corrected: bool) -> str:
    """按预注册阈值给出唯一裁决；历史 CAGR 不构成前瞻或生产结论。

    裁决只依据**三个内部固定 blend**与**两个真实候选 anchor**。派生端点（100/0、0/100）是
    组合层派生日程，既不是 standalone 候选，也不参与分类。
    """
    if not corrected:
        return "BLOCKED_BY_CORRECTNESS"
    interior = summary.loc[summary["series"].isin(INTERIOR_BLEND_SERIES_NAMES)]
    anchors = summary.loc[summary["series"].isin(ANCHOR_SERIES_NAMES)]
    if len(interior) != len(INTERIOR_BLEND_WEIGHTS):
        raise ValueError("内部 blend 结果必须且只能包含预注册的内部固定权重")
    if len(anchors) != len(ANCHOR_SERIES_NAMES):
        raise ValueError("必须同时提供两个 standalone 候选 anchor")
    best_interior = float(interior["cagr"].max())
    best_anchor = float(anchors["cagr"].max())
    if best_interior >= TARGET_CAGR:
        return "FEASIBLE_WITH_EXISTING_COMPONENTS"
    if best_anchor >= TARGET_CAGR:
        return "FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT"
    if max(best_interior, best_anchor) >= NEAR_TARGET_CAGR:
        return "PLAUSIBLE_BUT_PROSPECTIVE_EVIDENCE_INSUFFICIENT"
    return "NOT_SUPPORTED_BY_EXISTING_COMPONENTS"


def complexity_verdict(blends: pd.DataFrame, s30: pd.Series) -> str:
    """S30 是复杂度门槛；只用内部固定 blend 回答动态复杂度是否带来可记录的增量。"""
    if not set(blends["series"]).issubset(set(INTERIOR_BLEND_SERIES_NAMES)):
        raise ValueError("复杂度比较只能使用内部固定 blend，不使用派生端点")
    best = blends.sort_values("cagr", ascending=False).iloc[0]
    cagr_margin = float(best["cagr"]) - float(s30["cagr"])
    drawdown_margin = float(best["max_drawdown"]) - float(s30["max_drawdown"])
    if cagr_margin >= COMPLEXITY_CAGR_MARGIN or drawdown_margin >= COMPLEXITY_DRAWDOWN_MARGIN:
        return "COMPLEXITY_CLEARS_S30_HURDLE"
    return "COMPLEXITY_NOT_JUSTIFIED_BY_THIS_EVIDENCE"


def diversification_rows(summary: pd.DataFrame) -> list[dict[str, Any]]:
    """把"客观接近目标"与"机制分散证据"分开报告，而不是只挑历史 CAGR 最高者。"""
    anchors = summary.loc[summary["series_kind"].eq("component_anchor")].set_index("series")
    s2 = anchors.loc["S2_R1_committed_anchor"]
    s4c = anchors.loc["S4C_R1_committed_anchor"]
    best_anchor_max_drawdown = max(float(s2["max_drawdown"]), float(s4c["max_drawdown"]))
    best_anchor_sharpe = max(float(s2["sharpe"]), float(s4c["sharpe"]))
    rows: list[dict[str, Any]] = []
    for _, blend in summary.loc[summary["series_kind"].eq("blend")].iterrows():
        weighted = float(blend["s2_share"]) * float(s2["cagr"]) + float(blend["s4c_share"]) * float(
            s4c["cagr"]
        )
        rows.append(
            {
                "series": blend["series"],
                "s2_share": float(blend["s2_share"]),
                "s4c_share": float(blend["s4c_share"]),
                "cagr": float(blend["cagr"]),
                "weighted_anchor_cagr": weighted,
                "cagr_beyond_weighted_anchor": float(blend["cagr"]) - weighted,
                "max_drawdown": float(blend["max_drawdown"]),
                "best_anchor_max_drawdown": best_anchor_max_drawdown,
                "max_drawdown_improves_anchor": float(blend["max_drawdown"])
                > best_anchor_max_drawdown,
                "sharpe": float(blend["sharpe"]),
                "best_anchor_sharpe": best_anchor_sharpe,
                "sharpe_improves_anchor": float(blend["sharpe"]) > best_anchor_sharpe,
            }
        )
    return rows


def _identity_checks(
    prices: pd.DataFrame,
    series: str,
    schedule: pd.DataFrame,
    expected_sha256: str,
    path: Path,
    result: ResearchResult,
    mask: pd.DataFrame,
    lifetimes: dict[str, AssetLifetime],
    expected_rows: int,
) -> list[dict[str, Any]]:
    """冻结身份与回放输入的 identity 检查；不使用任何性能容差。"""
    replayed_input = result.execution_weights.dropna(how="all")
    pit_error = None
    try:
        validate_execution_targets(replayed_input, prices, mask, lifetimes)
    except ValueError as error:  # pragma: no cover - 只在实际违规时触发
        pit_error = str(error)
    rows = [
        {
            "series": series,
            "check": "frozen_schedule_sha256",
            "gate": "identity",
            "metric": "",
            "observed": float(int(sha256_frozen_repository_text(path) == expected_sha256)),
            "reference": float(1),
            "absolute_difference": float("nan"),
            "tolerance": float("nan"),
            "passed": bool(sha256_frozen_repository_text(path) == expected_sha256),
        },
        {
            "series": series,
            "check": "execution_row_count",
            "gate": "identity",
            "metric": "",
            "observed": float(len(schedule)),
            "reference": float(expected_rows),
            "absolute_difference": float(abs(len(schedule) - expected_rows)),
            "tolerance": float("nan"),
            "passed": bool(len(schedule) == expected_rows),
        },
        {
            "series": series,
            "check": "ordered_unique_execution_dates",
            "gate": "identity",
            "metric": "",
            "observed": float("nan"),
            "reference": float("nan"),
            "absolute_difference": float("nan"),
            "tolerance": float("nan"),
            "passed": bool(
                schedule.index.is_monotonic_increasing and not schedule.index.has_duplicates
            ),
        },
        {
            "series": series,
            "check": "row_sum_serialization_tolerance",
            "gate": "identity",
            "metric": "",
            "observed": float(schedule.sum(axis=1).sub(1.0).abs().max()),
            "reference": 0.0,
            "absolute_difference": float(schedule.sum(axis=1).sub(1.0).abs().max()),
            "tolerance": float(ROW_SUM_TOLERANCE),
            "passed": bool(schedule.sum(axis=1).sub(1.0).abs().le(ROW_SUM_TOLERANCE).all()),
        },
        {
            "series": series,
            "check": "pit_legal_execution_targets",
            "gate": "identity",
            "metric": "",
            "observed": float("nan"),
            "reference": float("nan"),
            "absolute_difference": float("nan"),
            "tolerance": float("nan"),
            "passed": pit_error is None,
        },
        {
            "series": series,
            "check": "replay_input_equals_frozen_schedule",
            "gate": "identity",
            "metric": "",
            "observed": float("nan"),
            "reference": float("nan"),
            "absolute_difference": float(replayed_input.sub(schedule).abs().max().max()),
            "tolerance": 0.0,
            "passed": bool(replayed_input.equals(schedule)),
        },
    ]
    return rows


def component_correctness(
    prices: pd.DataFrame,
    s2_schedule: pd.DataFrame,
    s4c_schedule: pd.DataFrame,
    s2_result: ResearchResult,
    s4c_result: ResearchResult,
    mask: pd.DataFrame,
    lifetimes: dict[str, AssetLifetime],
) -> tuple[bool, pd.DataFrame]:
    """组件 anchor 的 correctness 证据：S2 为身份式，S4C 复用既有 portability 规则。"""
    rows = _identity_checks(
        prices,
        ANCHOR_SERIES_NAMES[0],
        s2_schedule,
        S2_FROZEN_SHA256,
        S2_FROZEN_TARGETS,
        s2_result,
        mask,
        lifetimes,
        103,
    ) + _identity_checks(
        prices,
        ANCHOR_SERIES_NAMES[1],
        s4c_schedule,
        S4C_FROZEN_SHA256,
        S4C_FROZEN_TARGETS,
        s4c_result,
        mask,
        lifetimes,
        161,
    )
    committed_s4c = pd.read_csv(S4C_COMPARISON_PATH).iloc[0]
    for metric in ("cagr", "max_drawdown", "sharpe", "calmar", "turnover"):
        observed = float(s4c_result.metrics[metric])
        baseline = float(committed_s4c[metric])
        difference = abs(observed - baseline)
        tolerance = max(
            S4C_PORTABILITY_ABS_TOLERANCE,
            S4C_PORTABILITY_REL_TOLERANCE * abs(baseline),
        )
        rows.append(
            {
                "series": ANCHOR_SERIES_NAMES[1],
                "check": "committed_metric_portability",
                "gate": "preregistered_portability",
                "metric": metric,
                "observed": observed,
                "reference": baseline,
                "absolute_difference": difference,
                "tolerance": tolerance,
                "passed": bool(difference <= tolerance),
            }
        )
    committed_s2 = pd.read_csv(S2_PLATEAU_PATH)
    committed_s2 = committed_s2.loc[committed_s2["trend_window"].eq(200)].iloc[0]
    s2_metrics = period_metrics(
        s2_result.equity,
        s2_result.execution_weights,
        S2_REPRODUCTION_START,
        EVALUATION_END,
    )
    descriptive = {
        **{key: float(s2_metrics[key]) for key in ("cagr", "max_drawdown", "sharpe", "calmar")},
        "turnover": realized_turnover(s2_result.portfolio, S2_REPRODUCTION_START, EVALUATION_END),
    }
    for metric, observed in descriptive.items():
        baseline = float(committed_s2[metric])
        rows.append(
            {
                "series": ANCHOR_SERIES_NAMES[0],
                "check": "committed_metric_descriptive",
                "gate": "descriptive_only",
                "metric": metric,
                "observed": observed,
                "reference": baseline,
                "absolute_difference": abs(observed - baseline),
                "tolerance": float("nan"),
                "passed": True,
            }
        )
    frame = pd.DataFrame(rows).reindex(columns=CORRECTNESS_COLUMNS)
    return correctness_passed(frame), frame


def main() -> None:
    strategy = load_trend_config(ROOT / "config/strategy.toml")
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    columns = prices.columns
    mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))
    s2_schedule = load_frozen_schedule(S2_FROZEN_TARGETS, S2_FROZEN_SHA256, columns)
    s4c_schedule = load_frozen_schedule(S4C_FROZEN_TARGETS, S4C_FROZEN_SHA256, columns)
    replay_kwargs: dict[str, Any] = dict(
        fees=strategy.fees,
        slippage=strategy.slippage,
        initial_cash=strategy.initial_cash,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )

    s2_anchor = replay_schedule(
        prices, s2_schedule, metric_start=S2_REPRODUCTION_START, **replay_kwargs
    )
    s4c_anchor = replay_schedule(prices, s4c_schedule, metric_start=PRIMARY_START, **replay_kwargs)
    corrected, correctness = component_correctness(
        prices, s2_schedule, s4c_schedule, s2_anchor, s4c_anchor, mask, lifetimes
    )

    blend_schedules = {
        f"BLEND_S2_{int(s2_share * 100):02d}_S4C_{int(s4c_share * 100):02d}": (
            blend_target_schedule(s2_schedule, s4c_schedule, s2_share, s4c_share),
            s2_share,
            s4c_share,
        )
        for s2_share, s4c_share in BLEND_WEIGHTS
    }
    blend_results = {
        name: replay_schedule(prices, schedule, metric_start=PRIMARY_START, **replay_kwargs)
        for name, (schedule, _, _) in blend_schedules.items()
    }

    static_config = load_static_allocation_config(ROOT / "config/s30_static_allocation.toml")
    static_execution = build_static_execution_weights(prices, static_config)
    s30_start = static_execution.dropna(how="all").index[0]
    assert_s30_inception(s30_start)
    s30_result = run_target_weights(
        prices,
        static_execution,
        fees=static_config.fees,
        slippage=static_config.slippage,
        initial_cash=static_config.initial_cash,
        metric_start=s30_start,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )

    # 主窗口只含两个候选 anchor 与五个派生 blend；S30 只进入共同窗口比较。
    specs: list[tuple[str, str, str, ResearchResult, float | None, float | None, pd.Timestamp]] = [
        (
            ANCHOR_SERIES_NAMES[0],
            "component_anchor",
            "SIGNAL_CHANGE_ONLY (committed R1, 103 rows)",
            s2_anchor,
            None,
            None,
            PRIMARY_START,
        ),
        (
            ANCHOR_SERIES_NAMES[1],
            "component_anchor",
            "MONTHLY_TARGET_SUBMISSION (committed R1, 161 rows)",
            s4c_anchor,
            None,
            None,
            PRIMARY_START,
        ),
    ]
    for name, (_, s2_share, s4c_share) in blend_schedules.items():
        specs.append(
            (
                name,
                "blend",
                DERIVED_UNION_TARGET_SUBMISSION,
                blend_results[name],
                s2_share,
                s4c_share,
                PRIMARY_START,
            )
        )
    primary_specs = list(specs)
    common_window_specs = specs + [
        (
            S30_SERIES_NAME,
            "reference_baseline",
            "ANNUAL_TARGET_SUBMISSION (S30 reference)",
            s30_result,
            None,
            None,
            s30_start,
        )
    ]
    if tuple(spec[0] for spec in primary_specs) != PRIMARY_SERIES_NAMES:
        raise ValueError("主窗口序列必须与预注册列表一致（不含 S30）")
    if tuple(spec[0] for spec in common_window_specs) != COMMON_WINDOW_SERIES_NAMES:
        raise ValueError("共同窗口序列必须与预注册列表一致（含 S30）")

    summary = pd.DataFrame(
        [
            summary_row(
                name,
                kind,
                policy,
                result,
                start,
                EVALUATION_END,
                s2_share=s2_share,
                s4c_share=s4c_share,
            )
            for name, kind, policy, result, s2_share, s4c_share, start in primary_specs
        ]
    ).reindex(columns=SUMMARY_COLUMNS)
    common_summary = pd.DataFrame(
        [
            summary_row(
                name,
                kind,
                policy,
                result,
                max(start, s30_start),
                EVALUATION_END,
                s2_share=s2_share,
                s4c_share=s4c_share,
            )
            for name, kind, policy, result, s2_share, s4c_share, start in common_window_specs
        ]
    ).reindex(columns=SUMMARY_COLUMNS)

    rolling_series = [(spec[0], spec[3]) for spec in primary_specs]
    period_frame = pd.DataFrame(
        [row for name, result in rolling_series for row in period_rows(name, result)]
    ).reindex(columns=PERIOD_COLUMNS)
    rolling_frame = pd.DataFrame(
        [row for name, result in rolling_series for row in rolling_rows(name, result)]
    ).reindex(columns=ROLLING_COLUMNS)
    correlation = pd.DataFrame(
        [correlation_row(s2_anchor, s4c_anchor, PRIMARY_START, EVALUATION_END)]
    )
    diversification = pd.DataFrame(diversification_rows(summary)).reindex(
        columns=DIVERSIFICATION_COLUMNS
    )
    annual = annual_rows(
        [(name, result.equity, start) for name, _, _, result, _, _, start in common_window_specs]
    )

    decision = objective_feasibility_decision(summary, corrected=corrected)
    if decision not in DECISION_TOKENS:
        raise ValueError("裁决必须属于预注册的五个 token")
    interior_summary = summary.loc[summary["series"].isin(INTERIOR_BLEND_SERIES_NAMES)]
    common_interior = common_summary.loc[common_summary["series"].isin(INTERIOR_BLEND_SERIES_NAMES)]
    s30_row = common_summary.loc[common_summary["series"].eq(S30_SERIES_NAME)].iloc[0]
    complexity = complexity_verdict(common_interior, s30_row)

    for filename, frame in (
        ("portfolio_objective_10p_summary_v1.csv", summary),
        ("portfolio_objective_10p_common_window_v1.csv", common_summary),
        ("portfolio_objective_10p_diversification_v1.csv", diversification),
        ("portfolio_objective_10p_correctness_v1.csv", correctness),
        ("portfolio_objective_10p_periods_v1.csv", period_frame),
        ("portfolio_objective_10p_rolling_v1.csv", rolling_frame),
        ("portfolio_objective_10p_correlation_v1.csv", correlation),
        ("portfolio_objective_10p_annual_returns_v1.csv", annual),
    ):
        frame.to_csv(RESULTS / filename, index=False, float_format="%.8f", lineterminator="\n")

    print(summary.to_string(index=False))
    print(f"\ncomponent_correctness_ok={corrected}")
    print(f"interior_best_cagr={float(interior_summary['cagr'].max()):.6f}")
    print(f"decision={decision}")
    print(f"complexity={complexity}")


if __name__ == "__main__":
    main()
