# Goal: TactiCore — PIT Enforcement Hardening + Batch 05 Earned Stage Validation

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Architect
+
Research Correctness Reviewer
+
Execution Validation Reviewer
+
Repository Knowledge Maintainer
```

---

# 0. Why This Work Exists

TactiCore 已完成：

```text
Batch 00
External Evidence Foundation

Batch 01
Transparent Strategy Screens

Batch 02
Evidence-Informed Validation

Batch 03
Earned Stage Advancement

Batch 04
Community-Backed PIT Correctness Closure
```

Batch 04 已建立：

```text
External Evidence Gate
        ↓
PIT Tradability Gate
        ↓
Local Evidence Gap
        ↓
Historical Research
        ↓
Robustness
        ↓
Execution Review
        ↓
Candidate Freeze
        ↓
Prospective Shadow
```

当前研究状态按最新仓库权威事实应为：

```text
S2 R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
PIT integrity PASS

S27A
PIT-corrected
EXECUTION_REVIEW_ELIGIBLE

S10A
correctness-corrected
EXECUTION_REVIEW_ELIGIBLE

S4C
PIT-corrected
ROBUSTNESS_ELIGIBLE

S30
REFERENCE_BASELINE
```

本 Goal 不再扩展 strategy count。

本 Goal 完成两个层次的工作：

```text
Phase 0
Post-Batch-04 Research Contract Hardening

Phase 1
BATCH_05_EARNED_STAGE_VALIDATION
```

目标是：

```text
1. 让 PIT contract 从“可选能力”升级为“默认不可绕过”
2. 修正文档状态漂移
3. 对 S27A 做权威 RQAlpha execution review
4. 对 S10A 做权威 RQAlpha execution review
5. 对 S4C 做有界 robustness
6. 更新全部应同步的永久和当前文档
7. STOP，等待 Principal Review
```

---

# 1. Repository First

开始前必须重新读取 remote `main`。

执行：

```bash
git fetch origin
git status
git log --oneline -20
```

不要相信本 Prompt 中硬编码的 HEAD。

记录：

```text
starting HEAD
working tree state
recent commits
```

---

# 2. Mandatory Reading Order

严格按顺序阅读：

```text
AGENTS.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/CURRENT_STATE.md
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
docs/STRATEGY_RESEARCH_MAP.md

research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml

research/results/
  BATCH_04_COMMUNITY_BACKED_PIT_CORRECTNESS_CLOSURE.md
  PIT_TRADABILITY_IMPACT_AUDIT_V1.md
  S27A_PIT_CORRECTNESS_REVALIDATION_V1.md
  S10A_CORRECTNESS_REVALIDATION_V1.md
  S4C_PIT_CORRECTNESS_REVALIDATION_V1.md

research/results/
  S27A_ROBUSTNESS_V1.md
  S10A_ROBUSTNESS_V1.md
  S4C_ERC_SKFOLIO_TRANSFER_V1.md

research/results/
  S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md

research/batches/batch_04/
  COMMUNITY_PIT_AUDIT.md
  PROTOCOL.md

tacticore/data/tradability.py
tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/metrics.py

research/experiments/
  run_s27a_rqalpha_execution_review.py
  run_s10a_robustness.py
  run_s4c_erc_skfolio_transfer.py

research/shadow/s2_r1/candidate_manifest.json
```

仓库事实和冻结研究产物优先于旧文档。

---

# 3. Reconcile Repository State Before Coding

先检查是否存在：

```text
CURRENT_STATE
STRATEGY_CATALOG
STRATEGY_RESEARCH_MAP
RESEARCH_LEDGER
research/results
```

之间的冲突。

特别检查：

```text
S27A current status

S10A current status

