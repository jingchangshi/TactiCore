# Goal: S3A China Sector Rotation — Tradable Universe + Transparent Baseline V1

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
Strategy Research Reviewer
+
Repository Architecture Maintainer
```

---

# 0. Why This Work Exists

TactiCore 已完成 S2 的历史研究闭环并将：

```text
S2 Research Candidate R1
```

冻结为：

```text
FROZEN
+
PROSPECTIVE_SHADOW_ACTIVE
```

S2 现在等待真实未来市场数据，不能通过更多历史 backtest 加速。

因此当前主动研究主线转向：

```text
S3 China Sector / Theme Rotation
```

但 S3 不能一开始就变成 DailyETF 式的复杂系统。

本 Goal 只回答一个有限问题：

> 一个基于真实可交易 A 股行业 ETF、简单中期相对动量、绝对动量过滤和月频低换手执行的透明行业轮动 baseline，是否存在足够明确的经济证据，值得进入下一阶段稳健性研究？

本 Goal 是：

```text
hypothesis
→ tradable universe
→ canonical data
→ transparent signal
→ VectorBT economic screen
→ advance / reject
```

不是：

```text
production strategy
theme intelligence
multi-factor ranking
market regime engine
AI scoring
risk-budget platform
parameter optimizer
RQAlpha execution closure
```

---

# 1. Repository First

首先重新读取最新 remote `main`。

不要依据：

```text
本 Prompt 中的预期 HEAD
上一轮 Codex 报告
旧对话
CURRENT_STATE 的单一描述
记忆
```

直接实现。

第一步必须读取：

```text
AGENTS.md
```

并按其中 routing contract 继续。

至少读取：

```text
README.md

AGENTS.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/LESSONS_FROM_DAILYETF.md
docs/goal.md

config/strategy.toml
config/universe.csv

data/canonical/provenance.json

tacticore/data/tushare.py
tacticore/data/universe.py
tacticore/data/prices.py

tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

tacticore/strategies/global_dual_momentum.py
tacticore/strategies/multi_asset_trend.py

research/shadow/s2_r1/candidate_manifest.json
research/shadow/s2_r1/README.md

research/results/S2_R1_PROSPECTIVE_PROTOCOL_V1.md
research/results/S2_PARAMETER_PLATEAU_V1.md
```

并检查相关 tests。

记录：

```text
starting HEAD
recent commits
working tree
dependency versions
S2 R1 candidate state
S2 frozen file hashes
current S3 implementation state
```

如果仓库事实与本 Prompt 冲突：

```text
repository evidence wins
```

---

# 2. Protect S2 R1 Before Doing Anything Else

这是本 Goal 的硬约束。

首先运行已有 candidate integrity 验证：

```text
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须成功。

保存验证结果。

然后读取：

```text
research/shadow/s2_r1/candidate_manifest.json
```

确认所有 frozen inputs。

尤其是：

```text
config/strategy.toml
config/universe.csv

data/canonical/etf_adjusted_close.csv
data/canonical/trading_calendar.csv
data/canonical/provenance.json

tacticore/strategies/multi_asset_trend.py
tacticore/engines/rqalpha_adapter.py
```

---

# 3. S3 Must Not Modify S2 Frozen Inputs

禁止为了 S3 修改：

```text
config/strategy.toml
config/universe.csv

data/canonical/etf_adjusted_close.csv
data/canonical/trading_calendar.csv
data/canonical/provenance.json

tacticore/strategies/multi_asset_trend.py
```

也不要无必要修改：

```text
tacticore/engines/rqalpha_adapter.py
```

原因：

这些文件已经属于 S2 R1 frozen identity。

S3 必须拥有独立输入。

推荐新增：

```text
config/s3_sector_rotation.toml
config/s3_sector_universe.csv
```

而不是把 S3 section 追加到：

```text
config/strategy.toml
```

---

# 4. S3 Scope: Sector First, Themes Later

虽然长期策略家族叫：

```text
S3 China Sector / Theme Rotation
```

