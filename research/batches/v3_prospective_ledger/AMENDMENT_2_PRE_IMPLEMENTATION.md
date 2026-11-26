# V3 前瞻台账协议 V1 — 实现前补遗 2

状态：**实现前澄清（架构师治理文档）**。本文件在 `PROTOCOL_V1.md`（commit `5c76846`）与
`AMENDMENT_1_PRE_IMPLEMENTATION.md`（commit `c937b6b`）之后单独提交；后两者的既有字节不改。

## 0. 顺序偏差与审计

独立复核（`B_D_PROTOCOL_REVIEW.md`）在实现前指出 §3/§4/§5 三处阻断。实现者随后提交了
`7885983`、`86aaa0b`、`21c4377` 三个实现 commit，**早于本补遗**。本补遗由架构师在实现者交付后、
任何真实观测之前提交，记录该顺序偏差，并作为后续修正实现的正式契约。

偏差不构成事后调参：截至本补遗漏盘时，真实前瞻观测数 = **0**，没有决策、没有真实日报被写入、
没有初始化生产台账、没有修改任何冻结文件或生产库。已提交的实现只作为 provisional；
最终验收以本补遗之后的修正 commit 为准。若本补遗在 **2026-11-26 00:00 Asia/Shanghai 之前**
提交，最早合格日仍为 **2026-11-26**；若晚于该时刻，最早合格日重置为本补遗提交之后的首个交易日。

## 1. 收盘窗口与合格输入（闭合复核 #3）

- 只接受已确认开市日 `D`。`D` 必须由受信交易日历确认为开市日；日历未知/不可用即拒绝整次运行，
  不写任何 event。
- `generated_at` 必须是带时区的时间；其上海时间必须满足 `D 15:00:00 <= generated_at`。
- 台账实际运行时钟 `now` 必须是带时区的时间；必须满足
  `generated_at <= now < D+1 00:00:00`（上海）。
- 比较真实瞬间，不比较 UTC 日期字符串，不把“同一上海日历日”当作充分条件。
- 休市日、非开市日、日历未知、窗口外：整次拒绝，既有 evidence bytes 不变。
- 不得在当日截止前判 `MISSED`；`MISSED` 只对已过去的开市日派生，且只表示“无合格 SIGNAL”，
  不是一条事件。
- `COMMIT_RECORD.md` 中“其日报也早于协议”的旁证不作为 11-25 不合格的理由；11-25 不合格由
  “协议在收盘后提交 + 当日日报早于协议”共同决定，且本补遗的最早合格日规则独立适用。

## 2. 五类字段白名单（闭合复核 #4）

### SIGNAL
允许键：`brief_schema, report_id, status, actionable, generated_at, expected_next_trade_date,
account_id_source, account_status, decision{evidence_complete, no_action_reason,
suppressed_recommendation_count, trigger_codes}, market_regime, router, deconcentration_state,
data_quality`。

- `decision.trigger_codes` 只允许来自封闭枚举的结构化触发码；若无结构化码，省略该键并在
  `missing_fields` 记 `observation_triggers_text_unprojected`。
- `observation_triggers` 的原始自由文本**不得**进入 SIGNAL；它可能夹带份数或目标价。
- `market_regime/router/deconcentration_state` 只允许状态枚举、布尔与标量；不得含腿、份数、
  价格或可执行订单语义。
- SIGNAL 不得含 `legs`、`quantity`、`price_milli`、`fees_cents`、`executable` 或任何成交字段。

### RECOMMENDATION
`action` 允许键：`priority, kind, code, rank, title, reasons, counter_evidence, triggers,
invalidation_conditions, risk_impact, fees_cents, fees_assumed, legs`。
`legs[i]` 允许键：`side, ts_code, quantity, price_milli, executable`。

- 未知键一律拒绝；`FORBIDDEN_RECOMMENDATION_KEYS` 继续拒绝所有成交/执行字段。
- `legs` 原样保留 `executable`，但不得解释为成交。

### VALUATION
允许键：`brief_schema, report_id, status, generated_at, principal, holdings, concentration,
reconciliation_reminder, data_quality`。

- `holdings[i]` 只允许估值事实：`ts_code, name, quantity, weight, market_value_cents,
  price_milli, bar_quality, price_source, latest_bar_date, diluted_cost_per_share,
  diluted_total_cost_cents, cost_basis`。
- 剔除 `stance`、卖出/换马建议、理由、研究块、动作提示；VALUATION 不得含任何推荐或成交语义。

### UNEXECUTED_REASON
- `reason_code` 使用封闭枚举并拒绝未知值；`reason_note` 非空。
- 只引用同账户、已在账本中的唯一 recommendation；不按代码/日期把成交自动匹配给 recommendation。
- 一个 recommendation 至多一条原因，不得用第二条改写第一条。

### DATA_INSUFFICIENT
- 只写一条 SIGNAL（`evidence_complete=false` + 显式 `missing_fields`），不写
  RECOMMENDATION/VALUATION。
- 不得声称源持仓/腿为空，不得隐含 `count=0`，不得把该日算作可用策略信号。
- MCP 缓存未命中的 `not_ready` 响应不是磁盘 brief；无文件不记 SIGNAL。

## 3. 哈希、批次与写入完整性（闭合复核 #5）

- 每类记录先定义语义 `content`；`content_hash = sha256(record_type + "\n" +
  canonical_json(content))`，其中 `content` **排除** `event_id / ingest_batch / recorded_at /
  prev_event_hash / event_hash / content_hash`。
- `event_id = "V3L-" + content_hash[:24]`；
  `event_hash = sha256(canonical_json(完整持久化行去掉 event_hash))`，覆盖 event_id、时间与批元数据。
- `canonical_json` 固定 UTF-8、键排序、紧凑分隔符；拒绝非有限数值。
- `manifest` / `policy_baseline.json` 的权威来源在初始化时固定；不得被待验 brief 自动改写。
- 写入：单写者锁内先 `verify` 全账，再预检整批：
  - 同自然键 + 同 `content_hash` → 幂等 no-op；
  - 同自然键 + 不同 `content_hash` → 整批拒绝，既有字节不变；
  - 只为新行分配批 ID 与全局 `ordinal=1..count`；
  - `verify` 跨五文件按批分组，拒绝缺序号/重复序号/count 不一致/重复自然键；
  - 锁覆盖检查至最后一次 `fsync`。
- **预检拒绝**：所有文件字节不变。
- **I/O/崩溃**：既有前缀不变，可能留下不完整的新尾；停止写入并报错，不把该次运行算作已完成
  观测；`verify` 发现部分批后拒绝重放，不截断、不覆盖、不静默修复。
- 不宣称可检测“整批尾删”，除非独立保存根/收据。
- 合成测试至少覆盖：同日再生不同 SHA；先 A 再 A+B；跨午夜；14:59 生成/15:01 导入；
  持仓带 `stance`；建议含示意腿；历史成交后撤销；部分批故障；哈希黄金向量。

## 4. 边界

- 本补遗不改变五类事件定义、自然键、append-only、最早合格日或任何安全边界。
- 不部署、不实盘、不建定时器、不使用 Tushare；不写生产 DB；不重跑。
- 本补遗先于**修正实现**；修正实现与测试随后单独提交；独立验收由非实现者完成。
- 实现者已提交的 `7885983`、`86aaa0b`、`21c4377` 作为 provisional 保留在历史中；
  修正 commit 必须逐条满足本补遗，并在报告中说明偏差与修正。
