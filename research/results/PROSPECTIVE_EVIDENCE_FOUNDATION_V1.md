# Prospective Evidence Foundation V1 — 完成与 readiness 判定

终局判定：

```text
PROSPECTIVE_FOUNDATION_DECISION
  = PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS
```

本文件只记录 Foundation V1 的正确性闭环、当前前瞻证据状态与**未来**真实 cycle 的操作序列。
它**不**产生 observation、**不**创建 vintage、**不**接触真实 2026-09 市场数据，也**不**授权任何
候选人提升、组合候选或新策略工作。

## Repository

```text
STARTING_HEAD   = a3c01c1944c6f6587c086e6169e15865a5c20546
FINAL_HEAD      = f41423b (实现完成点；本文件所在的 closeout commit 紧随其后)
PUSH_STATUS     = 全部实现 commit 已推送；main == origin/main
```

本次 Goal 创建的 commit：

```text
59db93d  bind prospective snapshots to frozen universe identity
6c9fc94  require manifest-frozen snapshot identity before download
03169ac  derive and temporally seal rqalpha execution evidence
72d55eb  derive execution artifacts from native rqalpha output
b7bd36a  extract prospective evidence from native rqalpha analyser output
f41423b  bind execution artifacts to replayed rqalpha observation
```

## C2C gates

独立 C2C review 结论（`docs/protocol.md` 协议状态 + 只读 MCP 复核）：

```text
SNAPSHOT_IDENTITY_GATE                  = PASS
EXECUTION_EVIDENCE_GATE                 = PASS
PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE = PASS
```

三点补充说明：

```text
P1-A 冻结 snapshot 身份    已关闭
P1-B execution temporal seal 已关闭
P1-C artifact → metrics 绑定 已关闭
P1-D native RQAlpha → artifact 生产链 已关闭
```

## Foundation decision

```text
PROSPECTIVE_FOUNDATION_DECISION
  = PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS
```

含义：前瞻证据机制已足以开始收集真实 forward evidence；它**不**意味着 S2_R1、S4C_R1 或任何
组合已具备生产资格。portfolio promotion 仍然禁止。

## Snapshot identity

```text
PRODUCTION_UNIVERSE_SOURCE  = config/universe.csv（唯一授权生产 universe 来源）
UNIVERSE_SHA                = 以 normalized SHA-256 记录在 vintage provenance 的 universe 身份块中
SYMBOL_TUSHARE_MAPPING_STATUS = PASS（symbol → tushare_symbol → configured list date 逐项绑定）
TS_CODE_BINDING_STATUS      = PASS（fund_daily.ts_code 与 fund_adj.ts_code 均绑定冻结 tushare_symbol）
PRODUCTION_START_DATE_POLICY = 只来自 data/canonical/provenance.json；生产 CLI 与 callable 均无覆盖入口
```

实现与测试要点：

```text
freeze_prospective_vintage.py 生产 CLI = --candidate + --as-of + TUSHARE_TOKEN
  （--universe / --start-date 已移除；freeze_vintage() 不再接受 universe / start-date 覆盖）
下载前硬门：config/universe.csv 与 data/canonical/provenance.json 必须仍等于候选 manifest 冻结 hash
  （S2 读 file_hashes，S4C 读 frozen_identity_artifacts；缺失即拒绝）
vintage provenance 新增 universe 身份块：path / sha256 / canonical start_date / 逐标的映射
provenance 验证逐项绑定：record.symbol、record.tushare_symbol、两端点 ts_code、metadata.list_date、
  两端点 request start_date / end_date，以及冻结 universe SHA-256
重复 / 缺失 / 额外 symbol 与 provider 身份互换均被拒绝
mocked Tushare（trade_cal / fund_basic / fund_daily / fund_adj）成功路径覆盖：
  freeze → validate → canonical publish → S2 / S4C decision
```

## Temporal evidence

