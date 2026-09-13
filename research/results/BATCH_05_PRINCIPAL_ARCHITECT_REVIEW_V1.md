# Batch 05 principal architect review V1

独立 Principal Architect 复核 Batch 05 冻结证据、Windows 开发引导与当前权威文档后的阶段决定。本记录不重跑、不修改任何 Batch 05 结果、frozen target、策略语义或 S2 候选。

## 复核证据

- [Batch 05 阶段汇总](BATCH_05_EARNED_STAGE_VALIDATION.md)。
- [S27A execution review V2](S27A_RQALPHA_EXECUTION_REVIEW_V2.md) 及其 4 个 machine artifacts（161 个 PIT-legal frozen targets、native summary、target tracking、material differences）。
- [S10A execution review V1](S10A_RQALPHA_EXECUTION_REVIEW_V1.md) 及其 machine artifacts（含 1 个 native cash rejection）。
- [S4C robustness V1](S4C_ROBUSTNESS_V1.md) 及 summary / periods / rolling / costs / concentration artifacts。
- [S2 R1 前瞻协议](S2_R1_PROSPECTIVE_PROTOCOL_V1.md)、[candidate manifest](../shadow/s2_r1/candidate_manifest.json)、[observations](../shadow/s2_r1/observations.csv)。
- `docs/ARCHITECTURE.md`、`docs/RESEARCH_RULES.md`、`docs/RESEARCH_LEDGER.md`、`docs/STRATEGY_CATALOG.md`、`docs/STRATEGY_RESEARCH_MAP.md`、[外部证据 registry](../strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml)。
- Batch 05 protocol 序列（`PROTOCOL.md`、`PROTOCOL_V2.md`、`PROTOCOL_V3.md`）与 commit 顺序。
- Windows 开发环境实测：Python 3.10.21 / 3.11.15 / 3.12.14 隔离解析与同仓库 mypy 运行。

## 协议有效性

Protocol freeze `0450799`、V2 `1028dea`、V3 `6ce67f6` 三个提交均早于唯一被采纳的结果提交 `6acaab7`；V1/V2 运行以 `INVALID_RUN` 保留，V3 全量 rerun 是唯一权威结果。参数维度、gates、comparators 与 stop conditions 均在结果可见前预注册。S2 R1 未被本批判定触及。

## Windows 开发引导处置

`WINDOWS_NATIVE_STATUS = B_SUPPORTED_WITH_MINIMAL_PORTABILITY_FIXES`。已存在的 CRLF frozen-text 归一化（`sha256_frozen_repository_text`）满足 LF/CRLF 等价、真实内容变更仍改变 hash、raw hash 不归一化且冻结产物不变，因此不重写、不复制。

失败分类：`uv run mypy` 的失败是 resolver/toolchain skew，不是项目 typing 缺陷，也不是覆盖冻结候选的语义问题。同一源码在 Python 3.10.21 与 3.11.15 下解析到 `numpy 1.26.4` 并通过；Python 3.12.14 只能解析到 `numpy 2.5.3`（`rqalpha>=6.3.0` 在 `python>=3.12` 上要求 `numpy>=2.0.0`），其 stub 使用 PEP 695 `type` 语法，mypy 在 `python_version = "3.10"` 目标下无法解析。

处置：新增根级 `.python-version`（`3.11`）固定仓库开发与验证解释器；`README.md` 记录运行时范围（3.10–3.12）、验证解释器（3.11）与完整引导命令。`requires-python`、Ruff `py310` 与 mypy `python_version = "3.10"` 保持不变；未引入 lockfile、未改变依赖边界、未弱化第三方或项目检查。不采用“收窄 `requires-python`”，因为 3.12 的应用兼容性并未被否定，收窄会把开发期工具链不兼容误记成运行时不支持。

引导命令的实测补充：`uv sync --extra dev` 不包含 skfolio，会使 S4C 测试因缺少 skfolio 失败；因此完整引导为 `uv sync --extra dev --extra research`。

## 阶段决定

