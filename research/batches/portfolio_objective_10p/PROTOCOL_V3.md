# Portfolio Objective 10P — 预注册协议 V3（最终 pre-result 修正）

本文件在**任何可用于研究解释的 blend 结果**产生之前提交，修正 V2 的 correctness gate 依据、年度
报告起点与 S30 共同窗口 inception 契约。[`PROTOCOL.md`](PROTOCOL.md)（V1）与
[`PROTOCOL_V2.md`](PROTOCOL_V2.md)（V2）保留为历史记录；下列条款取代它们的对应部分。

## 0. 状态

```text
V1 阶段被提前执行的运行输出 : INVALID_FOR_RESEARCH_INTERPRETATION（已移除，不得引用）
V1 / V2 文档               : 历史记录保留
V3                         : 当前生效的 correctness 与报告口径
```

V1 的输出没有按 V1 自己规定的顺序产生，因此不构成预注册研究证据；它们未提交、已从工作区移除，
不得被引用、恢复或解释。本文件不引用也不需要它们的任何数值，也不需要**事后**观察到的偏差来决定
任何容差。

## 1. 取代 V2 §1.4：correctness gate 不再使用结果驱动的性能容差

### 1.1 S2_R1_committed_anchor — 身份式 gate

S2 anchor 的正确性**不**建立在与旧全精度历史运行的指标容差上，而是建立在冻结身份与回放输入本身：

```text
冻结目标 SHA-256 == 已登记 9cc5a8e7…0b61
行数 == 103
执行日唯一且严格递增
逐行合计在已登记序列化容差 |sum - 1| <= 1e-7 内
逐行 PIT 合法（validate_execution_targets）
回放输入逐值等于冻结目标 artifact（回放不得重算信号或改写目标）
严格 S2_R1 verifier（manifest / 冻结输入 hash / 前瞻边界）通过

另附：与 s2_parameter_plateau_summary.csv 的 trend_window=200 行做**描述性**对比，
      只报告偏差，不参与 correctness 判定。
```

### 1.2 S4C_R1_committed_anchor — 复用既有 portability 规则

S4C anchor 的指标复现沿用**本 Goal 之前就已存在**的规则，见
[`research/batches/s4c_execution_review/PROTOCOL_V2.md`](../s4c_execution_review/PROTOCOL_V2.md)：

```text
abs(current - baseline) <= max(1e-4, 1e-4 * abs(baseline))
```

该规则早于本 Goal 存在、由 RL-040 / `INVALID_RUN_S4C_EXECUTION_R1` 独立论证（`1e-12` 逐位判据
不可跨平台达成），因此不属于本 Goal 的结果驱动调整。identity 检查（SHA-256、161 行、日期、行合计、
PIT、回放输入等于冻结 artifact）同样必须通过。

### 1.3 不得出现的内容

源码、注释、协议与产物中不得出现"观察到某偏差所以放宽容差"一类的表述；correctness 依据只能是
冻结身份、PIT 与既有的、先于本 Goal 的 portability 规则。

## 2. 取代 V2 §1.3：年度收益按各自注册起点

年度收益为长表 `series, year, return`：

```text
S2_R1_committed_anchor / S4C_R1_committed_anchor / 五个派生 blend : 起点 2013-04-01
S30_REFERENCE                                                   : 起点 = S30 自身 inception
```

不得为任何序列制造 inception 之前的年份，也不得丢弃 S2/S4C/blend 在 2013 年的合法观测。

## 3. 补全 V2 §1.2：S30 共同窗口 inception 契约

```text
S30_COMMON_WINDOW_START = 2014-01-15
```

该日期由冻结 S30 规则（513500.SS 的上市日决定四资产共同可用起点）导出，并在运行时**断言**；
若实际 inception 不等于该值，运行必须失败，而不是静默使用一个未登记的日期。

## 4. 取代 V2 §1.6：输出 schema

```text
research/results/portfolio_objective_10p_summary_v1.csv            主窗口（不含 S30）
research/results/portfolio_objective_10p_common_window_v1.csv     共同窗口（含 S30）
research/results/portfolio_objective_10p_diversification_v1.csv   分散度证据
research/results/portfolio_objective_10p_correctness_v1.csv       identity / portability 证据
research/results/portfolio_objective_10p_periods_v1.csv
research/results/portfolio_objective_10p_rolling_v1.csv
research/results/portfolio_objective_10p_correlation_v1.csv
research/results/portfolio_objective_10p_annual_returns_v1.csv    长表
research/results/PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md
```

以上产物只在 Commit B 中由显式运行产生。

## 5. 继续有效的条款

V1 §2（External Evidence Gate）、§3（PIT Tradability Gate）、§4（冻结输入）、§5（组合定义与
`DERIVED_UNION_TARGET_SUBMISSION` 语义声明）、§6（固定权重集合）、§9（指标口径）、§14（禁止事项），
以及 V2 §1.1（裁决基础：`c_div` 三个内部 blend + `c_anchor` 两个真实 anchor，派生端点仅作上下文）、
§1.2（主窗口不含 S30）、§1.5（复杂度只用内部 blend）继续有效。

## 6. 停止条件

```text
不执行组合实验；不生成 research/results 产物
不读取或恢复被判定无效的运行数值
不修改任何冻结候选、config、canonical 数据或既有冻结研究证据
不在 Commit A 被独立接受前授权 Commit B，也不选择下一 Goal
```