S4C current status
```

最新权威结果应来自 Batch 04。

如果某个较低权威文档仍写：

```text
S27 environment blocked
S10 robustness rejected
```

而 Batch 04 已 supersede：

必须纳入 Phase 0 修复。

不得把旧历史 artifact 删除。

---

# ============================================================

# PHASE 0 — POST-BATCH-04 HARDENING

# ============================================================

# 4. Phase 0 Mission

Batch 04 已建立：

```text
tacticore/data/tradability.py
```

以及：

```text
validate_execution_targets()
```

但当前需要确认：

```text
run_target_weights()
```

是否允许：

```python
tradability_mask = None
lifetimes = None
```

从而绕过 PIT validation。

永久规则要求：

```text
Any historical simulation
must pass PIT Tradability Gate.
```

因此代码 contract 必须与永久规则一致。

---

# 5. Make PIT Validation Non-Optional by Default

核心目标：

```text
No research runner should accidentally bypass
positive-target tradability validation.
```

优先采用最小改动。

例如将：

```python
run_target_weights(
    ...,
    tradability_mask=None,
    lifetimes=None,
)
```

改为 required keyword-only context：

```python
run_target_weights(
    ...,
    tradability_mask: pd.DataFrame,
    lifetimes: Mapping[str, AssetLifetime],
)
```

或实现同等强度、不可无意绕过的 API。

要求：

```text
forgetting PIT context
must fail immediately
```

而不是默认继续回测。

---

# 6. Do NOT Build a Context Framework

禁止因为 required parameters 较多就创建：

```text
ResearchContext
BacktestContext
SimulationContext
PITEngine
SecurityMaster
PortfolioResearchEngine
```

除非仓库当前已有成熟抽象且只是自然复用。

默认保持：

```text
explicit simple arguments
```

---

# 7. Synthetic Tests May Use Synthetic Lifetimes

测试代码不得为了方便关闭 PIT validation。

构造：

```text
synthetic prices
synthetic AssetLifetime
synthetic tradability mask
```

显式传入。

---

# 8. Audit All run_target_weights Call Sites

搜索：

```bash
rg "run_target_weights"
```

逐个分类：

```text
production/research runner
test
historical reproduction helper
```

每个调用点必须明确拥有：

```text
lifetimes
tradability_mask
```

不要只修最新三个 runner。

---

# 9. No Silent Compatibility Escape Hatch

禁止增加：

```python
validate_tradability = False
```

作为常规参数。

如果确有历史 artifact reproduction 需要绕过：

必须使用非常明确的：

```text
legacy reproduction only
```

路径，并且：

```text
not reusable by new strategy research
```

正常情况应完全不需要这种例外。

---

# 10. S2 Integrity After PIT Enforcement

Phase 0 代码修改完成后：

运行：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

如果 S2 因 API hardening 需要调用点调整：

只调整：

```text
plumbing
```

不得修改：

```text
strategy semantics
manifest
targets
data
```

---

# 11. Document State Drift Closure

Phase 0 必须修复文档当前状态。

检查：

```text
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/STRATEGY_RESEARCH_MAP.md
```

确保 authoritative current status 一致：

```text
S2:
PROSPECTIVE_SHADOW_ACTIVE

S27A:
EXECUTION_REVIEW_ELIGIBLE

S10A:
EXECUTION_REVIEW_ELIGIBLE

S4C:
ROBUSTNESS_ELIGIBLE
```

---

# 12. Preserve Historical Decisions

不得删除：

```text
Batch 03 S27 environment block
Batch 03 S10 robustness reject
```

它们仍是历史过程。

但必须明确：

```text
SUPERSEDED_BY_BATCH_04_CORRECTNESS_CLOSURE
```

当前状态不能继续以旧 decision 为准。

---

# 13. STRATEGY_CATALOG Current Mapping Must Be Correct

检查 catalog 底部 canonical mapping 表。

不能存在：

```text
S27A -> environment blocked
S10A -> robustness rejected
```

作为 current local status。

应更新为：

```text
S27A
execution-review eligible after PIT correction

S10A
execution-review eligible after signed-MaxDD + PIT correction

S4C
robustness eligible after PIT correction
```

---

# 14. CURRENT_STATE Must Only Describe Current Frontier

`docs/CURRENT_STATE.md` 不应同时写：

```text
S10 execution-review eligible
```

又写：

```text
S10 closed
```

消除这类矛盾。

当前 state 应清楚区分：

```text
closed historical question

vs

current next-stage eligibility
```

---

# 15. RESEARCH_LEDGER Normally Append-Only

RL-031 / RL-032 / RL-033 已经记录：

```text
PIT contract
signed MaxDD semantics
Batch 04 corrected decisions
```

不要改写历史 entry。

如果 Phase 0 形成新的永久事实：

例如：

```text
PIT validation is now mandatory at VectorBT boundary
```

则追加新 ledger entry。

不要修改旧 entry 的历史措辞来“看起来更整洁”。

---

# 16. Phase 0 Validation

运行：

```bash
uv sync --extra dev

uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy

uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

全部 PASS。

---

# 17. Phase 0 Commit

建议独立 commit：

```text
enforce PIT validation and reconcile batch 4 state
```

push。

记录：

```text
PHASE_0_HARDENING_SHA
```

---

# ============================================================

# PHASE 1 — BATCH 05 EARNED STAGE VALIDATION

# ============================================================

# 18. Batch Definition

定义：

```text
BATCH_05_EARNED_STAGE_VALIDATION
```

