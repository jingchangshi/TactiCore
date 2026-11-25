# V3 账户前瞻台账预注册协议 V1

状态：**预注册**（本文件先于任何实现单独提交；实现前另以 `COMMIT_RECORD.md` 记录本文件的
实际 commit SHA 与作者时间，以及由此推导的最早合格日）
协议版本：`V3_PROSPECTIVE_LEDGER_V1`
作用域：`V3_OFFENSIVE_LOW_FREQ_SYSTEM` 对应的用户本人东方财富真实账户（`account_id = real-main`）
账本位置：默认 `~/.local/share/tacticore-v3-prospective-ledger/`（可用 `TACTICORE_V3_LEDGER_ROOT` 覆盖）

本协议只定义 V3 账户前瞻证据的**最小记录契约**，不修改任何策略、发布包、冻结身份或生产流程，
不是通用研究治理框架，也不产生任何真实前瞻观测。它与 `S2_R1` / `S4C_R1` 的 prospective
evidence 完全隔离：账户、输入、schema、记录路径均不同。

## 1. 目的与边界

V3 的日报每天给出市场档位、路由状态和精确到整手的动作预案，但"日报说了什么"不等于
"策略被真实执行了什么"。本台账把下列五类事实分别、可复核地固定下来，供以后判断
**V3 规则是否在其适用账户上产生了可执行、可跟踪的前瞻证据**：

```text
signal            规则状态（档位 / 路由 / 减少确认 / 数据质量）
recommendation    下一交易日的动作预案（精确到腿、整手、参考价）
confirmed fill    券商对账单确认的真实成交
unexecuted reason 人类明确给出的"未执行原因"
valuation         账户净值、持仓、集中度与对账提醒
```

本协议**不**评估收益、不批准生产、不创建新策略、不改变 V3 规则、不建立组合候选。
"台账机制可信"不等于"策略有效"或"已获生产资格"。

## 2. 只读输入边界

唯一允许的两个输入面：

1. **FinanceMCP 日报文件**：每日流水线在收盘后生成的 compact brief
   `<ASHARE_PRIVATE_HOST_DIR>/daily-briefs/YYYYMMDD.json`，schema
   `ashare-daily-brief/1.0`。台账只读取该文件字节；不调用 `portfolio-daily-report`、
   `daily`、`investment-research-record` 或任何可能写入的 CLI。
2. **FinanceMCP 私有账户库**：`portfolio.sqlite`（默认
   `~/.local/share/ashare-private/portfolio.sqlite`，可用 `ASHARE_PORTFOLIO_DB_PATH`
   覆盖），只以 SQLite `file:...?mode=ro` 打开，并设置 `PRAGMA query_only = ON`；
   只读 `account_event` 表。绝不写生产 DB，绝不复制 DB 覆盖原文件。
3. 可选只读交易日历：`ashare.sqlite` 的 `trade_cal` 表（同样 `mode=ro`），只用于复核
   "哪些交易日应有日报"，不用于生成任何事件。

brief 文件以一次 `read_bytes()` 读入，解析与 SHA-256 都基于同一份字节；不跟随写入后的二次读取。
若输入缺失、schema 不符、必需字段缺失或时间链不合法，**整次运行拒绝且不写任何 event**。

## 3. 五类事件必须分开

每一行只属于下列一种 `record_type`，并写入各自的 append-only 文件；任何跨类字段混写
（例如把成交结果写进 recommendation，或把 recommendation 当成 fill）一律拒绝。

