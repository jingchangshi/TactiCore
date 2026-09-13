# 当前状态

## 当前策略与最新决策

S2 Research Candidate R1 保持 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，仍是唯一活动前瞻候选，且 PIT integrity pass。S4C 权威执行审查已完成并通过全部预注册 gate，`ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW`；S27A 保留同一资格但推迟；S10A 维持 `DO_NOT_ADVANCE_S10A_EXECUTION`。三者均非候选、前瞻或生产批准。

## 最新决定性证据

S2 R1 的 [manifest](../research/shadow/s2_r1/candidate_manifest.json) 与冻结输入仍通过严格校验，`observations.csv` 仍无 decision record。S4C 的 committed 161 个冻结 ERC 目标在 Protocol V2 下完成 RQAlpha 6.3.0 原生回放：CAGR 12.0929%、signed MaxDD -18.3512%、Sharpe 0.7758、cash rejection 0、平均 execution-date deviation 0.3246%、material dates 3/161（两个 >5pp 单资产差异都有具体 native 原因；第三个是最大单资产偏差 3.84pp、现金残差 3.80% 的组合层偏离）、平均现金 0.1399%。P95 maximum weight 51.84% 仍是未消除的集中度特征。完整结论见 [S4C execution review V2](../research/results/S4C_RQALPHA_EXECUTION_REVIEW_V2.md) 与 [Batch 05 principal architect review](../research/results/BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md)。

## 剩余阻塞

S2 仍缺少足够前瞻 observation：中期完整性复核不早于 12 个日历月，production-candidate review 资格至少 18 个日历月且至少 10 次真实 target-change 执行事件。S4C 已获得 candidate-freeze review 资格，但其执行证据仍只是历史证据，不是前瞻样本外证据，集中度风险未被消除。S27A 的同类资格继续推迟。S10A 停止在 execution review，不能用局部执行修补重开。S3A、S3B、S3C、S4A、S8A 均已关闭，不得以参数微调重开；S4B Riskfolio-Lib block 保持历史事实。

## 下一项唯一实验

当前没有已授权的下一项实验。S4C 的下一有界问题是独立的 candidate-freeze review，但它只是**资格**：本里程碑不自动选择或启动该阶段，须由下一次独立的 research-priority 决策授权。无论何时开始，都不得以集中度或历史收益为由改参数、加 cap 或重跑窗口。

## External Evidence Foundation

`BATCH_00_EXTERNAL_EVIDENCE_FOUNDATION_COMPLETE` 保持有效；Batch 02 的三条有界 gap 已按外部证据、冻结协议和本地证据完成。外部 tier 未因本地结果改变，Theme Rotation 未开始。

当前前沿为 `AWAIT_NEXT_ARCHITECT_RESEARCH_DECISION`：Batch 05 之后的唯一授权 Goal（S4C authoritative execution review）已完成并记录，里程碑结束，不再自动开启下一阶段。未来策略选择必须先完成 External Evidence Gate 与 PIT Tradability Gate，并从本地 remaining gap 而非历史收益或叙事开始。