本轮只实现：

```text
S3A China Sector Rotation
```

不要加入 Theme ETF。

原因：

```text
行业 ETF
→ 相对清晰的经济分类
→ 较容易定义互斥 universe
→ 可以直接检验行业领导持续性
```

而 Theme ETF 经常存在：

```text
AI
半导体
机器人
算力
新能源
创新药
高端制造
```

之间的大量成分重叠。

如果一开始混合行业和主题，则无法区分：

```text
真实行业轮动 alpha
```

和：

```text
重复暴露同一热门因子
```

所以本 Goal：

```text
NO theme ETF
```

Theme extension 必须是后续独立研究问题。

---

# 5. Economic Hypothesis

在看回测结果之前，把 S3A V1 的经济假设写入报告：

> A 股行业收益存在数月尺度的相对趋势持续性。使用中期价格动量选择领先行业，同时过滤负绝对动量，并以月频、有限持仓和防御资产承接未使用风险预算，可能形成比静态行业暴露更好的风险调整后收益，同时保持较低交易频率。

重要：

这只是 hypothesis。

不要写成：

```text
sector momentum works
```

直到真实数据支持。

---

# 6. Universe Design Must Precede Return Inspection

Universe 是 S3 最大的潜在数据挖掘来源之一。

因此：

> 先冻结 universe selection rule，再运行收益回测。

不得根据：

```text
历史 CAGR
历史 Sharpe
2024–2026 热门行业
当前市场叙事
某 ETF 回测最好
```

决定是否纳入。

---

# 7. S3A Universe Requirements

建立：

```text
config/s3_sector_universe.csv
```

目标：

```text
约 10–15 个
广义、尽量非重叠的 A 股行业 ETF
```

最低：

```text
8 个有效行业
```

否则不足以形成有意义的 cross-sectional sector rotation。

每个行业原则上只选择一个代表 ETF。

允许的类别示例：

```text
银行
证券
消费
医药
科技/电子
通信
军工
新能源
汽车
机械/高端制造
电力设备
煤炭
有色
化工
农业
```

但具体分类必须由实际基金 metadata 和可交易性决定。

不要为了凑够类别强行加入主题产品。

---

# 8. Universe Selection Rule

Universe selection 不得使用收益数据。

预先采用类似规则：

1. 中国境内交易所挂牌 ETF；
2. 当前可交易；
3. 普通 long-only ETF；
4. 主要跟踪 A 股行业或明确行业指数；
5. 排除：

   * 宽基指数；
   * 海外指数；
   * 商品；
   * 债券；
   * 货币；
   * 杠杆；
   * 反向；
   * Smart Beta；
   * 高频策略型产品；
   * 主题重叠严重产品；
6. 一个 broad sector 最多一个代表 ETF；
7. 优先拥有更长真实交易历史的产品；
8. 同一行业存在多个合理候选时，使用明确 deterministic rule；
9. 不使用 backtest performance 作为 tie-break。

如果两个基金在 metadata 层面都满足条件：

优先：

```text
更早上市
```

若上市日相同：

```text
固定代码顺序
```

不要使用历史收益挑选。

---

# 9. Universe Evidence

生成：

```text
research/results/s3_sector_universe_v1.csv
```

至少记录：

```text
sector
symbol
tushare_symbol
rqalpha_symbol
fund_name
list_date
role
selection_reason
```

并在主报告解释：

```text
为什么纳入
为什么排除
选择是否使用了收益数据
```

正常答案：

```text
NO return data used for universe selection
```

---

# 10. Minimum Historical Coverage Gate

不要为了研究一个几乎只有最近两三年数据的 universe 而制造虚假的长期结论。

S3A baseline 启动前要求：

```text
至少 8 个 sector ETF
```

拥有足以支持：

```text
120-observation momentum
+
至少约 5 年评价期
```

的历史数据。

如果无法满足：

```text
BLOCK_S3A_UNIVERSE_COVERAGE
```

停止。

不要通过：

