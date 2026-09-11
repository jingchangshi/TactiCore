# Batch 03 无效运行 R2

受影响 track：S10A robustness。R2 在完成内部历史计算后、写 CSV 或输出决策前抛出异常，因此没有有效结果或决策产物。

问题：rolling gate 错将两个浮点占比进行位或运算。协议要求的是逐个滚动窗口判断“Sharpe 改善 **或** MaxDD 改善”，再计算该联合条件的占比。

允许的变更：只增加 `either_improves_share`，其定义为同一滚动窗口的 `(candidate Sharpe > comparator Sharpe) OR (candidate MaxDD > comparator MaxDD)`，并用它执行已冻结的 60% 门槛。不得改参数、比较器、窗口、成本或任一门槛。

处理：Protocol V3 冻结后只重跑 S10A robustness。S27A 的环境 block 与 S4C 不受影响。
