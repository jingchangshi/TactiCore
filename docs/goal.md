# Goal: TactiCore — S4C Candidate Freeze Review

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Execution mode:

```text
Codex with ChatGPT / C2C
```

本 Goal 由独立研究优先级决策授权，问题只有一个：**已经通过 transfer、PIT correctness、bounded robustness 与 RQAlpha 6.3.0 原生执行审查的 S4C 经济身份，是否应冻结为研究候选 `S4C_R1`？**

优先级决策见 [`research/results/RESEARCH_PRIORITY_DECISION_V1.md`](../research/results/RESEARCH_PRIORITY_DECISION_V1.md)；它在任何候选实现之前已提交。本 Goal 不重开该决策，也不自动执行第二顺位选项。

## External Evidence Gate

| 项 | 值 |
| --- | --- |
| Canonical mapping | `ERC_RISK_PARITY` — equal risk contribution / risk budgeting |
| External tier | `E2_ESTABLISHED_METHOD` |
| External conclusion | 成熟构造方法，不是 alpha 主张 |
| Relevant contradictions | 协方差/相关性估计、无约束下的集中度、无杠杆 ETF 域实现 |
| Upstream implementation | 官方 skfolio `RiskBudgeting`；S4B 的 Riskfolio-Lib dependency block 保持历史事实 |
| Existing TactiCore evidence | S4C transfer PASS → PIT correctness restored → 40/60/80 bounded robustness PASS → RQAlpha 6.3.0 authoritative execution PASS |
| Remaining local gap | 该历史身份是否完备、可复现、可追溯、可执行且具备前瞻协议准备度 |
| Research action | `UPSTREAM_COMPARE` 已通过执行阶段完成；当前动作只是候选身份/冻结裁决 |

## PIT Tradability Gate

沿用 RL-031 / RL-033 已关闭的 PIT contract：date-aware universe、asset lifetime metadata、上市前 fallback 处理、execution price 缺失处理与 strategy inception（`2013-04-01`）均已建立；正目标只在 execution timestamp 上标的 active 且 canonical 价格有限、正值时合法。本 Goal 不重新审计该契约，只验证它仍支撑冻结身份。

## 冻结范围（禁止事项）

```text
不新增 return window
不重跑 40 / 80
不新增 covariance estimator
不搜索 risk measure
不搜索 solver
不优化 weight cap 或集中度 cap
不改 fallback
不优化 asset universe
不调 cost
不按表现选择参数
```

审查的对象是**实际获得资格的 S4C**，不是可以被改进的 S4C。

## 允许的终局裁决

```text
FREEZE_S4C_RESEARCH_CANDIDATE_R1
DEFER
REJECT
BLOCK
```

不使用含糊的 PASS。

## 边界

只有当审查独立得出 `FREEZE_S4C_RESEARCH_CANDIDATE_R1` 时，才创建最小候选身份（`research/shadow/s4c_r1/`）并预注册前瞻协议；不得建设通用 candidate framework、scheduler、daemon、数据库或注册服务。

无论裁决如何：不得改写 S2 R1 及其冻结输入、不得改写 Batch 05 冻结产物或 `INVALID_RUN`、不得用历史结果制造前瞻证据、不得继续第二顺位研究方向。

## Status: completed

| 项 | 值 |
| --- | --- |
| Starting HEAD | `1b74b8e` |
| 优先级决策 commit | `7cef1bc`（先于任何候选实现） |
| 终局裁决 | `FREEZE_S4C_RESEARCH_CANDIDATE_R1` |
| 集中度处置 | `ACCEPT_AS_KNOWN_CANDIDATE_RISK` |
| 候选身份 | [research/shadow/s4c_r1/](../research/shadow/s4c_r1/README.md)（`prospective_activation = NOT_ACTIVE`） |
| 审查记录 | [S4C candidate-freeze review V1](../research/results/S4C_CANDIDATE_FREEZE_REVIEW_V1.md) |
| 前瞻观测数 | 0（`observations.csv` 只有表头） |

本 Goal 已由 C2C 协议执行完成并记录。它只冻结候选身份与预注册前瞻协议，**不激活**前瞻影子、不采集 observation、不创建 vintage。

## Status: AWAIT_NEXT_ARCHITECT_RESEARCH_DECISION

下一个可能的 Goal 是独立的前瞻影子激活决策，或由下一次 research-priority 决策另行授权；本 Goal 不自动启动它，也不启动第二顺位研究方向。
