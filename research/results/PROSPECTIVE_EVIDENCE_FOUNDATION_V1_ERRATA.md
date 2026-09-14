# Prospective Evidence Foundation V1 — errata / readiness revocation

本文件是一份**勘误与撤销记录**，不是新的研究结果，也不是新的 readiness 判定。
它以 Research Control Plane 的 `original result → errata → corrected implementation → revalidation`
模式登记：先前宣布的 Foundation readiness 在可执行证据面前失效。

历史记录**不被改写**：[Foundation V1 完成与 readiness 判定](PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md)
（commit `7252d75`）与 ledger 条目 RL-048 保持原样，继续作为审计历史存在。

## 0. Repository

本轮更正闭包开始时的仓库事实（repository-first start）：

```text
STARTING_HEAD      = 74613246aab3d93cf381239f3ab499a58f96b555
ORIGIN_MAIN_HEAD   = 74613246aab3d93cf381239f3ab499a58f96b555
WORKING_TREE_STATE = clean
```

`origin/main` 与上一次独立审计的 HEAD 相同，因此本轮无需先重新裁定 corrective scope；
第 2 节的 findings 直接适用。

## 1. 被撤销的结论

```text
PREVIOUS_READINESS_VERDICT
  = PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS

PREVIOUS_GATES (已失效)
  SNAPSHOT_IDENTITY_GATE                      = PASS
  EXECUTION_EVIDENCE_GATE                     = PASS
  PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE  = PASS
```

该判定的依据是本地 Windows 开发环境的 `pytest = 442 passed` 与只读 CLI 校验。
它**没有**任何 clean-environment（Linux）证据。这是判定过早的直接原因。

## 2. 使其失效的证据

GitHub Actions（`.github/workflows/ci.yml`，credential-free，`ubuntu-latest`，Python 3.11）：

| workflow run | head SHA | 结论 |
| --- | --- | --- |
| `34853395374` | `3f8f50fe`（add thin credential-free ci） | `failure` |
| `34854103876` | `74613246aab3d93cf381239f3ab499a58f96b555`（correct foundation runbook and closeout references，审计时 latest `main`） | `failure` |

run `34854103876`（2026-09-14T14:12:31Z）的 job `quality`：

```text
Install dependencies                 = success
pytest                               = failure
ruff check                           = skipped
ruff format --check                  = skipped
mypy                                 = skipped
S2 candidate verification            = skipped
S4C candidate verification           = skipped
S4C prospective shadow verification  = skipped
```

失败测试（6 个）：

```text
tests/test_freeze_prospective_vintage.py::test_mocked_tushare_snapshot_publishes_and_feeds_both_decisions
tests/test_prospective_readiness_drill.py::test_dual_candidate_synthetic_full_cycle_requires_no_code_change
tests/test_prospective_readiness_drill.py::test_readiness_drill_never_touches_the_repository_evidence
tests/test_s4c_execution_review.py::test_frozen_target_artifact_structure_and_hash_are_exact
tests/test_s4c_r1_shadow.py::test_frozen_semantics_still_reproduce_the_committed_schedule
tests/test_s4c_r1_shadow.py::test_read_only_verification_modes_cannot_write
```

共同根因（两个失败断言点）：

```text
research/experiments/run_s4c_rqalpha_execution_review.py::audit_recomputation
  committed 冻结目标 CSV 的**序列化字节**必须与新推导日程逐字节一致

research/experiments/run_s4c_r1_shadow.py::verify_semantics_reproduce_frozen_schedule
  最后一个冻结 signal 的**重推导**与 committed 行在 round(12) 后必须完全相等
```

两个断言都把「冻结语义可重推导」表达为**跨环境精确相等**。在 Linux clean environment 下
该断言不成立，其余 436 个测试通过。

计数一致性说明：CI 的 `6 failed + 436 passed` 与本地 Windows 的 `442 passed` 是同一测试集合
（442 collected）；差异只在平台，不在测试发现。

