# Prospective Evidence Foundation V1 — 最终 revalidation 与 readiness 恢复

本文件是 `PROSPECTIVE_EVIDENCE_FOUNDATION_V1_FOR_S2_AND_S4C` 的**最终治理 closeout**。
它只记录证据链与最终判定，不产生 observation、不创建 vintage、不接触真实 2026-09 市场数据、
不修改实现代码、不修改任何候选身份或策略经济语义。

历史证据链保持完整且不被改写：

```text
original readiness
→ clean-Linux contradiction
→ explicit errata / revocation
→ bounded corrective closure
→ independent revalidation   （本文件）
→ restored READY
```

## 1. Repository

```text
STARTING_HEAD   = c70e74e7c35a5cdc9e4e3654f7267bb05c1040b6
                  （independently audited implementation baseline）
ORIGIN_MAIN     = 与 STARTING_HEAD 相同，working tree clean
FINAL_HEAD      = 本文件所在的 governance closeout commit（紧随 c70e74e）
PUSH_STATUS     = main == origin/main
```

## 2. 历史链

### 2.1 Original readiness（历史，不修改）

RL-048 / [原始 Foundation V1 结果](PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md) 曾宣布：

```text
PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS
```

该判定只由本地 Windows 开发环境证据支撑。

### 2.2 Revocation

clean Linux CI 在 HEAD `74613246aab3d93cf381239f3ab499a58f96b555` 上给出：

```text
pytest = 6 failed / 436 passed
workflow conclusion = failure
```

失败全部指向「S4C 冻结语义无法再现 committed 冻结目标日程」，其判据是跨环境逐字节 /
`round(12)` 精确相等。该可执行证据使先前的 READY 失效。
RL-049 与 [errata / revocation](PROSPECTIVE_EVIDENCE_FOUNDATION_V1_ERRATA.md) 因此登记：

```text
FOUNDATION_V1_READINESS_STATUS              = READINESS_REVOKED_PENDING_CORRECTION
PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE  = FAIL
PROSPECTIVE_FOUNDATION_DECISION             = BLOCKED_BY_PROSPECTIVE_CORRECTNESS
CURRENT_FRONTIER                            = PROSPECTIVE_FOUNDATION_V1_FINAL_CORRECTIVE_CLOSURE
```

### 2.3 Corrective closure（commit 逐条复核自 repository history）

```text
31833879a2fd5ed76834abe64e8d7addeeec17f1  revoke premature foundation readiness after clean-ci failure
2550f10df972ca3231aa0d7006dd7b4b1cdd8c84  add s4c numerical portability diagnostics
677e1d9116e94a2273b99cb295535d831d15b773  extend s4c portability diagnostic with structure and economic materiality
b07299a917f7fe8394c877df602befeff0de1223  remove caller time authority from prospective execution artifact production
35cc57c4be3cd6a8f222e48b4310b54c0746b059  add integrated dual-candidate production-path readiness drill
f135f29bb73a918009618229b13fb03a5a565943  add structural reproduction guard and record frozen-module correction constraint
15b9bca5c101148cbce6441e0b38da4d362b8503  record executed corrective commit sequence in foundation errata
4d53da64e0d2ee49d06dcf30639700e1b3a0205e  fingerprint erc solver inputs to isolate cross-platform divergence
8b49db72b9464885651efe99133729e7e8de3a4b  preregister s4c portable reproduction contract v1
c70e74e7c35a5cdc9e4e3654f7267bb05c1040b6  implement s4c portable reproduction contract in prospective verifier
```

## 3. S4C portability

```text
S4C_PORTABILITY_DIAGNOSIS = NUMERICALLY_EQUIVALENT
```

证据（committed 诊断产物
[local](S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LOCAL_V1.json) /
[linux](S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LINUX_V1.json)）：

```text
returns_window_sha256 = 450a66193d2e1c7a9f7236cc3dfbf3c7d1d823ab345f2496a7297244c481903c
risk_windows          = 149
fallback_windows      = 23
solver                = CLARABEL（skfolio 显式传入）
tol_gap_abs           = 1e-9
tol_gap_rel           = 1e-9

Linux max absolute target-weight delta = 2.7996468267524333e-05
mean absolute delta                    = 6.891444410562036e-07
support changes                        = 0
maximum-weight identity changes        = 0
```

两个环境的求解器**输入指纹逐位相同**（149 RISK / 23 fallback），结构、support、maximum-weight
身份、execution 日期与资产列完全一致，同路径经济指标差异（CAGR 4.68e-07、MaxDD 2.02e-09、
Sharpe 4.27e-06、Calmar 2.54e-06、turnover 6.93e-05）都在已冻结的 V2 指标尺度内。差异因此被
独立分类为 solver/BLAS 浮点可移植性噪声，而非数据路径、PIT、universe、策略语义或
materially different solution 的分歧。

### 3.1 预注册契约

