# S4C 跨环境可移植性 reproduction 契约 V1

状态：**预注册（在 Commit B2 实现之前冻结）**
作用域：`S4C_R1` committed 冻结目标日程的「冻结语义可重现性」验证
独立裁决来源：C2C REVIEW `c2c_8b02` iteration 1，repository head
`4d53da64e0d2ee49d06dcf30639700e1b3a0205e`

本契约只解决一个问题：把**冻结产物身份**与**跨环境求解数值再现**分开，使「冻结语义仍然
重现 committed 日程」不再依赖某一个平台的浮点求解结果。它不修改候选经济语义、不产生
observation、不接触任何真实 2026-09 数据，也不是通用数值/治理框架。

## 1. 独立裁决

```text
RESEARCH_STATE_TRUTHFULNESS_GATE = PASS
S4C_PORTABILITY_DIAGNOSIS        = NUMERICALLY_EQUIVALENT
```

依据（committed 诊断产物
[`S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LOCAL_V1.json`](../../results/S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LOCAL_V1.json)、
[`S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LINUX_V1.json`](../../results/S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LINUX_V1.json)）：

| 项 | Windows 开发环境 | clean Linux |
| --- | --- | --- |
| pinned 数值栈 | numpy 1.26.4 / scipy 1.17.1 / skfolio 1.0.6 / cvxpy-base 1.7.5 | 同左 |
| solver / status | CLARABEL（显式）、optimal | CLARABEL（显式）、optimal |
| solver 输入指纹 | `450a6619…1903c`（149 RISK / 23 fallback） | 同左（逐位相同） |
| max abs weight delta | `1.11e-16` | `2.7996468267524333e-05` |
| mean abs weight delta | `2.94e-17` | `6.891444410562036e-07` |
| support 变化 | 0 | 0 |
| maximum-weight 身份变化 | 0 | 0 |
| execution date / asset column 差异 | 无 | 无 |
| 同路径经济指标 delta | ≤ `1.8e-15` | CAGR `4.68e-07`、MaxDD `2.02e-09`、Sharpe `4.27e-06`、Calmar `2.54e-06`、turnover `6.93e-05` |

两个环境的**求解器输入逐位相同**，差异只出现在求解数值本身；结构、regime、eligible 集合与
经济指标都落在已冻结的 V2 指标尺度内。因此该差异被独立分类为 solver/BLAS 浮点可移植性噪声，
而不是数据路径、PIT、universe、策略语义或 materially different solution 的分歧。

## 2. 两类契约必须分开

```text
artifact identity        committed 产物本身：精确、哈希绑定、不得漂移
semantic re-derivation   跨平台用求解器重推：结构精确 + 有证据的数值容差
```

把「冻结语义仍可重现」表达为**序列化 CSV 字节相等**会把契约绑定到单一平台的浮点结果，
从而把跨平台可移植性误判为 candidate 完整性失效。本契约取代该用途，但不削弱产物身份检查。

## 3. Artifact identity（EXACT，不得放松）

```text
normalized SHA-256 == manifest / verifier 冻结值
row count == 161
execution_date 区间 == 2013-04-01 .. 2026-08-03，唯一且单调递增
asset columns 与冻结 universe 逐列一致
非负权重
逐行权重和 == 1（round 12）
PIT/tradability 合法性
```

## 4. Structural semantic reproduction（EXACT，不得放松）

```text
execution-date 集合
asset 集合与列顺序
逐行 support（正权重标的集合）
每行 maximum-weight 标的身份
risk / fallback regime 结构
逐行权重和
```

任一结构不一致一律判为经济语义变化，**不适用任何数值容差**。

## 5. 跨平台求解数值比较

```text
SCHEDULE_WEIGHT_ABS_TOL = 1e-4
SCHEDULE_WEIGHT_REL_TOL = 0
```

逐元素比较 `|derived - committed| <= SCHEDULE_WEIGHT_ABS_TOL`。

## 6. 容差依据（不是猜测值）

```text
实测 clean Linux max delta          = 2.7996468267524333e-05
历史同类 portability 记录 max delta = 4.11e-05（INVALID_RUN R1 的逐月 ERC maximum_weight 漂移）
授权上界                            = 1e-4
safety factor（相对实测）           = 3.57x
经济含义                            = 1 bp 组合权重
```

上界必须小到「真的换了目标」会失败：结构性变化（asset 进出、support 变化、最大权重标的互换、
行权重和不成立）由 §4 精确拒绝，任何 ≥1e-4 的权重漂移由 §5 拒绝。

## 7. 边界

```text
不得修改 S4C candidate_manifest.json
不得修改 S4C activation.json
不得修改 research/results/s4c_pit_corrected_frozen_targets_v1.csv
不得修改 historical canonical 数据
不得修改 S4C 策略经济语义
不得修改冻结的 research/experiments/run_s4c_rqalpha_execution_review.py
实现只能落在非冻结的前瞻 verifier / helper / test 代码
该契约不得用于降低 artifact identity 检查、不得掩蔽结构变化
```

历史 byte-exact audit（`audit_recomputation`）保留为历史证据路径；clean Linux 的求解器重推
**不再**被要求逐字节复现序列化 CSV。

## 8. Machine-readable

```text
S4C_PORTABLE_REPRODUCTION_CONTRACT_V1
ARTIFACT_IDENTITY        = EXACT
STRUCTURAL_REPRODUCTION  = EXACT
SCHEDULE_WEIGHT_ABS_TOL  = 1e-4
SCHEDULE_WEIGHT_REL_TOL  = 0
```