只包含：

```text
Track A
S27A authoritative execution review

Track B
S10A authoritative execution review

Track C
S4C bounded robustness
```

不得加入第四个策略。

---

# 19. Why These Three

它们已经分别获得资格：

```text
S27A
historical baseline
→ robustness
→ PIT correction
→ EXECUTION_REVIEW_ELIGIBLE

S10A
baseline
→ robustness
→ correctness correction
→ EXECUTION_REVIEW_ELIGIBLE

S4C
canonical upstream transfer
→ PIT correction
→ ROBUSTNESS_ELIGIBLE
```

遵循：

```text
A strategy earns the next stage.
```

---

# 20. External Evidence Gate

Batch 05 开始时，不重新做全量 literature review。

读取已有 registry：

```text
VOL_SCALED_TREND
VOL_TARGETING
ERC_RISK_PARITY
```

确认 external tier 未变化。

只有发现真正新的高质量外部证据时才更新 registry。

本地 performance 不得修改 external tier。

---

# 21. PIT Tradability Gate

三个 track 都必须明确：

```text
date-aware universe

asset lifetime source

fallback semantics

execution-price rule

strategy inception

positive-target tradability
```

所有 VectorBT run 必须通过新的 mandatory validation。

---

# 22. Batch 05 Protocol

新增：

```text
research/batches/batch_05/
  PROTOCOL.md
```

在任何新 performance / execution result 前冻结。

必须记录：

```text
starting HEAD

Phase 0 SHA

canonical price hash
universe metadata hash

S2 manifest hash

S27 strategy/config hashes

S10 strategy/config hashes

S4C implementation hash

RQAlpha version

skfolio version

all decision gates

all comparator definitions

all allowed parameter dimensions

all stop conditions
```

---

# 23. Two-Commit Research Discipline

继续保持：

```text
Commit A
=
protocol
+
implementation
+
tests
+
NO new real result

then run

Commit B
=
results
+
ledger/catalog/state/doc sync
```

correctness bug 仍使用：

```text
INVALID_RUN
→ Protocol V2
→ freeze
→ rerun
```

---

# ============================================================

# TRACK A — S27A AUTHORITATIVE EXECUTION REVIEW

# ============================================================

# 24. Track A Question

唯一问题：

> PIT-corrected S27A frozen target schedule 是否能由 RQAlpha 原生账户、撮合、费用、滑点和资金约束忠实实现？

不重新研究：

```text
trend window
vol window
parameter plateau
historical robustness
```

---

# 25. S27 Frozen Semantics

必须保持：

```text
trend_window = 200
vol_window = 60

same risk universe
same fallback

monthly targets
next canonical observation execution

10 bps fees
5 bps slippage
```

使用 Batch 04 corrected inception。

不要 hard-code 日期；通过 PIT contract 得到。

---

# 26. Freeze Corrected S27 Schedule

生成新的权威 frozen target artifact，例如：

```text
research/results/
s27a_pit_corrected_frozen_targets_v1.csv
```

要求：

```text
all execution dates PIT legal

all positive weights tradable

rows sum to 1

nonnegative

dates unique
strictly increasing
```

保存：

```text
SHA-256
row count
first date
last date
```

---

# 27. VectorBT Reproduction Gate

把新 frozen target table 直接交回 VectorBT。

必须 reproduce Batch 04 corrected S27 baseline：

以最新 authoritative Batch 04 artifact 数字为准。

不要使用 Prompt 中硬编码数值作为 authority。

检查：

```text
CAGR
MaxDD
Sharpe
Calmar
turnover
```

严格 machine tolerance。

失败：

```text
BLOCK_S27A_EXECUTION_REPRODUCTION
```

不得运行 RQAlpha。

---

# 28. RQAlpha Must Replay Frozen Targets Only

RQAlpha callback 中禁止：

```text
trend calculation
volatility estimation
inverse-vol sizing
fallback decision
```

只允许：

```text
execution_date
→ read frozen target row
→ submit target portfolio
```

---

# 29. RQAlpha Upstream Path

复用已通过 S2 validation 的：

```text
RQAlpha >=6.3,<6.4

order_target_portfolio

partial_fill_on_insufficient_cash=true

native matching

native fees/slippage

native account

native analyser
```

禁止：

```text
local cash buffer
manual order sizing
retry system
custom matching
custom account
```

---

# 30. S27 Execution Diagnostics

至少记录：

```text
RQAlpha CAGR
MaxDD
native Sharpe

turnover
transaction costs

order count
trade count

cash rejection count
partial-fill residual count
volume-limit count

ending cash
average cash ratio

average execution-date total absolute deviation
maximum deviation

materially off-target execution dates
```

