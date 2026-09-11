# Batch 03 Protocol V3：S10A rolling 联合改善统计修正

R2 的无效原因见 [INVALID_RUN_BATCH_03_R2](../../results/INVALID_RUN_BATCH_03_R2.md)。唯一修正为将滚动门槛实现为协议原文所述的逐窗口 `(Sharpe 改善 OR MaxDD 改善)` 占比，而非对两个聚合比例运算。

S10A 的 10/20/40、8/10/12、20/10 baseline、fill_method=None、所有比较器、固定分期、3Y/5Y、成本和每个决策阈值均不变。S27A V2 与 S4C 协议均不变。本文件不含新的历史结果；Commit V3 后仅重跑 Track B。
