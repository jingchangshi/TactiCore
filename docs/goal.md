# TactiCore — 当前执行指令

状态：Foundation V1 的 readiness 已被撤销（RL-049），开发重新打开，仅用于更正闭包。

## 当前唯一前沿

```text
PROSPECTIVE_FOUNDATION_V1_FINAL_CORRECTIVE_CLOSURE
```

## 触发原因

RL-048 曾宣布：

```text
PROSPECTIVE_FOUNDATION_DECISION = PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS
```

该判定只由本地 Windows 环境支撑。clean Linux（GitHub Actions，审计时 `main` HEAD
`74613246aab3d93cf381239f3ab499a58f96b555`）给出 `pytest = 6 failed / 436 passed`、
workflow `conclusion = failure`，失败集中在「S4C 冻结语义无法再现 committed 冻结目标日程」。
可执行证据优先于状态文档，因此该 READY 已被显式撤销，历史不被改写：

[`PROSPECTIVE_EVIDENCE_FOUNDATION_V1_ERRATA.md`](../research/results/PROSPECTIVE_EVIDENCE_FOUNDATION_V1_ERRATA.md)

当前真实状态：

```text
FOUNDATION_V1_READINESS_STATUS              = READINESS_REVOKED_PENDING_CORRECTION
PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE  = FAIL
PROSPECTIVE_FOUNDATION_DECISION             = BLOCKED_BY_PROSPECTIVE_CORRECTNESS
```

## 更正范围（有界）

```text
1. S4C clean-environment 数值可移植性只读诊断（本地 + Linux，测量差值，不预设可接受性）
2. 独立分类：NUMERICALLY_EQUIVALENT / MATERIAL_SOLVER_DIVERGENCE / UNRESOLVED
3. 仅在分类为数值等价时：预注册有界 portable reproduction contract，并最小化修正 verifier
   —— 冻结 artifact 身份（SHA / 行数 / 日期 / 非负 / 逐行和）保持精确，不削弱
4. production execution artifact 不得接受 caller 注入的生成时间或未来 execution 时间戳；
   未来观测未发生时不得存在权威 artifact
5. 一条真正集成的 dual-candidate production-path readiness drill（MockTushare → vintage →
   decision → native RQAlpha artifact → execution）
6. 本地质量门 + GitHub HEAD CI 全绿，之后才可重新判定 readiness
```

每一步都必须在独立复核通过后才进入下一步；不得自行授权最终 gate。

## 硬边界

```text
不得在 2026-09-30 之前下载或查看真实 2026-09 市场数据
不得创建真实 vintage、不得 append 任何 observation
不得修改 candidate manifest、S4C activation、S4C 冻结目标文件、策略经济语义或 historical canonical 数据
不得以「让 CI 变绿」为由跳过测试、xfail、平台条件禁用、放宽容差或删除精确身份检查
不得改名重做已关闭问题，也不得借更正闭包启动新 alpha、S27A、Theme Rotation 或组合候选
```

## 完成后的下一步（未授权提前执行）

只有全部更正通过并由独立 review 判定 PASS 后，才可写入 revalidation 结果并恢复
`AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE`；届时在真实 `2026-09-30` 收盘后
（即该 as-of 数据已合法可得）启动该 cycle。流程保持
`freeze vintage → verify → derive decision → seal → append DECISION → commit/push → STOP`；
每个候选只有一次写操作（candidate CLI 在一次调用中完成 derive + seal + append），
不得再手工重复 append。execution 证据在下一 canonical 观测日由独立 Goal 追加。

执行步骤、验证清单与 STOP 边界仍冻结在 Foundation V1 结果文件的
`EXACT_2026_09_30_DECISION_RUNBOOK` 与 `EXACT_NEXT_EXECUTION_RUNBOOK`；届时不得临时改代码。