| 文件 | `record_type` | 语义 | 唯一自然键 |
| --- | --- | --- | --- |
| `signals.jsonl` | `SIGNAL` | 当日规则状态：`v3_cockpit.market_regime`、`router`、`deconcentration` 状态、决策状态与观察触发条件；**不含任何下单数量、价格或成交** | `(account_id, as_of_trade_date)` |
| `recommendations.jsonl` | `RECOMMENDATION` | `execution_plan.actions` 中的每个动作：优先级、代码、理由、腿（方向/代码/数量/参考价/费用/可执行性）；**不含成交、实际仓位或执行状态** | `(account_id, as_of_trade_date, action_code, rank)` |
| `confirmed_fills.jsonl` | `CONFIRMED_FILL` | 仅来自券商对账单确认的 `account_event` 行；**不来自 recommendation，也不来自推断** | `(account_id, account_event.event_id)` |
| `unexecuted_reasons.jsonl` | `UNEXECUTED_REASON` | 人类显式提供的"某条 recommendation 为何未执行"；原因码来自封闭枚举，备注非空 | `(account_id, recommendation_event_id)` |
| `valuations.jsonl` | `VALUATION` | 当日 `principal`、`holdings`、`concentration`、`reconciliation_reminder` 与行情质量；**不含动作建议** | `(account_id, as_of_trade_date)` |

**语义判定**：

- 有 recommendation 不代表有成交；没有 `CONFIRMED_FILL` 就永远不记成交。
- 没有成交也不自动产生 `UNEXECUTED_REASON`；未提供原因只是 `UNRESOLVED`（派生视图），
  不是一条事件。禁止从"没看到成交"反推"用户没执行"或"执行失败"。
- `SIGNAL` 里的 `deconcentration.recommended_sell_shares == 0` 之类字段只作为规则状态摘要；
  真正的动作腿只在 `RECOMMENDATION` 里。构造器对信号/估值字段采用白名单，对
  recommendation 拒绝任何成交语义键（`realized_weights`、`cash_weight`、`execution_status`、
  `fill_*`、`filled_quantity`、`execution_date` 等）。

## 4. 最早合格日、时间链与拒绝回填

- **最早合格日** = 本协议实际 commit 之后的首个交易日（见 `COMMIT_RECORD.md` 的 SHA/时间与
  交易日历依据）。任何 `as_of_trade_date` 早于该日的事件一律拒绝。
- `SIGNAL` / `RECOMMENDATION` / `VALUATION` 只能在**源日报自身的上海日历日当天**追加：
  - `generated_at` 必须时区感知，其上海日历日必须等于 `as_of_trade_date`；
  - `now`（台账实际运行时钟，上海日历日）必须等于 `as_of_trade_date`；
  - `now >= generated_at`；
  - 不满足即拒绝。**当天未运行即永久 MISSED，不得次日补录、不得回填、不得用前一交易日日报替代。**
- `CONFIRMED_FILL` 是外部确认事实，可以晚于 `occurred_on` 导入（券商/用户可能延迟申报）；
  但必须 `occurred_on >= 最早合格日`、`occurred_on <= now`，且只来自 `account_event` 的
  `source = 'broker_statement'`、`reversed_by IS NULL`、`event_type ∈ {TRADE_BUY, TRADE_SELL}`。
  `source = 'synthetic'` 的行永不导入。晚导入真实成交不是回填观测。
- `UNEXECUTED_REASON` 可在事后显式提供：`decided_on >= recommendation.as_of_trade_date`，
  且引用的 recommendation 必须已在账本中。一个 recommendation 至多一条未执行原因；
  不允许用第二条原因改写第一条。
- 失败运行、被拒绝的写入、验证不通过，都不得改变既有 evidence bytes。

## 5. Append-only、幂等键与完整性

每个事件行是独立 JSON object，公共信封固定为：

```text
ledger_version / record_type / event_id / natural_key / account_id / as_of_trade_date
source {kind, identity, sha256, schema_fingerprint|null}
policy {strategy_id, version, content_hash, production_admission}|null
missing_fields[] / ingest_batch {id, ordinal, count}
recorded_at / content_hash / prev_event_hash / event_hash
```

规则：