---

# 31. Material Difference Explanation

所有：

```text
target deviation > 5pp
```

必须有明确 RQAlpha native reason：

```text
cash
volume
instrument status
partial fill
other native status
```

不得：

```text
UNKNOWN
```

后仍宣布 PASS。

---

# 32. S27 Execution Gate

预注册：

```text
all frozen dates processed

no extra signal dates

cash rejection = 0

average execution-date total absolute deviation <= 3%

materially off-target dates <= 10%

average cash ratio <= 2%

RQAlpha CAGR > 0

RQAlpha CAGR >= VectorBT CAGR - 2pp

RQAlpha MaxDD
not worse than VectorBT by > 5pp
```

MaxDD 比较必须使用统一 signed-metric helper。

---

# 33. S27 Decision

只能：

```text
ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW

DO_NOT_ADVANCE_S27A_EXECUTION

BLOCK_S27A_EXECUTION_REPRODUCTION

BLOCK_S27A_EXECUTION_ENVIRONMENT
```

即使 ADVANCE：

禁止：

```text
create candidate
start prospective shadow
replace S2
```

---

# ============================================================

# TRACK B — S10A AUTHORITATIVE EXECUTION REVIEW

# ============================================================

# 34. Track B Question

唯一问题：

> PIT-corrected、robustness-qualified S10A 20/10 无杠杆 volatility-targeting frozen target schedule 能否由 RQAlpha 忠实实现？

不再研究：

```text
10/20/40
8/10/12
```

这些 robustness 问题已经关闭。

---

# 35. S10 Frozen Semantics

保持：

```text
base:
25% China equity
25% US equity
25% Gold
25% China bond

vol_window = 20

target volatility = 10%

scale range = [0,1]

no leverage

excess defensive allocation → bond

monthly signal
next canonical observation execution

10 bps fees
5 bps slippage
```

---

# 36. Corrected S10 Inception

必须使用 PIT contract 自动确定。

不要硬编码。

所有：

```text
positive target assets
```

必须在执行日 tradable。

---

# 37. Freeze S10 Target Schedule

生成：

```text
research/results/
s10a_pit_corrected_frozen_targets_v1.csv
```

记录：

```text
target count
first execution date
last execution date
SHA-256
```

---

# 38. VectorBT Reproduction Gate

frozen schedule 必须 reproduce Batch 04 corrected S10 baseline。

比较：

```text
CAGR
MaxDD
Sharpe
Calmar
turnover
```

失败：

```text
BLOCK_S10A_EXECUTION_REPRODUCTION
```

不得运行 RQAlpha。

---

# 39. RQAlpha Replay

与 S27 一样：

```text
frozen targets only
```

RQAlpha 不计算：

```text
realized vol
scale
base weights
```

---

# 40. S10 Execution Diagnostics

至少输出：

```text
same execution diagnostics as S27
```

另外增加：

```text
months scale < 1

average frozen scale

average implemented risky exposure

average implemented bond exposure
```

这些来自 frozen target diagnostics，而不是 RQAlpha 重算。

---

# 41. S10 Execution Gate

采用和 S27 一致的 execution-quality core gate：

```text
all dates processed

cash rejection = 0

avg target deviation <= 3%

material dates <= 10%

avg cash <= 2%

RQAlpha CAGR > 0

CAGR gap vs VectorBT <= 2pp

MaxDD worsening <= 5pp
```

---

# 42. S10 Decision

只能：

```text
ADVANCE_S10A_TO_CANDIDATE_FREEZE_REVIEW

DO_NOT_ADVANCE_S10A_EXECUTION

BLOCK_S10A_EXECUTION_REPRODUCTION

BLOCK_S10A_EXECUTION_ENVIRONMENT
```

禁止自动 candidate freeze。

---

# ============================================================

# TRACK C — S4C BOUNDED ROBUSTNESS

# ============================================================

# 43. Track C Question

唯一问题：

> PIT-corrected canonical ERC / skfolio transfer 优势是否在有限 risk-estimation neighborhood、时间切片和成本变化下稳定？

不是：

```text
find best ERC parameters
```

---

# 44. Freeze S4C Economic Semantics

保持：

```text
skfolio RiskBudgeting

RiskMeasure.VARIANCE

equal risk budgets

long only

fully invested

no leverage

no expected-return target

min eligible = 6

same risk universe

fallback semantics from PIT contract

month-end estimation

next canonical observation execution
```

---

# 45. One-Factor Risk Window Plateau

只改变：

