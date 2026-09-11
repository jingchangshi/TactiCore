# TactiCore

TactiCore 是一个面向个人投资者的低频、多资产战术配置研究系统，目标是发现稳健、可解释、可执行的配置策略，而不是建设通用量化平台。

当前高层状态：S1 全球双动量已拒绝；S2 多资产趋势 V2B 已通过经济筛选、RQAlpha 上游执行闭环和粗粒度参数平台检验，保持 200 个有效观测并冻结为 Research Candidate R1，现按前瞻影子协议积累证据。S2 尚不是生产候选。

## 基本使用

要求 Python 3.10–3.12，建议使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy

# 重现 S2 粗粒度参数平台检验
uv run python research/experiments/run_s2_parameter_plateau.py

# 重放冻结的 S2 V2B 目标，并启用已采用的 RQAlpha 原生能力
uv run python research/experiments/run_s2_rqalpha_validation.py \
  --partial-fill-on-insufficient-cash \
  --output-prefix s2_rqalpha_upstream_native
```

RQAlpha 官方 bundle 保存在仓库外的 `~/.rqalpha/bundle`。重建 Tushare 数据需要通过环境变量提供 `TUSHARE_TOKEN`，具体契约见 [canonical 数据说明](data/canonical/README.md)。

## 权威文档

- [稳定架构](docs/ARCHITECTURE.md)
- [研究规则](docs/RESEARCH_RULES.md)
- [研究账本](docs/RESEARCH_LEDGER.md)
- [当前状态](docs/CURRENT_STATE.md)
- [策略目录](docs/STRATEGY_CATALOG.md)
- [S2 参数平台报告](research/results/S2_PARAMETER_PLATEAU_V1.md)
- [S2 上游原生执行闭环报告](research/results/S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md)
- [S2 R1 前瞻影子协议](research/shadow/s2_r1/README.md)
- [S3A 行业轮动基线报告](research/results/S3_SECTOR_BASELINE_V1.md)

历史研究证据保存在 `research/results/`，已关闭问题应先查研究账本，不得由后续 Goal 无故重做。
