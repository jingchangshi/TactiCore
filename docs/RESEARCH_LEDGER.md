# TactiCore 研究账本

本文件是轻量、只追加的研究知识账本，用于避免后续 Goal 重复已关闭问题；它不是治理框架，也不配套软件。条目状态只使用 `CLOSED`、`REJECTED`、`ACTIVE`、`SUPERSEDED`。

通用重开条件：只有底层策略语义变化、canonical 数据契约变化、框架变化使相关假设失效，或出现新的矛盾证据时，才可重开已关闭条目。每项更窄的重开条件在条目内补充。

## RL-001 Tushare canonical 来源与复权

- 策略：S1 / S2
- 问题：Tushare canonical 数据来源以及 `fund_daily` / `fund_adj` 应如何解释？
- 状态：CLOSED
- 范围：ETF 日收盘、复权因子、交易日历、基金元数据和来源记录。
- 结论：后复权价格定义为 `fund_daily.close × fund_adj.adj_factor`；请求参数、下载时间、质量检查和文件哈希均已保存。`fund_daily` 缺失而 `fund_adj` 存在不等于价格为零，也不授权填补价格。
- 证据：[canonical 数据说明](../data/canonical/README.md)、[来源清单](../data/canonical/provenance.json)、[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)
- 数据快照：2012-01-01 至 2026-08-31 请求；价格 SHA-256 `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93`。
- 框架/版本：Tushare Pro；RQAlpha 5.6.5 仅用于缺失日有界对照。
- 重开条件：Tushare 接口/复权定义改变、快照重建产生矛盾，或 canonical 契约变化。

## RL-002 缺失值保持未知

- 策略：S1 / S2
- 问题：缺失行情是否可以静默填充？
- 状态：CLOSED
- 范围：上市前空白、上市后无行情和策略读取。
- 结论：缺失值保持为空；不得前向填充、插值、置零或猜测。
- 证据：[canonical 数据说明](../data/canonical/README.md)、[数据测试](../tests/test_data.py)
- 数据快照：同 RL-001。
- 框架/版本：不适用。
- 重开条件：canonical 数据契约明确变化。

## RL-003 S2 可用性与负信号语义

- 策略：S2 V2
- 问题：`UNAVAILABLE` 是否等于 `NEGATIVE_SIGNAL`，以及 200 日窗口如何取值？
- 状态：CLOSED
- 范围：逐资产趋势均线与信号日资格。
- 结论：两种状态不等价。每个资产独立使用截至信号日最近 200 个有效观测；信号日自身必须有有效价格，否则为不可用。
- 证据：[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)、[策略实现](../tacticore/strategies/multi_asset_trend.py)、[策略测试](../tests/test_multi_asset_trend.py)
- 数据快照：同 RL-001。
- 框架/版本：VectorBT 0.28.x 负责经济筛选，不负责定义信号。
- 重开条件：S2 可用性或窗口语义改变，或出现矛盾数据证据。

## RL-004 月末信号执行时点

- 策略：S1 / S2
- 问题：月末收盘形成的信号何时可执行？
- 状态：CLOSED
- 范围：信号到目标执行日期的映射。
- 结论：不能使用同一收盘价生成并执行信号；最早在下一 canonical 观测日执行。
- 证据：[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)、[策略实现](../tacticore/strategies/multi_asset_trend.py)、[策略测试](../tests/test_multi_asset_trend.py)
- 数据快照：同 RL-001。
- 框架/版本：不适用。
- 重开条件：交易时点或可用信息假设改变。

## RL-005 S2 V1 连续行行为

- 策略：S2 V1
- 问题：连续 200 个 dataframe 行的缺失处理是否可接受？
- 状态：REJECTED
- 范围：V1 严格连续行均线与每月精确目标提交。
- 结论：少量缺失会使资产长期不可用并混杂防御效果；V1 证据与机械月月重平衡不符合要求。
- 证据：[S2 V1 报告](../research/results/S2_BASELINE_ECONOMIC_SCREEN_V1.md)、[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)
- 数据快照：同 RL-001；510500.SS 在 2015-04-13/14 缺失。
- 框架/版本：VectorBT 0.28.x。
- 重开条件：不重开；新语义必须作为新版本研究。

## RL-006 V1 到 V2A 的可用性影响

