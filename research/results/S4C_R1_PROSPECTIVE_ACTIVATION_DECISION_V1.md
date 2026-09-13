# S4C R1 prospective activation decision V1

本文件记录 Goal `S4C_R1_PROSPECTIVE_SHADOW_ACTIVATION_DECISION`（见
[`docs/goal.md`](../../docs/goal.md)）的 Commit B 裁决。裁决由 C2C 独立审查给出，按预注册协议
[`research/batches/s4c_activation/PROTOCOL.md`](../batches/s4c_activation/PROTOCOL.md) 记录。

ACTIVATION_DECISION: ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW

裁决时间（UTC）：`2026-09-13T17:00:47+00:00`。
裁决性质：**lifecycle / evidence-collection authorization only**。它不是 performance PASS、
不是生产批准、不是组合建议，也不授权修改 `S4C_R1`。

## 1. 冻结与范围

| 项 | 值 |
| --- | --- |
| Candidate | `S4C_R1`（candidate_manifest.json 逐字节未变） |
| 生效预注册协议 | `research/batches/s4c_activation/PROTOCOL.md`（V1） |
| historical cutoff | `2026-08-31` |
| candidate freeze timestamp | `2026-09-13T13:28:15Z` |
| first eligible prospective signal | `2026-09-30` |
| prospective observations | `0` |
| 研究起点 HEAD（Commit A 前） | `2c60f4a` |
| Commit A | `29933f8`（预注册）→ `23c5cf6`、`4c14281`（两项 C2C review 后的 corrective pre-decision commits） |
| Implementation gate | `ACTIVATION_IMPLEMENTATION_GATE = PASS`（对 `4c14281`） |

本 Goal 未创建 real vintage、未产生任何 prospective observation、未检查 `2026-09-30` 之后的
市场结果、未重跑任何历史研究、未修改 S2 的 manifest / 语义 / 日程 / 协议 / 既有 observation、
未创建组合候选、未引入新依赖或新框架。

## 2. Activation Review（15 项）

| # | 问题 | 结论 | 证据 |
| --- | --- | --- | --- |
| 1 | Candidate identity 完整且 immutable？ | YES | manifest SHA-256（归一化）`09469df0ec06d741bee2f176fd1f8334154edafe84afef5b01d889222f6cd908` 与 Commit A 前一致；`verify_s4c_r1_candidate.verify_candidate` 校验策略/执行语义、冻结 hash、PIT 与框架版本 |
| 2 | historical / prospective boundary 无歧义？ | YES | cutoff `2026-08-31`、freeze `2026-09-13T13:28:15Z`、first eligible `2026-09-30`；`verify_prospective_boundary` 强制 first signal 严格晚于 cutoff 与 freeze 日，且必须是自然月末 |
| 3 | first eligible prospective signal 仍合法？ | YES | `2026-09-30` 是冻结后第一个自然月末 canonical 观测日；`validate_month_end` 只以已公布交易日历确认月末 |
| 4 | existing prospective protocol 足够明确？ | YES | `research/shadow/s4c_r1/README.md` + activation PROTOCOL V1 固定 as-of 纪律、vintage 契约、record 契约与复核资格 |
| 5 | data vintage contract 足以避免 future leakage？ | YES | 三件套 vintage、逐值重叠校验、拒绝 as-of 之后行情、拒绝不足整月日历、canonical 位置与目录名强校验（先于任何文件读取） |
| 6 | decision timestamp 与 execution timestamp 分离？ | YES | decision 行 `execution_status=PENDING_NEXT_CANONICAL_OBSERVATION` 且全部执行字段为空；execution 行只能追加且必须晚于 signal date |
| 7 | observation 是否 append-only？ | YES | 25 列 schema 逐字冻结；重复 decision / execution 被拒绝；被拒绝的重跑保持文件字节不变 |
| 8 | decision record 能在 execution result 出现前固定？ | YES | decision 在 signal date 当日或之后写；`record_generated_at` 早于 signal date 被拒绝；runner 不含执行环节 |
| 9 | execution evidence 可后续独立追加？ | YES | `append_execution_record` 要求唯一对应 decision 且 execution_date > signal_date；沿用 RQAlpha 6.3.x 原生语义 |
| 10 | 重跑 idempotent？ | YES | 同一 candidate + signal_date 的同类 record 只允许一条；重复运行失败而非覆盖 |
| 11 | duplicate decision 如何拒绝？ | 拒绝 | `append-only` 契约在写入前逐行比对 `record_type`/`candidate_id`/`signal_date` |
| 12 | candidate integrity failure 与 strategy weakness 分离？ | YES | protocol §7 与 README §9 明确两类失败；短期表现弱不构成修改候选的理由 |
| 13 | 本机 / framework versions 满足 frozen identity？ | YES | skfolio 1.0.6、RQAlpha 6.3.0、VectorBT 0.28.5、pandas 2.3.3、numpy 1.26.4、tushare 1.4.29 实测一致 |
| 14 | 是否存在必须在 activation 前解决的 correctness blocker？ | NONE FOUND | iteration 1–2 的 P1（授权旁路、schema 验证不足、vintage 位置、verdict binding）与 P2 全部关闭 |
| 15 | S2 + S4C 双 shadow 人工成本是否仍合理？ | ACCEPTABLE | 见 §4 |

