# S3B 行业趋势广度状态过滤基线 V1

## 1. Research Question

行业整体中期趋势广度能否在不选择赢家的前提下，改善广泛行业篮子的风险收益？

## 2. Why S3B Is Not S3A Tuning

S3A 选择 top-3 正动量行业而被拒绝；S3B 不排序、不选 winner，只把行业动量压缩为 aggregate breadth 并控制广泛篮子的风险开关。这是从负面证据产生的新 hypothesis，不是 S3A V2 或参数修补。

## 3. Prior Negative Evidence

S3A CAGR 5.81%、最大回撤 -52.43%、Sharpe 0.363，弱于行业等权的 8.40% / -34.59% / 0.513。

## 4. Predeclared Economic Hypothesis

当严格多数行业处于正中期趋势时，持有全部合格行业；多数恶化时持有国债 ETF，可能在保留 sector beta 的同时降低尾部风险。

## 5. Frozen Universe / Data Snapshot

复用 S3A 的 11 行业 ETF、511010.SS 防御资产和 2011-02-25 至 2026-08-31 的独立 canonical snapshot。价格、日历、provenance SHA-256 分别为 `337c28cc52c04f8b5257a8feffb7d1c508248cab10595466c8c69d758556a4a6`、`13f4240ee6531415e3ea7638d9691af01290e97da3607446246d3dc8f96e51e6`、`31a6b9870e485e317781f5cc05cccc87f1ac97af9cf0400592445e540fa40a0c`；universe SHA-256 为 `96dbfe463b09ec02bd63f1e8525827b0a64032f5dd71a71524b2b3655f4fc23d`。

## 6. Exact Breadth Definition

每个行业以 `current close / 120 valid observations ago close - 1` 分类。`breadth = positive / eligible`；不可用行业不进分母。

## 7. Availability Semantics

信号日缺价或没有足够有效历史即 `UNAVAILABLE`，不等于负动量；少于 8 个 eligible 时 regime 为 `UNAVAILABLE` 并 100% 防御。

## 8. Regime Definition

仅当至少 8 个行业 eligible 且 `breadth > 0.50` 时为 `RISK_ON`；恰好 50% 为 `RISK_OFF`。唯一配置为 120 observations、50% strict majority、8 个最低覆盖，不做搜索。

## 9. Portfolio Construction

RISK_ON 等权所有 eligible 行业；RISK_OFF/UNAVAILABLE 全部持有 511010.SS。没有 top-k、排名或只持有正动量行业。

## 10. Execution Timing

月末收盘信号，下一 canonical observation 执行；`SIGNAL_CHANGE_ONLY`，相同 target 不机械重平衡。

## 11. Primary Comparator

`UNGATED_SECTOR_BASKET` 在相同 eligible set、相同 next-observation、成本、初始资金和 `SIGNAL_CHANGE_ONLY` 下始终等权所有 eligible 行业；它隔离 breadth gate 本身。

## 12. Contextual Benchmarks

510300.SS buy-and-hold 仅作背景比较；S3A 机械月度行业等权仅作先前历史背景。

## 13. Predeclared Advance Gate

覆盖 ≥80%；CAGR >0、Sharpe≥0.40、最大回撤>-40%、年化 target change≤10；相对 ungated 最大回撤至少改善 5pp、CAGR 不低于其 -2pp，且 Sharpe 或 Calmar 严格提高。RISK_OFF 至少 5%、RISK_ON 至少 20%。

## 14. Full-Sample Results

评价期 2018-08-01 至 2026-08-31。S3B CAGR 5.82%、最大回撤 -27.83%、Sharpe 0.462、Calmar 0.209、最差年度 -6.43%、turnover 12.29、84 条交易、平均持有 224.1 天、14 个 target-change 月（年化 1.73）。

## 15. Drawdown Comparison

相对 ungated 的 -36.35%，S3B 最大回撤改善 8.52pp，超过 5pp 门槛。

## 16. Risk-Adjusted Comparison

S3B CAGR 比 ungated 8.46% 低 2.64pp，超过允许的 2pp sacrifice；Sharpe 0.462 低于 0.514，Calmar 0.209 低于 0.233。因此 return preservation 与 risk-adjusted improvement 均失败。

## 17. Regime Occupancy

97 个评价月末：RISK_ON 50（51.55%）、RISK_OFF 47（48.45%）、UNAVAILABLE 0；regime 非退化。

## 18. Regime Transitions

12 次 transition；平均 RISK_ON duration 8.33 月，平均 RISK_OFF duration 6.71 月。

## 19. Turnover / Maintenance

年化 1.73 个 target-change 月，显著低于 10 的低维护门槛，但这不能抵消相对长期复利与风险调整回报不足。

## 20. Known Biases

当前 ETF universe 仍有 survivorship、fund-launch、tracking-difference、行业重叠和当前 universe selection bias。S3B hypothesis 在 S3A 失败与强行业等权 comparator 已被观察后形成，因此只是 **historical follow-up hypothesis screen**，不是 untouched OOS 或 prospective evidence。

## 21. Decision

**REJECT_S3B_BREADTH_BASELINE**。breadth gate 降低回撤但以超过预声明上限的 CAGR sacrifice 换取，且 Sharpe/Calmar 未改善；不进行 threshold、lookback 或其他参数救援。

## 22. What This Does NOT Prove

这不证明 sector breadth 在所有经济语义下无效，也不表示 S3B 已被 OOS 验证或可生产使用。

## 23. Next ONE Research Direction

停止 S3B；下一 Goal 应选择新的独立经济 hypothesis，不自动进入 Theme Rotation。
