# INVALID_RUN — S4C execution review R1

Protocol V1（commit `356ed98`）的 S4C 权威执行审查在预注册 reproduction gate 处停止。RQAlpha 未启动，未产生 native 执行结果，未创建 candidate 或 shadow。

## 触发原因

VectorBT replay committed 冻结目标后，与已接受的 60-return PIT-corrected 基线（`s4c_pit_corrected_comparison_v1.csv`）比较，未落入 V1 冻结的 `1e-12` machine tolerance：

| 指标 | delta (current - baseline) |
| --- | --- |
| CAGR | `-1.9342885204665095e-07` |
| signed MaxDD | `-4.000413379168233e-07` |
| Sharpe | `-1.8268639836449552e-06` |
| Calmar | `-2.4364449349167927e-06` |
| turnover | `+1.128...e-04` |

机械决定：`BLOCK_S4C_EXECUTION_REPRODUCTION`。

## 诊断

这不是实现缺陷，也不是 S4C 经济语义变化：

1. 使用 Batch 04 自身的评估路径（`run_batch_04_pit_revalidations.executable` / `evaluate`）在**同一台当前机器**上重算，得到的五项指标与 frozen-target helper **完全一致**（path agreement `0.0`），说明 replay 路径等价。
2. 残差来自上游 skfolio/scipy/BLAS 求解：逐月 ERC `maximum_weight` 相对已接受的 Batch 03/04 diagnostics，median `1.46e-06`、max `4.11e-05`，出现在 149 个 RISK 月中的 146 个；regime、eligible 集合、signal 日期、执行日期与 target count（161）完全不变。
3. 隔离探针：Python 3.10（scipy 1.15.3）与 Python 3.11（scipy 1.17.1）在 numpy 1.26.4 下给出**逐位相同**的 delta；Python 3.12（numpy 2.5.3、scipy 1.18.1）给出不同但同量级的 delta。因此已接受基线与记录机器的数值栈绑定，`1e-12` 跨平台 reproduction 无法达成。

结论：缺陷是 V1 的 reproduction 判据本身（不可跨平台的精确相等），而不是策略语义。V2 只修正该 portability 契约，并**不**放松任何 native execution gate。

## 证据

- 失败运行产物：[invalid V1 reproduction](s4c_rqalpha_execution_vectorbt_reproduction_invalid_r1.csv)
- V1 协议：[PROTOCOL.md](../batches/s4c_execution_review/PROTOCOL.md)（保留为历史版本，不修改）
- V2 协议：[PROTOCOL_V2.md](../batches/s4c_execution_review/PROTOCOL_V2.md)
- 冻结目标日程：[s4c_pit_corrected_frozen_targets_v1.csv](s4c_pit_corrected_frozen_targets_v1.csv)，SHA-256 `f7bf398d7f8a016933cbe287bfa1cac98b3cccf175d40ef99092b95db1227e47`（161 行，2013-04-01 至 2026-08-03，未改动）
