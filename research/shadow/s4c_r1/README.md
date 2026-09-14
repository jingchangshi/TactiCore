# S4C R1 候选身份与前瞻协议 V1（已预注册，未激活）

本目录只服务冻结的 `S4C_R1`。候选的机器可验证身份见 [candidate_manifest.json](candidate_manifest.json)。

**当前状态：`FROZEN / NOT_ACTIVE`。** 候选身份与前瞻协议已经预注册，但**没有**前瞻失败观测被收集、没有被回填、没有 runner 在运行；`observations.csv` 只有表头。

## 1. 不可变身份与顺序版本规则

任何更改 S4C 的经济语义、风险度量、预算、约束、min eligible、收益窗口、风险 universe、fallback、信号或执行时点、目标提交政策、缺失值口径、成本、PIT 契约或 RQAlpha 原生执行政策的工作，均**不得**继续称为 S4C R1，必须创建下一顺序候选版本（R2、R3……）并保留 R1 文件不改写。

判据（`FROZEN_IDENTITY_INVALIDATED`）：manifest 校验失败、实现不再匹配 manifest、canonical 语义变化、资产不可用而使候选语义失效、RQAlpha 原生语义不兼容，或确认实现 bug 使记录并非 R1。

**不得**因为历史收益、短期前瞻回撤或与基准的短期偏离而修改 R1。

## 2. 历史截止与前瞻边界

```text
historical_data_cutoff        = 2026-08-31   （canonical 快照截止，provenance.end_date = 20260831）
candidate_freeze_timestamp    = 2026-09-13T13:28:15Z
first_eligible_prospective_signal = 2026-09-30
```

**不得回溯前瞻证据。** 冻结时点之前就已经可观察的数据或市场结果不能成为真正前瞻证据。冻结当天（`2026-09-13`）之前的任何 2026 年 9 月观测都不得回填成前瞻记录。

`2026-09-30` 是**严格晚于**冻结时点的第一个合格月末 signal（下一个自然月末）。因此第一条合法前瞻 decision 只能在 `2026-09-30` 月末收盘后形成，并在其后的下一 canonical 观测日才可观察执行——前提是届时已有真实 candidate-specific vintage。本文件不产生也不需要第一条记录。

## 3. 候选专属 vintage 与不可变历史

`data/canonical/` 始终是 R1 的冻结历史证据，**不能**为后续下载覆盖。每次前瞻拉取都必须写入候选专属目录：

```text
research/shadow/s4c_r1/vintages/YYYY-MM-DD/
```

该目录在首次真实拉取时才创建。vintage 应包含 `etf_adjusted_close.csv`、`trading_calendar.csv` 与 `provenance.json`。

如果与历史区间重叠，重叠价格与日历必须**逐值一致**；不一致是数据事件，不得静默覆盖或修订 R1 历史。

## 4. as-of 纪律

- 前瞻决策必须提供显式 `--as-of`，不得使用 wall-clock 默认值。
- `--as-of` 必须是该月最后一个 canonical 交易日（signal date）。
- vintage 不得包含 `as-of` 之后的行情；出现即拒绝，而不是截断后继续。
- vintage 日历必须覆盖完整 signal 月；不足该月自然月末的日历不能形成月末决策。
- 禁止把未来价格纳入信号；月末确认只使用已公布的交易日历。

## 5. 决策与执行时序

```text
月末 canonical 观测日收盘
  → 只用该时点可得的冻结历史 + 单一 prospective vintage
  → 估计 60 条对齐收益的 ERC target
  → 立刻追加一条 decision record（此时执行结果尚不可见）
  → 下一 canonical 观测日才可观察/回放 RQAlpha 6.3.x 原生执行
  → 另追加 execution evidence 行；不得回写 decision record
```

- `signal_date`：月末 canonical 观测日。
- `record_generated_at`：decision record 写入时间，必须早于任何执行结果可见时间。
- `execution_date`：最早为 `signal_date` 后的下一 canonical 观测日。
- decision 必须在后续执行或组合结果可见**之前**形成。不得把已知结果回填为"当时"的决策。

## 6. append-only 记录契约

`observations.csv` 是 append-only 的 Git-friendly 事件表。固定列 schema（顺序即契约）：

```text
record_type,candidate_id,protocol_version,record_generated_at,data_as_of,vintage_identifier,
historical_manifest_hash,prospective_data_hash,signal_date,eligible_asset_count,regime,
maximum_weight,effective_number_assets,target_changed,desired_targets,action_required,
execution_date,execution_status,realized_weights,cash_weight,
portfolio_total_absolute_weight_deviation,material_portfolio_tracking_date,
material_asset_differences,turnover,execution_evidence
```

规则：

- 每行要么是 `decision`，要么是 `execution`，不得混合。
- 同一 `signal_date` 只允许一条 `decision`；重复追加必须失败，而不是覆盖。
- `execution` 行只能追加在对应 `decision` 之后，不得修改或删除 decision 行。
- 不得重写、重建或改写旧 decision；不得重构历史。
- 不得自行重建 RQAlpha 的会计、撮合或成交数据；只保存框架原生结果引用/压缩字段。

当前只有表头，表示**尚无真实前瞻月末决策**，而不是零收益。

## 7. 两类执行偏离必须分别记录

```text
material_asset_difference
= 单个资产在某个 execution date 上的 |intended_weight - realized_weight| > 5pp

material_portfolio_tracking_date
= 某 execution date 上组合层 total absolute weight deviation > 5pp
```

两者**必须**在 `observations.csv` 中分别命名、分别记录：

