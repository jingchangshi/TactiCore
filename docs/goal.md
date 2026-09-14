# TactiCore — 当前执行指令

状态：Foundation V1 已完成，开发冻结，等待真实前瞻时间。

## 当前唯一前沿

```text
AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE
```

## 已完成

`PROSPECTIVE_EVIDENCE_FOUNDATION_V1_FOR_S2_AND_S4C` 已实现并通过独立 C2C review：

```text
SNAPSHOT_IDENTITY_GATE = PASS
EXECUTION_EVIDENCE_GATE = PASS
PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE = PASS

PROSPECTIVE_FOUNDATION_DECISION = PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS
```

完整记录、证据状态与未来 runbook 见
[`PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md`](../research/results/PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md)。
当前策略状态见 [`CURRENT_STATE.md`](CURRENT_STATE.md)，已关闭历史见
[`RESEARCH_LEDGER.md`](RESEARCH_LEDGER.md) 的 RL-048。

## 下一步（未授权提前执行）

在真实 `2026-09-30` 收盘后（即该 as-of 数据已合法可得）方可启动
`SEPTEMBER_2026_PROSPECTIVE_DECISION_CYCLE`；该 as-of 的 candidate-specific vintage 是该 cycle 的
第一阶段，此前并不存在。流程：`freeze vintage → verify → derive decision → seal → append DECISION
→ commit/push → STOP`。每个候选只有一次写操作（candidate CLI 在一次调用中完成 derive + seal +
append），不得再手工重复 append。execution 证据在下一 canonical 观测日由独立 Goal 追加。

执行步骤、验证清单与 STOP 边界已冻结在 Foundation V1 结果文件的
`EXACT_2026_09_30_DECISION_RUNBOOK` 与 `EXACT_NEXT_EXECUTION_RUNBOOK`；届时不得临时改代码。

## 硬边界

```text
不得在 2026-09-30 之前下载或查看真实 2026-09 市场数据
不得创建真实 vintage、不得 append 任何 observation
不得修改 candidate manifest、S4C activation、策略经济语义或 historical canonical 数据
不得启动新 alpha、S27A、Theme Rotation、组合候选或通用平台工作
不得以集中度、历史收益或时间压力为由改参数、加 cap 或回填数据
```

在真实前瞻信号出现或发现具体 correctness blocker 之前，开发保持冻结。