```text
SIGNAL_CLOSE               = signal_date 15:00 Asia/Shanghai
DECISION_SEAL_RULE         = signal_close <= provenance download_timestamp <= decision_seal_time
                             < next_canonical_execution_boundary（全部为时区感知 instant）
NEXT_EXECUTION_BOUNDARY    = 只由 decision 时点已合法可知的交易所日历推导
EXECUTION_CLOSE            = execution_date 15:00 Asia/Shanghai
ARTIFACT_TIME_RULE         = execution_close <= execution_timestamp <= artifact_generated_at
EXECUTION_RECORD_SEAL_RULE = decision record_generated_at < execution_timestamp
                             <= artifact_generated_at <= execution record_generated_at
```

生产 `decision_seal_time` 与 execution `record_generated_at` 都只能来自 runner 的实际运行时钟；
两者都不存在生产 CLI 覆盖入口。测试通过 monkeypatch runner 时钟复现历史/未来 fixture 时点，
因此 fixture 模式可以模拟未来日期，而**未注入**的 production clock 无法为未来 execution
观测封存 evidence（`tests/test_s2_r1_shadow.py::test_current_clock_cannot_seal_a_future_execution_observation`）。

`execution_date` 不再由调用方给出：它等于 artifact `execution_timestamp` 的上海本地日历日。

## RQAlpha binding

```text
RQALPHA_ARTIFACT_SCHEMA = tacticore.rqalpha.execution_artifact.v2
RQALPHA_PARSER          = parse_rqalpha_execution_artifact / verify_rqalpha_artifact_payload
ARTIFACT_TO_METRICS_BINDING = PASS
S2_EXECUTION_FIELDS   = realized_weights, cash_weight, target_deviation, portfolio_value,
                        drawdown, turnover, execution_status, execution_date
S4C_EXECUTION_FIELDS  = realized_weights, cash_weight,
                        portfolio_total_absolute_weight_deviation,
                        material_portfolio_tracking_date, material_asset_differences,
                        turnover, execution_status, execution_date
```

权威链（生产入口只有一条）：

```text
RQAlpha 原生 sys_analyser + captured order events + replayed_dates
  → extract_native_execution_block（只在 replayed_dates 证明该观测真实发生后才产生 EXECUTED）
  → build_rqalpha_execution_artifact_from_analyser
  → build_rqalpha_execution_artifact_payload（v2 payload）
  → write_rqalpha_execution_artifact（不可覆盖的冻结 artifact + SHA identity）
  → build_execution_record（只接受 decision + evidence identity）
  → verify_execution_row / append_execution_record（每次 append 重新解析并逐值比对）
```

关键不变量：

```text
artifact 内嵌 native facts（order_book_values / total_value / cash / turnover /
  max_drawdown / order events），并被解析器重新推导校验
派生声明（realized weights / cash / turnover / portfolio / drawdown / status / native 说明）
  与 native facts 不一致时，即使重新计算过合法 SHA 也会被拒绝
realized_weights = native market_value / total_value；缺失持仓 = 0 权重
cash_weight = native cash / total_value；空持仓 + 全现金是合法观测
order events 按 native date 列过滤到 execution 当日，其他日期的说明不得污染 evidence
foreign rqalpha_symbol 与持仓/现金不守恒的 native facts 均被拒绝
```

`tacticore/engines/rqalpha_adapter.py`、`research/experiments/run_s2_rqalpha_validation.py` 与
`research/experiments/run_s4c_rqalpha_execution_review.py` 未被修改；它们仍是冻结身份产物。

## Readiness

```text
FULL_PATH_READINESS_DRILL        = PASS
REAL_CYCLE_REQUIRES_CODE_CHANGE  = NO
```

drill（`tests/test_prospective_readiness_drill.py`）在 `tmp_path` 内只用 synthetic 数据跑通：

