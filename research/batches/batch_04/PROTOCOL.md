# Batch 04 Protocol：PIT tradability 与 signed MaxDD correctness closure

本协议冻结：正执行目标必须在 execution date 同时 active 与有有限正价格；缺 fallback 代表无可执行完整目标；策略 inception 是首个完整可执行目标。MaxDD 以负数保存，no-worse 使用 `candidate >= comparator`。

影响范围仅为 S2、S27A、S10A、S4C、S30、S4A、S8A 与 S3 family audit。只允许调整合法执行起点、过滤 inception 前无完整目标、使用统一 drawdown helper；不得调整参数、成本、比较器、资产池或 fallback。S2 若有正目标 violation 则整批停止；S27/S10/S4C 依既有 gates 作 bounded replay，且本批不运行 RQAlpha、S4C robustness 或新策略。
