# TactiCore

TactiCore 是一个面向个人投资者的低频多资产战术配置研究系统。它每天可以计算信号，但默认按月调仓，目标是回答“当前应持有什么、持有多少、是否需要操作”，而不是建设通用量化平台。

当前版本已完成 Tushare Pro 真实数据路径、S1 全球双动量证据闭环，以及 S2 多资产趋势跟踪的 VectorBT 与 RQAlpha 执行审计。S1 为 `REJECT_S1`；S2 V2 的当前决策为 `REVISE_S2_EXECUTION`：趋势经济性仍在，但全仓目标的资金不足拒单会因 signal-change-only 不重试而形成长期偏离。

## 快速开始

要求 Python 3.10–3.12，并建议使用 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python research/experiments/run_gdm_real_data.py
uv run python research/experiments/run_s1_evidence_closure.py
uv run python research/experiments/run_s2_economic_screen.py
uv run python research/experiments/run_s2_decision_audit_v2.py
uv run python research/experiments/run_s2_rqalpha_validation.py
```

仓库已冻结一份截止 2026-08-31 的 Tushare canonical 数据。前两个研究入口保留 S1 和 S2 V1 历史证据；`run_s2_decision_audit_v2.py` 比较严格 V1、有效观测 V2A 与只在目标变化时提交的 V2B。`run_s2_rqalpha_validation.py` 不重算信号，只把冻结的 V2B 目标变化日程交给仓库外 RQAlpha 官方 bundle 执行。

如需从相同请求参数重建数据，先通过环境变量提供 token，再运行：

```bash
uv run python research/experiments/download_tushare_data.py \
  --start-date 20120101 \
  --end-date 20260831
```

下载脚本只读取 `TUSHARE_TOKEN`，不会将 token 写入文件。数据格式、复权假设、缺失处理和复现方式见 [`data/canonical/README.md`](data/canonical/README.md)。保留的演示入口 `research/experiments/run_gdm_baseline.py` 只用于离线冒烟测试，其默认输出不构成市场证据。

## 当前研究证据

252 日基线在 2013-06-28 至 2026-08-31 指标区间内得到 CAGR 8.32%、最大回撤 -46.81%、Sharpe 0.491 和 Calmar 0.178。进一步证据显示：2020–2022 CAGR 为负，滚动 3/5 年均出现负 CAGR；美国宽基买入持有和全风险资产年度等权明显优于同区间 S1，简单股债金组合以相近 CAGR 获得显著较小回撤。完整结论见 [`research/results/S1_EVIDENCE_CLOSURE_V1.md`](research/results/S1_EVIDENCE_CLOSURE_V1.md)。

已用 RQAlpha 5.6.5 官方下载的仓库外 bundle 完整实跑。当前 adapter 在每月首个交易日用此前 253 根前复权日线计算 252 日动量，过滤未上市标的并提交目标仓位。RQAlpha 的整手、现金、费用、涨跌停和成交量限制使累计收益显著低于 VectorBT，这确认了当前 S1 执行表达的弱点。详见 [当前状态](docs/CURRENT_STATE.md) 与 [架构](docs/ARCHITECTURE.md)。

S2 不做横截面排名：每只具备最近 200 个有效观测且信号日有价格的风险资产拥有独立等额 sleeve，价格低于自身均线时该 sleeve 转入国债 ETF。RQAlpha 实现组合的 CAGR 为 7.87%、最大回撤 -22.45%，但 34 个目标执行日显著未达目标，72 个后续检查月仍显著偏离。42 个原生失败状态中 34 个来自资金不足，因此下一步只检验由既有费用和滑点推导的现金预留。历史 V1 结论见 [`S2_BASELINE_ECONOMIC_SCREEN_V1.md`](research/results/S2_BASELINE_ECONOMIC_SCREEN_V1.md)，V2 经济筛选见 [`S2_DECISION_AUDIT_V2.md`](research/results/S2_DECISION_AUDIT_V2.md)，执行结论见 [`S2_RQALPHA_EXECUTION_VALIDATION_V1.md`](research/results/S2_RQALPHA_EXECUTION_VALIDATION_V1.md)。

## 重要边界

- VectorBT 用于快速探索，RQAlpha 用于权威事件驱动验证。
- 仓库没有、也不会建立第三套回测、组合记账或撮合引擎。
- universe 中的 ETF 是研究代理，不代表已经通过容量、跟踪误差、税费、幸存者偏差或生产可交易性审查。
- 演示数据输出不能用于评价策略收益。
- S2 V2 仍不是生产候选；完成单一现金预留实验并关闭执行偏离前，不做参数稳健性或 S3。