```text
降低到 3 个行业
加入大量主题 ETF
使用指数替代交易 ETF
缩短到极短历史
```

绕过。

---

# 11. Independent Canonical Dataset

S3 使用独立 historical canonical dataset。

推荐：

```text
data/canonical/s3_sector_rotation_v1/
```

其中仍使用熟悉的：

```text
etf_adjusted_close.csv
trading_calendar.csv
provenance.json
```

但不得修改 S2 root canonical 文件。

历史截止日期本轮固定：

```text
2026-08-31
```

理由：

```text
避免 partial September
+
与当前历史研究边界一致
+
不消费 S2 prospective observations
```

这只是 S3 V1 historical research cutoff。

---

# 12. Reuse Existing Tushare Data Code

现有：

```text
tacticore/data/tushare.py
```

已经能够接受 universe DataFrame。

不要复制 downloader。

只在必要时最小修改：

```text
research/experiments/download_tushare_data.py
```

增加类似：

```text
--universe
```

参数。

默认仍保持：

```text
config/universe.csv
```

以保证已有用法不变。

S3 调用类似：

```text
uv run python research/experiments/download_tushare_data.py \
  --universe config/s3_sector_universe.csv \
  --start-date <appropriate-history-start> \
  --end-date 20260831 \
  --output-dir data/canonical/s3_sector_rotation_v1
```

不要增加：

```text
ProviderRegistry
SectorDataProvider
DataWarehouse
DataLake
CacheManager
DataService
```

---

# 13. Preserve Existing Data Semantics

继续遵循已关闭规则：

```text
fund_daily.close × fund_adj.adj_factor
```

作为历史研究价格。

缺失：

```text
UNKNOWN
```

不得：

```text
forward fill
interpolate
zero fill
guess
```

每个 sector ETF 独立按有效 observation 计算 momentum。

signal date 自身必须存在真实价格。

---

# 14. Add S3A Independent Strategy Config

新增：

```text
config/s3_sector_rotation.toml
```

不要修改 S2 frozen `strategy.toml`。

V1 只允许一个透明 baseline。

预声明：

```text
momentum_lookback = 120
top_k = 3
absolute_momentum_threshold = 0.0

rebalance_frequency = monthly
execution_policy = SIGNAL_CHANGE_ONLY

fallback_symbol = 511010.SS

fees = 0.001
slippage = 0.0005
initial_cash = 1000000
```

120 个有效交易 observation 大致代表中期趋势。

这不是“最优参数”。

本 Goal：

```text
NO parameter search
```

---

# 15. Do Not Import S2's 200-Day Parameter Into S3

不要因为 S2 的：

```text
trend_window = 200
```

已经通过历史研究，就默认：

```text
sector rotation should use 200
```

S2 与 S3 是不同经济假设。

S3A V1 使用单一 transparent momentum horizon。

后续只有 baseline 值得继续研究时，才能独立进行：

```text
coarse parameter plateau
```

---

# 16. Strategy Implementation

新增：

```text
tacticore/strategies/china_sector_rotation.py
```

只实现 S3A 自有经济语义。

不要把逻辑放进：

```text
vectorbt_adapter.py
```

VectorBT adapter 不应该知道 sector momentum。

---

# 17. Exact S3A V1 Signal

在每个月最后 canonical observation day：

对于每一个 sector ETF：

### Availability

要求：

```text
signal day 有真实价格
```

且至少拥有足够有效 observation 来计算：

```text
120-observation momentum
```

否则：

```text
UNAVAILABLE
```

不得设置 momentum = 0。

---

### Momentum

定义单一 trailing total-price momentum：

```text
momentum =
current adjusted close
/
lookback adjusted close
- 1
```

使用该 ETF 自身有效 observations。

不要加入：

```text
20d momentum
60d momentum
volatility-adjusted momentum
RSI
MACD
breadth
fund flow
technical score
fundamental score
macro score
```

---

### Absolute Filter

只有：

```text
momentum > 0
```

