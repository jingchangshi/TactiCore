# TactiCore — Prospective Evidence Foundation V1 + Dual-Candidate Operational Readiness

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Execution mode:

```text
Codex with ChatGPT / C2C
```

Recommended model roles:

```text
ChatGPT:
GPT-5.6 Sol
Reasoning: High

Role:
Principal Architect
Quant Research Reviewer
Prospective Evidence Architect
Research Correctness Gatekeeper
Independent Reviewer
```

```text
Codex:
DeepSeek Flash
Reasoning: High

Role:
Implementation Agent
Validation Runner
Repository Maintainer
Git Operator
```

============================================================
0. WHY THIS WORK EXISTS
=======================

TactiCore 已经完成了研究阶段的一次重要转换。

当前证据表明：

```text
10% long-term portfolio objective
historically feasible with existing components
```

而当前最大的 remaining gap 已经不是：

```text
MORE ALPHA
MORE STRATEGIES
MORE PARAMETER SEARCH
```

而是：

```text
PROSPECTIVE_EVIDENCE
```

当前预计存在两个 active research candidates：

```text
S2_R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE

S4C_R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
```

并且 prospective observations 仍应为 0。

因此现在真正的问题不是：

```text
如何再研究一个策略？
```

而是：

```text
如何确保从第一条真实 observation 开始，
TactiCore 获得的是不可回填、
不可重写、
有真实数据 vintage、
decision 先于 execution、
可以多年复现的真正 prospective evidence？
```

本 Goal 要建立的是：

```text
PROSPECTIVE_EVIDENCE_FOUNDATION_V1
```

它不是通用研究治理平台。

它只是目前两个 active candidates
产生可信前瞻证据所必需的
最小 evidence-control contract。

============================================================

1. LONG-TERM SYSTEM POSITION
   ============================================================

TactiCore 的长期主链应逐渐明确为：

```text
External Evidence
    ↓
PIT Canonical Data
    ↓
Historical Research
    ↓
Robustness
    ↓
Authoritative Execution Review
    ↓
Candidate Freeze
    ↓
Prospective Activation
    ↓
Prospective Evidence Collection
    ↓
Integrity Review
    ↓
Production-Candidate Review
    ↓
Possible Portfolio / Production Decision
```

本 Goal 只关闭：

```text
Prospective Activation
        ↓
Prospective Evidence Collection
```

之间的系统性 correctness gap。

不要推进后续 production。

============================================================
2. REPOSITORY FIRST
===================

开始前实际执行：

```bash
git status
git remote -v
git branch --show-current
git fetch origin
git log --oneline --decorate -25
```

记录：

```text
STARTING_HEAD
ORIGIN_MAIN_HEAD
WORKING_TREE_STATE
```

必须重新读取最新 repository。

不得只依据：

```text
本 Prompt
上轮对话
Codex summary
CURRENT_STATE 单一文档
```

============================================================
3. MANDATORY AUTHORITY READING
==============================

至少读取：

```text
AGENTS.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/PORTFOLIO_OBJECTIVE.md
docs/CURRENT_STATE.md
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
docs/STRATEGY_RESEARCH_MAP.md
docs/goal.md
```

Prospective candidates：

```text
research/shadow/s2_r1/
research/shadow/s4c_r1/
```

重点：

```text
candidate_manifest.json
README.md
observations.csv
activation.json（若存在）
```

Runners：

```text
research/experiments/run_s2_r1_shadow.py
research/experiments/run_s4c_r1_shadow.py
research/experiments/verify_s4c_r1_candidate.py
```

Data：

```text
research/experiments/download_tushare_data.py
tacticore/data/tushare.py
data/canonical/provenance.json
```

S4C activation：

```text
research/batches/s4c_activation/PROTOCOL.md
research/results/S4C_R1_PROSPECTIVE_ACTIVATION_DECISION_V1.md
```

以及所有当前 prospective rule / ledger evidence。

============================================================
4. FIRST ARCHITECT TASK — RECONSTRUCT THE REAL GAP
==================================================

ChatGPT 不要直接接受本 Prompt 中列举的问题。

独立比较：

```text
S2_R1 prospective path

vs

S4C_R1 prospective path
```

