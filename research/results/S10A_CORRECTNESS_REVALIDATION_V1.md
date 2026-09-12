# S10A correctness revalidation V1

S10A 有两项独立 correction：十个 pre-listing fallback 月没有完整可执行 target；固定分期 MaxDD 的负数语义应为 `candidate >= comparator`。中心 20/10 的 corrected inception 为 2013-04-01，CAGR 8.8540%、MaxDD -10.5628%、Sharpe 1.158、Calmar 0.838。

Batch 03 原 `REJECT_S10A_ROBUSTNESS` 的唯一拒绝理由是将负 MaxDD 用 `<=` 比较；该历史 decision 标记为 `SUPERSEDED_BY_CORRECTNESS_REVIEW`，R2/R3 与 Protocol V2/V3/V4 仍保留。统一 helper 下，-10% 相对 -13% 为 no-worse；冻结的中心、窗口、target、static comparator、成本与 rolling 语义不变，决策为 `RESTORE_S10A_EXECUTION_REVIEW_ELIGIBILITY`。

本批没有运行 S10 RQAlpha、选择参数或创建候选。
