# Goal: TactiCore — S4C R1 Prospective Shadow Activation Decision + Prospective Readiness Closure

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Execution mode:

```text
Codex with ChatGPT / C2C
```

本 Goal 由用户授权，只回答一个问题：

```text
S4C_R1 是否已经满足全部 activation correctness 条件，
可以从某个明确时刻开始收集未来的 prospective shadow evidence？
```

## 为什么存在这个 Goal

组合层已有历史诊断：`S30 ≈ 9.9%`、固定 `S2_R1 / S4C_R1` 粗粒度混合在主窗口与共同窗口都能达到
约 10% after-cost CAGR（见 [`PORTFOLIO_OBJECTIVE.md`](PORTFOLIO_OBJECTIVE.md) 与
[`PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md`](../research/results/PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md)）。
因此当前最大的研究缺口不是缺少 alpha，而是 `PROSPECTIVE_EVIDENCE_GAP`。

`S2_R1` 已经是 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`。`S4C_R1` 已达到
`FROZEN / NOT_ACTIVE`，已有 candidate identity、历史证据、robustness、RQAlpha authoritative
execution evidence、candidate-freeze review 与预注册前瞻协议，但
`prospective observations = 0`。

本 Goal **不是**：执行第一条 observation、重新研究或优化 S4C、创建 portfolio candidate。

## CRITICAL RESEARCH RULE

```text
NO REAL PROSPECTIVE RUN
BEFORE PROTOCOL + IMPLEMENTATION
HAVE BEEN COMMITTED
AND INDEPENDENTLY REVIEWED.
```

在 ChatGPT 明确给出 `ACTIVATION_IMPLEMENTATION_GATE = PASS` 之前，Codex 不得执行任何可能
`create real vintage` / `create real prospective decision` / `append observations.csv` /
`inspect post-freeze market result for research decision` 的命令。

## External Evidence Gate

本 Goal 不提出新 strategy family、signal、allocator 或 overlay，只对**已经冻结**的
`S4C_R1` 做生命周期 readiness 裁决，因此不创建新的 canonical mapping。

| 项 | S4C_R1 |
| --- | --- |
| Canonical mapping | equal risk contribution / risk budgeting（registry `ERC_RISK_PARITY`） |
| External tier | `E2_ESTABLISHED_METHOD`（成熟构造方法，不是 alpha 主张） |
| External conclusion | 方法成熟；软件可用不等于经济优越 |
| Relevant contradictions | 协方差/相关估计误差、无约束 ERC 的结构性集中度、无杠杆 ETF 实现域 |
| Upstream implementation | 官方 `skfolio` `RiskBudgeting`；RQAlpha 6.3.x 原生执行 |
| Existing TactiCore evidence | RL-030 / RL-031 / RL-033 / RL-037 / RL-040 / RL-042 |
| Remaining local gap | `prospective observations = 0`；第一条真实前瞻 decision 只能在其后真实到达的月末 signal 形成 |
| Research action | `UPSTREAM_COMPARE`（已在冻结身份内完成，本 Goal 不重跑） |

外部成熟证据不构成本地 PASS；本地结论不改变外部 tier。

## PIT Tradability Gate

沿用 RL-031 / RL-033 / RL-034 已关闭的 PIT contract，不重新审计：date-aware universe、
asset lifetime metadata、上市前 fallback 处理、execution price 缺失处理与 strategy inception
（`2013-04-01`）均已建立。本 Goal 不产生新的 execution target，只冻结未来 prospective
decision / execution record 的证据契约。

## 冻结范围（禁止事项）

```text
不修改 candidate_manifest.json（含 prospective_activation 字段）
不原地把 NOT_ACTIVE 改写为 ACTIVE
不创建 S4C_R2；不改变 S4C 经济语义、窗口、risk measure、fallback 或 solver
不添加集中度 cap；不因历史收益或短期表现改参数
不回溯前瞻证据；2026-09-01..candidate freeze 期间已观察的数据不得成为前瞻记录
不模拟 2026-09-30；不预填第一条 record；不使用未来数据
不创建 Blend_R1 / Portfolio_R1；不运行 portfolio shadow；不把 25/75 当 live recommendation
不重跑 Portfolio Objective 10P；不重跑 S2 参数平台；不重跑 S4C 40/60/80
不修改 S2_R1 的 manifest、语义、日程、协议或任何已有 observation
不引入新 quant 框架或依赖；不建设 scheduler、daemon、registry、governance framework
```

## 允许的最终裁决

```text
ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW
DEFER_S4C_R1_PROSPECTIVE_ACTIVATION
REJECT_S4C_R1_PROSPECTIVE_ACTIVATION
BLOCK_S4C_R1_ACTIVATION_CORRECTNESS
```

不使用含糊的 `PASS`。`research priority decision V2` 已选定本 Goal，**不**意味着必须 ACTIVATE。

## Activation 是生命周期决策，不是候选变更

候选身份 `S4C_R1` 已经冻结。Activation 只表示"从某个明确时刻开始，允许未来数据按预注册协议
形成 prospective evidence"。因此：

- `candidate_manifest.json` 必须逐字节不变，包括 `prospective_activation = NOT_ACTIVE`；
- activation 必须由**独立 lifecycle artifact**（候选级、最小、非通用框架）记录；
- activation 不创建 `S4C_R2`，也不修改 `S4C_R1` 的经济身份。

## Activation Review — 必须回答的问题

```text
1.  Candidate identity 是否完整且 immutable？
2.  historical/prospective boundary 是否无歧义？
3.  first eligible prospective signal 是否仍合法？
4.  existing prospective protocol 是否足够明确？
5.  data vintage contract 是否足以避免 future leakage？
6.  decision timestamp 与 execution timestamp 是否分离？
7.  observation 是否 append-only？
8.  decision record 是否能在 execution result 出现前固定？
9.  execution evidence 是否可以后续独立追加？
10. 重跑是否 idempotent？
11. duplicate decision 如何拒绝？
12. candidate integrity failure 与 strategy weakness 是否分离？
13. 当前机器 / framework versions 是否满足 frozen identity？
14. 是否存在任何必须在 activation 前解决的 correctness blocker？
15. 同时维护 S2 + S4C 两个 shadow 的人工成本是否仍合理？
```

## 前瞻边界（必须从 repository 核实）

```text
historical_data_cutoff            = 2026-08-31   （provenance.end_date = 20260831）
candidate_freeze_timestamp        = 2026-09-13T13:28:15Z
first_eligible_prospective_signal = 2026-09-30