至少建立：

```text
DUAL_CANDIDATE_PROSPECTIVE_AUDIT
```

逐项检查：

```text
candidate identity immutability

historical cutoff

first eligible signal

activation/lifecycle state

explicit as-of

candidate-specific vintage location

vintage authenticity

provenance parsing

data after as-of rejection

historical overlap validation

decision generation timestamp

decision-before-execution guarantee

append-only semantics

duplicate handling

execution-record completeness

execution evidence binding

framework identity

candidate integrity failures

performance weakness handling

CLI authorization surface

test coverage

operational burden
```

输出：

```text
S2 gaps
S4C gaps
shared gaps
candidate-specific gaps
```

============================================================
5. DO NOT LIMIT THE GOAL TO S4C
===============================

上一轮发现的 S4C P1 包括：

```text
decision temporal sealing

vintage provenance authenticity

execution record completeness
```

但 ChatGPT 必须检查：

```text
S2 是否存在相同或更早期的问题。
```

如果存在，

本 Goal 必须统一关闭两个 active candidates 的
prospective evidence correctness。

原因：

```text
一个严格的 S4C
+
一个宽松的 S2
!=
可信的 prospective portfolio evidence
```

============================================================
6. RESEARCH PRIORITY DECISION
=============================

在实现前必须明确：

```text
Is dual-candidate prospective evidence readiness
the highest-value current research problem?
```

至少与以下方向比较：

```text
A.
Prospective Evidence Foundation V1
for S2 + S4C

B.
Only fix S4C

C.
Start new strategy / S27A / Theme Rotation

D.
Create portfolio candidate now

E.
Do nothing until 2026-09-30
```

评分：

```text
research information gain
correctness impact
impact on 10% portfolio objective
prospective evidence value
time sensitivity
implementation freedom
maintenance cost
data-mining risk
architecture risk
reversibility
```

预期：

```text
A
```

应胜出。

但必须独立验证。

============================================================
7. TARGET END STATE
===================

本 Goal 的目标不是：

```text
生成 2026-09-30 observation
```

而是：

```text
READY_FOR_REAL_PROSPECTIVE_EVIDENCE
```

最终应能明确回答：

```text
如果今天就是 2026-09-30，
系统是否能在不看未来执行结果的情况下：

1. 获取并冻结真实 as-of market vintage
2. 证明 vintage 是当时下载的
3. 证明数据截止 as-of
4. 验证 candidate identity
5. 生成 frozen-semantics decision
6. 在 execution result 可见前永久 seal decision
7. append-only 保存
8. commit / push evidence
9. STOP

然后在下一 canonical execution 时点：

10. 使用 RQAlpha native semantics
11. 生成完整 execution evidence
12. append execution row
13. 不修改 decision
```

只有答案全部 YES 才完成。

============================================================
8. PERMANENT PROSPECTIVE EVIDENCE INVARIANTS
============================================

如果审计确认这些规则对 S2/S4C 都成立，
则将最小必要规则加入：

```text
docs/RESEARCH_RULES.md §9
```

不要建设 governance system。

建议永久 invariant：

```text
1.
prospective record 必须来自真实 candidate-specific vintage

2.
vintage 必须有机器可验证 provenance

3.
provenance 必须绑定实际数据文件 hash

4.
prospective decision 必须在 execution outcome
可观察之前永久固定

5.
decision 与 execution 是 append-only 的不同事件

6.
execution record 必须完整后才能 append；
不允许先写空壳后补字段

7.
失败运行不能改变 evidence bytes

8.
historical canonical baseline 永久冻结

9.
candidate identity 在 observation 后不可修改

10.
performance weakness != candidate integrity failure
```

不要把 candidate-specific threshold
写成永久规则。

============================================================
9. ARCHITECTURE RESPONSIBILITY UPDATE
=====================================

如果上述 contract 已成为系统真实稳定能力，

在 `ARCHITECTURE.md` 中增加一个很小的：

```text
Prospective Evidence Collection
```

职责边界。

应明确：

```text
Tushare
owns external market data

TactiCore
owns candidate-specific as-of freezing,
provenance verification,
thin evidence orchestration,
append-only records

strategy runner
owns candidate-specific signal semantics

RQAlpha
owns execution semantics

Git
owns versioned evidence history
```

