# Research Priority Decision V2（10% portfolio objective 之后的首个独立选择）

本记录在两件事**之后**、任何下一阶段实现**之前**产生：

1. [`PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md`](PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md)
   已完成历史可行性诊断（`FEASIBLE_WITH_EXISTING_COMPONENTS`）；
2. 该诊断没有创建任何候选、没有激活任何前瞻影子、也没有产生生产配置。

本文件只做优先级裁决与 Goal 授权，不实现、不激活、不重跑任何历史研究。
历史 CAGR 不参与排序；判据是**本地 remaining gap 的减少量、证据质量、机制区分度与实现自由度**。

## 1. 当前剩余缺口（裁决输入）

| 缺口 | 状态 |
| --- | --- |
| `RETURN_GAP` | 小：内部固定 blend 在主窗口已达 10.4849%，共同窗口 50/50 达 10.8404% |
| `DRAWDOWN_GAP` | 中等：达到该量级对应 signed MaxDD 约 -15.9% 至 -17.1% |
| `DIVERSIFICATION_GAP` | 部分关闭：50/50 与 25/75 的 signed MaxDD 优于任一 anchor；Sharpe 未超过 S4C 单独运行 |
| `EXECUTION_GAP` | 组件历史执行闭环已建立；派生组合没有独立执行审查 |
| `PROSPECTIVE_EVIDENCE_GAP` | **最大**：组合层前瞻观测为零；S4C R1 前瞻影子未激活 |
| `DATA_GAP` | 已按有界范围封闭；长期限制（universe 构造）仍登记在案 |
| `MAINTENANCE_GAP` | 明确：blend 年化动作日约 11.85 次，S30 约 1.03 次 |

时间价值（必须显式记录）：`S4C_R1` 的 `first_eligible_prospective_signal = 2026-09-30`，
该日期由候选冻结审查预先确定且**不得回溯**。当前日期为 2026-09-13。若在 2026-09-30 之前没有
激活授权，则该月的月末前瞻观测将永久不可回填——prospective evidence 具有时间价值，但时间压力
不得覆盖 research correctness。

## 2. 候选选项

```text
A. S4C_R1 前瞻影子激活决策（独立的下一 Goal）
B. 只保留 S2 前瞻影子，S4C R1 继续冻结/不激活
C. 固定组合候选 / 组合层执行审查（未来独立 Goal）
D. 开启新的经济正交 return source
E. 只改进组合 / 风险度量（仅在存在具体 correctness gap 时）
```

## 3. 评分（相对排序，不使用历史 CAGR）

| 判据 | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Expected information gain | **HIGH** | LOW | MEDIUM | MEDIUM | LOW |
| Contribution to 10% objective | HIGH | LOW | MEDIUM | MEDIUM | LOW |
| Economic orthogonality | HIGH（ERC ≠ trend） | LOW（重复 S2） | HIGH | HIGH（未知） | N/A |
| Prospective value | **HIGH** | MEDIUM | LOW（尚无前瞻基础） | LOW | LOW |
| Data-mining risk | LOW（协议已预注册） | LOW | MEDIUM | **HIGH** | MEDIUM |
| Candidate proliferation | NONE（身份已冻结） | NONE | MEDIUM（会创建组合身份） | HIGH | NONE |
| Implementation freedom | LOW（激活决策，非实现） | LOW | MEDIUM | HIGH | MEDIUM |
| Maintenance burden | LOW | LOW | MEDIUM | MEDIUM | LOW |
| Time to new evidence | **最短**（2026-09-30 起可观测） | 已有观测 | 长 | 很长 | 中 |
| Reversibility | HIGH（append-only 状态） | HIGH | 中 | 中 | HIGH |
| Community / upstream reuse | 高（skfolio 已固定） | 高 | 中 | 未知 | 中 |
| Correctness risk | LOW | LOW | MEDIUM | HIGH | MEDIUM |

## 4. 选择

```text
SELECTED_NEXT_GOAL = S4C_R1_PROSPECTIVE_SHADOW_ACTIVATION_DECISION
```

理由：

1. S2 R1 的前瞻影子**已经在运行**；"只保留 S2"（B）不会减少当前最大的不确定性，因为 S2 的
   前瞻观测本来就在继续积累。
2. 组合可行性结论**依赖对 S4C 的较高权重**（主窗口 25/75、共同窗口 50/50 及以上），而 S4C R1
   的前瞻观测为**零**。当前最大的缺口是前瞻证据，不是缺 alpha。
3. S4C 与 S2 在经济机制上相互区别（无杠杆 ERC 风险预算 vs 时序趋势），因此 S4C 前瞻证据能比
   推进与 S2 机制重叠的 S27A 提供更多**机制区分**信息。
4. 现在冻结/推进组合候选（C）为时过早：派生组合有自己独立的
   `DERIVED_UNION_TARGET_SUBMISSION` 政策、没有独立执行审查，且会在 S4C 自身尚无前瞻证据时叠加
   不确定性。
5. 开启新 return source（D）不符合当前本地 gap：历史 return gap 很小，而 D 会显著增加数据挖掘
   自由度并需要先通过 External Evidence Gate 与 PIT Tradability Gate。
6. 当前**没有**具体的组合/风险度量 correctness gap，所以 E 不成立。

## 5. 该选择的边界

- 本记录**不**激活 S4C R1 前瞻影子、**不**修改 `candidate_manifest.json`、**不**生成任何 observation。
- 下一 Goal 只回答"是否激活，以及在什么状态下激活"；若授权激活，生命周期转换必须由独立的
  activation artifact / state 记录，而不是改写 R1 的不可变身份。
- 不得以集中度、历史收益或 `2026-09-30` 的时间压力为由修改 R1 语义、加 cap 或重跑窗口。
- 不得借机创建组合候选、执行审查或新的 strategy family。

## 6. 未选择项的未来条件

```text
B  : 只有在 S4C 激活决策被明确否决时才成为自然延续
C  : 需要 S4C（以及组合层）先具备前瞻证据，或由后续独立优先级决策授权
D  : 必须先完成 External Evidence Gate 与 PIT Tradability Gate，且不得与已关闭问题重名
E  : 只有出现具体 correctness gap 时才成立
```
