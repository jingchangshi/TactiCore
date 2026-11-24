# 当前状态

## 当前策略与最新决策

S2 Research Candidate R1 保持 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，且 PIT integrity pass。S4C Research Candidate R1 经独立 [activation decision V1](../research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md) 完成前瞻影子激活裁决（`ACTIVATION_IMPLEMENTATION_GATE = PASS` 之后），现为 **`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`**，由候选级 lifecycle artifact [activation.json](../research/shadow/s4c_r1/activation.json) 记录；`candidate_manifest.json` 的 `prospective_activation = NOT_ACTIVE` 作为历史冻结身份保持不变。两个候选均**不是**生产候选；本地仓库中的两份 `observations.csv` 均只有表头，远程状态未在此核实。S27A 保留 candidate-freeze review 资格但继续推迟；S10A 维持 `DO_NOT_ADVANCE_S10A_EXECUTION`。没有任何候选获得生产资格。

组合层新增一次只读历史诊断：[portfolio 10% objective 可行性 V1](../research/results/PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md)，裁决 `OBJECTIVE_FEASIBILITY_DECISION = FEASIBLE_WITH_EXISTING_COMPONENTS`。它只用两个已冻结组件的粗粒度固定目标级混合，不修改任何候选、不创建组合候选、不构成生产批准。

对两个活动候选的前瞻证据路径已完成一次跨候选结构审计（RL-046，见 [双候选前瞻审计 V1](../research/results/DUAL_CANDIDATE_PROSPECTIVE_AUDIT_V1.md)），并据此作出研究优先级决策 V3（RL-047，见 [研究优先级决策 V3](../research/results/RESEARCH_PRIORITY_DECISION_V3.md)），选定 `PROSPECTIVE_EVIDENCE_FOUNDATION_V1_FOR_S2_AND_S4C`。该审计只读、未实现任何修复、未下载任何数据。

账户迁移研究 `ACCOUNT_INVESTABLE_ALLOCATION_TRANSFER_V1` 已完成历史配对裁决：A2 趋势倾斜对 A0 的主风险门槛未通过（最大回撤与 CVaR 均略差），结论 `REJECT`，见 [结果](../research/results/ACCOUNT_TRANSFER_V1.md) 与 RL-053。只否定该冻结映射在 2020-10–2026-08、约 6.9 万元账户、真实整手和费用约束下的历史表现；不是前瞻证据，不改变 S2/S4C 状态，也不构成生产批准。

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
READY 判定的本地判据已在 governance closeout（`ab8916b`）后的独立会话中于本地 Windows 完整复现
（[本地 revalidation 审计 V1](../research/results/FOUNDATION_V1_LOCAL_WINDOWS_REVALIDATION_V1.md)，
RL-051）：8/8 验证链命令 exit 0、pytest `462 passed / 0 skipped`、S4C portability 诊断
`within_contract = true`（max |Δw| 1.11e-16，求解器输入指纹与 committed Linux 基线逐位一致）、
冻结 identity 13/13 一致、两个候选 observations 仍为 0；未发现新 correctness blocker，
开发冻结不变。
恢复 READY 的依据是可执行证据：S4C 跨环境差异被独立分类为 `NUMERICALLY_EQUIVALENT` 并由预注册的
`S4C_PORTABLE_REPRODUCTION_CONTRACT_V1`（artifact identity 精确、结构精确、schedule 权重
`ABS_TOL = 1e-4`）承接；production execution artifact 不再接受调用方时间/位置权威；集成
dual-candidate production-path drill 通过；clean Linux CI run `34873004632`（head `c70e74e`）
`conclusion = SUCCESS`、`pytest = 462 passed`、无跳过步骤。
Foundation READY 只表示前瞻证据机制可信，**不**表示任一候选已具备生产资格。

## 最新决定性证据

