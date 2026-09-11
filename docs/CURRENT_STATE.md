# 当前状态

## 当前策略与最新决策

S2 Research Candidate R1 保持 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，等待真实未来 evidence；它仍不是生产候选。`BATCH_02_COMPLETE`：S27A 获 execution-review 资格，S10A 获 robustness 资格，S4B 因官方上游依赖阻塞；三者均不构成生产或新的前瞻候选。

## 最新决定性证据

S2 R1 的 [manifest](../research/shadow/s2_r1/candidate_manifest.json) 仍通过完整性验证。S27A 复现 corrected baseline 并通过冻结邻域、分期、滚动和成本测试；S10A 在消除隐式前填充后的 Protocol V2 rerun 中相对月频静态控制改善回撤、Sharpe 和 Calmar；完整结论见 [Batch 02](../research/results/BATCH_02_EVIDENCE_INFORMED_VALIDATION.md)。

## 剩余阻塞

S2 仍缺少足够前瞻 observation；S4B 等待官方当前 Riskfolio-Lib 依赖能在项目 Python 范围可靠解析。S3A、S3B、S3C、S4A、S8A 均已关闭，不得以参数微调重开。

## External Evidence Foundation

`BATCH_00_EXTERNAL_EVIDENCE_FOUNDATION_COMPLETE` 保持有效；Batch 02 的三条有界 gap 已按外部证据、冻结协议和本地证据完成。外部 tier 未因本地结果改变，Theme Rotation 未开始。

当前前沿为 `AWAIT_BATCH_02_ARCHITECT_REVIEW`。未来策略选择必须先完成 External Evidence Gate，并从本地 remaining gap 而非历史收益或叙事开始。