才进入 ranking。

否则：

```text
NEGATIVE_SIGNAL
```

与：

```text
UNAVAILABLE
```

保持不同状态。

---

### Relative Ranking

对所有：

```text
AVAILABLE
+
positive momentum
```

sector ETF：

按 momentum 降序。

tie-break 必须 deterministic，例如：

```text
symbol ascending
```

---

# 18. Portfolio Construction

最多选择：

```text
top_k = 3
```

每个 risk sleeve 固定：

```text
1 / top_k
```

即：

```text
1/3
```

如果有 3 个 positive sector：

```text
1/3
1/3
1/3
```

如果只有 2 个：

```text
sector A = 1/3
sector B = 1/3
fallback = 1/3
```

如果只有 1 个：

```text
sector A = 1/3
fallback = 2/3
```

如果没有：

```text
fallback = 100%
```

这样避免：

> 市场只剩一个正趋势行业时，自动把全部风险预算集中到一个 sector。

---

# 19. Target Invariants

每个 target 必须：

```text
weight >= 0
weight <= 1
sum(weights) == 1
```

且单个 sector：

```text
weight <= 1/3
```

除 fallback 外。

---

# 20. Execution Timing

继续遵循永久规则：

```text
month-end close
        ↓
signal
        ↓
next canonical observation day
        ↓
execution
```

严禁：

```text
same-close execution
```

---

# 21. SIGNAL_CHANGE_ONLY

S3A V1 使用：

```text
SIGNAL_CHANGE_ONLY
```

如果 top-3 / fallback target 与上月完全一致：

```text
不要机械重平衡
```

原因：

排名没有改变意味着没有新经济信号。

不要为了恢复严格 1/3 权重每月产生额外订单。

这是低维护 baseline。

---

# 22. Reuse VectorBT

使用已有：

```text
tacticore.engines.vectorbt_adapter.run_target_weights
```

把策略生成的 execution weights 交给 VectorBT。

不要新增：

```text
sector_backtester.py
rotation_engine.py
portfolio_simulator.py
reference_engine.py
```

VectorBT 继续拥有：

```text
portfolio simulation
orders
trades
accounting
records
```

---

# 23. Baselines / Benchmarks

S3A 至少比较两个 benchmark。

## Benchmark A — Broad Market

优先：

```text
510300.SS
```

buy-and-hold。

目的：

```text
是否值得承担 sector-selection complexity
```

---

## Benchmark B — Sector Equal Weight

建立一个非常简单、experiment-local 的：

```text
availability-aware equal-weight sector basket
```

目的：

> 区分 sector universe 本身的 beta 与 rotation selection 是否增加价值。

不要把它建设成新的 strategy package。

它只用于：

```text
research comparison
```

---

# 24. Evaluation Start

避免在只有少数 sector ETF 有历史的早期阶段宣称完成 cross-sectional rotation。

预声明 coverage gate：

评价期开始必须满足：

```text
data-eligible sectors >= 8
```

并已经拥有足够的 120-observation warm-up。

评价 start 应由这一规则确定。

报告实际：

```text
evaluation_start
evaluation_end
eligible-sector count distribution
```

不要事后选择表现最好的开始日期。

---

# 25. Economic Screen Metrics

S3A V1 至少报告：

```text
CAGR
Max Drawdown
Sharpe
Calmar
worst year

turnover
trade count
average holding days

target-change months
annualized target-change months

sector coverage
average eligible sector count
minimum eligible sector count

fallback usage
```

不要只看 CAGR。

---

# 26. Rotation-Specific Evidence

至少另外回答：

```text
哪些行业最常被选中？

持仓是否严重集中在少数行业？

top-3 实际变化频率是多少？

fallback 被使用多少月份？

是否存在单一行业贡献绝大部分收益？

early / late period 的 sector breadth 是否明显不同？
```

这些是 diagnostics。

不要因此增加复杂 scoring。

---

# 27. Do Not Run Parameter Search

本 Goal 禁止：