## 3. 定量定位（初步，本 commit 不修改任何 verifier）

同一份源码在 WSL Ubuntu（Linux, Python 3.11.16, `uv sync --frozen` 自 `uv.lock`）
完整复现了 CI 结果：

```text
LOCAL_WINDOWS   pytest = 442 passed / 0 failed
LOCAL_LINUX     pytest = 6 failed / 436 passed   （与 GitHub CI 逐项一致）
```

对 Linux 重推导日程与 committed 冻结目标日程做只读逐值比对（161 行 × 12 资产 = 1932 个元素）：

```text
rows                               161 == 161
execution_date 索引                完全一致
资产列                             完全一致
max  |Δw|                          2.7996e-05
mean |Δw|                          6.8914e-07
count(|Δw| > 1e-06)                243
count(|Δw| > 1e-04)                0
support（zero ↔ non-zero）变化     0
逐行权重和偏差（max）              2.22e-16
CSV 文本差异行                     54 / 163
```

初步判定：这是上游 ERC（skfolio / scipy / BLAS）求解在不同平台上的数值漂移，
与 [INVALID_RUN R1](INVALID_RUN_S4C_EXECUTION_R1.md) 已登记的同类现象同量级
（该记录在指标层观测到 median `1.46e-06`、max `4.11e-05` 的逐月 ERC 权重漂移）。

**这不构成对差异可接受性的裁决，也不授权放松任何容差。** 差异必须在
`S4C_PORTABILITY_DIAGNOSIS` 有界诊断中被独立分类（`NUMERICALLY_EQUIVALENT` /
`MATERIAL_SOLVER_DIVERGENCE` / `UNRESOLVED`），之后才允许预注册可移植 reproduction 契约。

## 4. 分类

```text
FAILURE_CLASS               = CLEAN_ENVIRONMENT_CORRECTNESS_GATE_FAILURE
ROOT_CAUSE_CLASS (初步)     = PLATFORM_BOUND_EXACT_REPRODUCTION_CONTRACT
                              （solver/BLAS 数值漂移被冻结为逐字节 / 1e-12 精确相等断言）
STRATEGY_SEMANTICS_CHANGED  = NO
FROZEN_ARTIFACT_CHANGED     = NO
```

这不是「CI 配置问题」，也不能通过跳过、xfail、平台条件禁用、删除精确身份检查或
无证据放宽容差来消除。它必须按 `diagnose → classify → preregister contract → correct verifier`
的顺序关闭。

## 5. 临时纠正状态

```text
FOUNDATION_V1_READINESS_STATUS           = READINESS_REVOKED_PENDING_CORRECTION
PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE = FAIL
PROSPECTIVE_FOUNDATION_DECISION            = BLOCKED_BY_PROSPECTIVE_CORRECTNESS
CURRENT_FRONTIER                           = PROSPECTIVE_FOUNDATION_V1_FINAL_CORRECTIVE_CLOSURE
```

只有全部满足后，才可恢复 READY（写入 [Foundation V1 revalidation](PROSPECTIVE_EVIDENCE_FOUNDATION_V1_REVALIDATION_V1.md)，
本文件登记时该 revalidation 尚不存在）：

```text
local deterministic quality gates = PASS
GitHub HEAD CI                    = SUCCESS
S4C clean-environment reproduction= PASS
execution artifact authenticity   = PASS
full integrated dual-candidate drill = PASS
independent review                = PASS
```

## 6. 本 commit 的边界

```text
ALGORITHM_CHANGED        = NO
STRATEGY_CHANGED         = NO
VERIFIER_CHANGED         = NO
FROZEN_TARGET_CHANGED    = NO
CANDIDATE_MANIFEST_CHANGED = NO
OBSERVATION_APPENDED     = NO
REAL_2026_09_DATA_USED   = NO
```

本 commit 只做事实纠正：撤销过早的 readiness，把 frontier 改回更正闭包。

## 7. 更正范围与已执行的 commit

计划范围（均需独立复核）：

