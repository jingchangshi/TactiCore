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
