# 策略目录

## S1 Global Dual Momentum

状态：已实现最小 baseline，尚无真实历史研究结论。

- 信号频率：每日价格可更新；每月最后观测日计算。
- 执行频率：下一交易日调仓。
- 绝对动量：252 个交易日收益率大于 0。
- 相对动量：合格风险资产按同一收益率降序排名。
- 组合：等权持有前 2 名。
- 防御：没有合格风险资产时持有 `511010.SS` 国债 ETF 研究代理。
- 成本假设：每笔订单 10 bps fee、5 bps slippage（VectorBT baseline）。
- 目标：验证低频多资产相对/绝对动量是否在真实成本与市场语义下稳健。

配置来源是 `config/strategy.toml`，并非散落在 adapter 中。当前研究待补齐真实复权价格、参数平台、walk-forward、样本外、最差年度、状态稳定性和成本敏感性，才能评价经济价值。

## S2 Multi-Asset Trend Following

状态：未实现。本轮明确禁止提前建设。

## S3 China Sector / Theme Rotation

状态：未实现。本轮明确禁止提前建设。
