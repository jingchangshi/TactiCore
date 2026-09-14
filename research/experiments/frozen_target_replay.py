"""Batch-local frozen target validation and VectorBT replay plumbing."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib

import pandas as pd

from tacticore.data.tradability import (
    AssetLifetime,
    first_executable_complete_target,
    validate_execution_targets,
)
from tacticore.engines.vectorbt_adapter import ResearchResult, run_target_weights


def freeze_pit_legal_schedule(
    prices: pd.DataFrame,
    execution: pd.DataFrame,
    tradability_mask: pd.DataFrame,
    lifetimes: dict[str, AssetLifetime],
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Trim pre-inception rows and freeze a legal, normalized target schedule."""
    start = first_executable_complete_target(execution, tradability_mask)
    schedule = execution.loc[execution.index >= start].dropna(how="all").copy()
    schedule.index.name = "execution_date"
    if schedule.index.has_duplicates or not schedule.index.is_monotonic_increasing:
        raise ValueError("冻结目标日期必须唯一且严格递增")
    if (schedule < 0).any().any() or not schedule.sum(axis=1).round(12).eq(1.0).all():
        raise ValueError("冻结目标必须非负且逐行合计为一")
    validate_execution_targets(schedule, prices, tradability_mask, lifetimes)
    return schedule, start


def schedule_sha256(schedule: pd.DataFrame) -> tuple[str, str]:
    serialized = schedule.reset_index().to_csv(
        index=False, float_format="%.17g", lineterminator="\n"
    )
    return hashlib.sha256(serialized.encode()).hexdigest(), serialized


def require_structurally_equivalent_schedule(
    committed: pd.DataFrame,
    derived: pd.DataFrame,
    *,
    label: str = "重新推导的冻结目标日程",
) -> None:
    """结构不变量：把「真的换了目标」与「同一求解语义的数值噪声」分开。

    这些不变量与数值容差无关，因此任何 future portability contract 都不得绕过它们：
    execution 日期集合、资产集合、逐行 support（哪些标的是正权重）、每行最大权重标的身份，
    以及逐行权重和都必须与 committed 日程完全一致。任一不一致都说明经济语义已经改变。
    """
    if list(committed.columns) != list(derived.columns):
        raise ValueError(f"{label} 的资产集合或列顺序与 committed 日程不一致")
    if committed.index.has_duplicates or not committed.index.is_monotonic_increasing:
        raise ValueError("committed 冻结目标日程的日期必须唯一且严格递增")
    if derived.index.has_duplicates or not derived.index.is_monotonic_increasing:
        raise ValueError(f"{label} 的日期必须唯一且严格递增")
    if not committed.index.equals(derived.index):
        raise ValueError(f"{label} 的 execution 日期集合与 committed 日程不一致")
    if (derived < 0).any().any():
        raise ValueError(f"{label} 不得包含负权重")
    if not derived.sum(axis=1).round(12).eq(1.0).all():
        raise ValueError(f"{label} 的逐行权重和必须为一")
    for date in committed.index:
        expected_support = tuple(sorted(committed.loc[date].index[committed.loc[date] > 0.0]))
        observed_support = tuple(sorted(derived.loc[date].index[derived.loc[date] > 0.0]))
        if expected_support != observed_support:
            raise ValueError(
                f"{label} 在 {pd.Timestamp(date).date().isoformat()} 改变了 support："
                f"{expected_support} → {observed_support}"
            )
        expected_maximum = str(committed.loc[date].idxmax())
        observed_maximum = str(derived.loc[date].idxmax())
        if expected_maximum != observed_maximum:
            raise ValueError(
                f"{label} 在 {pd.Timestamp(date).date().isoformat()} 改变了最大权重标的："
                f"{expected_maximum} → {observed_maximum}"
            )


def schedule_execution(prices: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    execution.loc[schedule.index, schedule.columns] = schedule
    return execution


def replay_vectorbt(
    prices: pd.DataFrame,
    schedule: pd.DataFrame,
    *,
    fees: float,
    slippage: float,
    initial_cash: float,
    tradability_mask: pd.DataFrame,
    lifetimes: dict[str, AssetLifetime],
) -> ResearchResult:
    return run_target_weights(
        prices,
        schedule_execution(prices, schedule),
        fees=fees,
        slippage=slippage,
        initial_cash=initial_cash,
        metric_start=schedule.index[0],
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )
