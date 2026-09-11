# Batch 03 无效运行 R3

受影响 track：S10A robustness。R3 的 CSV 与 `REJECT_S10A_ROBUSTNESS` 结论不作为有效证据。

问题：目标波动率维度的相对表现与非退化规模门槛只计算了 8% 和 12% 两个变体，漏掉已冻结的 20 日 / 10% 中心点；协议要求在 8% / 10% / 12% 三个变体中至少 2/3 通过。

允许的变更：仅令该维度由 `vol_window == 20` 且 `target_volatility in (0.08, 0.10, 0.12)` 的三个已运行变体组成。参数、价格、比较器、指标、阈值及其他 track 均不变。

处理：Protocol V4 冻结后仅重跑 S10A robustness。该修正不预设结果或决策。