- `material_asset_differences`：JSON 数组，元素含 `symbol` / `intended` / `realized` / `native_evidence`。
- `material_portfolio_tracking_date`：布尔或空字符串，配合 `portfolio_total_absolute_weight_deviation`。

历史审查中两者恰好共用同一个 5pp 阈值，但**不是同一个量**：组合层跟踪日期数（历史 3/161）多于单资产差异条目数（历史 2）。因此**不得**声称"每个组合层跟踪日期都有已记录的原生单资产原因"。

本定义只适用于未来候选前瞻协议；历史接受的结果与 V2 gate 不因本说明改变。

## 8. 复核资格与审查范围

以下阈值在**任何观测产生之前**冻结，不得在事后按表现选择：

```text
中期完整性复核（integrity only）
  资格：≥ 12 个日历月，且 ≥ 10 条真实前瞻 decision record
  范围：只检查完整性、执行、维护负担与定性一致性
  不构成：生产批准、收益结论

production-candidate review 资格
  资格：≥ 24 个日历月，且 ≥ 20 次真实月度 execution event
  范围：收益/风险一致性、回撤、集中度行为、执行偏离、换手、维护负担、意外失败
  不设预设 CAGR / Sharpe / 超额收益门槛
```

经济理由：S2 R1 用"真实 target-change 执行事件"作为门槛，因为趋势信号的**状态变化**是它的独立下注单位；S4C 每月都提交目标（历史 161/161 个月），因此它的独立下注单位是**每月执行事件本身**。用执行事件而非状态变化表达门槛才与 S4C 的经济结构一致。

同时不把门槛压低：ERC 的核心前瞻风险是**协方差估计误差**，它随市场状态缓慢变化，需要多个不同波动/相关状态才能形成有意义的样本外读数，所以采用 24 个日历月而非跟随 S2 的 18 个月。

## 9. 失效与表现偏弱的分离

```text
FROZEN_IDENTITY_FAILURE（候选完整性失效）
  仅可由第 1 节判据触发。
  在最短复核期之前唯一可以导致 CANDIDATE_INVALIDATED 的原因。

STRATEGY_PERFORMANCE_WEAK（策略表现偏弱）
  连续亏损、短期回撤、跑输基准。
  **不是**修改、提前失效或优化 S4C R1 的理由。
```

短期亏损不得触发候选优化。候选完整性失效与策略表现偏弱必须分别记录，不得互相代替。

## 10. 已知风险（冻结，不优化）

集中度是**已知候选风险**，裁决为 `ACCEPT_AS_KNOWN_CANDIDATE_RISK`：

```text
median maximum weight           26.94%
P95 maximum weight              51.84%
historical maximum weight       66.35%
months any asset > 50%          9
median effective assets         6.23
P05 effective assets            3.24
```

前瞻期必须**观测**这一风险，但不得为了降低它而添加 cap、改变 solver、替换 risk measure 或改 fallback。那属于新策略版本，不是 R1。

## 11. 明确不建设

禁止：scheduler、daemon、database、candidate registry service、notification system、broker integration、新执行引擎、通用候选治理框架。

## 12. 当前边界

本 Goal 只冻结身份并预注册协议。它**不**激活前瞻影子、**不**采集 observation、**不**创建 vintage。

身份一致性校验：

```bash
uv run python research/experiments/verify_s4c_r1_candidate.py --verify-candidate
```

## 13. Foundation V1 证据契约（实现更新，不改写候选历史）

本节只记录在预注册
[Foundation 协议](../../batches/prospective_evidence_foundation/PROTOCOL.md) 之后新增的
evidence-control 实现事实；第 1–12 节描述的候选身份、语义与生命周期保持不变。

```text
canonical vintage 位置   research/shadow/s4c_r1/vintages/<as-of>/；外部目录在读取任何文件之前被拒绝
provenance              source == Tushare Pro、end_date == as-of、fund_daily/fund_adj request end_date
                        == as-of、symbol 集合 == 冻结 universe、provenance 声明的 price/calendar
                        SHA-256 与行数 == 实际文件、adjustment 语义 == 冻结数据契约
price_as_of             逐标的最晚 data_timestamp 的最大值；必须 == as-of，且不得存在 as-of 之后行情
calendar_as_of          已公布交易日历覆盖上界；可以晚于 as-of，但只用于确认月末与下一个
                        canonical 日期，绝不作为价格证据
signal_close            signal_date 15:00 Asia/Shanghai
temporal seal           signal_close <= provenance download_timestamp <= decision_seal_time
                        < next_canonical_execution_boundary；decision_seal_time 的上海本地日历日
                        必须等于 signal_date，且只能来自 runner 的实际运行时钟
decision 行             不含任何执行结果字段；同一 signal_date 只允许一条，重复写入失败且不改 bytes
execution 行            append 前必须完整（执行日、状态、realized weights、cash、组合层与单资产
                        deviation、turnover、RQAlpha evidence path + SHA-256）；无 decision 不得追加
CLI 授权                 不暴露 --vintage-dir / --record-path / --activation-path / --generated-at；
                        vintage 位置由 --as-of 推导，record 目的地固定
```

只读校验分两级：`--verify-candidate`（候选身份，合法前瞻 observation 产生后仍然有效）与
`--verify-no-observations`（首个真实 cycle 之前的阶段性状态）。快照冻结由
`research/experiments/freeze_prospective_vintage.py --candidate S4C_R1 --as-of <date>` 负责，
它复用既有 Tushare downloader、拒绝覆盖既有 evidence，并在落盘前完成 provenance 校验。