明确不拥有：

```text
scheduler
database
workflow engine
generic event store
broker
execution simulator
research governance platform
```

============================================================
10. FREEZE A FOUNDATION PROTOCOL
================================

在实现任何修复前建立：

```text
research/batches/
prospective_evidence_foundation/
PROTOCOL.md
```

Protocol 必须在结果之前冻结。

它至少定义：

```text
scope

S2/S4C current identity

accepted current observations count

prospective timestamp semantics

vintage provenance contract

decision sealing contract

execution completeness contract

append-only contract

CLI authorization contract

candidate-specific boundaries

quality gates

allowed terminal decisions
```

允许的最终决定：

```text
PROSPECTIVE_FOUNDATION_READY

PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS

BLOCKED_BY_PROSPECTIVE_CORRECTNESS
```

============================================================
11. NO REAL SEPTEMBER MARKET DATA DURING THIS GOAL
==================================================

本 Goal 当前发生在真实 `2026-09-30` 之前。

因此禁止：

```text
下载 2026-09-01..09-30 真实价格
形成真实 prospective vintage
运行真实 S2/S4C September decision
inspect September target for research interpretation
```

本 Goal 所有验证使用：

```text
historical fixture

synthetic fixture

tmp_path

mocked API

或 <= historical cutoff 的已冻结数据
```

不要通过：

```text
“先跑一下看看”
```

验证未来 pipeline。

============================================================
12. REUSE THE EXISTING TUSHARE DATA IMPLEMENTATION
==================================================

仓库已经存在：

```text
download_tushare_dataset(...)
write_tushare_dataset(...)
```

它已经知道如何记录：

```text
source
request parameters
data_timestamp
download_timestamp
end_date
calendar requests
quality checks
price hash
calendar hash
```

因此禁止重新实现：

```text
Tushare fetch engine
CSV normalizer
adjustment logic
generic dataset version system
```

未来 prospective vintage 应尽量复用该实现。

允许增加：

```text
一个很薄的 candidate-specific /
prospective snapshot orchestration layer
```

例如：

```text
freeze_prospective_vintage.py
```

名称由实际 repository 风格决定。

它只能做：

```text
resolve candidate
resolve canonical candidate vintage path
require explicit as-of
invoke existing Tushare downloader
write to candidate-specific vintage directory
validate provenance
refuse overwrite
```

不要增加 provider abstraction。

============================================================
13. VINTAGE AUTHENTICITY CONTRACT
=================================

当前仅检查：

```text
provenance.json exists
```

是不够的。

必须真正 parse provenance。

至少验证：

```text
source == expected source

end_date == as-of

request end_date == as-of
for relevant price endpoints

symbol data_timestamp <= as-of

download_timestamp exists and timezone-aware

download_timestamp is temporally compatible
with the prospective seal

price file SHA matches provenance

calendar file SHA matches provenance

row counts match

adjustment semantics match candidate contract

universe symbols match frozen universe

historical overlap unchanged

no price data after as-of
```

如果 calendar 允许包含未来已公布的交易日安排，

必须把：

```text
price_as_of
calendar_as_of
```

语义明确分开。

不得因为 calendar 未来日期
误判为价格 future leakage。

============================================================
14. TEMPORAL DECISION SEALING
=============================

必须机器保证：

```text
decision exists
BEFORE
execution outcome becomes observable
```

当前仅有：

```text
record_generated_at >= signal_date
```

不够。

ChatGPT 必须设计一个最简单、
可证明的 temporal seal。

优先考虑：

```text
signal_close
    <= decision_seal_time
    < next_canonical_execution_observation
```

`next_canonical_execution_observation`
必须由在 decision 时已经合法可知的
exchange calendar contract 推导。

如果发现最简单且更可靠的方案是：

```text
decision 必须在 signal market date
完成并 commit/push
```

也可以采用，

但必须解释为什么它比宽松 window 更好。

无论选择哪种方案：

```text
不能允许几天后看到 execution result
再回填 signal-date decision。
```

============================================================
15. GIT EVIDENCE SEAL
=====================

