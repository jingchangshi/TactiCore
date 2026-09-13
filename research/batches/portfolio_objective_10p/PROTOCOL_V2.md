# Portfolio Objective 10P — 预注册协议 V2（取代 V1 的裁决与窗口口径）

本文件在**任何可用于研究解释的 blend 结果**产生之前提交，用于纠正 V1 的程序与语义缺陷。
[`PROTOCOL.md`](PROTOCOL.md)（V1）保留为历史记录，但下列条款由本文件取代。

## 0. V1 输出无效声明

```text
V1 阶段曾被执行顺序之外的一次运行产生的输出：INVALID_FOR_RESEARCH_INTERPRETATION
```

- 那些输出**没有**按 V1 自己规定的顺序产生（V1 要求 Commit A 不含任何 `research/results/` 产物），
  因此不构成预注册研究证据。
- 它们已从工作区移除，未提交，也不得被引用、解释或用于任何后续决策。
- 本纠正只基于程序与语义理由；本文件**不引用也不需要**那些输出的任何数值。

## 1. 对 V1 的取代条款

### 1.1 可行性裁决的基础（取代 V1 §11 的 `c_max` 口径）

裁决只依据**三个内部固定 blend**与**两个真实 standalone 候选 anchor**：

```text
c_div    = max CAGR over BLEND_S2_75_S4C_25 / BLEND_S2_50_S4C_50 / BLEND_S2_25_S4C_75
c_anchor = max CAGR over S2_R1_committed_anchor / S4C_R1_committed_anchor
```

```text
if 复现 gate 失败                     → BLOCKED_BY_CORRECTNESS
if c_div >= 10.0%                     → FEASIBLE_WITH_EXISTING_COMPONENTS
if c_anchor >= 10.0% > c_div          → FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT
if max(c_div, c_anchor) >= 9.5%       → PLAUSIBLE_BUT_PROSPECTIVE_EVIDENCE_INSUFFICIENT
otherwise                             → NOT_SUPPORTED_BY_EXISTING_COMPONENTS
```

派生端点 `BLEND_S2_100_S4C_00` 与 `BLEND_S2_00_S4C_100` 使用
`DERIVED_UNION_TARGET_SUBMISSION`，既不是 standalone 候选，也不是候选证据；它们只提供几何/上下文，
**永远不参与**可行性分类。

### 1.2 主窗口不含 S30（取代 V1 §7/§8 的实现口径）

```text
主窗口 summary          : 两个候选 anchor + 五个派生 blend（不含 S30）
共同窗口比较（含 S30）   : 全部序列在同一 2014-01-15 起点上的公平比较
```

S30 仍是只读复杂度门槛，不是第三个策略组件。

### 1.3 年度收益不得制造上市前年份（取代 V1 §9 的宽表做法）

年度收益按 `series, year, return` 长表报告，每个序列只在自己的可评价起始日之后报告年份；不得为
S30 或其他序列制造 inception 之前的比较年份。

### 1.4 复现 gate 的显式容差（补全 V1 §10）

复现回放的输入是**已提交的 8 位小数冻结目标**，而原始已提交指标由**内存全精度目标**计算，因此两者
必然存在定点舍入差。容差按该精度事先登记：

```text
非 turnover 指标容差 : 1e-4
累计 turnover 容差   : 1e-3
```

这是对齐冻结产物精度的数值口径，不是研究门槛，也不是结果驱动的放松。复现结果必须落盘为可审计的
逐指标偏差表。

### 1.5 复杂度 vs S30 只用内部 blend（补全 V1 §12）

`COMPLEXITY_*` 判定只使用三个内部固定 blend；派生的 100/0、0/100 端点被拒绝参与。

### 1.6 输出 schema（取代 V1 §13）

```text
research/results/portfolio_objective_10p_summary_v1.csv            主窗口（不含 S30）
research/results/portfolio_objective_10p_common_window_v1.csv     共同窗口（含 S30）
research/results/portfolio_objective_10p_diversification_v1.csv   分散度证据
research/results/portfolio_objective_10p_reproduction_v1.csv      复现 gate 偏差表
research/results/portfolio_objective_10p_periods_v1.csv
research/results/portfolio_objective_10p_rolling_v1.csv
research/results/portfolio_objective_10p_correlation_v1.csv
research/results/portfolio_objective_10p_annual_returns_v1.csv    长表
research/results/PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md
```

以上产物**只允许**在 Commit B 中由显式运行产生。

## 2. V1 中未被取代的条款

V1 的 §2（External Evidence Gate）、§3（PIT Tradability Gate）、§4（冻结输入）、§5（组合定义与
`DERIVED_UNION_TARGET_SUBMISSION` 语义声明）、§6（固定权重集合）、§9（指标口径）、§14（禁止事项）
继续有效。特别是以下四条仍然强制：

```text
不得把内部 blend 说成"S2_R1 与 S4C_R1 在同一账户中原样运行"
不得声称 blend 保持了 S2 单独运行时的执行政策行为
不得把派生的 100/0 端点当作 standalone S2_R1，或据此声明复现
组件 anchor 必须单独回放，作为各自候选的正确性参照
```

## 3. Commit 顺序（补全 V1 §14）

```text
Commit A : 目标文档 + 协议（V2）+ 实现 + 测试；不产生任何 research/results 产物
Commit B : 显式运行产生的产物 + OBJECTIVE_FEASIBILITY_DECISION + 文档同步
```

在 Commit A 被独立复核接受之前，不得运行研究实验，也不得生成任何 `research/results/` 产物。
