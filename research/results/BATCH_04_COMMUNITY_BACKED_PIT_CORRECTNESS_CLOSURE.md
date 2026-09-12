# Batch 04 Community-Backed PIT Correctness Closure

| Strategy | Prior state | PIT issue | Metric issue | Corrected decision |
| --- | --- | --- | --- | --- |
| S2 R1 | shadow candidate | 0 violations | none | `S2_R1_PIT_INTEGRITY_PASS` |
| S27A | execution blocked | 10 pre-listing fallback targets | none | `RESTORE_S27A_EXECUTION_REVIEW_ELIGIBILITY` |
| S10A | robustness rejected | 10 pre-listing fallback targets | signed MaxDD reversed | `RESTORE_S10A_EXECUTION_REVIEW_ELIGIBILITY` |
| S4C | robustness eligible | 10 pre-listing fallback targets | none | `RESTORE_S4C_ROBUSTNESS_ELIGIBILITY` |
| S30 | reference | 0 violations | none | `REFERENCE_BASELINE` |

RQAlpha lifecycle API、Zipline lifetime mask、LEAN IsTradable boundary 与 Qlib PIT scope 已审计；只新增生命周期 snapshot、tradability mask、目标验证与 signed metric helper。VectorBT 过去确实收到 inactive fallback 正目标；S27 的问题是 PIT contract，不是 bundle 环境。S2 R1 仍完整。S4A 同样记录十个历史 pre-listing fallback violation，但其已拒绝问题不在本批重开；S3 family、S8A 按其独立 universe/执行起点为 `UNAFFECTED`。

没有建设 PIT platform、替代 RQAlpha、引入 Qlib/Zipline/LEAN、调整参数或成本、替换 fallback、删除负证据、启动新策略/Theme/S4C robustness 或自动创建 candidate。Batch 在 `AWAIT_BATCH_04_ARCHITECT_REVIEW` 停止。