- 策略：S2 V1 / V2A
- 问题：逐资产有效观测语义对目标和结果影响多大？
- 状态：CLOSED
- 范围：只改变可用性语义，保持每月提交目标。
- 结论：增加 40 个合格资产月，改变 32 个月/40 个资产月的状态和 30 个目标月；影响已完整量化，不再重复。
- 证据：[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)、[变体比较](../research/results/s2_v2_variant_comparison.csv)
- 数据快照：同 RL-001。
- 框架/版本：VectorBT 0.28.x。
- 重开条件：V1/V2A 语义或数据快照改变。

## RL-007 V2A 到 V2B 的提交语义

- 策略：S2 V2A / V2B
- 问题：仅在目标变化时提交是否改变经济信号？
- 状态：CLOSED
- 范围：相同月末目标，不同目标提交频率。
- 结论：V2A 与 V2B 的信号目标相同；V2B 只省略不变目标的重复提交，绩效差异来自不再把组合漂移机械重置，而非新信号。
- 证据：[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)、[变体比较](../research/results/s2_v2_variant_comparison.csv)
- 数据快照：同 RL-001。
- 框架/版本：VectorBT 0.28.x。
- 重开条件：目标生成或 `SIGNAL_CHANGE_ONLY` 定义改变。

## RL-008 S2 VectorBT 经济筛选

- 策略：S2 V2B
- 问题：冻结基线是否具备继续做权威执行验证的经济证据？
- 状态：CLOSED
- 范围：完整期、基准、分期和基本风险收益。
- 结论：经济筛选已完成并支持进入 RQAlpha；这不等于生产可用或参数稳健。
- 证据：[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)、[基准比较](../research/results/s2_v2_benchmark_comparison.csv)、[分期结果](../research/results/s2_v2_period_performance.csv)
- 数据快照：同 RL-001。
- 框架/版本：VectorBT 0.28.x。
- 重开条件：策略语义、数据快照或 VectorBT 核心执行假设改变。

## RL-009 S2 滚动区间证据

- 策略：S2 V2B
- 问题：既有滚动 3 年/5 年表现如何？
- 状态：CLOSED
- 范围：已定义的全部滚动窗口。
- 结论：滚动证据已生成并完成解释；当前 Goal 不重复计算或扩展。
- 证据：[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)、[滚动结果](../research/results/s2_v2_rolling_performance.csv)
- 数据快照：同 RL-001。
- 框架/版本：VectorBT 0.28.x。
- 重开条件：策略语义、数据快照或滚动检验设计改变。

## RL-010 S2 成本敏感性

- 策略：S2 V2B
- 问题：既有 15/30/50 bps 成本敏感性是否完成？
- 状态：CLOSED
- 范围：既定单边总成本情景。
- 结论：成本敏感性已完成；成本提高会削弱表现，但既有范围内未单独否定策略。
- 证据：[S2 V2 审计](../research/results/S2_DECISION_AUDIT_V2.md)、[成本结果](../research/results/s2_v2_cost_sensitivity.csv)
- 数据快照：同 RL-001。
- 框架/版本：VectorBT 0.28.x 原生成本参数。
- 重开条件：策略换手语义、成本假设或执行工具改变。

## RL-011 S2 通用信号可信度

- 策略：S2 V2B
- 问题：是否还需要通用信号可信度审计？
- 状态：CLOSED
- 范围：数据、缺失、可用性、时点、V1/V2 和一般经济筛选。
- 结论：上述问题均已关闭；后续只在新矛盾证据指向具体条目时有界重开，不再做宽泛审计。
- 证据：RL-001 至 RL-010。
- 数据快照：同 RL-001。
- 框架/版本：见各引用条目。
- 重开条件：通用重开条件之一成立，并指出具体矛盾条目。

## RL-012 S2 V2B 冻结目标日程

- 策略：S2 V2B
- 问题：执行实验的固定输入是什么？
- 状态：CLOSED
- 范围：仅目标变化后的下一观测日与十个资产目标权重。
- 结论：冻结日程共 103 个执行日；执行实验不得在 RQAlpha 内重算信号。
- 证据：[冻结目标](../research/results/s2_v2_frozen_targets.csv)、[冻结日程测试](../tests/test_s2_rqalpha_validation.py)
- 数据快照：CSV SHA-256 `9cc5a8e70751f274cb7c4f900784400bd8de684450833ba6d4034fd75ca70b61`。
- 框架/版本：输入由 TactiCore 策略语义生成，与 RQAlpha 版本无关。
- 重开条件：S2 V2B 策略语义明确变更并建立新版本。

