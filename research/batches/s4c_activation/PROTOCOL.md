# S4C R1 Prospective Activation Protocol V1（预注册）

本协议属于 Goal `S4C_R1_PROSPECTIVE_SHADOW_ACTIVATION_DECISION`
（见 [`docs/goal.md`](../../../docs/goal.md)）。它在**任何真实前瞻运行之前**冻结
activation readiness 的判据、activation lifecycle artifact 的 schema、最小
candidate-specific runner 的行为契约与证据记录契约。

本协议**不**产生 activation 裁决。裁决只能由 Commit B 记录在
[`research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md`](../../results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md)。

## 0. 执行纪律

```text
NO REAL PROSPECTIVE RUN
BEFORE PROTOCOL + IMPLEMENTATION
HAVE BEEN COMMITTED
AND INDEPENDENTLY REVIEWED.
```

在 ChatGPT 明确给出 `ACTIVATION_IMPLEMENTATION_GATE = PASS` 之前，不允许
`create real vintage`、`create real prospective decision`、`append observations.csv`、
或为了研究判断而检视 `2026-09-30` 之后的市场结果。

## 1. 冻结对象（只读输入）

| 项 | 值 |
| --- | --- |
| candidate | `S4C_R1`（`candidate_manifest.json` 逐字节不可变） |
| manifest | [`research/shadow/s4c_r1/candidate_manifest.json`](../../shadow/s4c_r1/candidate_manifest.json) |
| 候选协议 | [`research/shadow/s4c_r1/README.md`](../../shadow/s4c_r1/README.md) |
| observation schema | 已冻结 25 列 `observations.csv`（顺序即契约） |
| historical cutoff | `2026-08-31` |
| candidate freeze timestamp | `2026-09-13T13:28:15Z` |
| first eligible prospective signal | `2026-09-30` |
| 权威执行语义 | RQAlpha 6.3.x 原生 `order_target_portfolio` |
| upstream | 官方 `skfolio==1.0.6` `RiskBudgeting` / `RiskMeasure.VARIANCE` |

invariant：

```text
first_eligible_prospective_signal > historical cutoff
first_eligible_prospective_signal > candidate freeze date
2026-09-01 .. 2026-09-13 已可观察的数据不得成为前瞻记录
```

## 2. Activation 与 Candidate Identity 的分离

- `candidate_manifest.json` 中的 `prospective_activation = NOT_ACTIVE` 是**历史候选冻结身份
  的一部分**，永久保留，不得原地改写为 `ACTIVE`。
- Activation 只由独立 lifecycle artifact
  [`research/shadow/s4c_r1/activation.json`](../../shadow/s4c_r1/activation.json) 表达。
- Activation 不创建 `S4C_R2`，不改变策略/执行/数据语义，不添加集中度 cap。
- Activation artifact **不得**包含自身的 commit hash（避免 self-reference）；实际 activation
  commit SHA 由 `RESEARCH_LEDGER` / `CURRENT_STATE` 在后续 metadata commit 中引用。

### 2.1 Activation State Schema V1（冻结）

`research/shadow/s4c_r1/activation.json` 只允许以下字段：

| 字段 | 含义 |
| --- | --- |
| `candidate_id` | 必须为 `S4C_R1` |
| `candidate_version` | 必须为 `R1` |
| `activation_status` | `ACTIVE`（未激活时文件不存在） |
| `activation_decision_timestamp` | 裁决记录时间（UTC ISO-8601） |
| `activation_protocol_version` | 本协议版本 `V1` |
| `candidate_manifest_sha256` | 冻结文本归一化后的 manifest SHA-256 |
| `historical_cutoff` | 必须等于 manifest 值 |
| `first_eligible_prospective_signal` | 必须等于 manifest 值 |
| `observation_schema_version` | `S4C_R1_OBSERVATIONS_V1` |
| `decision_record_policy` | decision 行写入策略的机器可读摘要 |
| `execution_record_policy` | execution 行写入策略的机器可读摘要 |
| `activation_decision_record` | 本 Goal 裁决文件路径 |

runner 必须校验 artifact 与 manifest 的一致性；任何不一致都是
`CANDIDATE_INTEGRITY_FAILURE`，必须拒绝运行，而不是降级继续。

## 3. Runner 行为契约

唯一新增实现：`research/experiments/run_s4c_r1_shadow.py`（最小、candidate-specific）。

```text
--verify-candidate     只读：校验 manifest、冻结身份输入、PIT 契约、observation schema
--verify-activation    只读：报告 activation 状态；artifact 存在但校验失败则非零退出
--as-of YYYY-MM-DD     前瞻 decision 的显式研究日期（wall-clock 默认值被禁止）
--vintage-dir PATH     candidate-specific vintage 目录
--record-path PATH     仅用于测试的 observations 路径覆盖
```

前瞻写入路径必须依次满足：

1. `verify_candidate`：manifest 身份、冻结 hash、框架版本、PIT 契约全部通过。
2. `require_activation`：activation artifact 存在、状态为 `ACTIVE`、且与 manifest 一致。
3. 显式 `--as-of`：缺失即拒绝，不使用 `datetime.now()` 推断 research date。
4. as-of 边界：`as_of > historical_cutoff` 且 `as_of >= first_eligible_prospective_signal`。
5. as-of 必须是该月最后一个 canonical 交易日（月末 signal）。
6. vintage 校验：三件套齐全；列一致；与冻结历史重叠逐值一致；不含 as-of 之后行情。
7. 冻结语义推导 target：60 条对齐日收益 → 官方 ERC；不足 6 个合格资产则整只 fallback。
8. 记录契约：append-only、duplicate-safe，且 decision 行不得包含任何执行结果。

不实现 scheduler、daemon、notification、broker、generic shadow engine、generic candidate framework。
不引入新依赖。