[`S4C_PORTABLE_REPRODUCTION_CONTRACT_V1`](../batches/prospective_evidence_foundation/PORTABLE_REPRODUCTION_CONTRACT_V1.md)

```text
S4C_PORTABLE_REPRODUCTION_CONTRACT_V1
ARTIFACT_IDENTITY        = EXACT
STRUCTURAL_REPRODUCTION  = EXACT
SCHEDULE_WEIGHT_ABS_TOL  = 1e-4
SCHEDULE_WEIGHT_REL_TOL  = 0
```

语义边界必须被明确区分：

```text
frozen artifact identity 保持精确
  normalized SHA-256 / 行数 / 日期区间 / asset 列 / 非负 / 逐行权重和 / PIT 合法性

只有 cross-platform solver re-derivation 使用数值容差
  逐元素 |Δw| <= SCHEDULE_WEIGHT_ABS_TOL
```

结构不变量（日期集合、资产集合、逐行 support、maximum-weight 身份、risk/fallback regime 结构、
逐行权重和）继续精确，任何结构变化都不适用容差。容差 `1e-4` 由实测证据授权（observed Linux max
`2.80e-05`、历史同类 portability 记录约 `4.11e-05`，safety factor 3.57×，经济含义 1 bp 权重），
不是猜测值。历史 byte-exact audit（`audit_recomputation`）保留为平台绑定的历史证据路径，
不再充当跨平台语义 gate。

## 4. Execution artifact authenticity

```text
EXECUTION_ARTIFACT_AUTHENTICITY_GATE = PASS
```

```text
caller cannot provide artifact_generated_at
caller cannot provide execution_timestamp
caller cannot provide arbitrary artifact path
execution observation date derives from native RQAlpha replay/analyser evidence
artifact_generated_at derives from the actual runner clock
future execution observation cannot produce an authoritative artifact before observation close
artifact path is candidate / signal-date / execution-date canonical
```

这只证明**机制**（production seam 不再信任调用方的时间与目标位置、未来观测不可能被封存），
**不**等于已经发生真实前瞻执行。真实 RQAlpha execution adapter 的首次真实运行仍是 future cycle。

## 5. Full-path readiness

```text
FULL_PATH_READINESS_GATE = PASS
```

一条合成、确定性的 drill 走完整条生产路径：

```text
MockTushare
→ candidate-specific frozen vintage（S2_R1 与 S4C_R1）
→ provenance verification 与 frozen universe identity verification
→ S2 decision
→ S4C decision
→ append-only decision evidence（重复 decision 被拒绝）
→ native-shaped RQAlpha execution evidence
→ production artifact seam（时钟只经 test-only seam 注入）
→ S2 execution row
→ S4C execution row
→ append-only execution evidence（重复 / 不完整 execution 被拒绝）
→ 先前 decision bytes 逐字节未变
```

全部断言在 synthetic / `tmp_path` 内完成，不产生任何真实 2026-09 evidence。

## 6. Clean-Linux CI

```text
GITHUB_CI_RUN_ID     = 34873004632
GITHUB_CI_HEAD_SHA   = c70e74e7c35a5cdc9e4e3654f7267bb05c1040b6
GITHUB_CI_CONCLUSION = SUCCESS
```

每个预期步骤都实际执行且成功：

```text
S4C numerical portability diagnostic = PASS（含 contract_compliance: within_contract = true）
pytest                               = 462 passed / 0 failed
ruff check                           = PASS
ruff format --check                  = PASS
mypy                                 = PASS
S2 candidate verification            = PASS
S4C candidate verification           = PASS
S4C prospective shadow verification  = PASS
```

```text
no required step skipped
no xfail used to hide the prior blocker
no platform-conditional suppression used
```

本地同一 HEAD 的 clean Linux（WSL Ubuntu + `uv sync --frozen`，Python 3.11.16）同样为
`462 passed / 0 failed`；本地 Windows 亦为 `462 passed / 0 failed`。

## 7. Gate table

```text
RESEARCH_STATE_TRUTHFULNESS = PASS
VINTAGE_PROVENANCE = PASS
FROZEN_UNIVERSE_IDENTITY = PASS
SYMBOL_TUSHARE_MAPPING = PASS
S4C_FROZEN_ARTIFACT_IDENTITY = PASS
S4C_CROSS_PLATFORM_REPRODUCTION = PASS
S4C_PORTABILITY_CONTRACT = PASS
DECISION_TEMPORAL_SEAL = PASS
EXECUTION_ROW_TEMPORAL_SEAL = PASS
EXECUTION_ARTIFACT_TIME_AUTHENTICITY = PASS
FUTURE_ARTIFACT_PREVENTION = PASS
RQALPHA_NATIVE_EXTRACTION = PASS
RQALPHA_ARTIFACT_INTERNAL_CONSISTENCY = PASS
RQALPHA_ARTIFACT_TO_METRICS_BINDING = PASS
DECISION_APPEND_ONLY = PASS
EXECUTION_APPEND_ONLY = PASS
FAILURE_BYTE_PRESERVATION = PASS
FULL_PATH_READINESS_DRILL = PASS
LOCAL_QUALITY_GATE = PASS
GITHUB_CI_GATE = PASS
PROSPECTIVE_PURITY = PASS
FROZEN_CANDIDATE_IDENTITY = PASS
PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE = PASS
```

