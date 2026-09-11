# S4C canonical ERC / skfolio transfer V1

**Decision: `ADVANCE_S4C_ERC_TRANSFER_TO_ROBUSTNESS`。**

S4B 的 Riskfolio-Lib dependency block 保持原样。本轮没有替换、删除或改写 S4B；它只在新官方上游路径 `skfolio==1.0.6` 上进行新的、预注册的 S4C 问题。

## 上游与实现边界

官方 PyPI/文档显示 skfolio 1.0.6 支持 Python >=3.10。以完整项目依赖做的隔离 resolver dry-run 在 Python 3.10、3.11、3.12 均成功；项目因此将其作为 `research` extra 引入。每个风险月以官方 `RiskBudgeting(risk_measure=RiskMeasure.VARIANCE, min_weights=0.0, max_weights=1.0)` 拟合，使用默认等风险预算；没有本地 ERC solver。

风险 universe 与 S2 相同。仅在月末现价有效且至少有 61 条历史价格时进入共同 non-null 对齐窗口；窗口必须产生 60 条有效 `fill_method=None` 日收益。少于六个资产完全回退 511010；六个及以上时上游失败即 block，而不回退。每月目标在下一 canonical date 用 VectorBT、10/5 bps、月频执行。

## 结果

| 组合 | CAGR | MaxDD | Sharpe | Calmar | 换手 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ERC / skfolio | 10.9102% | -18.3512% | 1.0576 | 0.5945 | 11.7903 |
| 同 eligible 等权 | 9.9577% | -22.3301% | 0.8186 | 0.4459 | 2.3790 |
| 同 eligible inverse-vol | 10.8883% | -22.4776% | 0.9819 | 0.4844 | 10.0659 |

风险覆盖为 87.13%，超过 80% gate。相对 inverse-vol，ERC CAGR 高 0.0219pp、MaxDD 改善 4.1264pp、Sharpe 高 0.0758，且换手为其 1.171x（低于 1.5x）；绝对 CAGR、Sharpe 和回撤门槛也均通过。

集中度诊断：最大权重中位数 26.94%、P95 51.84%，9 个风险月任一资产超过 50%。这记录集中风险，并不触发本协议的拒绝门槛。

## 边界

结果只授予 S4C 进入下一阶段的 robustness review 资格，不是 candidate、前瞻或生产批准，也不证明 ERC 是 alpha。机器证据：[比较](s4c_erc_skfolio_comparison_v1.csv)、[覆盖与逐月诊断](s4c_erc_skfolio_diagnostics_v1.csv)、[集中度](s4c_erc_skfolio_concentration_v1.csv)。