```text
60 / 80 / 100 / 120 / 160 / 200
```

批量搜索。

禁止：

```text
top_k = 1..10
```

搜索。

禁止：

```text
best Sharpe
best CAGR
grid search
Bayesian optimization
```

只有：

```text
lookback = 120
top_k = 3
threshold = 0
```

的 transparent V1 baseline。

---

# 28. Predeclare Economic Advance Gate

在运行收益结果前实现并写入报告。

S3A V1 只有满足以下全部基础条件才允许：

```text
ADVANCE_S3A_BASELINE_TO_ROBUSTNESS
```

### Data / Coverage

```text
>= 8 sector ETFs

AND

>= 8 data-eligible sectors
in at least 80% of evaluated month-end observations
```

---

### Absolute Economic Floor

```text
after-cost CAGR > 0

Sharpe >= 0.40

Max Drawdown better than -40%

annualized target-change months <= 10
```

---

### Rotation Value

相对于 availability-aware sector equal-weight benchmark：

在：

```text
CAGR
Max Drawdown
Sharpe
Calmar
```

四项中至少：

```text
2 项更优
```

且不能通过明显恶化其余风险指标获得。

Broad-market benchmark：

```text
510300.SS
```

作为重要 contextual comparison，但不要求 S3 必须 CAGR 超过沪深300才能进入下一阶段。

因为 S3 的目标是：

```text
risk-adjusted allocation value
```

而不只是 raw CAGR。

---

# 29. Decision Outcomes

本 Goal 必须最终给出一个主要决策。

## A. ADVANCE_S3A_BASELINE_TO_ROBUSTNESS

条件：

```text
数据覆盖成立
经济 floor 成立
rotation 相对 equal-weight 有明确价值
低频约束成立
```

表示：

> S3A transparent baseline 值得继续研究。

不表示：

```text
production candidate
```

下一 Goal 才考虑：

```text
universe robustness
+
coarse parameter plateau
+
historical regime stability
```

---

## B. REJECT_S3A_BASELINE

如果：

```text
baseline 本身缺乏经济价值
drawdown 过大
risk-adjusted evidence weak
rotation 不优于简单 sector equal-weight
维护/换手明显不符合低频使命
```

则：

```text
REJECT_S3A_BASELINE
```

禁止马上改成：

```text
lookback 93
top_k 4
weighted momentum
multi-factor
```

来救结果。

---

## C. BLOCK_S3A_UNIVERSE_COVERAGE

如果无法形成：

```text
>= 8
```

个具有合理历史长度的行业 ETF universe：

停止 baseline。

这代表：

```text
data/universe blocker
```

不是策略失败。

---

## D. REVISE_S3A_SEMANTICS

只允许在发现：

```text
明确 lookahead
目标权重数学错误
availability 定义错误
ETF 分类冲突
benchmark 方法错误
```

等具体方法缺陷时使用。

不得因为收益不好使用 REVISE。

---

# 30. Expected Implementation

合理新增文件大致为：

```text
config/s3_sector_rotation.toml
config/s3_sector_universe.csv

data/canonical/s3_sector_rotation_v1/
    etf_adjusted_close.csv
    trading_calendar.csv
    provenance.json

tacticore/strategies/china_sector_rotation.py

research/experiments/run_s3_sector_baseline.py

research/results/S3_SECTOR_BASELINE_V1.md
research/results/s3_sector_universe_v1.csv
research/results/s3_sector_targets_v1.csv
research/results/s3_sector_benchmark_comparison_v1.csv

tests/test_china_sector_rotation.py
tests/test_s3_sector_baseline.py
```

不要机械创建全部文件。

只有存在明确证据价值时才保留 CSV。

---

# 31. Downloader Change

允许对：

```text
research/experiments/download_tushare_data.py
```

做一个很小的通用化：

新增：

```text
--universe
```

默认值保持现有：

```text
config/universe.csv
```

S1/S2 旧调用必须继续工作。

不要修改：

```text
tacticore/data/tushare.py
```

