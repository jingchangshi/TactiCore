# TactiCore Agent 路由契约

## 仓库使命

TactiCore 是低频、多资产战术配置研究系统，首要目标是发现稳健、可解释、可执行、低维护的资产配置策略。

```text
策略研究 > 基础设施工程
```

本仓库不建设通用量化平台、自定义回测器、自定义会计或执行模拟器，也不建设通用研究治理框架。稳定的系统边界以 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) 为准。

## 必做启动检查

提出方案或修改代码前，依次阅读：

1. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
2. [`docs/RESEARCH_RULES.md`](docs/RESEARCH_RULES.md)
3. [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)
4. [`docs/RESEARCH_LEDGER.md`](docs/RESEARCH_LEDGER.md)
5. [`docs/STRATEGY_CATALOG.md`](docs/STRATEGY_CATALOG.md)

随后阅读所改策略在 `research/results/` 中的相关证据，最后读取 [`docs/goal.md`](docs/goal.md) 作为当前执行指令。

`goal.md` 是临时文件，不是永久架构或研究事实来源。

## 文档路由

| 需要了解 | 应读取 |
| --- | --- |
| 系统职责与所有权 | `docs/ARCHITECTURE.md` |
| 永久研究方法 | `docs/RESEARCH_RULES.md` |
| 已关闭问题 | `docs/RESEARCH_LEDGER.md` |
| 当前阻塞与下一实验 | `docs/CURRENT_STATE.md` |
| 策略生命周期状态 | `docs/STRATEGY_CATALOG.md` |
| 详细历史证据 | `research/results/*` |
| 当前任务 | `docs/goal.md` |

## 权威性与冲突顺序

```text
当前源代码 + 冻结研究产物
  ↓
ARCHITECTURE.md
  ↓
RESEARCH_RULES.md
  ↓
RESEARCH_LEDGER.md
  ↓
STRATEGY_CATALOG.md
  ↓
CURRENT_STATE.md
  ↓
goal.md
```

- 仓库事实覆盖过时文字。
- 架构文档拥有职责边界，研究规则拥有永久方法，研究账本拥有已关闭问题历史。
- 当前状态只拥有活动研究前沿；`goal.md` 不得静默覆盖永久架构或规则。
- 如果存在真实矛盾，不得自行折中；应指出矛盾，并在任务范围内修正恰当的权威文档。

## 已关闭问题不得无故重开

广泛调查前先查 `docs/RESEARCH_LEDGER.md`。Goal 涉及同一策略，不等于可以重做 `CLOSED` 或 `REJECTED` 问题。

仅在策略语义或 canonical 数据契约改变、框架变化使原假设失效，或出现新矛盾证据时重开。重开必须指出具体账本条目、矛盾证据和有界范围；不得无依据重做通用信号、数据质量或执行分类审计。

## 框架、社区与上游优先

```text
现有 TactiCore
→ 框架原生 API
→ 官方扩展 / Mod
→ 兼容或较新的稳定上游
→ 成熟社区方案
→ 最小本地适配
```

实现通用量化能力前，先检查 VectorBT、RQAlpha、Tushare 或已批准依赖是否拥有该职责。除非已证明框架无法解决当前具体阻塞，不得在本地实现组合会计、撮合、整手、现金、交易成本、通用订单生命周期、通用回测或通用绩效记录。完整约束见架构和研究规则。

## 代码与产物归属

- `tacticore/strategies/`：策略经济语义。
- `tacticore/engines/`：薄且可复用的框架适配。
- `research/experiments/`：一次性或范围明确的研究编排。
- `research/results/`：决策相关研究产物。
- `tests/`：保护 TactiCore 自有语义，不复测框架内部实现。

实验辅助函数在出现真实的可复用职责前不得提升到 `tacticore/`。没有多个生产调用方时，不得预建 `research_engine/`、`robustness_framework/`、`parameter_optimizer/`、`execution_framework/` 或 `governance/`。

## Goal 完成时的文档责任

每次完成都检查 `CURRENT_STATE.md`、`RESEARCH_LEDGER.md` 和 `STRATEGY_CATALOG.md`，仅在它们拥有的语义改变时更新。

- 只有架构或职责边界改变时更新 `ARCHITECTURE.md`。
- 只有形成新的永久方法时更新 `RESEARCH_RULES.md`。
- 当前实验数字写入 `research/results/*`，不得塞入架构、规则或本文件。

本文件只负责路由和启动，应在数个 Goal 后仍然有效。不要写入当前收益率、回撤、失败日期、HEAD、参数清单或其他瞬时状态。当前仓库只需要这一个根级文件；只有子树确有不同规则且反复需要独立指引时，才考虑嵌套 `AGENTS.md`。