```text
aligned returns window:

40
60  ← frozen center
80
```

对应价格 observation 数按实现语义正确转换。

禁止：

```text
40/60/80
×
covariance estimator
×
weight cap
×
risk measure
```

---

# 46. No Best Window Selection

中心永远：

```text
60 aligned returns
```

不管 40 或 80 历史表现更好。

本轮只回答：

```text
Is 60 inside a stable neighborhood?
```

---

# 47. Per-Case Comparator Alignment

每个 window 必须独立构造：

```text
ERC

same-eligible inverse-vol

same-eligible equal-weight
```

必须保持：

```text
same eligible assets
same aligned data
same execution dates
same costs
```

---

# 48. Fixed Periods

复用既有固定 period boundaries。

不得重新选择 bull/bear/crisis windows。

对每个 period 报告：

```text
ERC CAGR
MaxDD
Sharpe
Calmar

inverse-vol same-period metrics

equal-weight same-period metrics
```

---

# 49. Rolling Robustness

复用：

```text
rolling 3Y
rolling 5Y
```

重点记录 ERC 相对 aligned inverse-vol：

```text
positive CAGR share

Sharpe improvement share

MaxDD improvement share

Calmar improvement share
```

---

# 50. Cost Sensitivity

只对中心：

```text
60-return ERC
```

测试：

```text
15 bps
30 bps
50 bps
```

沿用已有 cost-definition convention。

不要做：

```text
window × cost
```

grid。

---

# 51. Concentration Robustness

必须记录：

```text
median maximum weight

P95 maximum weight

maximum observed weight

months any asset > 50%

effective number of assets
median
P05
```

不得事后加入：

```text
50% cap
40% cap
```

救结果。

---

# 52. S4C Robustness Gate

Protocol freeze 前定义。

建议要求：

## Reproduction

```text
60-return center
reproduces Batch 04 corrected baseline
```

否则：

```text
BLOCK_S4C_ROBUSTNESS_REPRODUCTION
```

## Window neighborhood

所有 40/60/80：

```text
CAGR > 0
Sharpe > 0
MaxDD > -30%
```

至少 2/3：

```text
relative to same-window inverse-vol

CAGR >= comparator CAGR - 1.5pp

MaxDD no worse by > 2pp

AND

Sharpe >= comparator Sharpe + 0.02
OR
Calmar >= comparator Calmar + 0.03
```

## Fixed periods

中心 60：

```text
all periods CAGR > 0
```

至少 3/4：

```text
Sharpe > inverse-vol
OR
Calmar > inverse-vol
```

## Rolling

中心：

```text
3Y positive CAGR share >= 90%

5Y positive CAGR share >= 95%
```

并至少：

```text
60% of 3Y windows
have Sharpe improvement
OR MaxDD improvement
vs inverse-vol
```

## Cost

50bps：

```text
CAGR > 0
Sharpe >= 0.60
```

---

# 53. Concentration Is Evidence, Not Automatic Optimization Trigger

如果：

```text
P95 max weight > 50%
```

仍然成立：

报告。

不要自动 REJECT，除非 protocol freeze 前明确设定 concentration hard gate。

更重要的是回答：

```text
Is the historical benefit dependent
on concentrated risk allocations?
```

---

# 54. S4C Decision

只能：

```text
ADVANCE_S4C_TO_EXECUTION_REVIEW

REJECT_S4C_ROBUSTNESS

BLOCK_S4C_ROBUSTNESS_REPRODUCTION

BLOCK_S4C_UPSTREAM_EXECUTION
```

即使 ADVANCE：

本 Goal 不运行 RQAlpha S4C。

---

# ============================================================

# SHARED IMPLEMENTATION RULES

# ============================================================

# 55. Mandatory PIT Enforcement Everywhere

三个 Batch 05 runner 必须全部使用新的 mandatory PIT validation。

禁止：

```text
temporary bypass
```

任何 pre-listing / missing execution price：

```text
FAIL or NO EXECUTABLE TARGET
```

按 frozen semantics 处理。

---

# 56. No New Infrastructure

禁止创建：

```text
ExecutionFramework
RobustnessFramework
ExperimentManager
CandidateManager
PITPlatform
SecurityMasterService
StrategyRegistryService
```

只允许：

```text
small helpers
when there is obvious shared responsibility
```

---

# 57. Shared Frozen-Target Replay Helper

如果 S27/S10 产生明显相同的：

```text
freeze target
hash target
VectorBT replay
RQAlpha replay
```

代码：

可以抽一个极小 helper。

例如：

```text
research/experiments/frozen_target_replay.py
```

但只能包含：