研究 record 写入后必须进入 Git history。

未来真实 decision cycle 建议：

```text
freeze vintage
↓
verify
↓
append decision
↓
tests / verifier
↓
commit
↓
push
↓
STOP
```

不能：

```text
append decision
↓
等 execution
↓
一起 commit
```

因为那会削弱
decision-before-execution 的证据。

本 Goal 不实际执行该流程，
只冻结并测试它。

============================================================
16. S2 R1 HARDENING
===================

S2_R1 candidate identity 不得修改。

特别禁止修改：

```text
candidate_manifest.json
trend_window
prospective_start
historical_cutoff
strategy semantics
frozen target identity
```

审计当前 S2 runner。

如存在以下问题，
必须关闭：

```text
production CLI 可以覆盖 record path

external/noncanonical vintage path 可成为 official evidence

provenance 未解析

decision temporal seal 不完整

append-only 只按 signal_date 检查，
无法安全扩展 execution event

record generation time 未校验

execution record contract 不完整
```

S2 不要求 retroactively 增加 S4C 风格 activation artifact。

不要伪造新的历史 lifecycle。

保持：

```text
S2_R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
```

只增强 future evidence correctness。

============================================================
17. S4C R1 HARDENING
====================

S4C candidate manifest 和 activation artifact
都不得修改语义。

必须关闭至少：

```text
P1-A
decision temporal seal

P1-B
provenance authenticity

P1-C
execution record completeness
```

S4C 当前 observation_count 必须仍为 0。

============================================================
18. COMMON PURE HELPERS — ONLY IF JUSTIFIED
===========================================

S2 与 S4C 将共享部分完全相同的 evidence mechanics：

```text
provenance validation

canonical vintage location

temporal seal

append-only event validation

file-hash validation
```

ChatGPT 必须判断：

```text
duplicate candidate-specific code
vs
tiny shared pure-validation helper
```

允许建立一个极小共享模块的前提：

```text
1. pure validation only
2. no candidate state machine
3. no strategy logic
4. no scheduler
5. no database
6. no provider abstraction
7. no generic research framework
8. materially removes duplicated correctness code
```

例如可能的职责：

```text
validate_vintage_provenance(...)
validate_decision_time_boundary(...)
verify_append_only_schema(...)
```

但：

```text
S2 target derivation
S4C target derivation
candidate manifests
observation schemas
```

必须保持 candidate-specific。

如果抽象没有明显收益：

不要抽象。

============================================================
19. EXECUTION RECORD CONTRACT
=============================

当前未来 execution 不能只要求：

```text
execution_date > signal_date
```

然后允许空记录 append。

在 append 前必须完整。

至少考虑要求：

```text
record_type = execution

candidate_id

protocol_version

signal_date

execution_date

execution_status

realized_weights

cash_weight

target deviation / portfolio deviation

turnover

execution evidence identity

RQAlpha evidence path/hash
```

candidate-specific 字段按实际 schema 定义。

禁止：

```text
append incomplete execution
then edit it later
```

因为 evidence 是 append-only。

============================================================
20. RQALPHA REMAINS EXECUTION AUTHORITY
=======================================

不要实现 shadow execution simulator。

未来 execution evidence 必须来自：

```text
RQAlpha native execution semantics
```

TactiCore 只：

```text
freeze intended target
run native replay / execution evidence
parse authoritative output
append evidence
```

不得复制：

```text
cash engine
round lot
matching
costs
partial fill
order lifecycle
```

============================================================
21. FIRST-PROSPECTIVE-CYCLE RUNBOOK
===================================

本 Goal 必须预注册未来真实 cycle 的操作顺序。

建议明确成：

```text
PHASE P1 — Freeze Market Vintage

PHASE P2 — Verify Vintage Authenticity

PHASE P3 — Verify Candidate Identity

PHASE P4 — Derive Candidate Decision

PHASE P5 — Seal Decision Before Execution

PHASE P6 — Append Decision

PHASE P7 — Commit + Push

STOP
```

然后未来另一个 execution Goal：

```text
PHASE E1 — Wait for next canonical execution observation

PHASE E2 — Run RQAlpha-native execution evidence

PHASE E3 — Build complete execution row

PHASE E4 — Append execution row

PHASE E5 — Commit + Push

STOP
```

