# 当前状态

## 当前策略与最新决策

S2 Research Candidate R1 保持 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，且 PIT integrity pass。S4C Research Candidate R1 经独立 [activation decision V1](../research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md) 完成前瞻影子激活裁决（`ACTIVATION_IMPLEMENTATION_GATE = PASS` 之后），现为 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，由候选级 lifecycle artifact [activation.json](../research/shadow/s4c_r1/activation.json) 记录；`candidate_manifest.json` 的 `prospective_activation = NOT_ACTIVE` 作为历史冻结身份保持不变。两个候选均**不是**生产候选，prospective observations 均为 0。S27A 保留 candidate-freeze review 资格但继续推迟；S10A 维持 `DO_NOT_ADVANCE_S10A_EXECUTION`。没有任何候选获得生产资格。

组合层新增一次只读历史诊断：[portfolio 10% objective 可行性 V1](../research/results/PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md)，裁决 `OBJECTIVE_FEASIBILITY_DECISION = FEASIBLE_WITH_EXISTING_COMPONENTS`。它只用两个已冻结组件的粗粒度固定目标级混合，不修改任何候选、不创建组合候选、不构成生产批准。

对两个活动候选的前瞻证据路径已完成一次跨候选结构审计（RL-046，见 [双候选前瞻审计 V1](../research/results/DUAL_CANDIDATE_PROSPECTIVE_AUDIT_V1.md)），并据此作出研究优先级决策 V3（RL-047，见 [研究优先级决策 V3](../research/results/RESEARCH_PRIORITY_DECISION_V3.md)），选定 `PROSPECTIVE_EVIDENCE_FOUNDATION_V1_FOR_S2_AND_S4C`。该审计只读、未实现任何修复、未下载任何数据。

该 Foundation V1 的历史链完整保留：RL-048 曾宣布
`PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS`
（[原始结果](../research/results/PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md)）→ clean Linux CI 在
`74613246aab3d93cf381239f3ab499a58f96b555` 上给出 `pytest = 6 failed / 436 passed`、
workflow `conclusion = failure`，该 READY 被显式撤销并登记为
[errata / revocation](../research/results/PROSPECTIVE_EVIDENCE_FOUNDATION_V1_ERRATA.md)（RL-049）
→ 有界更正闭包（`3183387..c70e74e`）→ **独立 revalidation**
（[Foundation V1 revalidation V1](../research/results/PROSPECTIVE_EVIDENCE_FOUNDATION_V1_REVALIDATION_V1.md)）。

当前真实状态：

`PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE = PASS`、
`PROSPECTIVE_FOUNDATION_DECISION = PROSPECTIVE_FOUNDATION_READY`。
恢复 READY 的依据是可执行证据：S4C 跨环境差异被独立分类为 `NUMERICALLY_EQUIVALENT` 并由预注册的
`S4C_PORTABLE_REPRODUCTION_CONTRACT_V1`（artifact identity 精确、结构精确、schedule 权重
`ABS_TOL = 1e-4`）承接；production execution artifact 不再接受调用方时间/位置权威；集成
dual-candidate production-path drill 通过；clean Linux CI run `34873004632`（head `c70e74e`）
`conclusion = SUCCESS`、`pytest = 462 passed`、无跳过步骤。
Foundation READY 只表示前瞻证据机制可信，**不**表示任一候选已具备生产资格。

## 最新决定性证据

S2 R1 的 [manifest](../research/shadow/s2_r1/candidate_manifest.json) 与冻结输入仍通过严格校验，`observations.csv` 仍无 decision record。S4C 的 committed 161 个冻结 ERC 目标在 Protocol V2 下完成 RQAlpha 6.3.0 原生回放：CAGR 12.0929%、signed MaxDD -18.3512%、Sharpe 0.7758、cash rejection 0、平均 execution-date deviation 0.3246%、material dates 3/161（两个 >5pp 单资产差异都有具体 native 原因；第三个是最大单资产偏差 3.84pp、现金残差 3.80% 的组合层偏离）、平均现金 0.1399%。P95 maximum weight 51.84% 仍是未消除的集中度特征。完整结论见 [S4C execution review V2](../research/results/S4C_RQALPHA_EXECUTION_REVIEW_V2.md) 与 [Batch 05 principal architect review](../research/results/BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md)。

