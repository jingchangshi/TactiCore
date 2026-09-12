# S27A PIT correctness revalidation V1

Batch 03 的 RQAlpha block 被 supersede：10 个 2012-06-01 至 2013-03-01 的月频正 fallback target 指向尚未上市的 511010.SS，并非可归因于 bundle 不完整。PIT contract 规定这些月份没有完整可执行 target，因而不作为策略历史或以现金/替代债券重写。

修正 inception 由 contract 自动得到为 2013-04-01。保持 200 trend、60 vol、月频目标、10/5 bps 后，VectorBT CAGR 8.3014%、MaxDD -12.5034%、Sharpe 1.048、Calmar 0.664。原 Batch 02 的预注册邻域/分期/rolling/成本证据仍适用于 inception 后共同样本，且修正 baseline 为正；决策为 `RESTORE_S27A_EXECUTION_REVIEW_ELIGIBILITY`。

本批不重跑 RQAlpha、不创建候选或前瞻记录。历史 [Batch 03 execution review](S27A_RQALPHA_EXECUTION_REVIEW_V1.md) 保留为发现 PIT defect 的有效证据，但其环境归因不再是当前结论。
