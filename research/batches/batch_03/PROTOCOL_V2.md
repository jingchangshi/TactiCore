# Batch 03 Protocol V2：S27A reproduction metric-start 修正

R1 的无效原因见 [INVALID_RUN_BATCH_03_R1](../../results/INVALID_RUN_BATCH_03_R1.md)。唯一修正是 VectorBT frozen-schedule reproduction 的计量起点由“首个 execution date 的前一日”改为 Batch 02 已冻结 S27A 基线使用的“首个 execution date”。

Track A 的冻结 schedule、策略和配置 hash、RQAlpha 运行起止日、原生 `order_target_portfolio` 回放、成本、滑点、cash/target/economic gates均不变。Track B、Track C、skfolio 依赖、全部参数邻域和比较器均不变。此文件不含新的历史或执行结果；Commit V2 后只重跑 Track A。
