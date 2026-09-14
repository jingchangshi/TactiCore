# Prospective Evidence Foundation V1 — 预注册协议

状态：**预注册（在 Commit B 实现之前冻结）**
作用域：`S2_R1` 与 `S4C_R1`
协议版本：`PROSPECTIVE_EVIDENCE_FOUNDATION_V1`

本协议在任何实现改动之前冻结。它只定义两个活动候选产生可信前瞻证据所必需的**最小
evidence-control contract**，不是通用研究治理框架。

## 1. 作用域与当前身份

| 项 | S2_R1 | S4C_R1 |
| --- | --- | --- |
| Lifecycle 表示 | 冻结 `candidate_manifest.json`（无 activation artifact） | 冻结 `candidate_manifest.json` + 候选级 `activation.json` |
| 当前状态 | `FROZEN / PROSPECTIVE_SHADOW_ACTIVE` | `FROZEN / PROSPECTIVE_SHADOW_ACTIVE` |
| `prospective observations` | `0` | `0` |
| `historical_cutoff` | `2026-08-31` | `2026-08-31` |
| `first_eligible_prospective_signal` | 由冻结月度语义推导为 `2026-09-30` | 显式冻结为 `2026-09-30` |
| 目标提交政策 | `SIGNAL_CHANGE_ONLY` | `MONTHLY_TARGET_SUBMISSION` |
| 观测表 schema | `research/shadow/s2_r1/observations.csv` 23 列契约 | `research/shadow/s4c_r1/observations.csv` 25 列契约 |

S2 的 first eligible signal 由冻结语义**推导**，不得通过修改 manifest 去显式添加字段。
S4C 的 lifecycle 继续由既有 `activation.json` 表示，不得修改 manifest 或 activation 语义。

本 Goal 不产生任何真实前瞻 observation；两个候选的 observation 计数在结束时必须仍为 `0`。

## 2. Canonical vintage 位置与显式 as-of

```text
research/shadow/s2_r1/vintages/YYYY-MM-DD/
research/shadow/s4c_r1/vintages/YYYY-MM-DD/
```

1. 每个 candidate-specific vintage 目录只允许 canonical 路径；任一外部/非 canonical 路径
   必须在**任何文件读取之前**被拒绝。
2. 生产 decision 路径必须显式提供 `--as-of`，禁止 wall-clock 默认值。
3. vintage 目录已存在时拒绝写入，不得覆盖既有 evidence。
4. vintage 至少包含 `etf_adjusted_close.csv`、`trading_calendar.csv`、`provenance.json`。
5. vintage 不得写入 `data/canonical/`；historical canonical 基线永久冻结。

## 3. Vintage provenance 契约（必须机器验证，而非仅检查存在）

验证必须真正 parse `provenance.json`，并至少回答：

```text
source == 预期的 canonical source（Tushare Pro）
end_date == as-of
相关价格端点的 request end_date == as-of
每个 symbol 的 data_timestamp <= as-of
download_timestamp 存在且时区感知
download_timestamp 与 prospective seal 时间上相容
price 文件 SHA-256 与 provenance 声明一致
calendar 文件 SHA-256 与 provenance 声明一致
行数与 provenance 声明一致
adjustment 语义与候选数据契约一致
universe symbol 集合与冻结 universe 一致
与 historical canonical 的重叠区间逐值一致
不存在 as-of 之后的行情
```

已公布的未来日历行可以用于确定下一个 canonical 日期或月末，但**绝不**作为价格证据。
因此必须显式区分：

```text
price_as_of     价格证据的实际截止日（必须 == as-of）
calendar_as_of  已知交易日历的覆盖上界（可以晚于 as-of）
```

不得因为日历含有未来日期而误判为价格泄漏，也不得因为日历未来日期而允许价格越界。

## 4. Temporal decision seal

采用更严格也更简单的 signal-day seal：

```text
signal_close = 15:00 Asia/Shanghai on signal_date
decision_seal_time 必须时区感知
decision_seal_time 的本地日历日 == signal_date
decision_seal_time >= signal_close
decision_seal_time < 下一个 canonical 交易日起点
provenance download_timestamp <= decision_seal_time
```

下一个 canonical 交易日只由 decision 时点已经合法可知的交易所日历推导。

