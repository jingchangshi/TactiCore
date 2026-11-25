# V3 前瞻台账协议 V1 — 生效记录

本文件是 [PROTOCOL_V1.md](PROTOCOL_V1.md) 的生效记录，单独提交于任何实现之前。

## 协议 commit

| 项 | 值 |
| --- | --- |
| commit SHA（完整） | `5c76846319c29eca78185c69b84393ed49f69bf9` |
| commit SHA（短） | `5c76846` |
| 作者时间（UTC） | `2026-11-25T09:55:29Z` |
| 作者时间（Asia/Shanghai） | `2026-11-25T17:55:29+08:00` |
| 分支 | `feat/v3e-prospective-ledger` |
| 提交内容 | 仅 `research/batches/v3_prospective_ledger/PROTOCOL_V1.md` |

## 最早合格日

**`2026-11-26`（周四）**

依据：

1. 协议 commit 的作者时间为上海 `2026-11-25 17:55:29`，晚于当日 A 股收盘 `15:00`；
   因此 `2026-11-25` 本身既不是"commit 之后"的交易日，其日报也早于协议存在，不能作为
   最早合格日。
2. **交易日后继日**按只读的 FinanceMCP 实时交易所日历核验：
   `/home/jcshi/.local/share/finance-mcp-ashare/ashare.sqlite` 的 `trade_cal` 表
   （`mode=ro` 只读打开）显示：
   - `20261125` `is_open = 1`（协议提交当日，已收盘）
   - `20261126` `is_open = 1`（commit 之后的首个交易日）
   - `20261127` `is_open = 1`
3. TactiCore 仓库内 `data/canonical/trading_calendar.csv` 只覆盖到 `2026-08-31`，
   不足以判定 2026-11 的交易日，故本记录使用上述只读实时日历，并在此写明依据。

因此，`as_of_trade_date` 早于 `2026-11-26` 的任何 signal / recommendation / valuation /
confirmed fill 事件一律拒绝；`2026-11-26` 收盘后生成的真实日报是第一条合格输入。

## 当前状态

- 本记录提交时，实现尚未开始，账本尚未初始化，真实前瞻观测数为 **0**。
- 本记录不产生任何观测、不修改任何策略或生产流程。
