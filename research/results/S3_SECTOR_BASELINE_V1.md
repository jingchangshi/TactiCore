# S3A 中国行业轮动透明基线 V1

## 1. Research Question

一个由真实可交易 A 股行业 ETF 构成、月频运行的简单价格动量轮动，是否有足够的历史经济证据进入稳健性研究？

## 2. Predeclared Hypothesis

> A 股行业收益存在数月尺度的相对趋势持续性。使用中期价格动量选择领先行业，同时过滤负绝对动量，并以月频、有限持仓和防御资产承接未使用风险预算，可能形成比静态行业暴露更好的风险调整后收益，同时保持较低交易频率。

这是待检验假设，不是预先结论。

## 3. Universe Selection Rule

只选当前可交易、境内 long-only、主要跟踪明确 A 股行业指数的 ETF；排除宽基、海外、商品、债券、货币、杠杆/反向、Smart Beta 与主题产品。每个 broad sector 至多一个代表；满足 metadata 条件的候选以最早上市日优先，再以代码升序打破平局。**Universe 构建未使用任何历史收益、CAGR、Sharpe 或回测表现。**

## 4. Final Frozen Universe

11 个行业 ETF：消费、医药、证券、军工、银行、有色、房地产、传媒、钢铁、煤炭、电子；防御资产为 `511010.SS`，不计为行业。完整代码、名称、上市日和选择理由见 [universe CSV](s3_sector_universe_v1.csv)。不包含 Theme ETF。

## 5. Data Provenance

独立 Tushare Pro canonical 快照位于 `data/canonical/s3_sector_rotation_v1/`，请求区间 2011-01-01 至 2026-08-31，实际价格区间为 2011-02-25 至 2026-08-31。后复权口径为 `fund_daily.close × fund_adj.adj_factor`。价格、日历、provenance 的 SHA-256 分别为 `337c28cc52c04f8b5257a8feffb7d1c508248cab10595466c8c69d758556a4a6`、`13f4240ee6531415e3ea7638d9691af01290e97da3607446246d3dc8f96e51e6`、`31a6b9870e485e317781f5cc05cccc87f1ac97af9cf0400592445e540fa40a0c`。S3 config/universe hash 为 `922f38f79abb0db2943f9ee442fcf872b65693df52ca6fcb800de228970ff2e3` / `96dbfe463b09ec02bd63f1e8525827b0a64032f5dd71a71524b2b3655f4fc23d`。

## 6. Missing / Availability Semantics

每个 ETF 独立使用有效价格；信号日没有真实价格或不足 120 个滞后有效观测时为 `UNAVAILABLE`，不参与排名且不以零替代。负动量是独立的 `NEGATIVE_SIGNAL`，同样不参与 ranking。

## 7. Exact Signal Definition

月末 canonical observation 的动量为 `current adjusted close / 120 个有效观测前 adjusted close - 1`。只有 `momentum > 0` 的可用行业按 momentum 降序、symbol 升序平局规则排序。

## 8. Portfolio Construction

固定 `top_k=3`，每只选中行业固定 1/3；不足三只的 sleeve 留给 `511010.SS`。配置为月频、`SIGNAL_CHANGE_ONLY`、10 bps fee、5 bps slippage 和 100 万初始资金。

## 9. Execution Timing

月末收盘产生信号，最早在下一 canonical observation day 交给 VectorBT；相同 target 不产生机械月度重平衡。

## 10. Benchmarks

`510300.SS` buy-and-hold 检验选择复杂度是否值得；availability-aware 行业等权篮子检验轮动是否优于 universe beta。两者使用同一成本、初始资金和 evaluation range。

## 11. Predeclared Advance Gate

须同时满足：至少 8 行业，至少 80% 评价月末有 8 个 data-eligible 行业；after-cost CAGR > 0、Sharpe ≥ 0.40、最大回撤优于 -40%、年化 target-change 月份 ≤ 10；相对行业等权在 CAGR/最大回撤/Sharpe/Calmar 至少两项更优，且非通过明显恶化其他风险指标获得。

## 12. Full-Sample Metrics

评价期为 2018-08-01 至 2026-08-31。S3A V1：CAGR 5.81%，最大回撤 -52.43%，Sharpe 0.363，Calmar 0.111，最差年度 -14.30%，turnover 28.00，155 条交易，平均持有 119.9 天，66 个 target-change 月（年化 8.17）。

## 13. Benchmark Comparison

| 系列 | CAGR | 最大回撤 | Sharpe | Calmar |
| --- | ---: | ---: | ---: | ---: |
| S3A V1 | 5.81% | -52.43% | 0.363 | 0.111 |
| 行业等权 | 8.40% | -34.59% | 0.513 | 0.243 |
| 510300 | 5.61% | -42.16% | 0.387 | 0.133 |

完整可复现数据见 [comparison CSV](s3_sector_benchmark_comparison_v1.csv)。S3A 没有达到绝对风险门槛，且四项比较均不优于行业等权。

## 14. Coverage Evidence

evaluation start 由首个已完成 warm-up 且至少 8 个 data-eligible 行业的月末决定，非事后选择。97 个评价月末中覆盖均值 10.25、最小 8、最大 11；100% 月末达到 8 个。2018–2021 早期平均 breadth 9.22，2022 以后为 11.00。

## 15. Turnover / Maintenance Evidence

年化 target-change 月份为 8.17，满足 ≤10 的低触达门槛；但行业等权有更高的月度重平衡次数，不能挽回 S3A 的风险收益不足。

## 16. Sector Selection Diagnostics

最常入选为银行 35 月、煤炭 34 月、有色 33 月；随后传媒 25、医药 23、证券/电子各 22。97 个目标月中 65 个发生 target change。fallback 在 21 月使用，平均权重 11.00%、最高 100%。诊断表明选择不是单一行业独占，但不改变经济筛选失败。

## 17. Known Biases / Limitations

当前 universe 可能含 survivorship bias、fund-launch bias、有限历史 breadth、ETF tracking differences、行业重叠及 current-universe selection bias；V1 不建设 PIT universe engine。未检验容量、税务、生产可交易性、参数稳定性、市场状态、成本敏感性或真正样本外。

## 18. Decision

**REJECT_S3A_BASELINE**。预声明的 S3A V1 假设未通过经济筛选：最大回撤低于 -40%，Sharpe 低于 0.40，且未显示相对行业等权的轮动价值。没有执行参数搜索、RQAlpha 验证或语义微调来挽救结果。

## 19. What This Does NOT Prove

这不证明“行业轮动无效”；它只说明这个预声明的、透明的 S3A V1 基线未通过。也不授权生产使用。

## 20. Next ONE Research Direction

停止 S3A V1，不做参数微调。下一方向应是新的、独立预声明的经济 hypothesis，而不是修改本基线。
