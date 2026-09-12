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
