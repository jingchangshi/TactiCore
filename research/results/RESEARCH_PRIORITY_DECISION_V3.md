# Research Priority Decision V3（双候选前瞻证据 foundation）

本记录在 [`DUAL_CANDIDATE_PROSPECTIVE_AUDIT_V1.md`](DUAL_CANDIDATE_PROSPECTIVE_AUDIT_V1.md)
之后、任何 Foundation 实现**之前**产生，只做优先级裁决与 Goal 授权。

本文件不实现任何修复、不激活任何候选、不生成 observation、不下载任何数据。
历史 CAGR 不参与排序；判据是 local remaining gap 的减少量、正确性影响、证据价值、实现自由度、
维护成本、数据挖掘风险、架构风险与可逆性。

## 1. 裁决输入

审计确认当前最大 remaining gap 不是 `RETURN_GAP`，而是 `PROSPECTIVE_EVIDENCE_GAP`
的**正确性形态**：两个活动候选的 prospective path 都还无法保证"第一条真实 observation
起即为不可回填、可机器验证的前瞻证据"。

时间价值必须显式记录：两个候选的 `first_eligible_prospective_signal = 2026-09-30`
（S2 由冻结月度语义推出，S4C 显式冻结）。当前日期为 2026-09-14。若证据路径在 2026-09-30
之前仍不合格，该月的月末前瞻观测将永久不可回填。

## 2. 候选选项

```text
A. Prospective Evidence Foundation V1 for S2 + S4C
B. 只修 S4C
C. 开启新策略 / S27A / Theme Rotation
D. 现在创建 portfolio candidate
E. 在 2026-09-30 之前什么都不做
```

## 3. 评分

评分 1–5，越高越好。对 freedom / cost / risk 类判据，"更高"表示更少自由度、更低成本或更低风险。
权重：information 2、correctness 3、10% objective 2、prospective value 3、time 3、
implementation freedom 1、maintenance 1、data-mining 2、architecture 2、reversibility 1，满分 100。

| Option | Info | Correctness | 10% objective | Prospective | Time | Impl. freedom | Maintenance | Mining risk | Arch risk | Reversible | Weighted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. S2 + S4C Foundation V1 | 5 | 5 | 5 | 5 | 5 | 4 | 4 | 5 | 4 | 4 | **95** |
| B. 只修 S4C | 3 | 2 | 3 | 2 | 4 | 5 | 4 | 5 | 5 | 5 | 70 |
| C. 新策略 / S27A / Theme | 3 | 1 | 2 | 1 | 1 | 1 | 2 | 1 | 3 | 3 | 33 |
| D. 现在创建 portfolio candidate | 2 | 1 | 3 | 1 | 1 | 2 | 2 | 3 | 2 | 2 | 35 |
| E. 等到 2026-09-30 | 1 | 1 | 1 | 1 | 1 | 5 | 5 | 5 | 5 | 5 | 48 |

## 4. 选择

```text
DECISION = A
SELECTED_NEXT_GOAL = PROSPECTIVE_EVIDENCE_FOUNDATION_V1_FOR_S2_AND_S4C
```

理由：

1. 历史约 10% 的可行性问题已经足够关闭，prospective correctness 因此成为主导性的信息瓶颈。
2. B 会让 S2 继续产出明显更弱的证据，因此无法建立可信的**双候选**前瞻证据：
   一个严格的 S4C 加一个宽松的 S2 不等于可信的组合前瞻证据。
3. C/D 在当前证据链可信之前扩大研究自由度或叠加组合层不确定性。
4. E 规避实现风险，但会在证据路径仍有缺陷时不可逆地浪费第一个合格前瞻周期。
5. 本工作有时间敏感性，但设计由**正确性**控制，而不是由 9 月 30 日这个日期控制。

## 5. 该选择授权什么

本裁决**只**授权 Foundation V1 的实现与 readiness 判定，不授权任何 observation：

```text
authorized:   provenance 机器验证、price_as_of/calendar_as_of 语义分离、
              signal-day temporal seal、decision/execution 分离 append-only、
              execution 行完整性、RQAlpha evidence 绑定、候选 CLI 授权收紧、
              只读 verifier 未来兼容性、thin CI 评估

not authorized: 生成任何真实前瞻 observation；创建 vintage 且从中形成证据；
                修改任一 candidate manifest / activation 语义 / 策略经济语义 /
                historical canonical 数据；创建 portfolio candidate；
                开启新策略或重开已关闭问题
```

## 6. 未选择项的未来条件

```text
B : 只有在 A 被明确否决，或审计证明 S4C 是唯一存在 correctness blocker 的候选时
C : 必须重新通过 External Evidence Gate 与 PIT Tradability Gate，且不得与已关闭问题重名
D : 需要两个候选先具备可信前瞻证据，或由后续独立优先级决策授权
E : 只有在 Foundation 被明确判为 BLOCKED 时才是自然延续
```

## 7. 边界

- 本记录**不**声称 Foundation 已 ready，**不**生成前瞻证据，**不**构成生产批准或组合建议。
- 两个候选的 lifecycle 表示保持不变：S2 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`，
  S4C `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`，`prospective observations = 0`。
- 预注册协议见 [`PROTOCOL.md`](../batches/prospective_evidence_foundation/PROTOCOL.md)，
  它在任何实现之前冻结。