invariant:
  first_eligible_prospective_signal > historical cutoff
  first_eligible_prospective_signal > candidate freeze date
```

任何 `2026-09-01 .. candidate freeze` 期间已经观察过的数据都不得成为 prospective evidence。
本 Goal 在 `2026-09-30` 之前执行，因此即使 ACTIVATE，结束时仍必须
`prospective observation count = 0`。

## 记录契约（在未来第一条 record 产生前冻结）

- `observations.csv` 保持 append-only event table，schema 与已冻结 25 列契约逐字一致。
- 每行只能是 `decision` 或 `execution`；同一 `signal_date` 只允许一条 `decision`。
- `execution` 行只能追加在对应 `decision` 之后，不得回写 decision。
- prospective decision 必须显式 `--as-of`，禁止 wall-clock 默认值。
- vintage 必须写入 `research/shadow/s4c_r1/vintages/YYYY-MM-DD/`，不得覆盖 `data/canonical/`。
- vintage 不得包含 `--as-of` 之后的行情；重叠历史必须逐值一致。
- 每个未来 record 至少可记录 `data_as_of`、`vintage_identifier`、canonical input hash、
  candidate manifest hash、`signal_date`、`record_generated_at`。
- 重复 `decision` / 重复 `execution` 必须被拒绝，不得 silent duplicate。

## 两类失败必须分离

```text
CANDIDATE_INTEGRITY_FAILURE   manifest mismatch / framework mismatch / wrong vintage /
                              future leakage / schema mismatch / PIT violation / duplicate
STRATEGY_PERFORMANCE_WEAK     负收益、跑输基准、回撤、集中度
```

短期 performance weakness **不得**触发参数变化、cap、候选变更或协议重写。

## 集中度保持冻结风险

`P95 max asset weight 51.84%`、`historical max 66.35%`、`median effective assets 6.23`、
`P05 effective assets 3.24` 是已登记的已知候选风险（`ACCEPT_AS_KNOWN_CANDIDATE_RISK`）。
Activation review 不允许添加 cap、改变 optimizer / covariance / risk measure / window。
未来 prospective observations 继续**记录**集中度，而不是修掉它。

## S2 + S4C 双 shadow 维护审查

Activation 决策必须显式评估同时运行两个 prospective candidates 是否符合个人研究系统的
低维护目标（S2 为 signal-change-driven；S4C 为 monthly）：combined review frequency、
data refresh burden、execution evidence burden、manual verification burden。
如负担明显不合理，`DEFER` 是允许结果。

## 提交 / 审查顺序

```text
COMMIT A  activation protocol + activation state schema + prospective runner + 契约测试
          （不含 activation 决策结果、不含真实 vintage、不含 observation）
          commit message 例：preregister s4c r1 prospective activation protocol
          ↓
          STOP；Codex 返回 EXECUTED
          ↓