```text
artifact loading
hashing
validation
thin replay plumbing
```

不得成为 execution framework。

---

# 58. RQAlpha Version Rule

不要因为发现 upstream 新 tag 就自动升级。

使用当前 repository 已批准版本。

只有：

```text
current approved version blocks execution
```

才允许有界 upstream investigation。

---

# 59. skfolio Version Rule

S4C 继续使用当前已验证 stable version。

不要：

```text
upgrade because newer exists
```

除非现版本出现明确 blocker。

---

# 60. No New Strategies

禁止：

```text
MinVar
HRP
HERC
Maximum Diversification
Black-Litterman

Theme Rotation
Sector Rotation V2
Breadth V2
Defensive Rotation

new trend variants
```

---

# 61. Protocol Freeze Validation

Commit A 前运行：

```bash
uv sync --extra dev
```

如果 S4C research extra 需要：

```bash
uv sync --extra dev --extra research
```

然后：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python research/experiments/run_s2_r1_shadow.py --verify-candidate
```

全部 PASS。

---

# 62. Commit A

建议：

```text
freeze batch 5 earned stage validation protocol
```

push。

记录：

```text
BATCH_05_PROTOCOL_FREEZE_SHA
```

---

# 63. Run Order

Protocol freeze 后：

```text
1. S27A VectorBT reproduction
2. S27A RQAlpha execution

3. S10A VectorBT reproduction
4. S10A RQAlpha execution

5. S4C robustness
```

三个 track 彼此独立。

一个 reject 不阻止其他 track。

---

# 64. Shared Correctness Blockers

只有：

```text
S2 integrity failure

PIT contract defect

canonical data corruption

shared metric bug

shared execution adapter defect
```

才暂停整批。

---

# 65. Invalid Run Discipline

任何：

```text
wrong metric start
wrong comparator
wrong PIT mask
wrong execution date
signal recomputed in RQAlpha
wrong target hash
signed MaxDD regression
lookahead
```

必须：

```text
INVALID_RUN_BATCH_05_R<N>.md
```

然后：

```text
Protocol V2
freeze commit
rerun affected track
```

不得静默修。

---

# ============================================================

# RESULTS + DOCUMENT OWNERSHIP

# ============================================================

# 66. Result Artifacts

建议生成：

```text
research/results/

S27A_RQALPHA_EXECUTION_REVIEW_V2.md
S10A_RQALPHA_EXECUTION_REVIEW_V1.md
S4C_ROBUSTNESS_V1.md

BATCH_05_EARNED_STAGE_VALIDATION.md
```

以及必要的 machine-readable CSV。

---

# 67. Batch 05 Summary

必须包含：

| Strategy | Stage Before     | Question                                            | Decision | Next Eligibility |
| -------- | ---------------- | --------------------------------------------------- | -------- | ---------------- |
| S27A     | Execution Review | Can RQAlpha implement PIT-corrected targets?        |          |                  |
| S10A     | Execution Review | Can RQAlpha implement frozen vol-targeting targets? |          |                  |
| S4C      | Robustness       | Is ERC benefit stable?                              |          |                  |

---

# 68. Cross-Track Interpretation

必须回答：

```text
1. Did S27A survive authoritative execution?

2. Did S10A survive authoritative execution?

3. Which execution deviations are native market/account effects?

4. Does S4C remain superior to aligned inverse-vol
   across a bounded neighborhood?

5. Is S4C improvement dependent on concentration?

6. Which strategies have now earned
   candidate-freeze eligibility?

7. Which strategy has only earned
   execution-review eligibility?

8. Which strategies should stop?

9. Does any result affect S2 R1?
```

最后一题正常应为：

```text
NO
```

---

# ============================================================

# MANDATORY DOCUMENT SYNCHRONIZATION

# ============================================================

# 69. Documentation Is Part of Definition of Done

本 Goal 不允许：

```text
code done
tests pass
results committed
docs stale
```

以下文档同步不是 optional cleanup。

它们属于：

```text
Goal completion criteria
```

---

# 70. docs/CURRENT_STATE.md — Mandatory

必须更新。

只描述：

```text
current active frontier
```

不要重复大段历史。

必须包含：

```text
S2 current state

S27 current state

S10 current state

S4C current state

next blockers / earned stages

current repository frontier
```

如果：

```text
S27 execution PASS
```

只能写：

```text
CANDIDATE_FREEZE_REVIEW_ELIGIBLE
```

不得写：

```text
candidate
```

除非真的执行了独立 freeze Goal。

---

# 71. docs/STRATEGY_CATALOG.md — Mandatory

必须更新每个策略生命周期。

同时检查：

```text
top-level strategy section