decision 与 execution
永远不要在同一个 delayed operation 中生成。

============================================================
22. DUAL-CANDIDATE MONTHLY OPERATING MODEL
==========================================

未来 S2 + S4C 都是月频候选。

目标是降低人工成本。

考虑是否可以：

```text
one as-of market download
```

经过验证后形成：

```text
candidate-specific immutable vintage evidence
```

供两个 candidate 使用。

但必须保证：

```text
candidate-specific provenance
candidate-specific record
candidate-specific manifest hash
candidate-specific decision
```

不要因此建立 PortfolioManager 或 CandidateManager。

如果复用同一市场快照：

在文档中明确：

```text
same source snapshot
!=
same candidate evidence record
```

============================================================
23. 2026-09-30 READINESS DRILL
==============================

在 synthetic / historical fixture 上完整演练：

```text
snapshot
→ provenance
→ verify
→ derive S2
→ derive S4C
→ append candidate records
→ duplicate rejection
→ execution builder
→ execution completeness
```

不得使用真实 September market data。

该演练必须证明：

```text
future real cycle requires no code change
```

如果 9 月 30 日当天还需要临时改代码，

foundation 不算完成。

============================================================
24. THIN CI — NOW JUSTIFIED
===========================

过去多个 milestone 都存在：

```text
GitHub status = none
workflow runs = none
```

Prospective evidence 即将成为长期研究资产，

因此这一次可以评估一个
**非常薄的 credential-free CI**。

目标不是建设 CI platform。

只验证：

```text
pytest

ruff

ruff format --check

mypy

strict candidate verifiers
```

禁止 CI：

```text
调用 Tushare

需要 TUSHARE_TOKEN

运行真实 prospective download

运行真实 RQAlpha research experiment

产生 observations
```

如果完整 suite 无法在 credential-free GitHub runner 上运行，

选择最小 deterministic subset，

并记录限制。

============================================================
25. NO NEW STRATEGY WORK
========================

本 Goal 严禁：

```text
S27A candidate freeze

Theme Rotation

new defensive strategy

new alpha

new trend parameter

new ERC parameter

new covariance model

new portfolio mix

Portfolio_R1

Blend_R1
```

原因：

```text
10% historical return gap already small

largest remaining gap = prospective evidence
```

============================================================
26. NO PORTFOLIO PROMOTION
==========================

即使：

```text
S2 + S4C
historically supports ~10%
```

本 Goal 也不能创建 portfolio candidate。

正确证据顺序：

```text
individual prospective candidate evidence
↓
integrity review
↓
independent research-priority decision
↓
possible portfolio-candidate research
```

============================================================
27. COMMIT STRUCTURE
====================

建议至少使用以下逻辑提交。

---

## COMMIT A — architect + protocol

```text
dual-candidate audit

research priority decision

Prospective Evidence Foundation V1 protocol

minimal RESEARCH_RULES / ARCHITECTURE updates
```

NO runner changes if practical.

NO real prospective data.

---

## COMMIT B — data / temporal integrity

```text
vintage provenance validation

prospective snapshot thin orchestration if required

temporal decision seal

S2/S4C write-path hardening

tests
```

NO observations.

---

## C2C REVIEW

ChatGPT independently reviews:

```text
protocol
source
tests
candidate manifests
activation artifact
CLI surface
data provenance
time semantics
```

Output:

```text
PROSPECTIVE_FOUNDATION_IMPLEMENTATION_GATE
=
PASS / FAIL
```

FAIL:

return exact corrections.

---

## COMMIT C — execution evidence contract

```text
complete execution-row validation

RQAlpha evidence binding

append-only execution tests

synthetic/historical readiness drill
```

Still no prospective observation.

---

## COMMIT D — readiness decision

Produce:

```text
PROSPECTIVE_EVIDENCE_FOUNDATION_V1.md
```

Terminal result:

```text
PROSPECTIVE_FOUNDATION_READY

or

PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS

or

BLOCKED_BY_PROSPECTIVE_CORRECTNESS
```

Sync authority docs.

---

## OPTIONAL COMMIT E — thin CI

