#!/usr/bin/env python3
"""S4C 跨环境可移植性 reproduction 契约 V1 的执行语义（非冻结 helper）。

契约本身预注册在 `research/batches/prospective_evidence_foundation/
PORTABLE_REPRODUCTION_CONTRACT_V1.md`。本模块只实现它，不重新定义它：

```text
artifact identity       精确（SHA / 行数 / 日期 / 列 / 非负 / 逐行和）—— 不属于本模块
structural reproduction 精确（日期集合 / 资产集合 / support / 最大权重身份 / 逐行和）
numerical 比较          SCHEDULE_WEIGHT_ABS_TOL = 1e-4、SCHEDULE_WEIGHT_REL_TOL = 0
```

它存在的原因：Windows 上冻结语义可逐字节重推 committed 日程，clean Linux 上同一求解语义会
产生约 2.8e-5 的浮点漂移。把可重现性表达为序列化字节相等会把契约绑死到单一平台，从而把
可移植性噪声误判为 candidate 完整性失效。本契约取代该用途，但**不**削弱 §3 的产物身份检查，
也不允许结构变化借容差通过。

前瞻语义：真实 decision 一旦封存，该 decision record 内的 `desired_targets` 就是权威证据；
日后的重推只需满足本契约，不再要求逐字节复现。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.experiments.frozen_target_replay import require_structurally_equivalent_schedule

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_RELATIVE_PATH = (
    "research/batches/prospective_evidence_foundation/PORTABLE_REPRODUCTION_CONTRACT_V1.md"
)
CONTRACT_NAME = "S4C_PORTABLE_REPRODUCTION_CONTRACT_V1"
SCHEDULE_WEIGHT_ABS_TOL = 1e-4
SCHEDULE_WEIGHT_REL_TOL = 0.0


def contract_text(root: Path = ROOT) -> str:
    return (Path(root) / CONTRACT_RELATIVE_PATH).read_text(encoding="utf-8")


def weight_tolerance(reference: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """逐元素容差：ABS_TOL + REL_TOL × |reference|。"""
    return SCHEDULE_WEIGHT_ABS_TOL + SCHEDULE_WEIGHT_REL_TOL * reference.abs()


def schedule_weight_deltas(committed: pd.DataFrame, derived: pd.DataFrame) -> pd.DataFrame:
    return (derived - committed).abs()


def maximum_absolute_delta(committed: pd.DataFrame, derived: pd.DataFrame) -> float:
    deltas = schedule_weight_deltas(committed, derived)
    return float(deltas.to_numpy(dtype=float).max()) if deltas.size else 0.0


def exceeding_deltas(committed: pd.DataFrame, derived: pd.DataFrame) -> pd.Series:
    """超出容差的 (date, asset) → |Δw|；未超差的单元格被丢弃，不会引入 NaN。"""
    deltas = schedule_weight_deltas(committed, derived)
    mask = deltas > weight_tolerance(committed)
    return deltas.where(mask).stack().dropna()


def require_portable_reproduction(
    committed: pd.DataFrame,
    derived: pd.DataFrame,
    *,
    label: str = "冻结语义重推导的 S4C 日程",
) -> None:
    """结构精确 + 权重落在预注册容差内；任一结构变化都不适用容差。"""
    require_structurally_equivalent_schedule(committed, derived, label=label)
    exceeding = exceeding_deltas(committed, derived)
    if not exceeding.empty:
        worst = float(exceeding.max())
        raise ValueError(
            f"{label} 超出 {CONTRACT_NAME} 的数值容差: "
            f"max |Δw| = {worst:.6e} > SCHEDULE_WEIGHT_ABS_TOL = {SCHEDULE_WEIGHT_ABS_TOL:g}"
        )


def reproduction_evidence(committed: pd.DataFrame, derived: pd.DataFrame) -> dict[str, object]:
    """只读证据块：供诊断/复核记录使用，不改变任何状态。"""
    return {
        "contract": CONTRACT_NAME,
        "schedule_weight_abs_tol": SCHEDULE_WEIGHT_ABS_TOL,
        "schedule_weight_rel_tol": SCHEDULE_WEIGHT_REL_TOL,
        "elements_compared": int(committed.size),
        "maximum_absolute_delta": maximum_absolute_delta(committed, derived),
        "elements_exceeding_tolerance": int(exceeding_deltas(committed, derived).size),
    }
