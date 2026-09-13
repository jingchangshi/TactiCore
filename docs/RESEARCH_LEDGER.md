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

## RL-019 S3B 行业趋势广度状态过滤基线

- 策略：S3B China Sector Breadth Regime Filter V1
- 问题：严格多数行业处于正 120 有效观测趋势时持有广泛行业篮子，能否改善同机制 ungated basket？
- 状态：REJECTED
- 范围：复用 RL-018 的冻结 universe/data；120 observation、严格 `breadth > 0.50`、至少 8 eligible、月频、`SIGNAL_CHANGE_ONLY`、511010.SS 防御。
- 假设来源：在已观察 S3A 失败及行业等权更强后提出，属于 historical follow-up hypothesis，不是 OOS。
- 结论：最大回撤相对 ungated 改善 8.52pp，但 CAGR 低 2.64pp（超过预声明 2pp 上限），Sharpe/Calmar 也未提高，决策 `REJECT_S3B_BREADTH_BASELINE`。
- 证据：[S3B 报告](../research/results/S3B_SECTOR_BREADTH_BASELINE_V1.md)、[状态](../research/results/s3b_sector_breadth_states_v1.csv)、[比较](../research/results/s3b_sector_breadth_comparison_v1.csv)。
- 数据快照：复用 RL-018；价格 SHA-256 `337c28cc52c04f8b5257a8feffb7d1c508248cab10595466c8c69d758556a4a6`。
- 框架/版本：VectorBT 0.28.5。
- 重开条件：仅当 S3B 语义、universe 或 canonical 契约作为新版本变化；不得调 threshold/lookback 重开。

## RL-020 S3C 行业固定 Sleeve 趋势过滤基线

- 策略：S3C China Sector Sleeve Trend Filter V1
- 状态：REJECTED
- 问题：逐行业 120 有效观测绝对趋势能否改善同机制 fixed-sleeve basket？
- 范围：复用 RL-018 universe/data；每行业固定 1/11，正趋势持有、负或不可用 sleeve 转 511010.SS，月频 `SIGNAL_CHANGE_ONLY`。
- 假设来源：在观察 S3A/S3B 后提出，仅属 historical follow-up，不是 OOS。
- 结论：回撤改善 10.30pp，但 CAGR sacrifice 2.51pp，Sharpe/Calmar 未提高，`REJECT_S3C_BASELINE`。
- 证据：[S3C 报告](../research/results/S3C_SECTOR_SLEEVE_BASELINE_V1.md)、[比较](../research/results/s3c_sector_sleeve_comparison_v1.csv)。
- 重开条件：仅新策略版本或数据/universe 契约变化；不得参数救援。

## RL-021 S4A inverse-volatility baseline

- 策略：S4A_INVERSE_VOL_V1；状态：REJECTED。
- 问题/范围：60 个有效日收益 inverse-vol 是否优于同 eligible set 的等权多资产配置；少于 6 个资产全防御。
- 结论：CAGR 10.88%、Sharpe 0.981 均高于等权，但最大回撤 -22.48% 略差于 -22.33%，未达到预注册的 3pp 改善门槛，`REJECT_S4A_BASELINE`。
- 证据：[报告](../research/results/S4A_INVERSE_VOL_BASELINE_V1.md)；冻结协议 `0d245b9`；canonical 同 RL-001。
- 重开条件：新策略语义、canonical 或 universe 契约变化；不得以 cap/optimizer/参数调优重开。

## RL-022 S8A equity/bond trend baseline

- 策略：S8A_EQUITY_BOND_TREND_V1；状态：REJECTED。
- 问题/范围：510300 的 200 有效观测趋势能否在 511010 之间形成低维护股债切换。
- 结论：CAGR 1.80%、最大回撤 -51.92%、Sharpe 0.193，弱于股票与静态 50/50 comparator，`REJECT_S8A_BASELINE`。
- 证据：[报告](../research/results/S8A_EQUITY_BOND_TREND_BASELINE_V1.md)；冻结协议 `0d245b9`；canonical 同 RL-001。
- 重开条件：新策略语义或 canonical 契约变化；不得调趋势窗口重开。

## RL-023 S27A trend + inverse-vol baseline