除非实际发现它无法处理 S3 ETF。

不要提前泛化。

---

# 32. S2 R1 Must Continue Passing

完成 S3 代码以后，再次执行：

```text
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须仍然：

```text
PASS
```

这是本 Goal 的强制 regression gate。

如果失败：

```text
STOP
```

找到被 S3 误改的 frozen input。

不要更新 S2 manifest hash 来“修复”。

---

# 33. Do Not Touch S2 Candidate

禁止：

```text
更新 S2 manifest hash
修改 S2 strategy
修改 S2 historical cutoff
更新 S2 config
改变 S2 universe
重新跑 S2 parameter optimization
```

S3 是独立 strategy family。

S2 R1 必须继续等待 prospective evidence。

---

# 34. No RQAlpha Yet

本 Goal 不运行 S3 RQAlpha execution validation。

当前研究顺序：

```text
hypothesis
 ↓
VectorBT economic screen
 ↓
robustness
 ↓
only then authoritative execution
```

不要因为 RQAlpha 已经存在就提前进入 execution engineering。

如果 baseline 被拒绝：

RQAlpha 工作价值为零。

---

# 35. No Production Infrastructure

禁止：

```text
scheduler
cron
daemon
dashboard
web UI
broker
notification
live trading
daily report
position recommendation
```

S3A V1 只是 historical research baseline。

---

# 36. No DailyETF Reimplementation

读取：

```text
docs/LESSONS_FROM_DAILYETF.md
```

继承：

```text
研究知识
风险意识
数据陷阱
轮动思想
```

不要继承：

```text
多因子评分平台
数据 provider framework
研究治理 plane
自研 backtest
日报系统
复杂状态机
```

尤其禁止一开始加入：

```text
资金流
政策事件
新闻情绪
估值
拥挤度
宏观
技术指标组合
```

那些都可以成为未来增量假设。

第一步必须先知道：

> 单纯价格型 sector rotation 是否有基础 alpha。

---

# 37. Tests

至少覆盖：

### Universe

```text
sector symbols unique
sector category unique
fallback not counted as sector
>= 8 sector ETFs
```

### Momentum

```text
uses only data <= signal_date
uses valid observations
requires signal-day price
UNAVAILABLE != NEGATIVE_SIGNAL
```

### Ranking

```text
descending momentum
deterministic tie-break
only positive assets ranked
```

### Portfolio

```text
top_k <= 3
sector weight <= 1/3
fallback receives unused sleeves
weights sum to 1
```

### Timing

```text
month-end signal
next observation execution
no same-close execution
```

### Low Touch

```text
unchanged target
→ no new execution target
```

### Regression

```text
S2 frozen hashes unchanged
S2 candidate verify still passes
```

---

# 38. Do Not Test Framework Internals

不要测试：

```text
VectorBT accounting internals
Tushare server behavior
RQAlpha matching
```

只测试：

```text
TactiCore-owned economic semantics
data boundary
target generation
benchmark construction
experiment reproducibility
```

---

# 39. Documents

## AGENTS.md

正常：

```text
UNCHANGED
```

S3 不需要新 routing。

---

## ARCHITECTURE.md

正常：

```text
UNCHANGED
```

这仍然是：

```text
data
→ strategy semantics
→ VectorBT research
→ evidence / decision
```

没有新 architecture layer。

---

## RESEARCH_RULES.md

正常：

```text
UNCHANGED
```

本 Goal 没有产生新的永久方法。

不要把：

```text
120 days
top 3
sector list
```

写进 permanent rules。

---

## LESSONS_FROM_DAILYETF.md

正常：

```text
UNCHANGED
```

除非确实发现一个以前不存在且值得永久保留的通用经验。

---

# 40. Update Research Ledger

向：

```text
docs/RESEARCH_LEDGER.md
```

追加：

```text
RL-018 S3A Transparent Sector Rotation Baseline
```

记录：

```text
strategy
question
status
scope
universe rule
signal semantics
historical cutoff
decision
evidence
data hashes
framework version
reopen condition
```

如果：

```text
ADVANCE
```

状态可以：

```text
CLOSED
```

因为 V1 baseline screen 已完成。

后续 robustness 是新问题。

如果 data blocker：

可以记录：

```text
ACTIVE
```

并明确 blocker。

---

# 41. Update STRATEGY_CATALOG

S2 保持：

```text
Research Candidate R1
FROZEN
PROSPECTIVE_SHADOW_ACTIVE
```

不要改写。

扩充 S3：

```text
S3 China Sector / Theme Rotation