- **S2**：保持 `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`，且仍是唯一活动前瞻候选。manifest、冻结输入 hash 与 `observations.csv`（仅表头、0 条 decision record）均未改动。
- **S27A**：`ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW` 资格保留，但本里程碑**推迟** candidate-freeze review，不拒绝。理由：S27A 复用 S2 的 200 有效观测趋势信号，仅以 inverse-vol 重分配已激活 sleeve，与当前唯一前瞻候选的经济机制重叠度高；在 S2 仍在积累前瞻证据时冻结第二个趋势型候选，边际信息低于 S4C 执行证据且增加污染风险。
- **S10A**：维持 `DO_NOT_ADVANCE_S10A_EXECUTION`。冻结的零 cash-rejection gate 被一个 native rejection 触发，且无后续被采纳证据推翻；不得以本地现金缓冲、手工 sizing、retry、备用订单序列或参数修补重开。
- **S4C**：`ADVANCE_S4C_TO_EXECUTION_REVIEW` 资格成立，并被选为本里程碑之后的唯一下一 Goal。未决问题是权威执行可实现性，而非参数问题；ERC/risk budgeting 机制与 S2 趋势暴露正交性更高。集中度证据保留为执行审查的诊断输入：P95 max weight 51.84%、maximum 66.35%、median 26.94%、9 个月任一资产超过 50%、effective assets median 6.23 / P05 3.24。

## S27A 与 S4C 比较

| 维度 | S27A candidate-freeze review | S4C authoritative execution review |
| --- | --- | --- |
| 已获资格 | candidate-freeze review | execution review |
| 与 S2 机制重叠 | 高：同一 200 有效观测趋势信号，仅 sizing 不同 | 低：风险预算配置，不含趋势信号 |
| 未决问题 | 候选身份、冻结清单与前瞻协议准备 | RQAlpha 原生执行保真、目标跟踪与现金行为 |
| 新增证据类型 | 流程性冻结，几乎不产生新经济证据 | 新的执行、整手、现金、成本与集中度证据 |
| 实现自由度风险 | 中：候选边界定义需要判断 | 低：targets 已冻结，只做 replay |
| 结论 | eligible but deferred | 选为唯一下一 Goal |

排序依据是阶段就绪度、机制正交性与新信息价值，不以历史 CAGR 排序；两者都不构成候选、前瞻或生产批准。

## 外部证据

未修改 [外部证据 registry](../strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml)（`evidence_as_of: 2026-09-11`）。其内嵌的 S27A/S10A/S4C `local_status` 是 Batch 03 时点快照，落后于本地冻结产物；本地生命周期的归属在 ledger / catalog / research map / current state。本地 PASS/FAIL 不改变外部 tier，因此该时点差异不是本 Goal 的阻塞项，也不触发外部证据刷新。

## 明确不授权

本记录不授权：S27A candidate manifest/freeze 或前瞻 shadow 激活；S4C RQAlpha 执行（须在新 Goal 与预先冻结的 execution gates 下进行）；S10A 修复或重试；S2 语义、manifest 或冻结输入的任何修改；参数/窗口/成本/cap 搜索；Theme Rotation、Batch 06、新策略或通用候选/执行基础设施；改写 `INVALID_RUN` 或历史负证据。

## 仓库状态

评审在 `main@f85b802` 开始；本记录与其文档同步只改变 `.python-version`、`README.md`、本记录、`docs/RESEARCH_LEDGER.md`、`docs/CURRENT_STATE.md`、`docs/STRATEGY_CATALOG.md`、`docs/STRATEGY_RESEARCH_MAP.md` 与 `docs/goal.md`，不触及策略代码、实验 runner、冻结产物或 S2 冻结输入。

## ARCHITECT_REVIEW（Batch 05 评审时点快照）

以下结构化块是本记录在 **Batch 05 architect-review 时点**的不可变快照，先于其后的 S4C authoritative execution work。后续仓库状态不得回填到该历史决策中；特别是 `FREEZE_DECISION` 不得因 S4C 之后通过执行审查而被改写。

