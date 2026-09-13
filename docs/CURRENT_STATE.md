# 当前状态

## 当前策略与最新决策

S2 Research Candidate R1 保持 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，仍是唯一活动前瞻候选，且 PIT integrity pass。`BATCH_05_COMPLETE` 已通过独立 Principal Architect 复核：S27A 保留 candidate-freeze review 资格但推迟，S10A 维持 `DO_NOT_ADVANCE_S10A_EXECUTION`，S4C 获得 execution-review 资格并被选为唯一下一 Goal；均非候选、前瞻或生产批准。

## 最新决定性证据

S2 R1 的 [manifest](../research/shadow/s2_r1/candidate_manifest.json) 与冻结输入仍通过严格校验，`observations.csv` 仍无 decision record。Batch 05 的 PIT-corrected frozen-target RQAlpha replay 使 S27A 通过 execution gate 且零 cash rejection；S10A 因一个 native cash rejection 未推进；S4C 在 40/60/80 return-window neighborhood、固定分期、rolling 与 50bps 成本下通过 robustness，P95 maximum weight 51.84% 作为集中度证据保留。独立复核结论见 [Batch 05 principal architect review](../research/results/BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md)。

## 剩余阻塞

S2 仍缺少足够前瞻 observation：中期完整性复核不早于 12 个日历月，production-candidate review 资格至少 18 个日历月且至少 10 次真实 target-change 执行事件。S27A 的下一有界问题是 candidate-freeze review，当前推迟。S10A 停止在 execution review，不能用局部执行修补重开。S4C 的下一有界问题是 authoritative execution review，也是当前唯一下一实验。S3A、S3B、S3C、S4A、S8A 均已关闭，不得以参数微调重开；S4B Riskfolio-Lib block 保持历史事实。

## 下一项唯一实验

`S4C_AUTHORITATIVE_EXECUTION_REVIEW`：在冻结的 60-return center 与既有经济语义下，用 RQAlpha 原生账户、撮合、现金、整手与成本回放 ERC frozen targets，并把集中度作为诊断证据保留而非优化触发。目标、External Evidence Gate、PIT Tradability Gate 与边界见 [goal](goal.md)。

## External Evidence Foundation

`BATCH_00_EXTERNAL_EVIDENCE_FOUNDATION_COMPLETE` 保持有效；Batch 02 的三条有界 gap 已按外部证据、冻结协议和本地证据完成。外部 tier 未因本地结果改变，Theme Rotation 未开始。

当前前沿为 `AWAIT_S4C_EXECUTION_REVIEW`。未来策略选择必须先完成 External Evidence Gate 与 PIT Tradability Gate，并从本地 remaining gap 而非历史收益或叙事开始。
