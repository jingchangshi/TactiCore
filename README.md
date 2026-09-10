# TactiCore

TactiCore 是一个面向个人投资者的低频多资产战术配置研究系统。它每天可以计算信号，但默认按月调仓，目标是回答“当前应持有什么、持有多少、是否需要操作”，而不是建设通用量化平台。

当前版本已在 M0–M2 最小闭环之上增加 Tushare Pro 真实数据路径：12 个资产的 canonical universe、全球双动量基线、VectorBT 真实历史研究，以及等待本地数据包验证的 RQAlpha 事件驱动路径。

## 快速开始

要求 Python 3.10–3.12，并建议使用 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python research/experiments/run_gdm_real_data.py
```

仓库已冻结一份截止 2026-08-31 的 Tushare canonical 数据，因此最后一条命令不需要联网。它会校验价格文件 SHA-256，运行 252 日基线，并比较 80/120/160/252 四个回看期。

如需从相同请求参数重建数据，先通过环境变量提供 token，再运行：

```bash
uv run python research/experiments/download_tushare_data.py \
  --start-date 20120101 \
  --end-date 20260831
```

下载脚本只读取 `TUSHARE_TOKEN`，不会将 token 写入文件。数据格式、复权假设、缺失处理和复现方式见 [`data/canonical/README.md`](data/canonical/README.md)。保留的演示入口 `research/experiments/run_gdm_baseline.py` 只用于离线冒烟测试，其默认输出不构成市场证据。

## 当前研究证据

252 日基线在 2013-06-28 至 2026-08-31 指标区间内得到 CAGR 8.32%、最大回撤 -46.81%、Sharpe 0.491 和 Calmar 0.178。四个指定回看期的 CAGR 均为正，但最大回撤均约为 -44% 至 -49%。这支持继续验证 S1，不代表策略已经稳健或适合生产。完整口径、换手、交易次数、平均持有期及局限见 [`research/results/GDM_REAL_DATA_RESEARCH.md`](research/results/GDM_REAL_DATA_RESEARCH.md)。

RQAlpha 验证需要仓库外的中国市场 bundle。准备 bundle 后，可调用 `tacticore.engines.rqalpha_adapter.run_rqalpha`；当前 adapter 在每月首个交易日用此前 253 根日线计算 252 日动量，并提交目标仓位。详见 [当前状态](docs/CURRENT_STATE.md) 与 [架构](docs/ARCHITECTURE.md)。

## 重要边界

- VectorBT 用于快速探索，RQAlpha 用于权威事件驱动验证。
- 仓库没有、也不会建立第三套回测、组合记账或撮合引擎。
- universe 中的 ETF 是研究代理，不代表已经通过容量、跟踪误差、税费、幸存者偏差或生产可交易性审查。
- 演示数据输出不能用于评价策略收益。