- 策略：S27A_TREND_INVERSE_VOL_V1；状态：CLOSED。
- 问题/范围：保持 S2 同一趋势状态和 P/N 风险预算，仅用 60 日 inverse-vol 重分配 active sleeves 是否改善风险调整效率。
- 假设来源：已观察 S2 evidence 后的 historical follow-up，不是 OOS。
- 结论：相对已修正为 `SIGNAL_CHANGE_ONLY` 的只读 S2 reproduction，CAGR 7.79% vs 6.16%、最大回撤 -12.50% vs -26.18%、Sharpe 1.015 vs 0.628；`ADVANCE_S27A_TO_ROBUSTNESS`，基线问题关闭。此前账本遗留 R1 comparator 数字，现仅作事实一致性更正，不重跑、不改变策略或决策。
- 证据：[报告](../research/results/S27A_TREND_INVERSE_VOL_BASELINE_V1.md)；correctness revision Protocol V2 `ae218d7`；canonical 同 RL-001。
- 重开条件：下一问题仅可为预注册 robustness；不得修改本基线以追逐结果。

## RL-024 S30 static strategic-allocation reference

- 策略：S30_REFERENCE_V1；状态：CLOSED。
- 范围：510300/513500/518880/511010 固定各 25%，年频再平衡的复杂度基准。
- 结论：CAGR 9.92%、最大回撤 -15.04%、Sharpe 1.114、Calmar 0.660；`REFERENCE_BASELINE`，不作 alpha pass/fail。
- 证据：[报告](../research/results/S30_STATIC_STRATEGIC_ALLOCATION_V1.md)；冻结协议 `0d245b9`；canonical 同 RL-001。
- 重开条件：只有静态配置或 canonical 契约明确变化。

## RL-025 S27A inverse-vol sizing robustness

- 策略：S27A_TREND_INVERSE_VOL_V1；状态：CLOSED。
- 问题/范围：在冻结 S27A 基线周围，仅以 160/180/200/220/240 趋势窗口和 40/60/80 波动窗口的单因素邻域，检验 inverse-vol active sizing 是否稳定；复用既有固定分期、3Y/5Y 滚动和 15/30/50 bps 成本语义。
- 外部映射：`VOL_SCALED_TREND`，E3；Kim/Tse/Wald 的缩放反证保留，问题仅为本地 ETF sizing transfer。
- 结论：实验层 evaluator 精确复现修正后的 200/60 基线；所有预声明参数、分期、滚动和 50 bps 成本门槛均通过，决策 `ADVANCE_S27A_TO_EXECUTION_REVIEW`。它不授权 RQAlpha、前瞻或生产。
- 证据：[报告](../research/results/S27A_ROBUSTNESS_V1.md)、[协议](../research/batches/batch_02/PROTOCOL.md)；canonical 同 RL-001。
- 重开条件：执行 review 发现具体矛盾，或 S27A 语义、canonical 契约或 VectorBT 核心假设变化；不得选择邻域最佳参数。

## RL-026 S4B canonical ERC ETF transfer

- 策略：S4B_ERC_RISK_PARITY_V1；状态：CLOSED。
- 问题/范围：官方上游 Riskfolio-Lib 是否能在 TactiCore 声明的 Python 环境可靠安装，从而开始预注册的无杠杆 ERC ETF transfer。
- 外部映射：`ERC_RISK_PARITY`，E2 established method；软件可用性不等同于经济优越性。
- 结论：当前 7.3.0 需要 `scipy>=1.16.1`，与项目 `>=3.10,<3.13` 的跨版本解析不兼容；决策 `BLOCK_S4B_UPSTREAM_DEPENDENCY`。没有本地 solver、旧版替代、ERC 权重或历史绩效证据。
- 证据：[报告](../research/results/S4B_ERC_TRANSFER_V1.md)、[协议](../research/batches/batch_02/PROTOCOL.md)。
- 重开条件：官方当前上游依赖在项目 Python 范围可靠解析；届时必须新建协议，不能把本 block 当作 ERC 经济失败。

## RL-027 S10A unlevered volatility-targeting adjudication

- 策略：S10A_UNLEVERED_VOL_TARGETING_V1；状态：CLOSED。
- 问题/范围：固定 25/25/25/25 base、20 个有效对齐日收益、10% target、[0,1] 无杠杆 scale，是否相对同 timing/cost 的月频静态控制带来本地风险调整增量。
- 外部映射：`VOL_TARGETING`，E3；Moreira/Muir 支持与 Cederburg 等反证均保留，结论不外推至文献争议。
- 结论：R1 因默认前填充违反有效对齐收益语义而无效；Protocol V2 后的唯一 rerun 以 `fill_method=None` 通过绝对、相对与非退化门槛，决策 `ADVANCE_S10A_VOL_TARGETING_TO_ROBUSTNESS`。结果不是前瞻或生产资格。
- 证据：[报告](../research/results/S10A_VOL_TARGETING_V1.md)、[无效运行记录](../research/results/INVALID_RUN_BATCH_02_R1.md)、[Protocol V2](../research/batches/batch_02/PROTOCOL_V2.md)；canonical 同 RL-001。
- 重开条件：仅 robustness、语义/canonical/VectorBT 变化或具体正确性矛盾；不得由历史结果改 target 或 lookback。