S2 R1 的 [manifest](../research/shadow/s2_r1/candidate_manifest.json) 与冻结输入在既有复核中通过严格校验；本地 `observations.csv` 只有表头。S4C 的 committed 161 个冻结 ERC 目标在 Protocol V2 下完成 RQAlpha 6.3.0 原生回放：CAGR 12.0929%、signed MaxDD -18.3512%、Sharpe 0.7758、cash rejection 0、平均 execution-date deviation 0.3246%、material dates 3/161（两个 >5pp 单资产差异都有具体 native 原因；第三个是最大单资产偏差 3.84pp、现金残差 3.80% 的组合层偏离）、平均现金 0.1399%。P95 maximum weight 51.84% 仍是未消除的集中度特征。完整结论见 [S4C execution review V2](../research/results/S4C_RQALPHA_EXECUTION_REVIEW_V2.md) 与 [Batch 05 principal architect review](../research/results/BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md)。

组合层最新证据：主窗口 2013-04-01 至 2026-08-31 上，`S2_R1` anchor CAGR 6.5713% / signed MaxDD -26.1813%，`S4C_R1` anchor CAGR 11.6375% / signed MaxDD -18.3512%；派生固定混合 25/75 的 after-cost CAGR 为 10.4849%，50/50 为 9.2696% 且 signed MaxDD -15.9165% 优于任一 anchor。共同窗口 2014-01-15 起 S30 为 9.9249%、50/50 为 10.8404%、25/75 为 11.8127%，复杂度门槛判定为 `COMPLEXITY_CLEARS_S30_HURDLE`。两个冻结机制日收益相关性 0.7835、下行相关性 0.6541。派生序列使用 `DERIVED_UNION_TARGET_SUBMISSION`，不保持 S2 单独执行政策，也不等于 standalone `S2_R1`。

## 剩余阻塞

S2 仍缺少足够前瞻 observation：中期完整性复核不早于 12 个日历月，production-candidate review 资格至少 18 个日历月且至少 10 次真实 target-change 执行事件。S4C R1 前瞻影子已激活，本地 observation 表只有表头；其执行证据仍是历史证据，不是前瞻样本外证据；集中度是已登记的已知候选风险（P95 最大权重 51.84%、历史最大 66.35%），既未被消除也不得通过 cap 修补。S27A 的同类资格继续推迟。S10A 停止在 execution review，不能用局部执行修补重开。S3A、S3B、S3C、S4A、S8A 均已关闭，不得以参数微调重开；S4B Riskfolio-Lib block 保持历史事实。

组合层的主导阻塞是 `PROSPECTIVE_EVIDENCE_GAP`：历史 return gap 已经很小，但组合层前瞻观测为零；派生组合也没有独立的 RQAlpha 执行审查。这**不是**缺少 alpha 策略的证据。

## 当前前沿与授权

