# Batch 05 protocol V2 — INVALID_RUN correction

Protocol V1 的 S10 supplementary diagnostic 将 execution-date frozen schedule 直接索引到 signal-date diagnostics，导致 `KeyError`，结果文件未写出。本修订仅将每个 execution date 映射回其前一 canonical signal observation 后读取已冻结的 `scale`；不改变 targets、PIT inception、RQAlpha callback、comparators、gates、参数或决策集合。

因此 V1 的该次运行是 `INVALID_RUN`，S27/S10/S4C 尚无可采纳 Batch 05 result。V2 freeze 后按原有顺序完整 rerun。
