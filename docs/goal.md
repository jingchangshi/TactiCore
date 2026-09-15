# TactiCore — 当前执行指令

状态：Foundation V1 实现完成并通过独立 revalidation，开发冻结，等待真实前瞻时间。

## 当前唯一前沿

```text
AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE
```

## 已完成

`PROSPECTIVE_EVIDENCE_FOUNDATION_V1_FOR_S2_AND_S4C` 的历史链完整保留并可复核：

```text
RL-048 原始 readiness
  → clean Linux CI 反证（74613246：6 failed / 436 passed）
  → RL-049 显式撤销 / errata
  → 有界更正闭包（3183387..c70e74e）
  → RL-050 独立 revalidation
  → 恢复 READY
```

当前真实状态：

```text
PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE = PASS
PROSPECTIVE_FOUNDATION_DECISION            = PROSPECTIVE_FOUNDATION_READY
S2_R1                                      = FROZEN / PROSPECTIVE_SHADOW_ACTIVE
S4C_R1                                     = FROZEN / PROSPECTIVE_SHADOW_ACTIVE
S2 prospective observations                = 0
S4C prospective observations               = 0
DEVELOPMENT_STATUS                         = FROZEN_PENDING_REAL_PROSPECTIVE_TIME
```

恢复 READY 的依据是可执行证据，不是文档：S4C 跨环境差异被独立分类为
`NUMERICALLY_EQUIVALENT` 并由预注册 [S4C portable reproduction contract
V1](../research/batches/prospective_evidence_foundation/PORTABLE_REPRODUCTION_CONTRACT_V1.md) 承接
（artifact identity 精确、结构精确、schedule 权重 `ABS_TOL = 1e-4`）；production execution
artifact 不再接受调用方的时间/位置权威；集成 dual-candidate production-path drill 通过；
clean Linux CI run `34873004632`（head `c70e74e`）`conclusion = SUCCESS`、`pytest = 462 passed`、
无跳过步骤。两个候选都**不是**生产候选。

完整记录见
[`PROSPECTIVE_EVIDENCE_FOUNDATION_V1_REVALIDATION_V1.md`](../research/results/PROSPECTIVE_EVIDENCE_FOUNDATION_V1_REVALIDATION_V1.md)；
当前策略状态见 [`CURRENT_STATE.md`](CURRENT_STATE.md)，已关闭历史见
[`RESEARCH_LEDGER.md`](RESEARCH_LEDGER.md) 的 RL-048–RL-050。

Foundation implementation is complete.

No discretionary development is authorized before the real 2026-09-30 prospective decision cycle
unless a new correctness blocker is discovered.

## 硬边界

```text
不得在 2026-09-30 之前下载或查看真实 2026-09 市场数据
不得创建真实 vintage、不得 append 任何 observation
不得修改 candidate manifest、S4C activation、S4C 冻结目标文件、策略经济语义或 historical canonical 数据
不得以「让 CI 变绿」为由跳过测试、xfail、平台条件禁用、放宽容差或删除精确身份检查
不得改名重做已关闭问题，也不得借更正闭包启动新 alpha、S27A、Theme Rotation 或组合候选
```

## 下一步（未授权提前执行）

在真实 `2026-09-30` 收盘后（即该 as-of 数据已合法可得）方可启动该 cycle；该 as-of 的
candidate-specific vintage 是该 cycle 的第一阶段，此前并不存在。流程保持
`freeze vintage → verify → derive decision → seal → append DECISION → commit/push → STOP`；
每个候选只有一次写操作（candidate CLI 在一次调用中完成 derive + seal + append），
不得再手工重复 append。execution 证据在下一 canonical 观测日由独立 Goal 追加。

执行步骤、验证清单与 STOP 边界仍冻结在 Foundation V1 结果文件的
`EXACT_2026_09_30_DECISION_RUNBOOK` 与 `EXACT_NEXT_EXECUTION_RUNBOOK`；届时不得临时改代码。