Batch history section

bottom canonical mapping table
```

三处必须一致。

禁止出现：

```text
top says eligible
bottom says rejected
```

这种状态漂移。

---

# 72. docs/STRATEGY_RESEARCH_MAP.md — Mandatory

更新 local mapping 和 remaining gap。

例如根据实际结果：

```text
S27A
execution validated / rejected

S10A
execution validated / rejected

S4C
execution-review eligible / rejected
```

External tier 不随本地结果变化。

---

# 73. docs/RESEARCH_LEDGER.md — Mandatory

按最新编号追加独立条目。

至少对应：

```text
S27A execution review

S10A execution review

S4C robustness

Batch 05 stage decisions
```

如果 Phase 0 PIT enforcement mandatory 是新永久事实：

也追加单独条目。

保持：

```text
append-only
```

旧 Batch 03/04 条目不删除。

---

# 74. docs/ARCHITECTURE.md — Conditional

只有 Phase 0 导致稳定 ownership / boundary 改变时更新。

如果现有架构已经明确：

```text
PIT validation before VectorBT
```

则无需为了 API 参数变化更新。

不要把：

```text
S27 numbers
S10 metrics
S4C window values
```

写入 architecture。

---

# 75. docs/RESEARCH_RULES.md — Conditional

如果已有永久规则已经覆盖：

```text
mandatory PIT gate
signed MaxDD semantics
```

则不重复新增。

如果代码 hardening 暴露永久规则缺失：

才更新。

---

# 76. AGENTS.md — Conditional but Must Be Audited

至少检查：

```text
External Evidence Gate

PIT Tradability Gate

document routing

authority order
```

是否仍与实现一致。

如果已有内容足够：

UNCHANGED。

不要把 Batch 05 参数写入 AGENTS。

---

# 77. External Evidence Registry — Conditional

只在有新的 external evidence 时更新。

不要根据：

```text
S27 PASS
S10 PASS
S4C FAIL
```

改变 external tier。

---

# 78. docs/goal.md — Mandatory

用本 Goal 替换上一轮完成 Goal。

完成后增加：

```text
Status: completed

Work:
Phase 0 + Batch 05

Starting HEAD:
...

Phase 0 SHA:
...

Protocol Freeze SHA:
...

Protocol Revisions:
...

Results SHA:
...

S2:
...

S27A:
...

S10A:
...

S4C:
...

Next:
AWAIT_BATCH_05_ARCHITECT_REVIEW
```

---

# 79. Documentation Consistency Audit

提交结果前必须执行人工/脚本检查：

```text
CURRENT_STATE
STRATEGY_CATALOG
STRATEGY_RESEARCH_MAP
RESEARCH_LEDGER
Batch 05 result
goal.md completion metadata
```

逐项确认当前 decision 一致。

特别禁止以下 drift：

```text
S27 current eligible
but catalog says blocked

S10 execution pass
but current state says closed

S4C robustness reject
but research map says robustness eligible
```

---

# 80. Authority Rule for Docs

保持：

```text
source + frozen artifacts
>
ARCHITECTURE
>
RESEARCH_RULES
>
RESEARCH_LEDGER
>
STRATEGY_CATALOG
>
CURRENT_STATE
>
goal.md
```

如果发现冲突：

修正拥有该语义的文档。

不要简单把所有内容复制到所有文件。

---

# ============================================================

# FINAL VALIDATION

# ============================================================

# 81. S2 Final Integrity Gate

最后再次：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

不得修改：

```text
research/shadow/s2_r1/candidate_manifest.json
```

---

# 82. Full Tests

运行：

```bash
uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy
```

research dependency 如启用：

```bash
uv sync --extra dev --extra research
```

后再验证一次关键 tests。

---

# 83. Architecture Drift Audit

最终回答：

```text
Did we modify S2 R1?

Did we bypass PIT validation?

Did we make PIT validation optional again?

Did we modify S27 economic semantics?

Did we modify S10 economic semantics?

Did we tune S4C to improve results?

Did we pick best ERC window?

Did RQAlpha recompute signals?

Did we implement local accounting/matching?

Did we add a generic execution framework?

Did we add a generic robustness framework?

Did we add new strategies?

Did we automatically create a candidate?

Did we automatically start prospective shadow?

Did we leave CURRENT_STATE stale?

Did we leave STRATEGY_CATALOG stale?