## RL-013 RQAlpha 5.6.5 冻结目标回放

- 策略：S2 V2B
- 问题：RQAlpha 5.6.5 原生执行能否忠实实现冻结目标？
- 状态：SUPERSEDED
- 范围：相同初始资金、费用、滑点、撮合、区间与冻结目标。
- 结论：经济性仍在，但 34 个现金相关失败状态与 `SIGNAL_CHANGE_ONLY` 共同造成持久留空；主导问题是资金不足整单拒绝。该执行版本已被 RL-014 的上游能力取代，历史证据不改写。
- 证据：[5.6.5 执行报告](../research/results/S2_RQALPHA_EXECUTION_VALIDATION_V1.md)、[原生汇总](../research/results/s2_rqalpha_native_summary.csv)
- 数据快照：同 RL-012；评价区间 2013-03-29 至 2026-08-31。
- 框架/版本：RQAlpha 5.6.5。
- 重开条件：仅当需要复核控制组完整性或新证据与控制结果矛盾。

## RL-014 RQAlpha 上游原生执行闭环

- 策略：S2 V2B
- 问题：上游原生能力能否关闭主导资金不足执行缺口？
- 状态：CLOSED
- 范围：冻结输入下比较 5.6.5 控制、6.3.0 兼容控制、6.3.0 原生部分成交，并检查 6.4.0 上游标签。
- 结论：6.3.0 的 `partial_fill_on_insufficient_cash` 将现金整单拒绝降为 0、显著偏离执行日由 34 降至 5、现金权重大于 5% 的检查月由 49 降至 2，同时未实质破坏经济证据；采用上游，不做本地现金预留。
- 证据：[上游执行闭环报告](../research/results/S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md)、[版本比较](../research/results/s2_rqalpha_upstream_comparison.csv)、[上游原生汇总](../research/results/s2_rqalpha_upstream_native_summary.csv)
- 数据快照：同 RL-012；评价区间 2013-03-29 至 2026-08-31。
- 框架/版本：采用 RQAlpha 6.3.x；检查 RQAlpha 6.4.0 标签但不将未发布到 PyPI 的版本纳入依赖。
- 重开条件：RQAlpha 升级改变该开关、订单/撮合/账户语义，或新执行证据出现实质矛盾。

## RL-015 S2 粗粒度参数平台与稳健性

- 策略：S2 V2B / Research Candidate R1
- 问题：200 个有效观测的趋势窗口是否处于宽泛、经济稳定的参数平台，而非孤立历史最优点？
- 状态：CLOSED
- 范围：仅比较预先声明的 `160/180/200/220/240`；冻结 canonical 数据、资产池、防御资产、有效观测、月末信号、下一观测日执行、`SIGNAL_CHANGE_ONLY`、等额 sleeve、成本、滑点、初始资金和 VectorBT 路径。
- 结论：五点全样本收益风险差异平滑，四个既有分期均保持正 CAGR 和 Sharpe，3 年/5 年滚动中位数及运营负担相近；决策为 `PASS_S2_PARAMETER_PLATEAU`，保持透明基线 `trend_window = 200`，不选择历史表现最好的邻点。S2 冻结为 Research Candidate R1，但不构成生产批准或真正前瞻样本外证据。
- 证据：[参数平台报告](../research/results/S2_PARAMETER_PLATEAU_V1.md)、[全样本与运营汇总](../research/results/s2_parameter_plateau_summary.csv)、[固定分期](../research/results/s2_parameter_periods.csv)、[滚动证据](../research/results/s2_parameter_rolling.csv)
- 数据快照：同 RL-001；评价区间 2013-03-29 至 2026-08-31，前瞻证据截止线为 2026-08-31。
- 框架/版本：VectorBT 0.28.5；仅使用原生组合记录，参数判定编排保留在一次性实验中。
- 重开条件：S2 R1 冻结语义或 canonical 数据契约变化，VectorBT 变更使结果不可复现，或未来前瞻影子证据与平台结论发生实质矛盾。

## RL-016 S2 Research Candidate R1 冻结