1. 每种记录只追加到自己的 `.jsonl`；既有行永不改写、删除、重排。
2. `content_hash = sha256(record_type + "\n" + canonical_json(内容))`，其中内容**排除**
   `recorded_at`、`prev_event_hash`、`event_hash`。同一自然键 + 同一 `content_hash` 重复运行
   → 幂等 no-op；同一自然键 + 不同 `content_hash` → 冲突拒绝（例如同日日报被重新生成、
   来源行被改写），不得覆盖。
3. `event_id = "V3L-" + content_hash[:24]`。
4. 每个文件内部形成哈希链：`prev_event_hash` 为上一行的 `event_hash`（首行为 64 个 `0`），
   `event_hash = sha256(canonical_json(除 event_hash 外的完整行))`。
5. 同一 `ingest_batch` 的 `ordinal/count` 必须连续完整；`verify` 发现缺批即报错。
6. `canonical_json` 固定为 UTF-8、键排序、紧凑分隔符，跨机器可复现。
7. 写入使用文本追加 + `flush` + `fsync`，一行一次；崩溃产生的半行由 `verify` 直接报错，
   不做静默修复。

## 6. 显式缺失

- **整份拒绝**：schema 非 `ashare-daily-brief/1.0`；`report_id`/`as_of_trade_date`/
  `generated_at`/`status`/`account_id`/`holdings`/`execution_plan`/`data_quality` 缺失；
  `status` 不在 `ACTIONABLE|ILLUSTRATIVE|NO_ACTION|DATA_INSUFFICIENT`；
  `execution_plan.count != len(actions)`；`status` 与 `no_action_reason` 自相矛盾；
  非 `DATA_INSUFFICIENT` 日缺少 `v3_cockpit` 核心块。拒绝时不写 event，只在 stdout 给出原因。
- **显式缺失字段**：可选但预期存在的字段（如某持仓的 `price_source`、`concentration`、
  `reconciliation_reminder`、某条腿的 `reason`）缺失时，对应值写 `null` 并在
  `missing_fields` 中逐项列出；不允许省略键或写空对象冒充存在。
- `status = DATA_INSUFFICIENT`：允许（且必须）记录一条 `SIGNAL`，带
  `decision.evidence_complete = false` 与显式 `missing_fields`；当日**不**产生
  `RECOMMENDATION` / `VALUATION`。这是诚实的"当日无可用输入"，不是真实观测。
- 无日报的交易日：不产生任何事件；`status --calendar-db` 将其列为 `MISSED`（派生视图）。

## 7. 版本与输入哈希

- `ledger_version` 固定为 `V3_PROSPECTIVE_LEDGER_V1`；`manifest.json` 在初始化时写入
  `protocol_commit`、协议作者时间（UTC 与 Asia/Shanghai）、最早合格日、日历依据与账户。
  manifest 创建后不可修改；与代码常量不一致时拒绝运行。
- 每个 brief 派生事件记录 `source.sha256` = 该 brief 文件的真实 SHA-256，`source.identity`
  含 `report_id`、`generated_at`、schema。
- 每个 fill 记录 `source.sha256` = 该 `account_event` 行 canonical JSON 的 SHA-256，
  `source.identity` 含 `portfolio_sqlite` + `event_id` + DB 行 `recorded_at`，
  `source.schema_fingerprint` = `account_event` 列定义指纹（列名/类型/非空/主键）。
- 每个未执行原因记录输入文件字节 SHA-256。
- `policy` 来自 `v3_cockpit.policy_release`（`strategy_id`、`version`、`content_hash`、
  `production_admission`），逐字段原样记录，不做解释。

## 8. 人工 / 受控运行指引（不自动建定时器）

本仓库**不**新增 systemd/cron/daemon/调度代码，不修改任何生产定时器。人工在每个合格交易日
收盘并等到 FinanceMCP 日报生成后，按下列顺序受控运行（示例日期 `YYYYMMDD`）：