```text
mock Tushare API
→ freeze S2 / S4C candidate vintage（真实 downloader）
→ 机器验证冻结 universe 映射与 provenance
→ 派生 S2 / S4C decision 并 append
→ 重复 decision 被拒绝且 bytes 不变
→ callback 形状的 native RQAlpha 输出 → 权威 artifact → SHA identity
→ 派生 S2 / S4C execution 行并 append
→ 重复 execution / 缺 decision / 不完整 execution 被拒绝
→ 先前 decision bytes 逐字节未变
```

`tests/test_rqalpha_execution_artifact.py` 另外覆盖 native 抽取层：replay 证明、date 列过滤、
空持仓全现金、foreign symbol、不守恒、覆盖保护，以及“重新算过 SHA 的内部不一致 artifact 仍被拒绝”。

## Candidate integrity

```text
S2_MANIFEST_CHANGED        = NO
S4C_MANIFEST_CHANGED       = NO
S4C_ACTIVATION_CHANGED     = NO
S2_OBSERVATION_COUNT       = 0
S4C_OBSERVATION_COUNT      = 0
REAL_VINTAGES_CREATED      = NO
REAL_SEPTEMBER_DATA_USED   = NO
```

冻结身份检查（Git blob 比较）：

```text
S2_STRATEGY_ECONOMICS_CHANGED     = NO（trend_window / fallback / fees / slippage 未变）
S4C_STRATEGY_ECONOMICS_CHANGED    = NO（ERC 语义、窗口、阈值、fees / slippage 未变）
HISTORICAL_CANONICAL_DATA_CHANGED = NO（data/canonical/* 未被任何 commit 触碰）
S4C_FROZEN_TARGETS_CHANGED        = NO
```

## Quality

```text
PYTEST            = 442 passed / 0 failed / 0 skipped / 0 xfailed / 0 xpassed
RUFF              = ruff check . → All checks passed
FORMAT            = ruff format --check . → 169 files already formatted
MYPY              = Success: no issues found in 20 source files
S2_VERIFY         = PASS（--verify-candidate --verify-no-observations，0 records）
S4C_VERIFY        = PASS（verify_s4c_r1_candidate.py，0 observations）
S4C_SHADOW_VERIFY = PASS（activation_status = ACTIVE，0 observation rows）
FOUNDATION_VERIFY = 无独立 verifier；共享只读校验由上述三个入口覆盖
CI                = 本 commit 不含 CI；见下方 limitations
```

## Nonblocking limitations

以下条目均为已登记的**非阻塞**限制，不构成 correctness 缺口：

```text
1. S4C 候选 README 与 verify_s4c_r1_candidate.py 的 header-only 历史行文差异（RL-046 已登记）。
   它不削弱不可变 manifest / activation 契约，也不影响未来 observation。
2. 真实 RQAlpha execution adapter 目前只在 synthetic native-shaped fixture 上演练；
   第一次真实执行 cycle 将是它在真实输出上的首次使用（这是本阶段的边界，不是设计缺口）。
3. decision-time seal 的下一个 canonical 边界只由当时已合法可知的日历推导；当 vintage 日历
   未覆盖下一开放日时，回退为 signal_date 次日 00:00（更严格的上界）。
4. execution_date 只强制“晚于 signal_date”，不强制等于下一 canonical 开放日：冻结语义本身是
   下界（"不得早于"），延迟执行合法；该判定经独立 review 明确裁定。
5. 尚未建立 credential-free CI；见下方"后续可选工作"。
```

## Future operation

以下序列只被**记录**，本次 Goal 未执行，也不得在 2026-09-30 之前执行。

### EXACT_2026_09_30_DECISION_RUNBOOK

在真实 `2026-09-30`（且仅在该日收盘后）执行：

