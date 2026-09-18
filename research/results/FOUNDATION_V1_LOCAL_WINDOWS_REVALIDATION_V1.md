# Foundation V1 本地 Windows 独立 revalidation 审计 V1

本文件是 `PROSPECTIVE_EVIDENCE_FOUNDATION_V1_FOR_S2_AND_S4C` READY 判定的**独立对抗性验证审计**。
它只执行既有验证链并复核冻结 identity，不修改任何实现代码、不修改任何候选身份、
不创建 vintage、不产生 observation、不接触真实 2026-09 市场数据。

## 1. 审计动机与范围

[Foundation V1 revalidation](PROSPECTIVE_EVIDENCE_FOUNDATION_V1_REVALIDATION_V1.md)（RL-050）恢复
READY 的依据包含「本地 Windows 亦为 462 passed」的声明，但该声明发布后本地开发环境事实未再被验证。
本审计在独立会话中回答一个狭窄问题：

```text
Foundation V1 READY 的全部本地判据，今天是否仍可在本地 Windows 上完整重现？
```

范围：CI 同构验证链 + 冻结 identity 逐项复核 + 诊断产物数值交叉核对。
超范围（未做）：任何实现修改、任何候选修改、任何新策略或新基础设施工作。

## 2. 起点与环境事实

```text
AUDIT_BASE_HEAD = ab8916b1fdd574e01479dcb53fe62714e01aa81d
                  （governance closeout "record foundation v1 revalidation and restore ready frontier"，
                    origin/main == main，working tree clean）
分支策略          = 仓库为单分支 main 工作流，本审计按仓库惯例提交至 main
CI 参照           = GITHUB_CI_RUN_ID 34873004632 @ c70e74e（revalidation §6）
```

审计开始时发现的环境事实（**非仓库缺陷**）：

```text
.venv 失效：其 python.exe 指向 uv 管理的 CPython 3.11.15，该解释器已不存在
```

修复方式：`uv sync --extra dev --extra research`（uv 按 `.python-version` 重新供给
CPython 3.11.16 并从 `uv.lock` 重建全部依赖，与 CI 的 Python 3.11 同版本）。
修复只作用于 gitignored 的本地 `.venv`，仓库文件零改动。

## 3. 验证链结果（命令矩阵）

全部命令在本地 Windows（pwsh 7.6.6）实际执行；exit code 为进程真实返回码。

```text
#  命令                                                                  exit  关键结果
1  uv sync --extra dev --extra research                                  0     CPython 3.11.16 + uv.lock 全量重建
2  uv run ruff check .                                                   0     All checks passed!
3  uv run ruff format --check .                                          0     177 files already formatted
4  uv run mypy                                                           0     no issues found in 20 source files
5  s4c_numerical_portability_diagnostic.py                               0     within_contract = true（见 §4）
   --output <tmp> --environment-label local_windows_dsh_r1
6  uv run pytest -q                                                      0     462 passed / 0 failed / 0 skipped（85.39s）
7  run_s2_r1_shadow.py --verify-candidate                                0     manifest/历史边界/PIT/append-only 校验通过；observation=0
8  verify_s4c_r1_candidate.py --verify-candidate                         0     校验通过；observation=0；activation=NOT_ACTIVE（manifest 历史身份）
9  run_s4c_r1_shadow.py --verify-candidate --verify-activation           0     校验通过；activation_status=ACTIVE；observation=0
```

与 [revalidation §6](PROSPECTIVE_EVIDENCE_FOUNDATION_V1_REVALIDATION_V1.md) 的 clean Linux CI
（`pytest = 462 passed`、ruff PASS、mypy PASS、三项 candidate verification PASS、无跳过步骤）
逐项对照：**全部一致，无任何 mismatch**。

## 4. S4C 数值可移植性诊断交叉核对

本地新产生的诊断（`environment_label = local_windows_dsh_r1`，`read_only = true`，
`artifacts_modified = []`）与 committed Linux 基线
[S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LINUX_V1.json](S4C_NUMERICAL_PORTABILITY_DIAGNOSTIC_LINUX_V1.json)：