```text
ARCHITECT_REVIEW

STARTING_HEAD:
f85b802

WINDOWS_STATUS:
B_SUPPORTED_WITH_MINIMAL_PORTABILITY_FIXES

SYSTEM_MISSION:
Low-frequency multi-asset tactical-allocation research;
discover robust, explainable, executable, low-maintenance strategies;
strategy research > infrastructure.

ARCHITECTURE_MODEL:
External evidence
-> local evidence gap
-> canonical/PIT data
-> strategy semantics
-> research screening
-> authoritative execution validation
-> evidence/decision
-> future production decision.
No generic quant platform.

ENGINE_OWNERSHIP:
TactiCore owns economic semantics, canonical data contracts,
evidence, bounded orchestration and decisions.
VectorBT owns rapid research/simulation.
RQAlpha owns authoritative execution/accounting/cash/lots/matching/costs.
Tushare Pro is canonical research data;
RQAlpha bundle supplies authoritative China execution semantics.

RESEARCH_CONTROL_PLANE:
External Evidence Gate
-> PIT Tradability Gate
-> bounded historical research
-> robustness
-> execution review
-> candidate-freeze review
-> prospective shadow.
Protocol freeze and INVALID_RUN discipline apply;
closed questions are not reopened without contradictory evidence.

BATCH_05_PROTOCOL_VALIDITY:
VALID_V3_ONLY.
V1/V2 remain preserved INVALID_RUN history;
V3 was frozen before the accepted complete rerun.

BATCH_05_RESULT_VALIDITY:
VALID.
V3 accepted results are authoritative;
S2 R1 was not modified by Batch 05.

S2_STATE:
FROZEN / PROSPECTIVE_SHADOW_ACTIVE;
sole active prospective candidate;
PIT integrity PASS.

S27A_STATE:
ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW;
eligible but deferred;
not candidate/shadow/production approved.

S10A_STATE:
DO_NOT_ADVANCE_S10A_EXECUTION;
native cash-rejection gate failed;
no local repair authorized.

S4C_STATE:
ADVANCE_S4C_TO_EXECUTION_REVIEW;
selected as the single next bounded Goal at this review point;
not candidate/shadow/production approved.

REPRODUCIBILITY_STATUS:
Native Windows supported with minimal portability fixes:
Python 3.11 development/verification pin,
CRLF-safe frozen repository-text hashing,
strict S2 verification demonstrated.
Python 3.12 development mypy failure classified as resolver/stub skew,
not a project typing or strategy defect.
WSL was not audited.

CURRENT_FRONTIER:
AWAIT_S4C_EXECUTION_REVIEW

FREEZE_DECISION:
NOT_READY_TO_FREEZE
```

`NOT_READY_TO_FREEZE` 在该时点意为“不追加新的候选冻结”：S2 已经冻结并处于前瞻影子；S27A 已获得审查资格但因与 S2 机制高度重叠而被有意推迟；S4C 仍需权威执行审查；S10A 未通过执行 gate。

## Findings（Batch 05 评审时点）

### P0 — no open correctness/architecture blocker after accepted V3

- **Evidence**：V1/V2 作为 `INVALID_RUN` 保留；V3 protocol 先于唯一被采纳的完整结果；PIT/correctness contract 已建立；S2 候选完整性始终保持不变。
- **Why it matters**：它决定 Batch 05 证据能否被接受，而不是整批判为无效。
- **Stage Blocking**：NO
- **Smallest Closure**：无需额外动作；保留 V3 作为唯一被接受的 Batch 05 结果，并保留 invalid-run 历史。

### P1 — native Windows reproducibility required minimal portability fixes

- **Evidence**：Python 3.10/3.11 解析到 NumPy 1.26.4 并通过项目 mypy；Python 3.12 因 RQAlpha 约束解析到 NumPy 2.x，mypy 在项目 Python 3.10 typing 目标下解析这些 stub 时失败。Windows checkout 还需要既有的 CRLF-safe frozen-text hashing 才能通过严格 S2 校验。
- **Why it matters**：缺少开发解释器固定与换行安全的 frozen-text 契约时，受支持的原生 Windows checkout 会因为工具链/checkout 原因而验证失败，而这与策略语义无关。
- **Stage Blocking**：YES — 在最小移植性修复落地前阻塞 milestone/environment closure；现已 CLOSED。
- **Smallest Closure**：保留 `.python-version = 3.11`、保留窄口径 CRLF 归一化、显式记录 native Windows/WSL 边界并记录 Phase A 审计。不要收窄 `requires-python`、不要仅为该问题引入 lockfile、不要在没有独立证据时添加 `.gitattributes`。

### P2 — external registry local lifecycle fields are a stale snapshot

- **Evidence**：外部证据 registry 的时点为 `2026-09-11`；其内嵌 local-status 字段早于后续 Batch 05 生命周期证据，而当前生命周期归属在冻结产物 / ledger / catalog / current state。
- **Why it matters**：读者可能把外部证据快照误认为当前本地策略状态，但这既不否定外部 tier，也不否定本地结果。
- **Stage Blocking**：NO
- **Smallest Closure**：外部 registry 保持不变；在本评审记录中显式保留 authority/snapshot 澄清。本地 PASS/FAIL 不得改写外部证据 tier。

Phase A 环境基线与静态移植性审计证据见 [Phase A Windows native portability audit](PHASE_A_WINDOWS_NATIVE_PORTABILITY_AUDIT_V1.md)。
