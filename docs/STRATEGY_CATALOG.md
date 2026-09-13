# 策略目录

## S1 Global Dual Momentum

状态：已完成 VectorBT 证据闭环与 RQAlpha 验证，最终决策为 `REJECT_S1`，不支持生产使用。

- 信号频率：每日价格可更新；每月最后观测日计算。
- 执行频率：下一交易日调仓。
- 绝对动量：252 个交易日收益率大于 0。
- 相对动量：合格风险资产按同一收益率降序排名。
- 组合：等权持有前 2 名。
- 防御：没有合格风险资产时持有 `511010.SS` 国债 ETF 研究代理。
- 成本假设：每笔订单 10 bps fee、5 bps slippage（VectorBT baseline）。
- 目标：验证低频多资产相对/绝对动量是否在真实成本与市场语义下稳健。

配置来源是 `config/strategy.toml`，并非散落在适配器中。完整证据显示简单基准和时序稳定性不足，最大回撤约 47%，且 RQAlpha 暴露了 100% 目标仓位在真实市场语义下的执行弱点，因此不再通过参数搜索修补。

## S2 Multi-Asset Trend Following

状态：V1 在严格连续行与每月精确重平衡语义下被拒绝；V2B 已通过 VectorBT 经济筛选、RQAlpha 上游原生执行闭环和粗粒度参数平台检验。S2 Research Candidate R1 已冻结并处于 `PROSPECTIVE_SHADOW_ACTIVE`；尚不是生产候选。

- 趋势窗口：逐资产最近 200 个有效观测，信号日必须有价格。
- 组合：每只合格风险资产拥有等额 sleeve；正趋势持有风险资产，否则转入国债 ETF。
- 执行：月末检查，冻结目标仍只在变化后的下一观测日提交；RQAlpha 6.3.x 启用原生 `partial_fill_on_insufficient_cash`。
- 参数稳健性：预声明的 160/180/200/220/240 个有效观测均保留相近的全样本、固定分期、滚动和低频运营结构；200 不是孤立历史峰值，也未改选为表现最好的邻点。
- 生命周期：经济筛选通过；执行闭环通过；参数平台通过；Research Candidate R1：冻结；前瞻影子：活动；生产候选：否。
- 实现边界：复用 RQAlpha 原生组合订单、部分成交、撮合、成本、账户与 analyser；项目代码只冻结和映射目标、编排回放并做有界追踪，没有本地现金预留或通用执行框架。
- R1 冻结语义：200 个有效观测、月末检查、下一观测日执行、`SIGNAL_CHANGE_ONLY`、现有风险资产池和防御资产、等额 sleeve、既有成本与 RQAlpha 6.3 原生资金不足部分成交。
- 尚未证明：2026-08-31 之后的真正前瞻稳定性或生产可交易性；前瞻协议仅预注册了观察和复核规则，不构成收益结论。
- 下一步：S2 R1 依 [前瞻影子协议](../research/shadow/s2_r1/README.md)积累证据而不修改候选；S3 可在下一独立 Goal 开始透明基线/假设研究。

## S3 China Sector / Theme Rotation

状态：S3A Sector Rotation V1 已完成透明经济筛选并被 `REJECT_S3A_BASELINE`；Theme Rotation 未启动。S2 R1 继续独立积累前瞻 evidence。

- S3A 假设：A 股行业中期相对动量加正绝对动量过滤，月频 top-3 固定 sleeve 与防御资产可能提供风险调整配置价值。
- Universe：11 个按 long-only、境内、明确 A 股行业、最早上市且不使用收益数据的 ETF；不混入 Theme ETF。
- 基线：120 个有效观测动量、`top_k=3`、月末信号/下一观测日执行、`SIGNAL_CHANGE_ONLY`、511010.SS 防御。
- 历史筛选：覆盖与低触达成立，但 CAGR 5.81%、最大回撤 -52.43%、Sharpe 0.363，且不优于 availability-aware 行业等权；经济 baseline：REJECTED。
- 尚未证明：任何不同的 S3 hypothesis、PIT universe、执行或生产可交易性；本拒绝不泛化为“行业轮动无效”。
- 下一步：停止 S3A V1；新的经济 hypothesis 必须使用新版本，而非参数微调。
- Theme Rotation：未启动。

