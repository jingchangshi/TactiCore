# S3C 行业固定 Sleeve 趋势过滤基线 V1

## Research Question / Hypothesis Provenance

S3C 在 S3A winner picking 失败、S3B global breadth 降低回撤却牺牲过多复利后提出：逐行业绝对趋势是否能在保留广泛参与的同时提升同机制固定 sleeve 篮子的风险调整收益？这是 historical follow-up hypothesis screen，不是 OOS 或 prospective confirmation。

## Frozen Universe and Data

复用 11 个冻结行业 ETF、511010.SS fallback 及 S3A/S3B 同一 2011-02-25 至 2026-08-31 canonical snapshot。价格/日历/provenance/universe SHA-256：`337c28cc52c04f8b5257a8feffb7d1c508248cab10595466c8c69d758556a4a6` / `13f4240ee6531415e3ea7638d9691af01290e97da3607446246d3dc8f96e51e6` / `31a6b9870e485e317781f5cc05cccc87f1ac97af9cf0400592445e540fa40a0c` / `96dbfe463b09ec02bd63f1e8525827b0a64032f5dd71a71524b2b3655f4fc23d`。

## Exact Semantics

每个行业用 `current close / 120 valid observations ago close - 1`。正值持有固定 `1/11` sleeve；负值或不可用将自己的 sleeve 转给 fallback。没有 ranking、top-k、breadth 或全局 risk switch。月末信号、下一观测日执行、`SIGNAL_CHANGE_ONLY`。

## Primary Comparator and Gate

`UNGATED_FIXED_SLEEVE_BASKET` 对每个 AVAILABLE 行业永久给 1/11，否则给 fallback，保留相同数据、时点、成本和提交政策。预声明门槛：CAGR>0、Sharpe≥0.45、最大回撤>-35%、年化 target changes≤10；回撤改善≥5pp、CAGR sacrifice≤1.5pp、Sharpe 与 Calmar 均严格提高，平均风险资产权重在 30%–95%。

## Results

评价期 2018-08-01 至 2026-08-31。S3C：CAGR 4.89%、最大回撤 -26.05%、Sharpe 0.470、Calmar 0.188、最差年度 -7.43%、turnover 14.00、277 条交易、平均持有 250.1 天、72 个 target-change 月（年化 8.91）。平均风险资产 49.77%，平均 fallback 50.23%，最低 0%、最高 100%。

Primary comparator：CAGR 7.40%、最大回撤 -36.35%、Sharpe 0.491、Calmar 0.203。S3C 回撤改善 10.30pp，但 CAGR sacrifice 2.51pp，Sharpe 低 0.021、Calmar 低 0.016。510300 背景指标为 CAGR 5.61%、最大回撤 -42.16%、Sharpe 0.387、Calmar 0.133。

## Sector Diagnostics / Maintenance

逐月状态与逐行业 POSITIVE/NEGATIVE_SIGNAL/UNAVAILABLE 见 [states CSV](s3c_sector_sleeve_states_v1.csv)。固定 sleeve 使风险暴露能在 0/11 至 11/11 间渐变；但 target change 年化 8.91，低维护门槛虽通过，未能补偿相对收益与风险调整效率失败。

## Biases, Decision and Next Direction

存在 same-sample reuse、hypothesis-generation、current-universe、survivorship、fund-launch 和 ETF tracking bias。**REJECT_S3C_BASELINE**：不满足 return preservation、Sharpe improvement 与 Calmar improvement。它不证明所有 sector trend filter 无效，不授权生产，也不应以 100/140 日、partial sleeve 或其他参数救援。下一方向应暂停继续改造 sector-momentum family，选择真正不同的经济 hypothesis；Theme Rotation 仍未启动。