Did we leave STRATEGY_RESEARCH_MAP stale?
```

正常答案全部：

```text
NO
```

最后三项尤其必须为：

```text
NO
```

---

# 84. Commit B

结果与所有文档同步后：

```bash
git status
git diff
```

创建：

```text
evaluate batch 5 earned strategy stages
```

push。

若仅需填写：

```text
docs/goal.md
Results SHA
```

允许一个 metadata-only commit。

---

# 85. Final Completion Report

最终回复必须报告：

```text
Starting HEAD

Phase 0 SHA

Batch 05 Protocol Freeze SHA

Protocol Revision SHAs

Results SHA

Ending HEAD
```

---

# 86. Report Phase 0

至少：

```text
PIT validation mandatory?
YES/NO

all run_target_weights callers migrated?
YES/NO

S2 verification?
PASS/FAIL

CURRENT_STATE synchronized?
YES/NO

STRATEGY_CATALOG synchronized?
YES/NO

STRATEGY_RESEARCH_MAP synchronized?
YES/NO
```

---

# 87. Report S27A

```text
corrected frozen target count

target SHA

VectorBT reproduction

RQAlpha version

RQAlpha CAGR
MaxDD
Sharpe

turnover
cost

cash rejections
partial fills
volume limits

average cash ratio

average target deviation

material deviation dates

decision
```

---

# 88. Report S10A

```text
corrected frozen target count

target SHA

VectorBT reproduction

RQAlpha version

RQAlpha CAGR
MaxDD
Sharpe

turnover

average implemented risky exposure

average bond exposure

cash / deviation diagnostics

decision
```

---

# 89. Report S4C

```text
40 / 60 / 80 results

same-window inverse-vol comparators

same-window equal-weight comparators

fixed periods

rolling 3Y

rolling 5Y

15/30/50 bps costs

concentration diagnostics

effective number of assets

decision
```

---

# 90. Current-State Matrix in Final Report

必须明确给：

| Strategy | Before                    | Batch 05 Decision | Current Status |
| -------- | ------------------------- | ----------------- | -------------- |
| S2       | Prospective Shadow        | untouched         |                |
| S27A     | Execution Review Eligible |                   |                |
| S10A     | Execution Review Eligible |                   |                |
| S4C      | Robustness Eligible       |                   |                |

---

# 91. Mandatory Stop

完成全部内容后：

```text
BATCH_05_COMPLETE

AWAIT_BATCH_05_ARCHITECT_REVIEW
```

必须 STOP。

禁止自动：

```text
freeze S27 candidate

freeze S10 candidate

run S4C execution

start new prospective shadow

compare candidate portfolio

start Theme Rotation

start Batch 06
```

---

# 92. What the Next Principal Review Will Decide

本 Goal 不执行，但应为下一轮留下清楚信息：

```text
Should S27A become a formal Research Candidate?

Should S10A become a formal Research Candidate?

Should S4C advance to authoritative execution?

Should multiple candidates coexist?

Does S2 remain the only prospective shadow?

Which strategies add genuinely orthogonal value?
```

---

# 93. Final Principle

```text
Correctness is now a contract,
not a convention.

PIT validation must be
difficult to bypass accidentally.

Historical PASS
does not create a candidate.

Robustness PASS
earns execution.

Execution PASS
earns candidate review.

Candidate review
is separate from candidate freeze.

Candidate freeze
is separate from prospective evidence.

Do not skip stages.

Do not optimize after observing outcomes.

Do not start new strategies
while qualified existing strategies
still have unanswered stage questions.

Keep external evidence
separate from local evidence.

Keep historical evidence
separate from current state.

Keep current state synchronized
across every owning document.

Code is not complete
until the repository's knowledge
matches the code and results.

Literature first.
PIT first.
Correctness first.
Earn the next stage.
Document the decision.
Then stop.
```

## Status: completed

Work: Phase 0 PIT enforcement + Batch 05 earned stage validation.

Starting HEAD: `0a90868`

Phase 0 SHA: `de558618859c684affc143db0f0a425df7cf0e05`

Protocol Freeze SHA: `04507995ed67effdff1ec459b946586a521b75fb`

Protocol Revisions: `1028dea903f0a46204e45ef904c7f54222586ffc` (V2), `6ce67f6b47d3deefe852d1356c7a20ade082c281` (V3).

Results SHA: pending Commit B.

S2: unchanged; frozen prospective shadow remains active.

S27A: `ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW` only.

S10A: `DO_NOT_ADVANCE_S10A_EXECUTION` because one native cash rejection violates the frozen gate.

S4C: `ADVANCE_S4C_TO_EXECUTION_REVIEW` only; concentration evidence retained.

Next: `AWAIT_BATCH_05_ARCHITECT_REVIEW`.