## S3B Sector Breadth Regime Filter V1

状态：`REJECT_S3B_BREADTH_BASELINE`。它是由 S3A 负面证据触发的新历史 hypothesis screen，不是 S3A 参数调整。

- 信号：11 个冻结行业 ETF 的 120 有效观测动量正负号；严格超过 50% breadth 且至少 8 个 eligible 为 RISK_ON。
- 组合：RISK_ON 等权全部 eligible 行业；RISK_OFF 或 UNAVAILABLE 为 511010.SS；月末信号、下一观测日执行、`SIGNAL_CHANGE_ONLY`。
- 历史筛选：最大回撤较同机制 ungated basket 改善 8.52pp，但 CAGR sacrifice 2.64pp，且 Sharpe/Calmar 未改善。
- 尚未证明：任何其他 breadth 规则、OOS、执行或生产可交易性。
- 下一步：停止 S3B，选择新的独立 economic hypothesis；Theme Rotation 未启动。

## S3C Sector Sleeve Trend Filter V1

状态：`REJECT_S3C_BASELINE`。逐行业正趋势保留 1/11 sleeve，负或不可用 sleeve 转防御资产。

- 机制：无 ranking、top-k、breadth 或全局开关；月末信号、下一观测日执行、`SIGNAL_CHANGE_ONLY`。
- 历史筛选：回撤相对 fixed-sleeve ungated basket 改善 10.30pp，但 CAGR sacrifice 2.51pp，Sharpe/Calmar 未改善。
- 尚未证明：OOS、执行、生产可交易性或其他 trend window/sleeve 语义。
- 下一步：停止 S3C；暂停继续改造 sector-momentum family，选择新的独立 hypothesis。Theme Rotation 未启动。

## Batch 01 multi-asset screens

- S4A inverse-volatility：`REJECT_S4A_BASELINE`；未实现所需的相对回撤改善，详见 [报告](../research/results/S4A_INVERSE_VOL_BASELINE_V1.md)。
- S8A equity/bond trend：`REJECT_S8A_BASELINE`；绝对指标与两个简单 comparator 均不成立，详见 [报告](../research/results/S8A_EQUITY_BOND_TREND_BASELINE_V1.md)。
- S27A trend + inverse vol：`ADVANCE_S27A_TO_ROBUSTNESS`；仅 baseline 问题关闭，尚非执行或前瞻候选，详见 [报告](../research/results/S27A_TREND_INVERSE_VOL_BASELINE_V1.md)。
- S30 static strategic allocation：`REFERENCE_BASELINE`；固定 25/25/25/25 的复杂度门槛，详见 [报告](../research/results/S30_STATIC_STRATEGIC_ALLOCATION_V1.md)。

## Batch 02 evidence-informed validation

- S27A trend + inverse vol：`ADVANCE_S27A_TO_EXECUTION_REVIEW`；预声明趋势/波动邻域、分期、滚动及成本均通过，详见 [robustness 报告](../research/results/S27A_ROBUSTNESS_V1.md)。这不是 RQAlpha、前瞻或生产批准。
- S4B canonical ERC：`BLOCK_S4B_UPSTREAM_DEPENDENCY`；官方 Riskfolio-Lib 当前依赖无法在项目声明的 Python 范围可靠解析，未实现或回测 ERC，详见 [报告](../research/results/S4B_ERC_TRANSFER_V1.md)。
- S10A unlevered volatility targeting：`ADVANCE_S10A_VOL_TARGETING_TO_ROBUSTNESS`；20 日/10% 无杠杆、月频静态对照通过本地经济门槛，详见 [报告](../research/results/S10A_VOL_TARGETING_V1.md)。这不是前瞻或生产批准。

## Batch 03 earned stage advancement