- 策略：S2 V2B / Research Candidate R1
- 问题：进入真正前瞻观察前，R1 的可复现身份、输入边界与替换规则是什么？
- 状态：CLOSED
- 范围：200 个有效观测、月末收盘信号、下一 canonical 观测日执行、`SIGNAL_CHANGE_ONLY`、既有资产池/防御资产/成本/缺失值语义，以及 RQAlpha 6.3 原生资金不足部分成交。
- 结论：S2_R1 于 commit `68c31b88e8432bee8078aa233a2b95ab414afdb6` 的已验证历史基线冻结；historical cutoff 为 2026-08-31，prospective start 为 2026-09-01。身份、框架版本与关键输入 SHA-256 见 [manifest](../research/shadow/s2_r1/candidate_manifest.json)。任何实质语义或数据契约变更均创建下一顺序候选版本，不改写 R1。
- 证据：[R1 前瞻协议报告](../research/results/S2_R1_PROSPECTIVE_PROTOCOL_V1.md)、[协议](../research/shadow/s2_r1/README.md)。
- 数据快照：RL-001 的冻结 canonical；价格 SHA-256 `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93`，交易日历 SHA-256 `ad942a3e1e3e3ae4b7703ea5319ec12793d484b4c49423181682357a1a9d7512`。
- 框架/版本：VectorBT 0.28.5；RQAlpha 6.3.0。
- 重开条件：不重开 R1；新语义、新 canonical 契约或不兼容框架变化必须产生新的候选版本。

## RL-017 S2 前瞻影子协议 V1

- 策略：S2 Research Candidate R1
- 问题：如何在不重做历史研究的前提下，积累真正前瞻 evidence？
- 状态：ACTIVE
- 范围：候选专属 data vintages、as-of 驱动的月度 decision record、追加式 execution evidence、评审资格与候选完整性规则。
- 结论：协议 V1 已预注册。中期完整性复核不得早于 12 个日历月；production-candidate review 资格为至少 18 个日历月且至少 10 个真实 target-change 执行事件。没有预设收益门槛；当前尚无足够前瞻 observation。
- 证据：[协议](../research/shadow/s2_r1/README.md)、[记录表](../research/shadow/s2_r1/observations.csv)、[R1 前瞻协议报告](../research/results/S2_R1_PROSPECTIVE_PROTOCOL_V1.md)。
- 数据快照：historical cutoff 2026-08-31；前瞻数据仅接受严格晚于该日期的 candidate-specific vintage。
- 框架/版本：不新增框架；决策沿用冻结策略语义，执行证据沿用 RQAlpha 6.3.x 原生结果。
- 重开条件：只在 manifest/协议无法保持身份、历史/前瞻隔离或 as-of 正确性时有界修订协议；不得因短期表现重开或优化 R1。

## RL-018 S3A 透明行业轮动基线

- 策略：S3A China Sector Rotation V1
- 问题：预声明的 120 有效观测、top-3、月频正动量行业 ETF 轮动是否值得进入稳健性研究？
- 状态：REJECTED
- 范围：11 个按非收益 metadata 规则选取的 A 股行业 ETF；独立 Tushare canonical，截止 2026-08-31；`SIGNAL_CHANGE_ONLY`、1/3 固定 sleeve、511010.SS 防御、VectorBT 经济筛选。
- 结论：覆盖门槛和低触达约束成立，但 after-cost CAGR 5.81%、Sharpe 0.363、最大回撤 -52.43% 未达预声明 floor，且相对行业等权的 CAGR/回撤/Sharpe/Calmar 均不优，决策 `REJECT_S3A_BASELINE`。不得通过参数微调重开。
- 证据：[S3A 报告](../research/results/S3_SECTOR_BASELINE_V1.md)、[universe](../research/results/s3_sector_universe_v1.csv)、[benchmark 比较](../research/results/s3_sector_benchmark_comparison_v1.csv)。
- 数据快照：价格 SHA-256 `337c28cc52c04f8b5257a8feffb7d1c508248cab10595466c8c69d758556a4a6`；日历 SHA-256 `13f4240ee6531415e3ea7638d9691af01290e97da3607446246d3dc8f96e51e6`。
- 框架/版本：Tushare Pro；VectorBT 0.28.5。
- 重开条件：仅当 S3A V1 语义、universe 契约或 canonical 数据契约改变时作为新版本研究；不得以本轮收益结果或更优参数重开。