## RL-028 S27A frozen-target RQAlpha execution review

- 策略：S27A_TREND_INVERSE_VOL_V1；状态：BLOCKED。
- 问题/范围：171 个冻结的月频 S27A execution targets 能否在 RQAlpha 6.3.0 原生账户中覆盖全期回放，并满足 fidelity、现金与经济门槛。
- 结论：VectorBT 从首个 execution date 精确复现 Batch 02 baseline；但本地 RQAlpha bundle 在首个 frozen date `2012-06-01` 不识别 511010.XSHG，未产生可信原生指标。决策 `BLOCK_S27A_EXECUTION_ENVIRONMENT`，不创建候选。
- 证据：[报告](../research/results/S27A_RQALPHA_EXECUTION_REVIEW_V1.md)、[冻结 schedule](../research/results/s27a_v1_frozen_targets.csv)、[Protocol V2](../research/batches/batch_03/PROTOCOL_V2.md)。
- 重开条件：可覆盖完整冻结 schedule 的 RQAlpha bundle，或明确的原生数据契约变化；不得改 target 或以本地执行替代。

## RL-029 S10A unlevered volatility-targeting robustness

- 策略：S10A_UNLEVERED_VOL_TARGETING_V1；状态：REJECTED。
- 问题/范围：对冻结 20 日/10% 无杠杆 overlay 做单因素窗口与 target 邻域、固定分期、3Y/5Y rolling 和 15/30/50 bps 成本审查。
- 结论：V4 有效重跑的绝对、相对邻域、scale、rolling 与 50 bps 门槛通过；按冻结字面固定分期 MaxDD `<=` static MaxDD 规则，只有 1/4 分期通过，未达 3/4。决策 `REJECT_S10A_ROBUSTNESS`，不运行 RQAlpha。
- 证据：[报告](../research/results/S10A_ROBUSTNESS_V1.md)、[Protocol V4](../research/batches/batch_03/PROTOCOL_V4.md)、[R2](../research/results/INVALID_RUN_BATCH_03_R2.md)、[R3](../research/results/INVALID_RUN_BATCH_03_R3.md)。
- 重开条件：仅新策略语义、canonical/VectorBT 契约变化或具体新矛盾证据；不得调 window 或 target 救援。

## RL-030 S4C canonical ERC skfolio transfer

- 策略：S4C_CANONICAL_ERC_SKFOLIO_TRANSFER_V1；状态：CLOSED。
- 问题/范围：在 Python 3.10–3.12 可解析的官方 skfolio `RiskBudgeting` variance long-only/equal-budget 路径下，对 S2 risk universe 以 61 对齐价格/60 收益做无杠杆 ERC transfer，并与同 eligible set equal/inverse-vol 比较。
- 结论：3.10/3.11/3.12 resolver 均通过；风险覆盖 87.13%，ERC CAGR 10.91%、MaxDD -18.35%、Sharpe 1.058，满足绝对和 inverse-vol 相对门槛，决策 `ADVANCE_S4C_ERC_TRANSFER_TO_ROBUSTNESS`。S4B Riskfolio-Lib block 保持不变；没有本地 solver。
- 证据：[报告](../research/results/S4C_ERC_SKFOLIO_TRANSFER_V1.md)、[比较](../research/results/s4c_erc_skfolio_comparison_v1.csv)、[Protocol](../research/batches/batch_03/PROTOCOL.md)。
- 重开条件：下一问题仅可为预注册 S4C robustness；不得通过 ERC 参数调优、替换 S4B 历史或跳过 upstream 路径重开。

## RL-031 PIT tradability contract

- 状态：CLOSED。RQAlpha lifecycle 与 local universe 12/12 一致；正执行目标必须同时 active 和有有限正 canonical price，完整 target 的首个合法 execution date 定义 strategy inception。
- 证据：[影响审计](../research/results/PIT_TRADABILITY_IMPACT_AUDIT_V1.md)、[lifetime audit](../research/results/asset_lifetime_audit_v1.csv)。