- S27A trend + inverse vol：`BLOCK_S27A_EXECUTION_ENVIRONMENT`；171 个冻结月频目标精确复现 VectorBT baseline，但本地 RQAlpha bundle 在首个 frozen date 不识别 511010.XSHG，未形成原生执行指标或候选，详见 [执行审查](../research/results/S27A_RQALPHA_EXECUTION_REVIEW_V1.md)。
- S10A unlevered volatility targeting：`REJECT_S10A_ROBUSTNESS`；V4 有效重跑的邻域、rolling 和成本均通过，但冻结的固定分期 MaxDD 数值条件只为 1/4，详见 [稳健性报告](../research/results/S10A_ROBUSTNESS_V1.md)。不得通过改参数重开。
- S4C canonical ERC / skfolio：`ADVANCE_S4C_ERC_TRANSFER_TO_ROBUSTNESS`；新官方 skfolio 路径在同 eligible-set 控制下通过 transfer gates，S4B Riskfolio-Lib block 保持，详见 [报告](../research/results/S4C_ERC_SKFOLIO_TRANSFER_V1.md)。这不是候选、前瞻或生产批准。

## Batch 04 correctness closure

- S27A：Batch 03 的环境 block 被 pre-listing fallback PIT defect supersede；`RESTORE_S27A_EXECUTION_REVIEW_ELIGIBILITY`，但本批不执行 RQAlpha。
- S10A：Batch 03 robustness reject 被 signed MaxDD correction supersede；`RESTORE_S10A_EXECUTION_REVIEW_ELIGIBILITY`，但本批不执行 RQAlpha。
- S4C：pre-listing fallback 修正后 `RESTORE_S4C_ROBUSTNESS_ELIGIBILITY`；本批不启动 robustness。

## Batch 05 earned stage validation

- S27A：PIT-corrected frozen targets 的 RQAlpha 6.3.0 target-only replay 通过全部 execution gates，`ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW`；这不是 candidate 或 shadow。
- S10A：同一 native replay 发生一个 cash rejection，`DO_NOT_ADVANCE_S10A_EXECUTION`；不得用本地 cash buffer、手工 sizing 或 retry 修补。
- S4C：40/60/80 returns、固定 periods、rolling 和 50bps robustness gates 通过，`ADVANCE_S4C_TO_EXECUTION_REVIEW`；P95 max weight 51.84% 是后续执行审查的风险证据。

## Batch 05 architect review disposition