```text
Commit B1  S4C clean-environment 数值可移植性诊断（只读，本地 + Linux 证据）
Commit B2  S4C portable reproduction contract（仅在诊断为数值等价且经独立分类后预注册）
Commit C   移除 production execution artifact 的 caller 时间权威（artifact_generated_at /
           future execution timestamp 不得由调用方注入），并证明未来 artifact 不可能被封存
Commit D   一条真正集成的 dual-candidate production-path readiness drill
Commit E   仅在 CI 仍要求时做 bounded 纠正
Commit F   Foundation V1 revalidation 结果与 authority docs 同步
```

已在 `74613246` 之后实际推送的 commit：

```text
3183387  revoke premature foundation readiness after clean-ci failure        (Commit A)
2550f10  add s4c numerical portability diagnostics                            (Commit B1)
677e1d9  extend s4c portability diagnostic with structure and economic materiality (B1.1)
b07299a  remove caller time authority from prospective execution artifact production (Commit C)
35cc57c  add integrated dual-candidate production-path readiness drill        (Commit D)
f135f29  add structural reproduction guard and record frozen-module correction constraint
```

未执行的唯一原因是缺少独立分类：`Commit B2` 与 `Commit E/F` 都以
`S4C_PORTABILITY_DIAGNOSIS = NUMERICALLY_EQUIVALENT`（独立 review）为前提。Codex 不得自行授权。

## 8. 更正范围的实现约束（已核实）

S4C candidate manifest 的 `frozen_identity_artifacts` 把 13 个文件按 CRLF→LF 归一化 SHA-256 冻结，
其中三个是**研究实现文件**，不是数据或配置：

```text
research/experiments/run_s4c_rqalpha_execution_review.py   (00da9343…)
research/experiments/run_s4c_erc_skfolio_transfer.py       (34224359…)
research/experiments/run_s2_rqalpha_validation.py          (446faeba…)
```

逐项复核（`sha256_frozen_repository_text` 与 manifest 逐条比对）：13/13 全部一致（`OK`）。

由此得到一条硬约束：

```text
跨环境 semantic reproduction gate 不能实现在 run_s4c_rqalpha_execution_review.py 内：
  该文件是冻结候选身份的一部分，修改它会使 S4C candidate 完整性校验失败，
  而 manifest 本身在本 Goal 内不得修改。
```

因此 Commit B2（若要实施）必须：

```text
1. 保持 frozen 脚本与其 byte-exact audit 原样（它是与 Windows 数值栈绑定的历史证据路径）；
2. 在**非冻结**的前瞻 verifier（research/experiments/run_s4c_r1_shadow.py）与新 portable
   reproduction helper 中实现可移植 contract；
3. 让 CI 中的 semantic gate 走新 contract，而不是已证明不可移植的「重推导序列化字节相等」；
4. 不删除任何 artifact identity 检查（SHA / 行数 / 起始日期 / 列 / 非负 / 逐行和保持精确）。
```

本轮已先行加入与容差无关的**结构不变量护栏**（`frozen_target_replay.require_structurally_
equivalent_schedule`），它是纯加强：日期集合、资产集合、逐行 support、每行最大权重标的身份与
逐行权重和必须与 committed 日程完全一致，任一不一致即判为经济语义变化。任何 future 数值容差
都不得绕过该护栏；Linux 与 Windows 上该护栏均通过（support change = 0、maximum-weight identity
change = 0）。

## 9. 关联

- 原始结果：[PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md](PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md)（历史，不修改）
- 预注册协议：[PROTOCOL.md](../batches/prospective_evidence_foundation/PROTOCOL.md)（历史，不修改）
- 同类先例：[INVALID_RUN_S4C_EXECUTION_R1.md](INVALID_RUN_S4C_EXECUTION_R1.md)
- 平台移植性背景：[PHASE_A_WINDOWS_NATIVE_PORTABILITY_AUDIT_V1.md](PHASE_A_WINDOWS_NATIVE_PORTABILITY_AUDIT_V1.md)
