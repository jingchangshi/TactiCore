# Batch 03 无效运行 R1

受影响 track：S27A RQAlpha execution review；首次运行只输出 `BLOCK_S27A_EXECUTION_REPRODUCTION`，未产生可解释的 RQAlpha 经济结论。

问题：冻结表交回 VectorBT 时，runner 使用首个执行日前一交易日为 `metric_start`；Batch 02 的 S27A 200/60 权威基线则从首个 execution date 计量。相同 target schedule 因指标起点不同而无法满足严格 reproduction gate。

允许的变更：仅将 VectorBT reproduction 的 `metric_start` 修正为冻结 schedule 的首个 execution date，并新增回归测试。不得改变 S27 参数、target schedule、RQAlpha 回放、费用、滑点、比较器或任何决策门槛。

处理：建立并冻结 Batch 03 Protocol V2 后，重新运行受影响的 Track A。S10A 与 S4C 未运行，故不受影响。
