# Goal: TactiCore — 10% Portfolio Objective Feasibility + Research Priority Decision

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Execution mode:

```text
Codex with ChatGPT / C2C
```

本 Goal 由用户授权，先回答一个组合层问题，再决定下一单位研究预算投向何处。
它不提出新策略族，不重开任何已关闭问题，也不修改任何冻结候选。

## 问题

```text
在当前已经获得的证据基础上，TactiCore 是否已经存在一条可信的、无杠杆的长期 10% portfolio path？
如果存在，接下来真正缺的是前瞻验证还是 portfolio construction？
如果不存在，缺的是哪一种经济暴露？
```

组合目标定义见 [`PORTFOLIO_OBJECTIVE.md`](PORTFOLIO_OBJECTIVE.md)；它是 portfolio-level objective，
不是收益保证、不是每年必须达到的门槛、不是参数优化目标、不是 candidate promotion hard gate。

## External Evidence Gate

本 Goal 只做**已冻结组件之间的固定权重组合**，不提案新策略族、signal、allocator 或 overlay，
因此不创建新的 canonical mapping。

| 项 | S2_R1 | S4C_R1 | S30（比较器） |
| --- | --- | --- | --- |
| Canonical mapping | time-series momentum / trend following | equal risk contribution / risk budgeting | 1/N 与 static diversified allocation |
| External tier | `E1_MATURE` | `E2_ESTABLISHED_METHOD` | `E1_MATURE` |
| External conclusion | 跨资产期货趋势证据成熟，域不等于长多 ETF | 成熟构造方法，不是 alpha 主张 | 强估计误差复杂度基准，不是 alpha 主张 |
| Relevant contradictions | 期货/多空/波动缩放域不匹配 | 协方差/相关估计、集中度、无杠杆 ETF 实现 | 权重依赖投资者目标 |
| Upstream implementation | VectorBT 原生组合记录 | 官方 skfolio `RiskBudgeting`；RQAlpha 6.3 原生执行 | VectorBT 原生组合记录 |
| Existing TactiCore evidence | RL-015 / RL-016 / RL-017 | RL-030 / RL-037 / RL-040 / RL-042 | RL-024 |
| Remaining local gap | 前瞻本地稳定性 | 前瞻影子未激活；集中度为已知候选风险 | 机制匹配的简单比较器 |
| Research action | `TRANSFER_VALIDATE`（本 Goal 不执行） | `UPSTREAM_COMPARE`（本 Goal 不执行） | `REFERENCE_ONLY` |

外部成熟证据不构成本地 PASS；本地 REJECT 也不否定 canonical literature。

## PIT Tradability Gate

沿用 RL-031 / RL-033 / RL-034 已关闭的 PIT contract，不重新审计：date-aware universe、
asset lifetime metadata、上市前 fallback 处理、execution price 缺失处理与 strategy inception
（`2013-04-01`）均已建立；正目标只在 execution timestamp 上标的 active 且 canonical 价格有限、
正值时合法。任何派生组合目标同样必须逐行通过该验证，否则不得进入 VectorBT。

## 冻结范围（禁止事项）

```text
不修改 S2_R1 或 S4C_R1 的 manifest、日程、语义、verifier
不重跑 S2 参数平台；不重跑 S4C 40/60/80
不新增 trend window / covariance estimator / risk measure / solver
不搜索或微调 strategy weight；只使用预注册的粗粒度固定权重
不添加杠杆；不添加 S4C concentration cap
不修改 fallback、universe、cost、执行时点或缺失值口径
不为达到 10% 开启新 strategy；不重开 REJECTED / CLOSED 策略
不建设通用 portfolio framework / optimizer / analytics platform
不创建 S31 / S32 / Portfolio_R1 / Blend_R1 等任何候选身份
不得把历史可行性称为 expected future return，也不得回填历史-前瞻边界
```

## 允许的终局裁决

```text
FEASIBLE_WITH_EXISTING_COMPONENTS
FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT
PLAUSIBLE_BUT_PROSPECTIVE_EVIDENCE_INSUFFICIENT
NOT_SUPPORTED_BY_EXISTING_COMPONENTS
BLOCKED_BY_CORRECTNESS
```

不使用含糊的 PASS。裁决规则在结果产生之前预注册于
[`research/batches/portfolio_objective_10p/PROTOCOL_V2.md`](../research/batches/portfolio_objective_10p/PROTOCOL_V2.md)。

## 提交顺序

```text
Commit A : 目标文档 + 预注册协议 + 实验实现 + 契约测试；不含任何 research/results 产物
Commit B : 显式运行产生的证据产物 + OBJECTIVE_FEASIBILITY_DECISION + 文档同步
Commit C : 独立 RESEARCH_PRIORITY_DECISION + 选定唯一下一 Goal 的授权
```

## 边界

本 Goal 只回答可行性并选择下一项研究；它**不**产生生产配置、**不**激活 S4C R1 前瞻影子、
**不**创建候选、**不**自动启动所选下一 Goal。生产/真实持仓需要前瞻证据与独立生产审查。

## Status: IN_PROGRESS

| 项 | 值 |
| --- | --- |
| Starting HEAD | `ea5dc86` |
| Commit A（初始） | `f04ae0c`（目标文档、协议、实现、测试；无结果产物） |
| Corrective pre-result commits | `86e711d`（裁决基础/窗口/顺序）、`516d6f7`（identity-based correctness gate、年度报告起点、S30 inception 契约） |
| 生效预注册协议 | [PROTOCOL_V3](../research/batches/portfolio_objective_10p/PROTOCOL_V3.md)（V1/V2 保留为历史记录） |
| 无效运行 | V1 阶段被提前执行产生的一次输出已判定为 `INVALID_FOR_RESEARCH_INTERPRETATION`，未提交并已移除 |
| 冻结候选状态 | S2 R1 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`；S4C R1 `FROZEN / NOT_ACTIVE`（均未改动） |
| 可行性裁决 | 尚未产生（Commit B） |
| 下一 Goal | 尚未选择（Commit C） |

前一个已完成 Goal（S4C candidate freeze review）的历史事实保留在
[`RESEARCH_LEDGER.md`](RESEARCH_LEDGER.md) RL-042、[`STRATEGY_CATALOG.md`](STRATEGY_CATALOG.md)
与 [`S4C candidate-freeze review`](../research/results/S4C_CANDIDATE_FREEZE_REVIEW_V1.md)；
本文件按 Goal 契约更新为当前执行指令。本 Goal 目前**没有**任何有效的组合层研究结果。