Only if justified and credential-free.

============================================================
28. TEST REQUIREMENTS
=====================

Tests should include at minimum:

```text
S2 manifest unchanged

S4C manifest unchanged

S4C activation unchanged

candidate-specific vintage path

external vintage rejected before read

provenance source validated

provenance end_date == as-of

provenance file hash validated

wrong data timestamp rejected

future price rejected

historical overlap drift rejected

explicit as-of required

pre-eligible date rejected

decision temporal seal enforced

late/backfilled decision rejected

decision contains no execution evidence

duplicate decision rejected

rejected write leaves bytes unchanged

incomplete execution rejected

execution without decision rejected

execution <= signal rejected

duplicate execution rejected

complete execution accepted

append-only existing rows unchanged

S2 and S4C candidate-specific schemas remain distinct
```

No test may depend on actual 2026-09 market data.

============================================================
29. QUALITY GATE
================

Final local validation:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Strict candidate validation:

```bash
uv run python research/experiments/run_s2_r1_shadow.py --verify-candidate

uv run python research/experiments/verify_s4c_r1_candidate.py --verify-candidate

uv run python research/experiments/run_s4c_r1_shadow.py \
  --verify-candidate \
  --verify-activation
```

If a new shared prospective verifier exists:

run its read-only verification.

NO real observation mode.

============================================================
30. FINAL STATE
===============

Ideal result:

```text
S2_R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
observation_count = 0

S4C_R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
observation_count = 0
```

And:

```text
PROSPECTIVE_EVIDENCE_FOUNDATION_V1
= READY
```

Current frontier should become something equivalent to:

```text
AWAIT_2026_09_30_DUAL_CANDIDATE_PROSPECTIVE_DECISION_CYCLE
```

rather than：

```text
继续做研究开发
```

============================================================
31. FUTURE SEPTEMBER CYCLE — DO NOT EXECUTE NOW
===============================================

On or after the actual eligible September signal:

```text
2026-09-30
```

未来独立 Goal：

```text
SEPTEMBER_2026_PROSPECTIVE_DECISION_CYCLE
```

should do:

```text
download/freeze as-of vintage
↓
verify provenance
↓
verify S2 candidate
↓
verify S4C candidate + activation
↓
derive S2 decision
↓
derive S4C decision
↓
seal both before execution outcome
↓
append separate candidate decision records
↓
commit
↓
push
↓
STOP
```

这将是：

```text
真正的 prospective evidence
```

而不是本 Goal 的测试结果。

============================================================
32. FUTURE EXECUTION CYCLE — SEPARATE GOAL
==========================================

下一 canonical execution observation 到达后，

另一个 Goal：

```text
SEPTEMBER_2026_PROSPECTIVE_EXECUTION_EVIDENCE
```

才执行：

```text
RQAlpha authoritative execution
↓
parse native evidence
↓
complete execution rows
↓
append only
↓
commit / push
```

不得回写 decision。

============================================================
33. 12–24 MONTH ROADMAP
=======================

不要因为 foundation 完成
又开始新 alpha work。

未来主线应逐步变为：

```text
monthly prospective evidence

↓
candidate integrity monitoring

↓
12-month integrity review

↓
candidate-specific review threshold

↓
18/24-month production-candidate eligibility

↓
independent research-priority decision

↓
possible portfolio candidate
```

S2/S4C 各自 review horizon
沿用已经冻结的 candidate protocol。

============================================================
34. RELATION TO THE 10% OBJECTIVE
=================================

这项工作的经济意义必须写清楚。

当前约 10% 历史路径主要由：

```text
strategic beta
+
S4C return-scale / risk allocation
+
S2 mechanism/downside diversification
```

构成。

现在不应继续问：

```text
如何把 historical CAGR 再提高？
```

而应问：

```text
这些机制在真正 forward data 上
是否仍按冻结语义工作？
```

只有 prospective evidence
才能开始回答这个问题。

============================================================
35. STOP CONDITIONS
===================

立即 STOP 并返回 C2C review，如果出现：

