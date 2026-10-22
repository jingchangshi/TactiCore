# research/ashare — FinanceMCP 数据研究域

本目录是一个**新增的独立研究域**，数据来源是 FinanceMCP 的只读研究导出快照。
它不触碰、不覆盖、不比较本仓库任何既有冻结状态。

## 边界

| 本域 | 既有域 |
|---|---|
| `research/ashare/data/` — 读快照、校验契约 | `data/canonical/`（冻结） |
| `research/ashare/experiments/` — 本域实验 | `research/experiments/`、`research/batches/`、`research/shadow/`（冻结） |
| `research/ashare/candidates/<id>/` — 新候选身份 | `research/shadow/s2_r1/`、`research/shadow/s4c_r1/`（冻结） |

**没有交叉写入。** 两个域各自自洽，不宣称在比较"同一策略"：资产池、信号定义与成本口径
都不同。任何以 FinanceMCP ETF 数据重新定义资产池、信号或成本的策略**必须**获得新的
`candidate_id`。

## 数据流

```
FinanceMCP  research-export（生产库只读）
        │  输出目录 + manifest.json（内容寻址）
        ▼
research/ashare/data/contract.py    校验 manifest 与逐文件 SHA-256
        │  任何不符即拒绝加载
        ▼
research/ashare/data/adapter.py     prices / tradability_mask / lifetimes
        │
        ▼
tacticore.engines.vectorbt_adapter.run_target_weights()   ← 未修改，直接复用
```

## 三条不可谈判的规则

1. **未知值保持 NaN，绝不变 0。** FinanceMCP 把 null 写成空 CSV 字段，本域读成 NaN。
   停牌、缺行、未上市都表现为"不可交易"，而不是"价格为 0"。
2. **未上市证券不得有正目标。** 早于 `list_date` 的价格行被丢弃，`lifetimes` 按真实
   `list_date` 构造，`build_tradability_mask` 保证这些日期上 mask 为 False。这是结构性
   保证，不依赖调用方自觉。
3. **身份分类是当前快照，不是历史 vintage。** `fund_type` / `market` / `exchange`
   在快照中没有 PIT 语义（manifest 标注 `CURRENT_SNAPSHOT_NOT_PIT`），因此**不**用于
   任何筛选或分组，只原样透传供人查看。

## 统计机制归属

统计机制（block bootstrap、Holm 校正、walk-forward）**只在** FinanceMCP
`src/ashare/validation.ts`。本域不重写。需要多重检验校正时调用 FinanceMCP CLI，
或复用一个已冻结的结果文件；若在 Python 内复算，必须以相同种子与相同 block 长度
复算并比对结果，差异即失败——**不得成为第二套独立实现**。

## 运行测试

```bash
cd /home/jcshi/workspace/TactiCore
.venv/bin/python -m pytest tests/test_ashare_contract.py -v
```

测试 fixture `tests/fixtures/ashare_export/` 是 FinanceMCP `research-export` CLI
**真实导出**的合成市场快照（不是手写 CSV）：as-of 20260107，含一只
`list_date=20260108` 的后上市证券（其上市前行情行必须被丢弃）、一条空公告日的
财务记录、一个停牌日、一只 ETF。不含任何真实市场数据。
