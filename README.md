# TactiCore

TactiCore 是一个面向个人投资者的低频、多资产战术配置研究系统，目标是发现稳健、可解释、可执行的配置策略，而不是建设通用量化平台。

当前高层状态：S1 全球双动量已拒绝；S2 多资产趋势 V2B 已通过经济筛选、RQAlpha 上游执行闭环和粗粒度参数平台检验，保持 200 个有效观测并冻结为 Research Candidate R1，现按前瞻影子协议积累证据。S2 尚不是生产候选。

## 基本使用

运行时支持 Python 3.10–3.12；仓库开发与验证解释器固定为 Python 3.11（[`.python-version`](.python-version)），因此普通的 `uv sync` / `uv run` 都会选中 3.11。S2 Research Candidate R1 冻结的框架版本包含 `numpy==1.26.4`，而 `rqalpha>=6.3` 在 Python 3.12 上要求 `numpy>=2`，因此 Python 3.12 环境无法完成冻结候选校验，也无法在 `mypy` 的 Python 3.10 目标下解析 NumPy stub。

`uv sync --extra dev` 只安装基础开发依赖（pytest / ruff / mypy）；S4C 的 skfolio 研究路径需要 research extra，否则一个测试会因缺少 skfolio 而失败，完整引导为 `uv sync --extra dev --extra research`。

建议使用 [uv](https://docs.astral.sh/uv/)，Windows PowerShell 示例：

```powershell
uv sync --extra dev --extra research
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy

# 冻结 S2 R1 候选的严格校验（冻结输入 hash 与框架版本）
uv run python research/experiments/run_s2_r1_shadow.py --verify-candidate

# 重现 S2 粗粒度参数平台检验
uv run python research/experiments/run_s2_parameter_plateau.py

# 重放冻结的 S2 V2B 目标，并启用已采用的 RQAlpha 原生能力
uv run python research/experiments/run_s2_rqalpha_validation.py --partial-fill-on-insufficient-cash --output-prefix s2_rqalpha_upstream_native
```

RQAlpha 官方 bundle 保存在仓库外的主目录下。重建 Tushare 数据需要通过环境变量提供 `TUSHARE_TOKEN`，具体契约见 [canonical 数据说明](data/canonical/README.md)。

### 原生 Windows 与 WSL 边界

原生 Windows 11 开发路径已验证可用（`WINDOWS_NATIVE_STATUS = B_SUPPORTED_WITH_MINIMAL_PORTABILITY_FIXES`），完整环境基线、解释器分类与静态移植性审计见 [Phase A Windows native portability audit](research/results/PHASE_A_WINDOWS_NATIVE_PORTABILITY_AUDIT_V1.md)。

**WSL 未经验证**：仓库目前不要求 WSL，也没有 WSL 实测证据，因此不声明 WSL 受支持。若将来在 WSL 中执行，必须在 WSL 内重新准备解释器、虚拟环境、bundle 与凭据，并重新运行严格校验。

`~` 在不同环境中解析到不同主目录，以下路径不可互换：

| 资源 | 原生 Windows | WSL |
| --- | --- | --- |
| RQAlpha bundle | `%USERPROFILE%\.rqalpha\bundle`（本机为 `C:\Users\<用户>\.rqalpha\bundle`） | `<WSL 家目录>/.rqalpha/bundle` |
| 开发解释器 | 仓库 `.python-version`（Python 3.11） | 需在该 Linux 环境内自行创建并重新验证 |
| `TUSHARE_TOKEN` | 必须在执行数据命令的那个环境中设置 | 必须在执行数据命令的那个环境中设置 |

在一个环境中安装的 bundle 不是另一个环境的 bundle，两者不共享。

## 权威文档

- [稳定架构](docs/ARCHITECTURE.md)
- [研究规则](docs/RESEARCH_RULES.md)
- [研究账本](docs/RESEARCH_LEDGER.md)
- [当前状态](docs/CURRENT_STATE.md)
- [策略目录](docs/STRATEGY_CATALOG.md)
- [策略研究地图](docs/STRATEGY_RESEARCH_MAP.md)
- [外部策略证据快照](research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml)
- [S2 参数平台报告](research/results/S2_PARAMETER_PLATEAU_V1.md)
- [S2 上游原生执行闭环报告](research/results/S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md)
- [S2 R1 前瞻影子协议](research/shadow/s2_r1/README.md)
- [S3A 行业轮动基线报告](research/results/S3_SECTOR_BASELINE_V1.md)

历史研究证据保存在 `research/results/`，已关闭问题应先查研究账本，不得由后续 Goal 无故重做。
