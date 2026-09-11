# Batch 03 Protocol V4：S10A target 维度成员修正

R3 的无效原因见 [INVALID_RUN_BATCH_03_R3](../../results/INVALID_RUN_BATCH_03_R3.md)。唯一修正为使 S10A 的 target-volatility 维度严格包含冻结的 20 日 / 8%、20 日 / 10% 和 20 日 / 12% 三个变体；相对表现及非退化规模门槛均按这三个成员判定至少 2/3。

S10A 的参数、`pct_change(fill_method=None)`、比较器、固定分期、滚动窗口、成本与所有数值阈值均不变。S27A V2、S10A V3 的 rolling 联合统计修正与 S4C 协议均不变。本文件不含新历史结果；Commit V4 后仅重跑 Track B。