独立 Principal Architect 复核后：S2 保持 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE` 且仍是唯一前瞻候选；S27A 保留 `ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW` 资格但**推迟**（与 S2 的趋势信号机制重叠度高）；S10A 维持 `DO_NOT_ADVANCE_S10A_EXECUTION`，不得以本地现金、retry 或 sizing 修补；S4C 的 `ADVANCE_S4C_TO_EXECUTION_REVIEW` 成立并被选为唯一下一 Goal，集中度（P95 max weight 51.84%、maximum 66.35%、effective assets median 6.23 / P05 3.24）保留为执行审查的诊断证据。三者的资格都不构成候选、前瞻或生产批准。

记录见 [Batch 05 principal architect review](../research/results/BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md)。

## S4C authoritative execution review

S4C canonical ERC / skfolio：`ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW`。Protocol V2 下 committed 161 个冻结目标的 RQAlpha 6.3.0 原生回放通过全部预注册 gate：CAGR 12.0929%、signed MaxDD -18.3512%、Sharpe 0.7758、cash rejection 0、平均 execution-date deviation 0.3246%、material dates 3/161（两个 >5pp 单资产差异都有具体 native 原因；第三个是最大单资产偏差 3.84pp、现金残差 3.80% 的组合层偏离）、平均现金 0.1399%。

V1 的 `1e-12` reproduction 判据不可跨平台达成，作为 `INVALID_RUN` 保留；Protocol V2 只替代该 portability 判据并附带数值容差，不放松任何 native execution gate，也不改变经济语义或冻结目标。这是 execution review 资格，不是 candidate、前瞻或生产批准；集中度（P95 max weight 51.84%、maximum 66.35%）仍是未消除的风险特征。

记录见 [S4C execution review V2](../research/results/S4C_RQALPHA_EXECUTION_REVIEW_V2.md)。

## S4C Research Candidate R1（已冻结，前瞻影子活动）

状态：`FROZEN / PROSPECTIVE_SHADOW_ACTIVE`。独立候选冻结审查的裁决为 `FREEZE_S4C_RESEARCH_CANDIDATE_R1`；集中度裁决为 `ACCEPT_AS_KNOWN_CANDIDATE_RISK`；独立 activation 裁决为 `ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW`。这不是生产候选，也不是前瞻绩效结论。

- 冻结身份：官方 skfolio `RiskBudgeting` / `RiskMeasure.VARIANCE` / equal risk budgets / long-only、fully invested、无杠杆；min eligible 6；61 价格 / 60 `fill_method=None` 对齐收益；现有 9 个风险资产 + `511010.SS` fallback；月末估计 → 下一 canonical 观测日执行；`MONTHLY_TARGET_SUBMISSION`（不是 S2 的 `SIGNAL_CHANGE_ONLY`）；10 bps fee + 5 bps slippage；RQAlpha 6.3.x 原生执行与 `partial_fill_on_insufficient_cash`。
- 历史截止 / 前瞻边界：`historical_cutoff = 2026-08-31`，`freeze_timestamp = 2026-09-13T13:28:15Z`，`first_eligible_prospective_signal = 2026-09-30`；不得回溯前瞻证据。
- 冻结目标：161 行，`2013-04-01` 至 `2026-08-03`，SHA-256 `f7bf398d…1227e47`。
- 阶段限制：冻结候选 ≠ 激活前瞻 ≠ 生产批准。前瞻影子由候选级 lifecycle artifact [activation.json](../research/shadow/s4c_r1/activation.json) 激活（`candidate_manifest.json` 的 `prospective_activation = NOT_ACTIVE` 保持为历史冻结身份）；`observations.csv` 只有表头，`observation_count = 0`，`first_eligible_prospective_signal = 2026-09-30`。
- 已知风险：P95 最大权重 51.84%、历史最大 66.35%、effective assets median 6.23 / P05 3.24。不得添加集中度 cap 或据此改参；那属于新策略版本。
- 下一步：`S4C_R1_FIRST_PROSPECTIVE_DECISION` 于真实 `2026-09-30` 及之后、且已有该 as-of 的 candidate-specific vintage 时方可启动；它不修改 R1 身份，也不提前产生执行证据。

身份与协议见 [S4C R1](../research/shadow/s4c_r1/README.md)、[manifest](../research/shadow/s4c_r1/candidate_manifest.json)；审查记录见 [S4C candidate-freeze review](../research/results/S4C_CANDIDATE_FREEZE_REVIEW_V1.md)。

## 外部 canonical 映射与本地边界

详细外部范围见 [策略研究地图](STRATEGY_RESEARCH_MAP.md)，此处只记录已实现策略的本地生命周期。

| Local strategy | Canonical external mapping | Tier | Local question/status | Local result does NOT prove |
| --- | --- | --- | --- | --- |
| S1 | cross-sectional / dual momentum | E1/E3 | 受限ETF transfer，REJECTED | 全球 momentum 被否定 |
| S2 | time-series momentum | E1 | 长多ETF transfer，PROSPECTIVE_SHADOW_ACTIVE | 已获得生产资格 |
| S3A | industry momentum | E1 | 中国行业ETF transfer，REJECTED | industry momentum 不存在 |
| S3B | aggregate breadth regime | E4 | 本地广度假设，REJECTED | 所有 breadth 规则无效 |
| S3C | per-sector trend transfer | E3 | 本地固定sleeve filter，REJECTED | trend globally invalid |
| S4A | inverse-volatility allocation | E2 | 复杂度是否有增量价值，REJECTED | inverse-vol 方法无用 |
| S8A | moving-average tactical allocation | E3 | 两资产中国ETF规则，REJECTED | trend literature 被否定 |
| S27A | trend + inverse-vol sizing | E3 | candidate-freeze review eligible | 新异常或生产资格 |
| S4B / S4C | equal risk contribution | E2 | S4B Riskfolio BLOCKED；S4C R1 FROZEN / PROSPECTIVE_SHADOW_ACTIVE（非生产候选，observations = 0） | 前瞻有效性、生产适用性或 ERC 的一般优越性；历史冻结目标日程的原生可执行性已证明，但不构成未来可执行性或有效性证据 |
| S10A | unlevered volatility targeting | E3 | native cash rejection 后 execution review 未推进 | volatility-managed 文献已被本地证明 |
| S30 | naive/static diversification | E1 | REFERENCE_BASELINE | alpha 策略 |