## 4. Decision / Execution 分离

```text
signal date（月末 canonical 观测日收盘）
  → 追加 decision 行（此时执行结果不可见）
  → 下一 canonical 观测日才可观察 / 回放 RQAlpha 6.3.x 原生执行
  → 另追加 execution 行；不得回写 decision 行
```

- `record_generated_at` 是 decision 写入时间，必须早于任何执行结果可见时间。
- decision 行的 `execution_date` / `realized_weights` / `cash_weight` /
  `portfolio_total_absolute_weight_deviation` / `material_portfolio_tracking_date` /
  `material_asset_differences` / `turnover` / `execution_evidence` 必须为空，
  `execution_status` 必须为 `PENDING_NEXT_CANONICAL_OBSERVATION`。
- execution 行不得改写 decision 行；只能追加，且必须已存在对应 decision。

## 5. Append-only 与 Idempotency

- 同一 `candidate_id` + `signal_date` 只允许一条 `decision` 行。
- 同一 `candidate_id` + `signal_date` 只允许一条 `execution` 行，且必须已有 decision。
- 完全相同的已提交行再次追加必须失败（`NO_OP_ALREADY_RECORDED` 语义），不得 silent duplicate。
- 不得重写、删除、重排或就地更新任何既有行；不得重建历史。
- schema 漂移（列名、顺序、数量不一致）必须拒绝，而不是自动迁移。

## 6. Vintage 契约

```text
research/shadow/s4c_r1/vintages/YYYY-MM-DD/
  etf_adjusted_close.csv
  trading_calendar.csv
  provenance.json
```

- `data/canonical/` 是冻结历史证据，任何情况下不得被后续下载覆盖。
- vintage 与历史区间的重叠价格/日历必须逐值一致；不一致是数据事件，必须停止。
- vintage 不得包含 `--as-of` 之后的行情（拒绝，而不是截断）。
- vintage 日历必须覆盖完整 signal 月；不足该月自然月末不能形成月末 decision。
- 每个 record 至少可追溯 `data_as_of`、`vintage_identifier`、vintage hash、
  manifest hash、`signal_date`、`record_generated_at`。
- 不建设 generic DataVersioning 平台；沿用 S2 已有 vintage 机制的形状。

## 7. 失效与表现偏弱的分离

```text
CANDIDATE_INTEGRITY_FAILURE
  manifest hash mismatch / framework mismatch / activation artifact mismatch /
  wrong vintage / future leakage / schema drift / PIT violation / duplicate record

STRATEGY_PERFORMANCE_WEAK
  负收益 / 跑输基准 / 回撤 / 集中度
```

后者不是修改参数、添加 cap、变更候选或重写协议的理由。集中度
（P95 51.84% / 历史最大 66.35% / median effective assets 6.23）是
`ACCEPT_AS_KNOWN_CANDIDATE_RISK`，前瞻期只**记录**，不修补。

## 8. Activation Review 判据

Commit B 的裁决必须逐条回答：

```text
1.  candidate identity 完整且 immutable
2.  historical/prospective boundary 无歧义
3.  first eligible prospective signal 仍合法
4.  existing prospective protocol 足够明确
5.  data vintage contract 足以避免 future leakage
6.  decision timestamp 与 execution timestamp 分离
7.  observation append-only
8.  decision record 能在 execution 结果出现前固定
9.  execution evidence 可后续独立追加
10. 重跑 idempotent
11. duplicate decision 被拒绝
12. candidate integrity failure 与 strategy weakness 分离
13. 本机 / framework versions 满足 frozen identity
14. 是否存在必须在 activation 前解决的 correctness blocker
15. S2 + S4C 双 shadow 的人工维护成本是否仍合理
```

允许的终局裁决只有：

```text
ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW
DEFER_S4C_R1_PROSPECTIVE_ACTIVATION
REJECT_S4C_R1_PROSPECTIVE_ACTIVATION
BLOCK_S4C_R1_ACTIVATION_CORRECTNESS
```

## 9. 双 shadow 维护预算（review 输入，不是自动通过）

| 维度 | S2 R1 | S4C R1 |
| --- | --- | --- |
| 决策触发 | signal change driven | 每月 1 次 |
| 历史提交频率 | 目标变化时 | 161/161 月 |
| 手工复核 | 状态切换日 | 近似机械的月末复核 |
| vintage | 每月 1 个 candidate-specific vintage | 同左 |
| 执行证据 | 状态切换日的换手 | 常规月度再平衡 |

若合并负担明显超出个人研究系统的低维护目标，`DEFER` 是允许且合法的裁决。

## 10. 测试契约

测试必须使用 fixtures / `tmp_path` / synthetic data，不得修改系统时间，不得运行真实未来
observation。至少覆盖：

```text
candidate manifest unchanged
activation requires correct candidate id
historical cutoff cannot be prospective
freeze day cannot be prospective
pre-eligible signal rejected
first eligible signal accepted by pure validation
explicit as-of required
future data beyond as-of rejected
candidate manifest hash mismatch rejected
framework mismatch rejected
activation artifact mismatch rejected
observation schema drift rejected
duplicate decision rejected
duplicate execution rejected
append-only behavior
decision record cannot contain future execution evidence
runner refuses to write when NOT_ACTIVE
runner refuses real record before first eligible date
```

## 11. 边界

本协议不激活前瞻影子、不生成 observation、不创建 vintage、不修改 manifest、不创建组合候选、
不重跑任何历史研究、不引入新框架。Activation 之后的下一个 Goal 才是
`S4C_R1_FIRST_PROSPECTIVE_DECISION`，且只能在真实 `2026-09-30` 及之后、并已有该 as-of 的
candidate-specific vintage 时执行。
