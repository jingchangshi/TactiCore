# 组合投资目标（Portfolio Objective）

本文件只记录 TactiCore 的**长期投资目标与边界**，不记录任何实验数字、收益率、回撤或候选状态。
它不是治理框架，不创建 gate，也不改变 [`RESEARCH_RULES.md`](RESEARCH_RULES.md) 的永久方法。

## 1. 目标

```text
Long-horizon nominal CAGR target: 约 10% / 年
Currency:                        以当前 TactiCore ETF 投资组合的真实计价口径为准（CNY）
Costs:                           after modeled transaction costs
Leverage:                        none
Frequency:                       low frequency
Evaluation:                      multi-year，不是自然年保证
```

该目标作用于**组合层**，不作用于任何单个策略，也不是任何候选的 promotion gate。

## 2. 它意味着什么

- 它是一个**长期、多年度**的量级目标，允许年度之间大幅波动。
- 它是 after modeled cost、无杠杆、低频的现有多资产 ETF 域目标。
- 它要求组合在经济上可解释、可执行、低维护。
- 它把"简单 beta / 静态分散已经接近该量级"当作**复杂度门槛**，而不是当作需要被击败的基准。

## 3. 它不意味着什么

```text
10% target != 10% forecast
10% target != 10% guarantee
10% target != strategy gate
```

- 不是每年必须达到 10%，也不是"未达 10% 即失败"的单次回测判据。
- 不是参数优化目标；不得为了接近它而搜索权重、窗口、风险度量或资产池。
- 不是"必须增加 alpha"的理由：如果长期多资产 beta / 静态配置已经接近该量级，战术机制的任务应转向
  改善回撤、regime 稳健性、执行与分散度。
- 不是任何已冻结候选（例如 `S2_R1`、`S4C_R1`）可以据以修改、加 cap 或重跑的理由。

## 4. 目标层级

Portfolio objective 不只包含 CAGR。冲突时以较低编号的层级优先：

```text
Level 1: Capital survival / correctness
Level 2: Acceptable drawdown and execution
Level 3: Robust long-term compounding
Level 4: Target ~10% CAGR
Level 5: Operational simplicity / maintenance
```

不得为了 Level 4 牺牲 Level 1 或接受不可理解的风险。

## 5. 风险包络

本文件**不**声明永久 MaxDD 阈值。任何 `MaxDD < x%` 之类的永久规则必须在有充分证据后写入
[`RESEARCH_RULES.md`](RESEARCH_RULES.md)，且必须由独立研究支持。

当前只允许给出**建议性**风险包络：即"在长期约 10% 量级目标下，历史证据显示的回撤 / Sharpe /
Calmar / worst year / turnover / 集中度取舍"。建议性包络记录在 `research/results/` 的历史诊断中，
不是永久规则，也不是候选 gate。