S3A Sector Rotation V1
hypothesis
universe
baseline semantics
historical screen result
decision
remaining unproven items
next stage
```

如果 baseline advance：

写：

```text
economic baseline: PASS
robustness: pending
execution validation: not started
production candidate: no
```

Theme Rotation：

仍然：

```text
not started
```

---

# 42. Update CURRENT_STATE

完成后 CURRENT_STATE 应表达两条并行但职责不同的线：

```text
S2 R1:
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
waiting for future evidence

S3:
current active research family
```

如果 S3A PASS：

```text
current S3 decision:
ADVANCE_S3A_BASELINE_TO_ROBUSTNESS

next unique active research direction:
S3A universe robustness + coarse parameter plateau
```

如果 REJECT：

写实际下一方向。

不要让 CURRENT_STATE 变成历史日志。

---

# 43. Replace docs/goal.md

当前完成的 S2 prospective Goal 已经是历史执行任务。

用本 Goal 替换：

```text
docs/goal.md
```

完成时可以保留：

```text
Status: completed
Decision: <actual result>
```

永久事实必须进入：

```text
RESEARCH_LEDGER
STRATEGY_CATALOG
research/results
CURRENT_STATE
```

---

# 44. Main Research Report

生成：

```text
research/results/S3_SECTOR_BASELINE_V1.md
```

结构至少包括：

```text
1. Research Question
2. Predeclared Hypothesis
3. Universe Selection Rule
4. Final Frozen Universe
5. Data Provenance
6. Missing / Availability Semantics
7. Exact Signal Definition
8. Portfolio Construction
9. Execution Timing
10. Benchmarks
11. Predeclared Advance Gate
12. Full-Sample Metrics
13. Benchmark Comparison
14. Coverage Evidence
15. Turnover / Maintenance Evidence
16. Sector Selection Diagnostics
17. Known Biases / Limitations
18. Decision
19. What This Does NOT Prove
20. Next ONE Research Direction
```

---

# 45. Explicit Bias Disclosure

S3A V1 使用当前明确选择的 tradable ETF universe。

因此必须说明可能存在：

```text
survivorship bias
fund-launch bias
limited historical sector breadth
ETF tracking differences
industry overlap
current-universe selection bias
```

不要在 V1 为了解决全部偏差建设 PIT universe engine。

如果 baseline 根本没有经济价值：

没有必要建设它。

如果 baseline advance：

下一阶段再专门验证：

```text
universe robustness / PIT sensitivity
```

---

# 46. Important Interpretation Rule

如果 S3A 表现良好：

不能说：

```text
行业轮动已验证
```

只能说：

```text
transparent sector rotation baseline
has enough historical economic evidence
to justify robustness research
```

如果表现不好：

不要说：

```text
行业轮动无效
```

只能说：

```text
this predeclared S3A V1 hypothesis
failed the economic screen
```

不同 hypothesis 必须成为新版本，而不是偷偷修改 V1。

---

# 47. Architecture Drift Audit

提交前逐项回答：

```text
Did we modify any S2 R1 frozen input?

Did we update the S2 manifest to hide such a modification?

Did we put S3 into config/strategy.toml?

Did we put S3 ETFs into config/universe.csv?

Did we mix themes into the sector baseline?

Did we choose ETFs based on historical return?

Did we run parameter optimization?

Did we implement custom backtesting?

Did we duplicate VectorBT?

Did we start RQAlpha validation before economic screening?

