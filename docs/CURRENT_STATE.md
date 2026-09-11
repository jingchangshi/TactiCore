# 当前状态

## 当前策略与最新决策

S2 Research Candidate R1 保持 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，等待真实未来 evidence；它仍不是生产候选。`BATCH_03_COMPLETE`：S27A 因 RQAlpha bundle 环境阻塞，S10A 被稳健性 gate 拒绝，S4C 获 ERC robustness-review 资格；三者均不构成生产或新的前瞻候选。

## 最新决定性证据

S2 R1 的 [manifest](../research/shadow/s2_r1/candidate_manifest.json) 仍通过完整性验证。S27A 的 171 个冻结月频目标精确复现 Batch 02 VectorBT baseline，但 RQAlpha 在首个日期缺少 511010.XSHG；S10A V4 在冻结固定分期 MaxDD 数值条件仅 1/4；S4C skfolio ERC 在 87.13% 风险覆盖下通过绝对与同 eligible inverse-vol 相对门槛。完整结论见 [Batch 03](../research/results/BATCH_03_EARNED_STAGE_ADVANCEMENT.md)。

## 剩余阻塞

S2 仍缺少足够前瞻 observation；S27A 需要覆盖冻结 schedule 的 RQAlpha bundle 或新数据契约；S4C 只获下一轮 robustness 资格。S10A、S3A、S3B、S3C、S4A、S8A 均已关闭，不得以参数微调重开；S4B Riskfolio-Lib block 保持历史事实。

## External Evidence Foundation

`BATCH_00_EXTERNAL_EVIDENCE_FOUNDATION_COMPLETE` 保持有效；Batch 02 的三条有界 gap 已按外部证据、冻结协议和本地证据完成。外部 tier 未因本地结果改变，Theme Rotation 未开始。

当前前沿为 `AWAIT_BATCH_03_ARCHITECT_REVIEW`。未来策略选择必须先完成 External Evidence Gate，并从本地 remaining gap 而非历史收益或叙事开始。