```text
1.  验证 repository HEAD 与 working tree clean。
2.  验证两个 candidate manifest 与 S4C activation。
3.  用 canonical 冻结 universe 冻结 S2_R1 candidate-specific vintage：
      uv run python research/experiments/freeze_prospective_vintage.py --candidate S2_R1 --as-of 2026-09-30
4.  同法冻结 S4C_R1 vintage（--candidate S4C_R1）。
5.  验证 provenance：source / symbol→tushare 映射 / 两端点 ts_code / 价格与日历 hash /
    timestamp / historical overlap / price_as_of / calendar_as_of。
6.  确认实际运行时刻仍落在合法 decision seal 区间内。
7.  生成 S2_R1 冻结语义 decision：uv run python research/experiments/run_s2_r1_shadow.py --as-of 2026-09-30
8.  生成 S4C_R1 冻结语义 decision：
      uv run python research/experiments/run_s4c_r1_shadow.py --as-of 2026-09-30
9.  append S2 DECISION。
10. append S4C DECISION。
11. 运行只读 candidate / evidence verifier。
12. 运行与该 cycle 相关的 deterministic tests。
13. git diff 检查。
14. git add 仅 candidate vintage 与 decision evidence。
15. commit。
16. push。
17. STOP：不得等待 execution 结果再一起提交 decision。
```

### EXACT_NEXT_EXECUTION_RUNBOOK

在下一 canonical execution 观测真实存在之后（独立 Goal）：

```text
1.  验证先前的 DECISION commit 已在上游。
2.  确认 execution_date 是该 candidate 的合法 canonical execution 日。
3.  用冻结目标运行 RQAlpha 原生 execution（不得重算 target）。
4.  通过生产入口冻结 authoritative execution artifact：
      freeze_prospective_execution_artifact(analyser, order_events, replayed_dates, ...)
5.  artifact_generated_at 必须晚于真实执行观测。
6.  记录 artifact SHA identity。
7.  用批准的 parser 解析 artifact（v2 自洽校验）。
8.  派生 candidate-specific execution metrics。
9.  由 artifact 构造 execution 行（build_execution_record）。
10. 验证 artifact 身份、artifact/row 时间链、candidate、signal date、execution date、metrics 一致性。
11. append EXECUTION。
12. 验证先前 DECISION bytes 逐字节未变。
13. 运行 verifier / tests。
14. commit。
15. push。
16. STOP。
```

### Future options

```text
可选：credential-free GitHub Actions（pytest + ruff check + ruff format --check + mypy +
       只读 candidate verifier）。若加入，必须不调用 Tushare、不需要 TUSHARE_TOKEN、
       不运行真实 RQAlpha research experiment、不产生任何 observation。
```

## Current frontier

```text
CURRENT_FRONTIER = AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE
```

含义：Foundation 开发结束，系统等待真实前瞻时间产生证据。不得在 2026-09-30 之前启动任何真实
decision / execution cycle，也不得在新 alpha、Theme Rotation、S27A 或组合候选上重新开始开发。

## Checklist

```text
VINTAGE_PROVENANCE = PASS
FROZEN_UNIVERSE_IDENTITY = PASS
SYMBOL_TUSHARE_MAPPING = PASS
PRICE_AS_OF_CONTRACT = PASS
CALENDAR_AS_OF_CONTRACT = PASS
SNAPSHOT_ATOMIC_PUBLISH = PASS
S2_CANONICAL_WRITE_PATH = PASS
S4C_CANONICAL_WRITE_PATH = PASS
DECISION_TEMPORAL_SEAL = PASS
LATE_DECISION_BACKFILL_REJECTION = PASS
EXECUTION_TEMPORAL_SEAL = PASS
FUTURE_EXECUTION_PREVENTION = PASS
RQALPHA_ARTIFACT_IDENTITY = PASS
RQALPHA_ARTIFACT_TO_METRICS_BINDING = PASS
EXECUTION_COMPLETE_BEFORE_APPEND = PASS
DECISION_APPEND_ONLY = PASS
EXECUTION_APPEND_ONLY = PASS
FAILURE_BYTE_PRESERVATION = PASS
S2_VERIFIER_FUTURE_COMPATIBLE = PASS
S4C_VERIFIER_FUTURE_COMPATIBLE = PASS
FULL_PATH_READINESS_DRILL = PASS
```