## 3. 报告字段

```text
CURRENT_CANDIDATE_STATE
  S2_R1  FROZEN / PROSPECTIVE_SHADOW_ACTIVE（唯一既有活动前瞻候选）
  S4C_R1 FROZEN / NOT_ACTIVE（本裁决将其转换为 FROZEN / PROSPECTIVE_SHADOW_ACTIVE）
  S27A   candidate-freeze review eligible / deferred
  S10A   DO_NOT_ADVANCE

CANDIDATE_INTEGRITY
  manifest 未改动；冻结目标 161 行 / SHA-256 f7bf398d…1227e47；冻结语义再推导可逐值重现
  committed schedule；PIT 契约通过；框架版本一致。

PROSPECTIVE_BOUNDARY
  historical cutoff 2026-08-31
  candidate freeze 2026-09-13T13:28:15Z
  first eligible prospective signal 2026-09-30
  不变式 first_signal > cutoff 与 first_signal > freeze date 均成立；
  2026-09-01..2026-09-13 期间已可观察的数据不构成前瞻证据。

DATA_VINTAGE_READINESS
  vintage contract 已冻结；位置、命名、重叠一致性与 no-future-leakage 均由机器校验，
  且位置校验先于任何 vintage 文件访问。本 Goal 未创建任何 vintage。

DECISION_EXECUTION_SEPARATION
  decision 先于执行固定；decision 行不得携带执行结果；execution 只能作为新行追加。

APPEND_ONLY_STATUS
  25 列 schema 冻结；重复写失败；失败重跑不改变文件字节；observations.csv 仍只有表头。

IDEMPOTENCY_STATUS
  同一 candidate + signal_date 的 decision / execution 均唯一，重复运行被拒绝。

DUAL_SHADOW_MAINTENANCE
  ACCEPTABLE（详见 §4）。

ACTIVATION_DECISION
  ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW
```

## 4. 双 shadow 维护评估

| 维度 | S2 R1 | S4C R1 | 合计 |
| --- | --- | --- | --- |
| 决策触发 | signal change driven | 每月 1 次 | 期望约 1 次/月 + S2 状态切换日 |
| 历史提交频率 | 目标变化时（103 个执行日 / 161 个月） | 161/161 个月 | — |
| 人工复核负担 | 状态切换日判断 | 近似机械的月末复核 | 个人投资者可承受 |
| vintage 负担 | 每月最多 1 个 candidate-specific vintage | 同左 | 两个候选各自独立、互不覆盖 |
| 执行证据负担 | 状态切换日的换手 | 常规月度再平衡 | 沿用同一 RQAlpha 原生语义，无新工具 |
| 依赖负担 | 无新增 | 无新增（`skfolio` 已是 research extra） | 无新增依赖 |

结论：负担来自"每月一次机械复核 + 一次 vintage 拉取"，不含方向性判断、不含手工 sizing、
不含新框架；两个候选的 record 目录彼此独立。该负担不构成 `DEFER` 的理由。

## 5. 裁决与边界

```text
ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW
```

理由：

1. 候选身份、边界、vintage 契约、record 契约与失败分离全部通过机器校验与独立审查；
2. `prospective observations = 0` 且 `first_eligible_prospective_signal = 2026-09-30` 未到，
   因此 activation 只开启未来证据收集，不产生任何前瞻结论；
3. activation 由独立 lifecycle artifact 记录，`candidate_manifest.json` 保持
   `prospective_activation = NOT_ACTIVE` 不变；
4. 双 shadow 维护负担仍属月频低维护范围。

明确不构成：

```text
不是 prospective performance 结论
不是生产批准或生产配置
不是 S4C 集中度风险的消除
不是修改 R1 经济语义、参数、窗口、risk measure、fallback 或 solver 的授权
不是创建 S4C_R2、组合候选或 portfolio shadow 的授权
```

集中度保持 `ACCEPT_AS_KNOWN_CANDIDATE_RISK`（P95 最大权重 51.84%、历史最大 66.35%、
median effective assets 6.23、P05 3.24）。前瞻期只**记录**该风险，不添加 cap。

## 6. 下一步（本 Goal 不执行）

下一个 Goal 才是 `S4C_R1_FIRST_PROSPECTIVE_DECISION`，且只能在真实日期到达
`2026-09-30` 及之后、并已有该 as-of 的 candidate-specific vintage 时执行：

```text
freeze vintage → verify candidate → verify activation → derive decision
→ append DECISION → STOP（执行证据在下一 canonical 观测日另行追加）
```

本 Goal 结束时 `observation_count = 0`。