```text
需要修改 S2 manifest

需要修改 S4C manifest

需要修改 S4C activation semantics

为了修 evidence 修改 strategy economics

需要看真实 September target 才能设计 contract

需要改参数

需要添加 cap

需要创建 portfolio candidate

需要创建 generic candidate framework

需要 database / scheduler / workflow engine

需要修改 historical canonical data

需要回填 observation

需要用晚到数据冒充早期 vintage
```

============================================================
36. FINAL REPORT
================

必须报告：

```text
STARTING_HEAD
FINAL_HEAD
COMMITS_CREATED
PUSH_STATUS
```

Architecture:

```text
CURRENT_PROSPECTIVE_ARCHITECTURE

S2_PROSPECTIVE_PATH

S4C_PROSPECTIVE_PATH

SHARED_INVARIANTS

CANDIDATE_SPECIFIC_BOUNDARIES
```

Data:

```text
VINTAGE_PROVENANCE_CONTRACT

AS_OF_CONTRACT

DOWNLOAD_TIMESTAMP_CONTRACT

FILE_HASH_CONTRACT

OVERLAP_CONTRACT
```

Timing:

```text
SIGNAL_TIME

DECISION_SEAL_TIME

NEXT_EXECUTION_BOUNDARY

HOW_LATE_BACKFILL_IS_MACHINE_REJECTED
```

Records:

```text
DECISION_APPEND_ONLY_STATUS

EXECUTION_COMPLETENESS_STATUS

EXECUTION_EVIDENCE_BINDING

IDEMPOTENCY_STATUS
```

Candidate integrity:

```text
S2_MANIFEST_CHANGED = NO

S4C_MANIFEST_CHANGED = NO

S4C_ACTIVATION_CHANGED = NO

S2_OBSERVATION_COUNT

S4C_OBSERVATION_COUNT
```

Quality:

```text
pytest
ruff
format
mypy
candidate verifiers
CI status
skips
xfails
```

Decision:

```text
PROSPECTIVE_FOUNDATION_DECISION
```

with one of:

```text
PROSPECTIVE_FOUNDATION_READY

PROSPECTIVE_FOUNDATION_READY_WITH_NONBLOCKING_LIMITATIONS

BLOCKED_BY_PROSPECTIVE_CORRECTNESS
```

Then provide:

```text
EXACT_2026_09_30_RUNBOOK
```

but do NOT execute it.

============================================================
37. DONE GATE
=============

DONE requires:

```text
1.
Latest repository independently re-read.

2.
Both active candidates audited.

3.
No real September prospective data inspected.

4.
No candidate identity changed.

5.
Vintage authenticity is machine validated.

6.
Late decision backfill is machine impossible.

7.
Decision precedes execution evidence.

8.
Execution records cannot be appended incomplete.

9.
Append-only behavior is proven.

10.
Failure leaves evidence unchanged.

11.
S2 and S4C remain candidate-specific.

12.
No generic framework was introduced.

13.
No new strategy was started.

14.
Full quality gate is explicit.

15.
Future September run requires no code change.

16.
Current frontier truthfully becomes:
wait for real prospective signal.
```

============================================================
38. START
=========

执行：

```text
Repository baseline
↓
Dual-candidate architect audit
↓
Research-priority decision
↓
Freeze Prospective Evidence Foundation V1 protocol
↓
Commit A
↓
Implement data provenance + temporal sealing
↓
Harden S2 + S4C
↓
Commit B
↓
Independent C2C Review
↓
Correct until implementation gate PASS
↓
Execution evidence contract
↓
Readiness drill on non-prospective fixtures
↓
Commit C
↓
Foundation readiness decision
↓
Authority docs
↓
Optional thin CI
↓
Full validation
↓
Commit / push
↓
STOP DEVELOPMENT
↓
WAIT FOR REAL 2026-09-30
```

Primary principles:

```text
Prospective evidence > more historical alpha.

Evidence must be true at the time,
not reconstructed later.

Decision must exist before execution outcome.

Provenance must be verified,
not merely present.

Append-only means incomplete records
must never be appended.

S2 and S4C share evidence discipline,
not strategy semantics.

Reuse Tushare / VectorBT / RQAlpha.

No new strategy.

No portfolio candidate.

No generic research platform.

After readiness:
stop coding and let time generate evidence.
```