CHATGPT INDEPENDENT REVIEW GATE
          独立读取 git diff / protocol / runner / tests / manifest / observation schema
          给出 ACTIVATION_IMPLEMENTATION_GATE = PASS / FAIL
          FAIL → 返回具体 PLAN；只有 PASS 才允许继续
          ↓
COMMIT B  activation decision 记录（research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md）
          若 ACTIVATE：创建 activation lifecycle artifact，并同步
          RESEARCH_LEDGER / STRATEGY_CATALOG / CURRENT_STATE / docs/goal.md
          ↓
COMMIT C  仅当需要记录 actual activation commit SHA 时使用；不得改变 activation semantics
```

本 Goal 在 `2026-09-30` 之前必须以 `prospective observation_count = 0` 结束。

## 允许的实现面

只实现最小、candidate-specific 的能力：

```text
research/experiments/run_s4c_r1_shadow.py    verify candidate / verify activation /
                                             require explicit --as-of / load candidate vintage /
                                             enforce as-of boundary / derive frozen-semantics target /
                                             build deterministic record / append only if eligible
```

不实现 scheduler、daemon、notification、broker、generic shadow engine 或 generic candidate framework。
只读模式 `--verify-candidate` / `--verify-activation` 允许。`--dry-run` 若存在，必须不 append、
不创建真实 vintage、不产生 research evidence，且只对 synthetic fixtures 使用。

测试必须覆盖：manifest 不变、activation 需要正确 candidate id、historical cutoff 与 freeze day
不能被当作 prospective、pre-eligible signal 被拒绝、first eligible signal 通过纯校验、显式 as-of
必须提供、as-of 之后数据被拒绝、manifest hash mismatch、framework mismatch、activation artifact
mismatch、schema drift、duplicate decision、duplicate execution、append-only、decision record
不得含 future execution evidence、NOT_ACTIVE 时拒绝写入、first eligible 之前拒绝真实 record。
测试使用 fixtures / `tmp_path` / synthetic data，不得修改系统时间，不得运行真实未来 observation。

## Quality Gate

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python research/experiments/run_s2_r1_shadow.py --verify-candidate
uv run python research/experiments/verify_s4c_r1_candidate.py --verify-candidate
uv run python research/experiments/run_s4c_r1_shadow.py --verify-candidate --verify-activation
```

## 边界

本 Goal 不产生生产配置、不创建候选、不启动下一 Goal。组合层 10% objective 是 portfolio
objective，不是优化目标；当前问题是证据，不是缺少 alpha。

## Status: COMPLETED（Commit B activation 裁决完成；本 Goal 未产生任何 observation）

| 项 | 值 |
| --- | --- |
| Starting HEAD | `2c60f4a` |
| 生效预注册协议 | [`research/batches/s4c_activation/PROTOCOL.md`](../research/batches/s4c_activation/PROTOCOL.md) |
| Commit A | `29933f8`（预注册、activation schema、最小 runner、契约测试；无决策、无 vintage、无 observation） |
| Corrective pre-decision commits | `23c5cf6`（canonical-only authorization、完整 lifecycle 校验、canonical vintage 位置）、`4c14281`（位置校验先于任何 vintage 读取、机器可读裁决行绑定） |
| Implementation gate | `ACTIVATION_IMPLEMENTATION_GATE = PASS`（独立 C2C review） |
| Activation 裁决 | `ACTIVATE_S4C_R1_PROSPECTIVE_SHADOW`（见 [activation decision V1](../research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md)） |
| 生命周期表示 | 候选级 [activation.json](../research/shadow/s4c_r1/activation.json)；`candidate_manifest.json` 的 `prospective_activation = NOT_ACTIVE` 保持不变 |
| 冻结候选状态 | S2 R1 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`（未改动）；S4C R1 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE` |
| 前瞻 observation | `0`；`first_eligible_prospective_signal = 2026-09-30` 尚未到达，本 Goal 未创建 vintage |
| 下一 Goal（未启动） | `S4C_R1_FIRST_PROSPECTIVE_DECISION`，只能在真实 `2026-09-30` 及之后执行 |
| 当前前沿 | `AWAIT_FIRST_S4C_R1_PROSPECTIVE_SIGNAL` |

本 Goal 未创建组合候选、未运行 portfolio shadow、未把 25/75 等历史诊断当作 live recommendation、
未重跑 Portfolio Objective 10P、未引入新框架，也未以集中度或时间压力改变 R1 语义。