该契约的唯一目的是让"先看 execution 结果，再回填 signal-date decision"在机制上不可能。
它比必要更严格，但不引入 scheduler、daemon 或 database。

真实 decision cycle 必须在 append 之后 commit + push decision evidence，然后 **STOP**，
早于任何 execution evidence goal。

## 5. Decision 与 execution 是两类 append-only 事件

1. `observations.csv` 保持 append-only event table，schema 与各自冻结契约逐字一致。
2. 每行只能是 `decision` 或 `execution`；同一 `signal_date` 只允许一条 `decision`。
3. `execution` 行只能追加在对应 `decision` 之后，且 `execution_date > signal_date`。
4. decision 行不得包含 execution 结果字段（必须为空或 `PENDING_*`）。
5. 任何被拒绝的写入（重复、越界、schema drift、完整性不足）都不得改变 evidence bytes。
6. 失败运行不能改变 evidence bytes。

## 6. Execution 行完整性（complete-before-append）

execution 行在 append 之前必须完整；**禁止**先写空壳再补字段。至少要求：

```text
record_type = execution
candidate_id
protocol_version
signal_date（必须已存在对应 decision）
execution_date（必须晚于 signal_date）
execution_status
realized_weights
cash_weight
candidate-specific deviation 字段
turnover
execution evidence identity
RQAlpha evidence path/hash
```

候选级字段按各自实际 schema 定义；S2 与 S4C 的观测 schema 继续保持不同。

## 7. 执行权威

RQAlpha 6.3.x 原生执行语义是唯一执行权威。TactiCore 只做：

```text
freeze intended target → run native replay/execution evidence →
parse authoritative output → append evidence
```

不得复制 cash engine、整手、撮合、成本、部分成交或订单生命周期，不得实现 shadow execution
simulator。

## 8. 生产 CLI 授权面

1. 生产路径不得暴露 record-path 覆盖（例如 `--record-path`）或 lifecycle 覆盖。
2. 官方 vintage 只能来自 §2 的 canonical candidate 目录。
3. 只读模式（`--verify-candidate`、`--verify-activation`）保持可用且不得写入。
4. 未来真实 cycle 不得需要临时改代码；需要改代码即视为 foundation 未完成。

## 9. 候选级边界（共享纪律，不共享策略语义）

共享（允许最小 pure validation helper）：

```text
provenance validation
canonical vintage location
temporal seal
append-only event validation
file-hash validation
```

必须保持 candidate-specific：

```text
S2 target derivation / S4C target derivation
candidate manifests
observation schemas
execution rollup 字段
```

任何共享模块必须是 pure validation，且不得包含候选状态机、策略逻辑、scheduler、database、
provider abstraction 或通用研究框架。若抽象没有明显收益，则不抽象。

## 10. Quality gates

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python research/experiments/run_s2_r1_shadow.py --verify-candidate
uv run python research/experiments/verify_s4c_r1_candidate.py --verify-candidate
uv run python research/experiments/run_s4c_r1_shadow.py --verify-candidate --verify-activation
```

若出现新的共享 prospective verifier，运行其只读校验；不得运行真实 observation 模式。

测试必须覆盖：manifest/activation 不变、candidate-specific vintage 路径、外部 vintage 在读取前被拒绝、
provenance source 与 end_date 校验、文件 hash 与行数校验、错误 data timestamp 与未来价格拒绝、
historical overlap drift 拒绝、显式 as-of 必需、pre-eligible 日期拒绝、temporal seal 双向强制、
decision 不含 execution evidence、duplicate decision/execution 拒绝、失败写入字节不变、
不完整 execution 拒绝、无 decision 的 execution 拒绝、完整 execution 接受、S2/S4C schema 保持不同。

所有测试使用 fixture / `tmp_path` / synthetic 数据；**不得**依赖真实 2026-09 市场数据。

## 11. 允许的最终决定

```text
PROSPECTIVE_FOUNDATION_READY
PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS
BLOCKED_BY_PROSPECTIVE_CORRECTNESS
```

## 12. 本协议的边界

- 本协议**不**产生 observation，**不**创建 vintage，**不**接触 2026-09 真实市场数据。
- 本协议**不**修改任一 candidate manifest、activation 语义、策略经济语义、
  historical canonical 数据或已有 observation bytes。
- 本协议**不**授权组合候选、portfolio shadow、S27A/Theme Rotation 或新的 alpha 工作。