## RL-032 signed MaxDD semantics

- 状态：CLOSED。MaxDD 为负值，较少负值更好；no-worse 统一为 `candidate >= comparator`，不得用裸反向比较。

## RL-033 Batch 04 corrected local decisions

- 状态：CLOSED。S2 R1 PIT integrity pass；S27A Batch 03 environment block 与 S10A robustness reject 均被 correctness review supersede，分别恢复 execution-review eligibility；S4C 恢复 robustness eligibility。没有运行后续阶段。
- 证据：[Batch 04](../research/results/BATCH_04_COMMUNITY_BACKED_PIT_CORRECTNESS_CLOSURE.md)。

## RL-034 VectorBT PIT validation enforcement

- 状态：CLOSED。`run_target_weights` 必须显式接收 lifecycle-derived tradability mask 与 lifetimes；遗漏 PIT context 立即失败，不提供通用绕过开关。
- 结论：此为研究 contract plumbing，不改变 S2 冻结策略、数据、targets 或历史经济语义。

## RL-035 S27A PIT-corrected native execution review

- 状态：CLOSED。161 个 PIT-legal frozen targets 严格重现 Batch 04 VectorBT baseline；RQAlpha 6.3.0 target-only replay 全日期处理、无额外日期、零 cash rejection，所有预注册 fidelity 和经济 gates 通过。
- 结论：`ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW`，不创建 candidate 或 shadow。
- 证据：[报告](../research/results/S27A_RQALPHA_EXECUTION_REVIEW_V2.md)。

## RL-036 S10A PIT-corrected native execution review

- 状态：CLOSED。161 个 PIT-legal frozen targets 严格重现 Batch 04 VectorBT baseline，tracking 与经济门槛通过；但 RQAlpha 原生记录一个 cash rejection，违反零容忍 gate。
- 结论：`DO_NOT_ADVANCE_S10A_EXECUTION`；不得以本地现金缓冲、手工 sizing 或 retry 修补。
- 证据：[报告](../research/results/S10A_RQALPHA_EXECUTION_REVIEW_V1.md)。

## RL-037 S4C bounded ERC robustness

- 状态：CLOSED。固定中心 60-return 严格重现 Batch 04，40/60/80 return windows、固定 periods、3Y/5Y rolling 与 50bps cost gates 均通过；P95 maximum weight 51.84% 作为 concentration 风险保留。
- 结论：`ADVANCE_S4C_TO_EXECUTION_REVIEW`，本批不运行其 RQAlpha。
- 证据：[报告](../research/results/S4C_ROBUSTNESS_V1.md)。

## RL-038 Batch 05 earned stage decisions

- 状态：CLOSED。Protocol V1/V2 的实现缺陷均作为 INVALID_RUN 由 V3 完整 rerun 取代；外部 evidence tier 未变，S2 R1 未改动。
- 证据：[Batch 05](../research/results/BATCH_05_EARNED_STAGE_VALIDATION.md)、[Protocol V3](../research/batches/batch_05/PROTOCOL_V3.md)。

## RL-039 Batch 05 principal architect review

