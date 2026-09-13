# 当前状态

## 当前策略与最新决策

S2 Research Candidate R1 保持 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，仍是唯一**活动**前瞻候选，且 PIT integrity pass。S4C 经独立 [research priority decision](../research/results/RESEARCH_PRIORITY_DECISION_V1.md)（A/B/C/D 比较后选定 A）完成 [candidate-freeze review](../research/results/S4C_CANDIDATE_FREEZE_REVIEW_V1.md)，裁决 `FREEZE_S4C_RESEARCH_CANDIDATE_R1`：S4C R1 为**已冻结研究候选**，但前瞻影子**未激活**（`prospective_activation = NOT_ACTIVE`），也不是生产候选。S27A 保留 candidate-freeze review 资格但继续推迟；S10A 维持 `DO_NOT_ADVANCE_S10A_EXECUTION`。没有任何候选获得生产资格。

## 最新决定性证据

S2 R1 的 [manifest](../research/shadow/s2_r1/candidate_manifest.json) 与冻结输入仍通过严格校验，`observations.csv` 仍无 decision record。S4C 的 committed 161 个冻结 ERC 目标在 Protocol V2 下完成 RQAlpha 6.3.0 原生回放：CAGR 12.0929%、signed MaxDD -18.3512%、Sharpe 0.7758、cash rejection 0、平均 execution-date deviation 0.3246%、material dates 3/161（两个 >5pp 单资产差异都有具体 native 原因；第三个是最大单资产偏差 3.84pp、现金残差 3.80% 的组合层偏离）、平均现金 0.1399%。P95 maximum weight 51.84% 仍是未消除的集中度特征。完整结论见 [S4C execution review V2](../research/results/S4C_RQALPHA_EXECUTION_REVIEW_V2.md) 与 [Batch 05 principal architect review](../research/results/BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md)。

## 剩余阻塞

S2 仍缺少足够前瞻 observation：中期完整性复核不早于 12 个日历月，production-candidate review 资格至少 18 个日历月且至少 10 次真实 target-change 执行事件。S4C R1 已冻结并预注册前瞻协议，但其执行证据仍只是历史证据，不是前瞻样本外证据；集中度是已登记的已知候选风险（P95 最大权重 51.84%、历史最大 66.35%），既未被消除也不得通过 cap 修补。S4C R1 前瞻影子尚未激活。S27A 的同类资格继续推迟。S10A 停止在 execution review，不能用局部执行修补重开。S3A、S3B、S3C、S4A、S8A 均已关闭，不得以参数微调重开；S4B Riskfolio-Lib block 保持历史事实。

## 下一项唯一实验

当前没有已授权的下一项实验。S4C R1 的下一有界问题是**独立的前瞻影子激活决策**（prospective-shadow protocol / activation）；本 Goal 只冻结身份并预注册协议，不自动启动该阶段。无论何时启动，都不得以集中度或历史收益为由改参数、加 cap、重跑窗口或用历史结果制造前瞻证据。

## External Evidence Foundation

`BATCH_00_EXTERNAL_EVIDENCE_FOUNDATION_COMPLETE` 保持有效；Batch 02 的三条有界 gap 已按外部证据、冻结协议和本地证据完成。外部 tier 未因本地结果改变，Theme Rotation 未开始。

当前前沿为 `AWAIT_NEXT_ARCHITECT_RESEARCH_DECISION`：研究优先级决策已选定并关闭 S4C candidate-freeze review，S4C R1 已冻结但前瞻未激活。下一个可能的 Goal 是独立的前瞻影子激活决策，或由下一次 research-priority 决策另行授权；S27A 资格保留但继续推迟；D 类本地缺口需先通过 External Evidence Gate 与 PIT Tradability Gate。未来策略选择仍必须从本地 remaining gap 而非历史收益或叙事开始。
