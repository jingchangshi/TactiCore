# Phase A Windows native portability audit V1

本记录是 Windows 11 原生开发环境的可审计证据与静态移植性审计结果。它是 provenance / environment evidence，**不是**研究结果，不产生任何策略、参数、候选或前瞻结论。

## 环境基线（实测）

| 项 | 值 |
| --- | --- |
| OS | Windows 11，`Microsoft Windows NT 10.0.26200.0` |
| shell | PowerShell Core 7.6.5 |
| 架构 | AMD64 |
| git | `2.55.0.windows.3` |
| uv | `0.12.13` |
| workspace | `D:\workspace\TactiCore` |
| 仓库 `.venv` | Python `3.11.15` |
| 关键数值栈 | NumPy `1.26.4`、SciPy `1.17.1`、Pandas `2.3.3` |
| `core.autocrlf` | `true` |
| `core.eol` | 未设置 |
| `.gitattributes` | 不存在 |
| 文本换行观测 | Git index 为 LF，多数 checkout 的受版本控制文本为 CRLF；工作树中 `pyproject.toml` 为 mixed |

## 解释器分类（Phase A 关键证据）

同一份仓库源码在三个隔离解释器下解析并运行 `mypy`：

| 解释器 | 解析到的 NumPy | mypy | 备注 |
| --- | --- | --- | --- |
| Python 3.10.21 | 1.26.4 | PASS | 与冻结候选的框架版本一致 |
| Python 3.11.15 | 1.26.4 | PASS | 同时通过 strict S2 R1 candidate verification |
| Python 3.12.14 | 2.5.3 | FAIL | 失败发生在 NumPy stub 解析阶段，未进入项目源码 |

失败原因：`rqalpha>=6.3.0` 在 `python>=3.12` 上要求 `numpy>=2.0.0`，而 NumPy 2.5.x 的 stub 使用 Python 3.12 的 `type` 语句语法，项目 `mypy` 目标为 `python_version = "3.10"`，因此无法解析。

分类：**resolver/toolchain skew**，不是项目 typing 缺陷，也不是策略语义或冻结候选完整性问题。

处置（已实施于 commit `8df12b2`）：固定仓库开发与验证解释器为 Python 3.11（根级 `.python-version`），`requires-python = ">=3.10,<3.13"`、Ruff `py310` 与 mypy `python_version = "3.10"` 全部保持不变；未收窄支持范围、未引入额外 lockfile、未弱化第三方或项目检查。

## 静态移植性审计

审计范围：`tacticore/`、`research/`、`tests/`、`config/`、`data/`。

以下模式在审计范围内**零匹配**：

```text
/tmp
/home/
/dev/null
shell=True
chmod
symlink 创建或使用
os.sep
os.name
platform.system
sys.platform
subprocess 调用
tempfile 依赖
shutil.which
有问题的 glob / PATH 操作
```

因此仓库当前没有 POSIX-only 路径假设、shell 依赖、权限位依赖、符号链接依赖或平台分支逻辑，也没有本地实现的通用执行/数据平台组件。

观测到的非问题匹配（单独记录，均为正确用法）：

- 显式 `encoding="utf-8"` 与 `newline=""`：控制文本编码与换行，正是跨平台正确做法。
- `TUSHARE_TOKEN` 环境变量读取：canonical 数据重建的已文档化凭据契约。
- 文档中的 shell 命令排版：仅出现在 Markdown 说明中，不影响运行时行为。

### CRLF / frozen text

严格 S2 R1 candidate verification 依赖仓库自有文本的冻结 hash。Windows checkout 默认产生 CRLF，因此已存在的 `sha256_frozen_repository_text` 在计算前做 CRLF → LF 归一化，使 LF 与 CRLF checkout 得到同一 hash，同时保持：真实内容修改仍改变 hash、raw/binary hash 不被静默归一化、冻结产物与 manifest 不变。新增的 S4C 冻结目标读取路径使用同一归一化思想，并有对应回归测试。

## 已知限制

- **WSL 未被执行或审计**：本记录只覆盖 Windows 原生路径；没有 WSL 实测证据，因此不声明 WSL 受支持或已验证。
- 这是开发期移植性审计，不等于“所有受支持 Python / 运行时组合都是严格候选验证环境”。冻结候选 R1 的框架版本要求 `numpy==1.26.4`，因此严格候选验证的解释器是 Python 3.10/3.11。
- 本记录不包含任何策略绩效结论，也不修改任何策略语义、候选或前瞻状态。

## 结论

```text
WINDOWS_NATIVE_STATUS = B_SUPPORTED_WITH_MINIMAL_PORTABILITY_FIXES
```

关联记录：[Batch 05 principal architect review](BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md)、[README](../../README.md)、[S2 R1 前瞻协议](S2_R1_PROSPECTIVE_PROTOCOL_V1.md)。