Did we build a data/provider platform?

Did we build production infrastructure?

Did we recreate DailyETF complexity?

Did we modify AGENTS.md without a routing problem?

Did we modify ARCHITECTURE.md without a responsibility change?

Did we modify RESEARCH_RULES.md merely to record S3 parameters?

Did we claim S3 is production-ready?
```

正常答案：

```text
NO
```

---

# 48. Validation

运行当前仓库全部正式验证：

```text
uv sync --extra dev

uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy
```

运行 S3 historical experiment。

运行前记录：

```text
data hashes
universe hash
config hash
```

运行后确保结果可复现。

然后再次：

```text
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须通过。

---

# 49. Git Diff Audit

提交前：

```text
git status
git diff
```

特别检查：

```text
config/strategy.toml
config/universe.csv
data/canonical/etf_adjusted_close.csv
data/canonical/trading_calendar.csv
data/canonical/provenance.json
tacticore/strategies/multi_asset_trend.py
tacticore/engines/rqalpha_adapter.py
```

这些 S2 R1 frozen files 不得发生变化。

---

# 50. Commit and Push

全部完成后创建一个 coherent commit。

建议 intent：

```text
establish S3 sector rotation transparent baseline
```

随后：

```text
git push
```

不要混入无关重构。

---

# 51. Final Report

最终报告必须包括：

```text
starting HEAD
ending HEAD
commit SHA

S2 R1 integrity before
S2 R1 integrity after

S3 universe size
sector list
selection rule
data range
data hashes

signal semantics
lookback
top_k
fallback semantics

evaluation range

CAGR
Max Drawdown
Sharpe
Calmar
worst year
turnover
trade count
average holding period
target-change months
fallback usage

510300 benchmark comparison
sector equal-weight benchmark comparison

final decision
```

并明确回答：

```text
Was S2 R1 modified?
NO

Did S2 candidate verification still pass?
YES

Were themes included?
NO

Was historical return used to construct the universe?
NO

Was parameter optimization performed?
NO

Was RQAlpha S3 validation performed?
NO

Was any generic infrastructure added?
NO

Is S3 production-ready?
NO
```

---

# 52. Expected Next Direction

如果：

```text
ADVANCE_S3A_BASELINE_TO_ROBUSTNESS
```

下一 Goal 应围绕：

```text
S3A Universe Robustness
+
Coarse Parameter Plateau
```

重点回答：

```text
结果是否依赖少数 ETF？
是否依赖当前幸存 universe？
120 日是否处于稳定参数平台？
top-3 是否具有结构稳定性？
不同市场阶段是否仍然成立？
```

而不是：

```text
加新闻
加资金流
加技术指标
加宏观
加 AI
```

如果：

```text
REJECT_S3A_BASELINE
```

则停止这一 baseline。

下一步重新选择经济 hypothesis，而不是微调参数。

---

# 53. Expected Architecture After This Goal

```text
                         TactiCore
                             │
               ┌─────────────┴─────────────┐
               │                           │
               ▼                           ▼
          S2 Research                  S3 Research
          Candidate R1
               │                           │
            FROZEN                  Sector Baseline V1
               │                           │
     Prospective Shadow               Tushare data
               │                           │
       future evidence             transparent momentum
               │                           │
               │                       VectorBT
               │                           │
               │                    economic screen
               │                     /           \
               │                  PASS          REJECT
               │                   │
               │                   ▼
               │          robustness research
               │
               └──────── no semantic coupling ────────
```

关键原则：

```text
S2 waits for time.
S3 continues research.

S3 must not mutate S2.

Sector before theme.

Simple price hypothesis before
complex factor intelligence.

Economic evidence before infrastructure.

VectorBT before RQAlpha.

Robustness before production.
```

---

## 完成状态

Status: completed

Decision: `REJECT_S3A_BASELINE`

权威结果：[S3A 中国行业轮动透明基线 V1](../research/results/S3_SECTOR_BASELINE_V1.md)。