组合层最新证据：主窗口 2013-04-01 至 2026-08-31 上，`S2_R1` anchor CAGR 6.5713% / signed MaxDD -26.1813%，`S4C_R1` anchor CAGR 11.6375% / signed MaxDD -18.3512%；派生固定混合 25/75 的 after-cost CAGR 为 10.4849%，50/50 为 9.2696% 且 signed MaxDD -15.9165% 优于任一 anchor。共同窗口 2014-01-15 起 S30 为 9.9249%、50/50 为 10.8404%、25/75 为 11.8127%，复杂度门槛判定为 `COMPLEXITY_CLEARS_S30_HURDLE`。两个冻结机制日收益相关性 0.7835、下行相关性 0.6541。派生序列使用 `DERIVED_UNION_TARGET_SUBMISSION`，不保持 S2 单独执行政策，也不等于 standalone `S2_R1`。

## 剩余阻塞

S2 仍缺少足够前瞻 observation：中期完整性复核不早于 12 个日历月，production-candidate review 资格至少 18 个日历月且至少 10 次真实 target-change 执行事件。S4C R1 前瞻影子已激活但 prospective observations 仍为 0；其执行证据仍是历史证据，不是前瞻样本外证据；集中度是已登记的已知候选风险（P95 最大权重 51.84%、历史最大 66.35%），既未被消除也不得通过 cap 修补。S27A 的同类资格继续推迟。S10A 停止在 execution review，不能用局部执行修补重开。S3A、S3B、S3C、S4A、S8A 均已关闭，不得以参数微调重开；S4B Riskfolio-Lib block 保持历史事实。

组合层的主导阻塞是 `PROSPECTIVE_EVIDENCE_GAP`：历史 return gap 已经很小，但组合层前瞻观测为零；派生组合也没有独立的 RQAlpha 执行审查。这**不是**缺少 alpha 策略的证据。

## 下一项唯一实验

没有可立即执行的实验：Foundation 更正闭包已完成并通过独立 revalidation，当前 frontier 是
`AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE`。真实前瞻 cycle 只在真实
`2026-09-30` 收盘后（即该 as-of 数据已合法可得）启动；该 as-of 的 candidate-specific vintage
是该 cycle 的第一阶段，尚不存在。流程保持
`freeze vintage → verify → derive decision → seal → append DECISION → commit/push → STOP`，
每个候选只有一次写操作（candidate CLI 在一次调用中完成 derive + seal + append），
不得再手工重复 append；execution 证据在下一 canonical 观测日由独立 Goal 追加。无论何时启动，
都不得以集中度、历史收益或时间压力为由改参数、加 cap、重跑窗口、回填
`2026-09-01..candidate freeze` 已可观察的数据，或用历史结果制造前瞻证据。

在真实前瞻信号出现前，禁止新策略开发、portfolio candidate、S27A、Theme Rotation 或任何
"再研究一次"的替代工作。系统现在需要的是前瞻时间。

## External Evidence Foundation

`BATCH_00_EXTERNAL_EVIDENCE_FOUNDATION_COMPLETE` 保持有效；Batch 02 的三条有界 gap 已按外部证据、冻结协议和本地证据完成。外部 tier 未因本地结果改变，Theme Rotation 未开始。

当前唯一前沿为 `AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE`：10% portfolio
objective 的可行性历史诊断已完成并记录（`FEASIBLE_WITH_EXISTING_COMPONENTS`），S4C R1 前瞻影子已按
`ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW` 激活；其后的双候选前瞻审计（RL-046）、研究优先级决策 V3
（RL-047）与 Foundation V1 实现闭环（RL-048）已完成，但 RL-048 的 readiness 已被 RL-049 撤销
（clean Linux CI 失败），随后由更正闭包与 RL-050 的 revalidation 恢复为
`PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE = PASS`、
`PROSPECTIVE_FOUNDATION_DECISION = PROSPECTIVE_FOUNDATION_READY`。
S4C R1 与 S2 R1 现均为
`FROZEN / PROSPECTIVE_SHADOW_ACTIVE` 且 `observation_count = 0`，
`first_eligible_prospective_signal` 为 `2026-09-30`；S27A 资格保留但继续推迟；D 类本地缺口需先
通过 External Evidence Gate 与 PIT Tradability Gate。Foundation 已 ready，因此当前 frontier
是「等待真实前瞻时间」，且**不得**在 2026-09-30 之前启动任何前瞻 decision cycle。开发在此冻结，
直到真实前瞻 evidence 出现或发现具体 correctness blocker。未来选择仍必须从本地 remaining gap
而非历史收益或叙事开始。