- 状态：CLOSED。独立复核 Batch 05 冻结证据、Windows 开发引导与权威文档后，选定唯一下一 Goal 为 `S4C_AUTHORITATIVE_EXECUTION_REVIEW`；`AWAIT_BATCH_05_ARCHITECT_REVIEW` 前沿关闭。
- 范围：S2 / S27A / S10A / S4C 阶段处置、开发解释器固定与归属正确的文档同步。不重跑、不修改冻结结果、不创建候选、不运行 S4C RQAlpha。
- 结论：S2 保持 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE` 且仍是唯一前瞻候选；S27A 保留 candidate-freeze review 资格但推迟（与 S2 趋势信号机制重叠度高）；S10A 维持 `DO_NOT_ADVANCE_S10A_EXECUTION`，不得以本地现金/retry/sizing 修补；S4C 获得 execution review 并被选为下一 Goal，集中度作为执行审查诊断证据保留。Windows 开发引导为 resolver/toolchain skew 而非项目 typing 缺陷，处置为固定 Python 3.11 开发解释器并记录于 README。
- 证据：[Batch 05 principal architect review](../research/results/BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md)、[Batch 05](../research/results/BATCH_05_EARNED_STAGE_VALIDATION.md)。
- 重开条件：仅当 Batch 05 冻结证据出现矛盾、S2 候选完整性失败、canonical 数据契约或框架语义变化时才可重开；不得以历史收益、参数偏好或“换名重做”重开。

## RL-040 S4C authoritative RQAlpha execution review

- 状态：CLOSED。Protocol V2 下对 committed 161 个 S4C 冻结目标执行一次 RQAlpha 6.3.0 原生 target-only 回放，全部预注册 gate 通过。
- 范围：冻结 60-return center、既有 S4C 经济语义与 PIT 契约。不重跑 40/80、不添加集中度 cap、不在 RQAlpha 内重算信号/波动/ERC 权重。
- 结论：`ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW`。RQAlpha CAGR 12.0929%、signed MaxDD -18.3512%、Sharpe 0.7758、cash rejection 0、平均 execution-date total absolute weight deviation 0.3246%、material dates 3/161（1.86%：两个 >5pp 单资产差异都有具体 native 原因，第三个是最大单资产偏差 3.84pp、现金残差 3.80% 的组合层偏离，不产生 5pp 条目）、平均现金 0.1399%。V1 的 `1e-12` reproduction 判据不可跨平台达成，作为 INVALID_RUN R1 保留并由 Protocol V2 的数值 portability 容差替代；该项替代不放松任何 native gate。集中度（P95 max weight 51.84%、maximum 66.35%）仍是未消除的风险特征。本条目只授予 candidate-freeze review 资格，不授权启动该阶段。
- 证据：[S4C execution review V2](../research/results/S4C_RQALPHA_EXECUTION_REVIEW_V2.md)、[Protocol V2](../research/batches/s4c_execution_review/PROTOCOL_V2.md)、[INVALID_RUN R1](../research/results/INVALID_RUN_S4C_EXECUTION_R1.md)。
- 重开条件：仅在 canonical 数据契约、S4C 经济语义或 RQAlpha 订单/撮合/账户语义变化，或出现具体矛盾证据时；不得以集中度、历史收益或参数偏好为由改参数、加 cap 或重跑窗口。

## RL-041 研究优先级决策（Batch 05 之后的首个独立选择）

- 状态：CLOSED。在候选实现之前完成一次独立 RESEARCH_PRIORITY_DECISION，比较 A（S4C candidate-freeze review）、B（S27A candidate-freeze review）、C（只保留 S2 前瞻影子并等待）、D（开启新的经济正交本地缺口），并把结果作为 Commit 先行提交。
- 范围：只做优先级裁决与 Goal 授权；不实现候选、不激活前瞻、不重跑历史、不修改任何冻结产物或 S2。
- 结论：选定 **A**，唯一主 Goal 为 `S4C_CANDIDATE_FREEZE_REVIEW`。判据与 `STRATEGY_RESEARCH_MAP` 的未来选择规则一致（相关性、证据质量、经济正交、低实现自由度、机制区分度），历史 CAGR 不参与排序。S4C 同时满足阶段已获得资格、实现自由度接近零、机制与 S2 不同；S27A 与 S2 共用趋势信号故继续推迟；C 不减少任何当前可减少的不确定性；D 需先过 External Evidence Gate 与 PIT Tradability Gate，成本与数据挖掘风险更高。它同时确认候选人名额是稀缺预算：是否占用取决于 S4C 冻结审查自身的终局裁决，而不是本次优先级决策。
- 证据：[research priority decision](../research/results/RESEARCH_PRIORITY_DECISION_V1.md)、[Goal](goal.md)。
- 重开条件：仅当 S4C 冻结审查终局裁决出现新矛盾证据、S2 候选完整性失败，或候选预算/前瞻注意力分配需要用户决策时；不得用历史收益或“换名重做”重开本次排序。

## RL-042 S4C 候选冻结审查与 S4C R1 身份

- 状态：CLOSED。对已通过 transfer、PIT correctness、bounded robustness 与 RQAlpha 6.3.0 原生执行的 S4C 经济身份做一次只读候选冻结审查，不作任何优化。
- 范围：只读核对冻结目标 SHA-256、结构与 PIT、canonical/config/策略 hash、框架版本与已接受机器产物的一致性。不重跑 40/80、VectorBT 历史或 RQAlpha 历史。
- 结论：`FREEZE_S4C_RESEARCH_CANDIDATE_R1`。存在唯一无歧义的权威证据链；经济身份全部维度可从源代码与冻结产物核对；canonical provenance 完整（截至 `2026-08-31`）；PIT inception 为 `2013-04-01`；upstream/execution 语义可固定（skfolio 1.0.6 / RQAlpha 6.3.0）；historical/prospective 边界可干净划定。集中度裁决为 `ACCEPT_AS_KNOWN_CANDIDATE_RISK`（P95 最大权重 51.84%、历史最大 66.35%、effective assets median 6.23 / P05 3.24），不得以 cap 消除或据此改参。同时明确 `material_asset_difference`（单资产 >5pp）与 `material_portfolio_tracking_date`（组合层总绝对偏差 >5pp）是两个不同的量，历史条件下后者多于前者，不得声称每个组合层跟踪日期都有已记录的原生单资产原因；历史结论与 V2 gate 不改写。
- 结论边界：S4C R1 为**已冻结研究候选**，`prospective_activation = NOT_ACTIVE`；前瞻影子激活是独立的下一项决策，本条目不授权。候选身份与预注册前瞻协议见 [S4C R1](../research/shadow/s4c_r1/README.md) 与 [manifest](../research/shadow/s4c_r1/candidate_manifest.json)，审查记录见 [S4C candidate-freeze review](../research/results/S4C_CANDIDATE_FREEZE_REVIEW_V1.md)。RL-001 到 RL-041 的内容未改写。
- 重开条件：仅在 canonical 数据契约、S4C 经济语义或 RQAlpha 订单/撮合/账户语义变化，或出现具体矛盾证据时；不得以集中度、历史收益、短期前瞻回撤或参数偏好为由改参数、加 cap 或重跑窗口。前瞻期出现连续亏损或跑输基准只能是 `STRATEGY_PERFORMANCE_WEAK`。

## RL-043 10% portfolio objective 可行性历史诊断

- 状态：CLOSED。
- 问题/范围：只使用**已经冻结**的 `S2_R1` 与 `S4C_R1` 目标，按其提交日并集上的粗粒度固定权重
  （100/0、75/25、50/50、25/75、0/100）构造**派生组合目标**，是否已经构成可信的无杠杆 ~10%
  历史路径。不重跑组件、不搜索权重、不加杠杆、不加集中度 cap、不创建候选。
- 外部映射：组合构造本身不是新策略族，不创建新 canonical mapping；S2 `E1_MATURE`、
  S4C `E2_ESTABLISHED_METHOD`、S30 `E1_MATURE` 均不变。
- 结论：`OBJECTIVE_FEASIBILITY_DECISION = FEASIBLE_WITH_EXISTING_COMPONENTS`。主窗口
  （2013-04-01 至 2026-08-31）内部固定 blend 最高 after-cost CAGR 为 10.4849%（25/75）；50/50 为
  9.2696%，且 signed MaxDD -15.9165% 优于任一单独 anchor。共同窗口（2014-01-15 起，含 S30）
  50/50 为 10.8404%、25/75 为 11.8127%，S30 为 9.9249%，预注册规则给出
  `COMPLEXITY_CLEARS_S30_HURDLE`。两个冻结机制的日收益相关性 0.7835、下行相关性 0.6541；
  所有 blend 的分期与 3Y/5Y 滚动 CAGR positive share 均为正（滚动占比 100%）。派生 blend 使用
  `DERIVED_UNION_TARGET_SUBMISSION`，**不**保持 S2 单独执行政策，也**不**等于 standalone `S2_R1`；
  两个 anchor 单独回放并作为各自候选的 correctness 参照。
- 结论边界：历史可行性不等于未来收益；不激活 `S4C_R1` 前瞻影子、不创建任何组合候选、不构成生产
  批准。当前最大缺口是**前瞻证据**，不是缺少 alpha 策略：S30 单独即达 9.92%，25% 权重的 S2 相对
  加权 anchor 只抬高约 0.11–0.18pp，其价值主要体现在回撤与机制分散。
- 证据：[可行性报告](../research/results/PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md)、
  [协议 V3](../research/batches/portfolio_objective_10p/PROTOCOL_V3.md)、
  `research/results/portfolio_objective_10p_*.csv`。
- 数据快照：canonical 同 RL-001；组件冻结目标 SHA-256 `9cc5a8e7…0b61`（S2）与
  `f7bf398d…7e47`（S4C）保持不变。
- 框架/版本：VectorBT 0.28.5 组合记录；skfolio 1.0.6 / RQAlpha 6.3.0 仅作为组件既有证据的版本。
- 重开条件：仅在 canonical 数据契约、组件经济语义或框架语义变化，或出现具体矛盾证据时；不得以
  历史收益、集中度或短期前瞻表现为由改参数、加 cap、搜索权重或重跑组件。