## 8. Foundation decision

```text
PROSPECTIVE_FOUNDATION_DECISION = PROSPECTIVE_FOUNDATION_READY
```

不使用 `READY_WITH_NONBLOCKING_LIMITATIONS`：没有发现新的 Foundation 级 correctness limitation。
以下均为候选成熟度/风险事实，不是 Foundation correctness limitation：

```text
prospective observations = 0
S4C concentration risk（已登记 known risk，不得以 cap 修补）
S2_R1 / S4C_R1 都不是 production candidate
真实 RQAlpha execution adapter 尚未在真实输出上运行过（首次真实执行是 future cycle 的边界）
```

Foundation READY 只表示前瞻证据机制可信，**不**表示任何候选具备生产资格。

## 9. Prospective purity 与 frozen identity

```text
S2_OBSERVATION_COUNT  = 0（observations.csv 仅表头）
S4C_OBSERVATION_COUNT = 0（observations.csv 仅表头）

S2_REAL_VINTAGE_COUNT  = 0（无 vintages/ 目录）
S4C_REAL_VINTAGE_COUNT = 0（无 vintages/ 目录）
REAL_EXECUTION_ARTIFACTS = 0（无 execution_artifacts/ 目录）

REAL_2026_09_MARKET_DATA_USED        = NO
REAL_PROSPECTIVE_DECISION_GENERATED  = NO
REAL_PROSPECTIVE_EXECUTION_GENERATED = NO
```

```text
S2_MANIFEST_CHANGED              = NO
S4C_MANIFEST_CHANGED             = NO
S4C_ACTIVATION_CHANGED           = NO
S4C_FROZEN_TARGET_CHANGED        = NO（SHA-256 f7bf398d…1227e47 未变）
HISTORICAL_CANONICAL_DATA_CHANGED = NO
S2_STRATEGY_ECONOMICS_CHANGED    = NO
S4C_STRATEGY_ECONOMICS_CHANGED   = NO
```

证据方式：`git diff 74613246..c70e74e -- <frozen paths>` 为空；S4C manifest 的 13 个
`frozen_identity_artifacts` 与 S2 manifest 的冻结 hash 逐条复核一致；冻结目标文件 hash 未变。

## 10. Future operation（语义未变）

`EXACT_2026_09_30_DECISION_RUNBOOK` 与 `EXACT_NEXT_EXECUTION_RUNBOOK` 仍冻结在
[原始 Foundation V1 结果](PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md)，本 Goal 未改动其语义。

在真实 `2026-09-30` 收盘后（该 as-of 数据已合法可得）：

```text
verify clean repo / frozen candidates
freeze S2 vintage
freeze S4C vintage
verify provenance
derive + seal + append S2 DECISION（每个候选只有一次写操作）
derive + seal + append S4C DECISION
read-only verify
tests
commit
push
STOP（不得等待 execution 结果再一起提交）
```

execution 是其后独立 Goal，只在对应 canonical 观测真实存在后用 production artifact seam 追加。

## 11. Frontier 与开发冻结

```text
CURRENT_FRONTIER = AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE
DEVELOPMENT_STATUS = FROZEN_PENDING_REAL_PROSPECTIVE_TIME
```

系统现在需要的是前瞻时间，不是更多代码。不得以历史收益、集中度或时间压力为由改参数、加 cap、
重跑窗口、回填已可观察数据或用历史结果制造前瞻证据；也不得在此阶段启动 S27A、Theme Rotation、
新 alpha/factor、新 ERC 变体、新 trend 参数、组合候选、组合优化器或新研究基础设施。

## 12. 关联

- 原始结果（历史，不修改）：[PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md](PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md)
- 撤销记录（历史，不修改）：[PROSPECTIVE_EVIDENCE_FOUNDATION_V1_ERRATA.md](PROSPECTIVE_EVIDENCE_FOUNDATION_V1_ERRATA.md)
- 预注册契约：[PORTABLE_REPRODUCTION_CONTRACT_V1.md](../batches/prospective_evidence_foundation/PORTABLE_REPRODUCTION_CONTRACT_V1.md)
- Foundation 协议：[PROTOCOL.md](../batches/prospective_evidence_foundation/PROTOCOL.md)
- 同类先例：[INVALID_RUN_S4C_EXECUTION_R1.md](INVALID_RUN_S4C_EXECUTION_R1.md)
- 平台背景：[PHASE_A_WINDOWS_NATIVE_PORTABILITY_AUDIT_V1.md](PHASE_A_WINDOWS_NATIVE_PORTABILITY_AUDIT_V1.md)
