# S27A RQAlpha 执行审查 V1

**Decision: `BLOCK_S27A_EXECUTION_ENVIRONMENT`。**

本审查只将 Batch 02 已冻结的 S27A 月频目标日程交给 RQAlpha 6.3.0 原生账户；没有在 RQAlpha 回调中计算趋势或 inverse-vol 信号，也没有创建候选、前瞻记录或替代 S2 R1。

## 冻结输入与 VectorBT 复现

`s27a_v1_frozen_targets.csv` 含 171 个严格递增、唯一的 execution dates，所有权重非负且逐行和为 1；SHA-256 为 `674d38e2c7226e10f478c3a436468b5cc683a7966b598372e3d396a1bb353455`。schedule 保留 S27A 的“每月提交目标”语义，不采用 S2 的 `SIGNAL_CHANGE_ONLY`。

R1 曾以首个执行日前一日开始计量，不能精确复现冻结 baseline，已按 [INVALID_RUN_BATCH_03_R1](INVALID_RUN_BATCH_03_R1.md) 与 Protocol V2 作废。V2 从首个 execution date 计量，逐项以 `< 1e-12` 通过重现：CAGR 7.7867%、MaxDD -12.5034%、Sharpe 1.015。

## RQAlpha 环境结果

通过原生 `order_target_portfolio` 和显式 `partial_fill_on_insufficient_cash=true` 启动后，RQAlpha bundle 在第一个 frozen date `2012-06-01` 即拒绝 `511010.XSHG`：`RQInvalidArgument: invalid order_book_id/instrument`。因此没有可靠的订单、成交、持仓、现金或 analyser 数据，不能伪造 target-tracking、现金拒绝、偏离、CAGR 或 MaxDD 指标。

这属于 frozen schedule 覆盖日期与本地 RQAlpha 数据 bundle 的环境可用性冲突，而非 VectorBT 复现、策略经济性或本地执行实现失败。协议规定此情形使用环境 block；未改变 target、跳过日期、用别的资产替代，或回退到本地会计/撮合。

## 结论与边界

`BLOCK_S27A_EXECUTION_ENVIRONMENT`。S27A 未获得 candidate-freeze review、前瞻或生产资格；S2 R1 不变。只有能覆盖该冻结 schedule 的 RQAlpha 原生环境，或有明确的新数据契约，才可在新 Goal 中有界重审。
