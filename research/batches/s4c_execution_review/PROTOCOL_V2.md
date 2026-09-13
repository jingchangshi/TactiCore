# S4C authoritative execution review protocol V2 — numerical portability of the reproduction gate

本版本只修正 V1 的 reproduction portability 契约。**S4C 经济语义、冻结目标 artifact、native execution gates 与禁止事项与 V1 完全相同**，不得借 V2 放松任何决策门槛。

## 与 V1 的关系

- V1（`356ed98`）的权威执行运行在预注册 reproduction gate 处停止，作为 [INVALID_RUN R1](../results/INVALID_RUN_S4C_EXECUTION_R1.md) 保留。
- 触发原因：`1e-12` 精确相等判据在记录平台之外不可达成（上游 solver/BLAS 漂移），而非策略语义变化。
- V2 在任何真实 RQAlpha 结果之前冻结；V2 的 protocol commit 必须先于运行。

## 不变项（零容忍）

| 不变项 | 要求 |
| --- | --- |
| committed frozen targets SHA-256 | `f7bf398d7f8a016933cbe287bfa1cac98b3cccf175d40ef99092b95db1227e47` |
| row count | 161 |
| first execution date | 2013-04-01 |
| last execution date | 2026-08-03 |
| 日期 | 唯一且严格递增 |
| 权重 | 非负，每行合计为一 |
| PIT 校验 | `validate_execution_targets` 通过 |
| 策略语义 | 与 V1 相同：skfolio `RiskBudgeting` / `RiskMeasure.VARIANCE` / equal risk budgets / long-only、fully invested、无杠杆 / min eligible 6 / 60 aligned returns（61 prices）/ 511010.SS fallback / 月末估计→下一 canonical observation execution / 10 bps fee + 5 bps slippage |

committed 冻结目标文件是 RQAlpha 的权威输入。RQAlpha 直接回放该文件；回调内不得重算信号、波动、ERC 权重或 fallback。

额外审计（不放松任何条件）：以冻结语义重新推导 target 日程时，其序列化必须与 committed artifact **逐字符相等**（hash 相同）。不相等即停止，不得改写 artifact。

## Reproduction gate（V2）

将 committed 冻结目标的当前 VectorBT replay 与 `s4c_pit_corrected_comparison_v1.csv` 比较，对 CAGR、signed MaxDD、Sharpe、Calmar、turnover 逐项要求：

```text
abs(current - baseline) <= max(1e-4, 1e-4 * abs(baseline))
```

等价实现 `math.isclose(rel_tol=1e-4, abs_tol=1e-4)` 可接受。当前量级下约为性能比率 1e-4 绝对容差、turnover 约 1.18e-3。

该容差比任何经济/执行决策门槛小若干量级，不能把实质不同的策略判为 reproduction PASS。

失败决定：`BLOCK_S4C_EXECUTION_REPRODUCTION`，且不得启动 RQAlpha。

## Native execution gate

与 V1 完全一致，不放松：全部 frozen execution dates 被处理、无额外 replay dates、`cash_rejection_events == 0`、平均 execution-date total absolute weight deviation `<= 3%`、materially off-target execution dates `<= 10% of frozen dates`、平均 cash ratio `<= 2%`、RQAlpha CAGR `> 0` 且 `>= VectorBT CAGR - 2pp`、signed RQAlpha MaxDD `>= VectorBT MaxDD - 5pp`、所有 material difference 必须有具体 native 解释（`UNKNOWN` / `UNEXPLAINED_EXECUTION_DIFFERENCE` 不算通过）。material difference 沿用既有 5pp 口径。

Allowed terminal decisions 不变：

```text
ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW
DO_NOT_ADVANCE_S4C_EXECUTION
BLOCK_S4C_EXECUTION_REPRODUCTION
BLOCK_S4C_EXECUTION_ENVIRONMENT
```

## Artifacts（V2 命名空间）

```text
research/results/s4c_rqalpha_execution_vectorbt_reproduction_v2.csv
research/results/s4c_rqalpha_execution_summary_v2.csv
research/results/s4c_rqalpha_execution_target_tracking_v2.csv
research/results/s4c_rqalpha_execution_material_differences_v2.csv
research/results/s4c_rqalpha_execution_user_effort_v2.csv
research/results/S4C_RQALPHA_EXECUTION_REVIEW_V2.md
```

冻结目标文件保持 `s4c_pit_corrected_frozen_targets_v1.csv`，因为其身份与语义未变。reproduction CSV 必须包含 baseline、observed、delta、tolerance、逐指标 PASS 与整体 reproduction PASS，使 portability 判断可审计。

## 停止条件

- frozen target SHA 变化（停止，不是 V2 调整）。
- S2 完整性校验失败。
- V2 reproduction 超出上述已冻结容差：永久停在 `BLOCK_S4C_EXECUTION_REPRODUCTION`，除非出现新的矛盾证据，不得再次调整容差。
- 需要放松任何 RQAlpha gate、改变 S4C 经济语义，或在 RQAlpha 内重算信号/ERC。
- 任何进一步协议缺陷：停止并报告，不得静默修改或重跑。

## 禁止事项（与 V1 相同）

不添加集中度 cap、不做现金修补、不做手工 sizing、不做 retry、不改参数或窗口、不替换 solver、不修改 S2 或 Batch 05 冻结产物、不创建 candidate 或 prospective shadow、不建设通用 execution framework。
