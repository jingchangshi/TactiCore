# TactiCore

TactiCore 是一个面向个人投资者的低频多资产战术配置研究系统。它每天可以计算信号，但默认按月调仓，目标是回答“当前应持有什么、持有多少、是否需要操作”，而不是建设通用量化平台。

当前版本完成 M0–M2 的最小闭环：12 个资产的 canonical universe、Global Dual Momentum baseline、VectorBT 研究路径，以及等待本地数据 bundle 验证的 RQAlpha 事件驱动路径。

## 快速开始

要求 Python 3.10–3.12，并建议使用 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python research/experiments/run_gdm_baseline.py
```

最后一条命令默认使用明确标注的确定性演示价格，只证明研究管线可运行，不构成真实市场回测或 alpha 证据。要研究真实价格，请准备 `date × symbol` 的复权收盘价 CSV：首列名为 `date`，其余列名必须与 `config/universe.csv` 的 `symbol` 一致。

```bash
uv run python research/experiments/run_gdm_baseline.py --prices path/to/prices.csv
```

RQAlpha 验证需要仓库外的中国市场 bundle。准备 bundle 后，可调用 `tacticore.engines.rqalpha_adapter.run_rqalpha`；当前 adapter 在每月首个交易日用此前 253 根日线计算 252 日动量，并提交目标仓位。详见 [当前状态](docs/CURRENT_STATE.md) 与 [架构](docs/ARCHITECTURE.md)。

## 重要边界

- VectorBT 用于快速探索，RQAlpha 用于权威事件驱动验证。
- 仓库没有、也不会建立第三套回测、组合记账或撮合引擎。
- universe 中的 ETF 是研究代理，不代表已经通过容量、跟踪误差、税费或生产可交易性审查。
- 演示数据输出不能用于评价策略收益。