```text
                                    本地 Windows（本次）          committed Linux 基线
contract                            S4C_PORTABLE_REPRODUCTION_CONTRACT_V1   （同）
elements_compared                   1932                          1932
elements_exceeding_tolerance        0                             0
maximum_absolute_delta              1.1102230246251565e-16        2.7996468267524333e-05
within_contract                     true                          true
returns_window_sha256               450a6619…481903c              450a6619…481903c   （逐位一致）
observed_normalized_sha256          f7bf398d…1227e47              f7bf398d…1227e47   （逐位一致）
```

解读：求解器输入指纹（`returns_window_sha256`）跨环境逐位一致，本地重推导与冻结目标在
机器精度级一致（1.11e-16，冻结目标本就在 Windows 域推导）；Linux 路径的 2.80e-05 差异保持
在预注册契约 `SCHEDULE_WEIGHT_ABS_TOL = 1e-4` 内（safety factor ≈ 3.57×）。跨环境
`NUMERICALLY_EQUIVALENT` 分类在本地独立复现。

## 5. 冻结 identity 独立复核

```text
S4C manifest frozen_identity_artifacts   13/13 SHA-256 一致（项目官方 CRLF→LF 规范化口径）
S4C 冻结目标                             research/results/s4c_pit_corrected_frozen_targets_v1.csv
                                         = f7bf398d…1227e47，未变
S2 observations.csv                      1 行（仅表头），observation_count = 0
S4C observations.csv                     1 行（仅表头），observation_count = 0
vintages/ 目录（S2/S4C）                  均不存在
execution_artifacts/ 目录（S2/S4C）       均不存在
git diff ab8916b -- research/shadow/ data/canonical/ tacticore/strategies/   空（无改动）
```

口径说明：manifest 哈希按项目官方 verifier 的
`sha256_frozen_repository_text`（CRLF→LF 规范化）计算；用原始工作树字节计算会在
`core.autocrlf=true` 的 Windows 上对 11/13 个文本文件产生假 MISMATCH，这是审计方法差异，
不是仓库状态差异。最终 13/13 以官方口径复核通过。

## 6. Gate 对照结论

对 [revalidation §7 gate table](PROSPECTIVE_EVIDENCE_FOUNDATION_V1_REVALIDATION_V1.md) 中
由本地可执行证据支撑的 gate（LOCAL_QUALITY_GATE、S4C_CROSS_PLATFORM_REPRODUCTION、
S4C_PORTABILITY_CONTRACT、FROZEN_CANDIDATE_IDENTITY、S4C_FROZEN_ARTIFACT_IDENTITY、
PROSPECTIVE_PURITY、DECISION/EXECUTION_APPEND_ONLY 的当前状态、FULL_PATH_READINESS_DRILL、
GITHUB_CI_GATE 参照）逐项复核：

```text
FOUNDATION_V1_LOCAL_WINDOWS_REVALIDATION_GATE = PASS
NEW_CORRECTNESS_BLOCKER_FOUND                 = NO
```

READY 判定的本地判据今天完整重现。本审计**不产生**新的研究结论，不改变任何候选资格，
不构成生产批准，也不改变 `FROZEN_PENDING_REAL_PROSPECTIVE_TIME` 的开发冻结状态。

## 7. 已知限制

- 本审计只覆盖当前本地 Windows 环境；clean Linux CI 证据（run 34873004632）仍是历史参照，
  本次未触发新 CI 运行（本 commit 推送后 GitHub Actions 将自动给出新一轮 CI 证据）。
- pytest「无跳过」由 `-q` 输出统计行（`462 passed`，无 skipped 计数）确认，与 CI 的
  「无跳过步骤」声明一致。
- 环境修复（uv 重供给 Python 3.11.16）是本地事实，不属于仓库可审计内容；记录于此仅为完整披露。

## 8. 下一步

唯一前沿保持 `AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE`。
在真实 `2026-09-30` 收盘数据合法可得之前，不启动任何前瞻 decision cycle、不修改冻结候选、
不开始新策略工作。下一个自然检查点是推送后 CI 是否再次 SUCCESS；若失败，按
RL-049 先例以可执行证据撤销/更正，不得以「让 CI 变绿」为由跳过测试或放宽容差。