[RL-052](RESEARCH_LEDGER.md#rl-052-所有者授权仓库外月度编排器与有界迁移研究-goal) 记录：
`2026-09-30` 与 `2026-10-30` 月末决策窗口已错过，**永久不回填**；`2026-09-30` 仍是原先冻结的
first eligible signal，并非现在应执行的周期。前瞻时钟从首个真实 DECISION 起算。

所有者授权仓库外月度编排器按合格月末交易日调用冻结 CLI，决策提交同时推送；失败即停，
不重试写入、不补造历史决策。流程保持 `freeze vintage → verify → derive decision → seal →
append DECISION → commit/push → STOP`，每个候选只由 CLI 一次完成 derive、seal 与 append；
execution 证据由下一 canonical 观测日的独立 Goal 处理。该编排器说明已随仓库清理移除，
`AShareInvestor/docs/v3-offensive-system/SERVER_EXECUTION_WORK_ORDER.md` §IV 明确退役对应定时器；
RL-052 的安装/dry-run 记录是**历史授权**，不代表当前存在远程调度器或已安装定时器。当前只保留
冻结 CLI 的人工/受控运行入口，不得据此新建调度或推断执行状态。

RL-052 同时授权有界的 `ACCOUNT_INVESTABLE_ALLOCATION_TRANSFER_V1` 研究，协议须先于结果提交，
范围与文件边界以该条为准；这不授权修改冻结候选或创建组合候选。其他新策略、S27A、Theme Rotation
及以历史收益或集中度为由改参、加 cap、重跑窗口仍不在授权范围内。

## External Evidence Foundation

`BATCH_00_EXTERNAL_EVIDENCE_FOUNDATION_COMPLETE` 保持有效；Batch 02 的三条有界 gap 已按外部证据、冻结协议和本地证据完成。外部 tier 未因本地结果改变，Theme Rotation 未开始。

10% portfolio objective 的可行性历史诊断已完成并记录（`FEASIBLE_WITH_EXISTING_COMPONENTS`），
S4C R1 前瞻影子已按 `ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW` 激活；其后的双候选前瞻审计（RL-046）、
研究优先级决策 V3（RL-047）与 Foundation V1 实现闭环（RL-048）已完成，但 RL-048 的 readiness
已被 RL-049 撤销（clean Linux CI 失败），随后由更正闭包与 RL-050 的 revalidation 恢复为
`PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE = PASS`、
`PROSPECTIVE_FOUNDATION_DECISION = PROSPECTIVE_FOUNDATION_READY`。
S4C R1 与 S2 R1 均为 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`；本地 observation 表只有表头。
原先的 `2026-09-30` first eligible signal 与后续 `2026-10-30` 窗口均已错过，按 RL-052 不得回填；
月度前瞻流程和有界迁移研究的当前授权见上节。S27A 资格保留但继续推迟；其他本地缺口须先通过
External Evidence Gate 与 PIT Tradability Gate。

## 账户专属进取型低频攻防域（V3 Offensive System Phase 2，2026-11-15）

- 所属范围与边界：`EXP-V3-01..03` 服务用户本人东财 10 万级（现净值约 6.9 万）低频攻防账户（见 [RL-054](RESEARCH_LEDGER.md#rl-054-v3_offensive_system_phase2双锚超级-etf-轮动主板右侧强势股波段与重仓四批换马实证裁决)），与长期多资产 ETF 前瞻候选 `S2_R1` / `S4C_R1` 及 `RL-053` 完全隔离；`S2_R1` 与 `S4C_R1` 继续保持冻结非生产前瞻状态。
- 验证状态：三大验证实验已基于完整 PIT 快照 `v3_snapshot_20261113` 与原生 `RQAlpha 6.3.0` 全部完结：
  - `EXP-V3-01`（`PASS_WITH_IS_WHIPSAW_DISCLOSURE`）：`85%/60%/15%` + `511010.SH` 国债蓄水池 + 万 0.5 免五超级 ETF 在 VBT 全期 CAGR `4.79%`（MaxDD `-13.79%`，OOS CAGR `12.57%` / MaxDD `-12.38%` / 牛市捕获 `122.4%`），RQAlpha `842` 笔 `0` 拒单（MaxDD `-13.13%`），已如实披露 2020-02 IS `crash_override` V 反弹滞回（Bull1 `39.2%`）。
  - `EXP-V3-02`（分买点裁决）：PIT `QualityCore` 加持下仅 **`BP1_PULLBACK`（缩量回踩 MA20）** OOS 净期望为正（¥100k `+2.329%`、¥70k `+0.592%`）获准进入 Phase 3；**`BP2_BREAKOUT`（15日窄幅突破）** OOS 净期望为负（¥100k `-0.187%`、¥70k `-0.001%`）已直接淘汰禁用。
  - `EXP-V3-03`（`PASS_PREEMPTIVE_L2_LOCKED`）：证实滞后 `-15% -> 15%` 熔断在 `T+1` 延迟下于 4/5 历史崩溃窗口击穿红线；锁定高浓度降浓期前置 **`-12% -> 0%` 权益锁 15 交易日**参数，5/5 窗口在 VBT（`-11.02%..-12.85%`）与 RQAlpha（`-8.70%..-12.48%`）均严守 `-15%` 红线。
- 策略规格包：已签发 [v3_offensive_policy_release_v3.2.0.json](../research/ashare/releases/v3_offensive_policy_release_v3.2.0.json)（`production_admission = APPROVED_FOR_ACCOUNT`，同步保留 `v3.1.0` 归档），新增 `EXP-V3-04` 对 `159558.SZ` 的 `25%` 底仓与四门槛震荡磨底降本模式（`BOTTOM_GRIND_25`），进入 Phase 3 实盘状态机升级接入。