```bash
# 0) 一次性初始化（仅首次；目录 0700）
/…/python -m research.experiments.v3_prospective_ledger init

# 1) 当日日报（必须当天运行；过期即 MISSED，不得补录）
/…/python -m research.experiments.v3_prospective_ledger ingest-brief \
  --brief ~/.local/share/ashare-private/daily-briefs/YYYYMMDD.json

# 2) 券商确认成交（可晚于 occurred_on；只读 portfolio.sqlite）
/…/python -m research.experiments.v3_prospective_ledger ingest-fills

# 3) 显式未执行原因（仅在人类确知原因时；每条引用一条 recommendation）
/…/python -m research.experiments.v3_prospective_ledger ingest-unexecuted-reason \
  --input /path/to/reason-YYYYMMDD.json

# 4) 只读复核
/…/python -m research.experiments.v3_prospective_ledger verify
/…/python -m research.experiments.v3_prospective_ledger status --calendar-db \
  ~/.local/share/finance-mcp-ashare/ashare.sqlite
```

要求：

- 运行顺序为 brief → fills → reasons → verify/status；任何一步失败即停止并报告，不重试写入。
- 同一份 brief 重复运行是幂等的；不同 `report_id` 的同日 brief 是冲突，必须人工复核，
  不得删除旧行或换一份来源重试。
- `ingest-fills` 只读 DB；若发现已导入 fill 在源库被标记 `reversed_by` 非空，打印
  `SOURCE_REVERSED_AFTER_IMPORT` 并建议暂停；不得改写已追加行。
- 台账目录只做备份，不做跨机器重写；不把账户数据提交进 git。

## 9. 复核与暂停建议

- **每次运行后**：`verify` 必须通过；任何哈希链断裂、batch 不完整、schema 漂移、
  自然键冲突都视为完整性失败。
- **每个交易日/至少每周**：`status` 检查 MISSED 日、UNRESOLVED recommendation、显式缺失字段。
- **建议暂停**（停止继续追加并报告所有者，不通过修改既有行修复）：
  1. `verify` 失败或出现来源冲突；
  2. 已导入 fill 被源库撤销（`SOURCE_REVERSED_AFTER_IMPORT`）；
  3. 连续 5 个交易日无合格日报（`MISSED`）；
  4. 存在 3 条以上、且已超过 3 个交易日仍未执行也未给出显式原因的 recommendation；
  5. 日报 `policy_release.content_hash` 与 manifest 记录不一致（规则包被替换）。
- 暂停不等于否定策略；恢复需所有者明确指示并记录恢复原因，历史事件保持不变。

## 10. 质量门与允许的结论

- 实现只能用 `tmp_path` 与合成 fixture 测试；禁止写生产 DB、禁止伪造真实观测、禁止把
  2026-11 之后的真实日报用于测试断言。
- 测试必须覆盖：五类分离；幂等；冲突拒绝；早于最早合格日拒绝；非当日 brief 拒绝；
  缺失字段显式记录；`DATA_INSUFFICIENT` 不产生 recommendation/valuation；
  推荐不生成成交；`synthetic` 与已撤销成交不导入；重复/未知 reason 拒绝；失败写入字节不变；
  哈希链篡改检测。
- 允许的最终决定：`V3_PROSPECTIVE_LEDGER_INFRASTRUCTURE_READY`、
  `V3_PROSPECTIVE_LEDGER_PARTIAL`、`BLOCKED_BY_LEDGER_CORRECTNESS`。

## 11. 明确不做

- 不部署、不上线、不实盘、不新建或修改定时器、不使用 sudo、不使用 Tushare / 泄露 token。
- 不修改 V3 策略、`v3_offensive_policy_release_v3.2.0.json`、冻结身份文件、
  `research/ashare/v3_data.py`、已签 release 或任何 FinanceMCP 生产代码。
- 不产生任何真实前瞻观测：若协议提交后尚无合格的真实日报，账本保持为空，这是预期结果。
- 不把本台账当作生产批准、收益证据或组合候选回放。
