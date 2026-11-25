# V3 前瞻台账 — 人工运行手册

对应协议：[PROTOCOL_V1.md](PROTOCOL_V1.md) + [AMENDMENT_1_PRE_IMPLEMENTATION.md](AMENDMENT_1_PRE_IMPLEMENTATION.md)
+ [AMENDMENT_2_PRE_IMPLEMENTATION.md](AMENDMENT_2_PRE_IMPLEMENTATION.md)。
实现：`research/experiments/v3_prospective_ledger.py`，测试：`tests/test_v3_prospective_ledger.py`。

本手册只描述**人工/受控运行**。台账不注册任何 systemd/cron/daemon；不得为它新建定时器。

## 0. 前置

- 工作目录：TactiCore worktree 根（例如 `/home/jcshi/workspace/TactiCore-wt/v3e-ledger`）。
- 解释器：`/home/jcshi/workspace/TactiCore/.venv/bin/python`（不要用 worktree 内 `.venv/bin/pytest`，
  不要对共享环境 `uv sync`）。
- 台账目录：默认 `~/.local/share/tacticore-v3-prospective-ledger`（0700，私有，不提交 git）。
  可用 `TACTICORE_V3_LEDGER_ROOT` 或全局参数 `--ledger-root` 覆盖。
- 只读输入：FinanceMCP 私有目录 `~/.local/share/ashare-private/` 下的
  `daily-briefs/YYYYMMDD.json` 与 `portfolio.sqlite`。本工具只读，不调用任何 FinanceMCP CLI。

```bash
cd /home/jcshi/workspace/TactiCore-wt/v3e-ledger
PY=/home/jcshi/workspace/TactiCore/.venv/bin/python
$PY -m research.experiments.v3_prospective_ledger --help
```

## 1. 首次初始化（只做一次）

```bash
$PY -m research.experiments.v3_prospective_ledger init
```

成功返回 `{"status":"INITIALIZED", ...}`，创建 `manifest.json`（0600）与五个空的
`*.jsonl`。**不要删除或重建**；重复 `init` 会被拒绝。

## 2. 每个合格交易日（收盘后、日报生成后）

**顺序：brief → fills → reasons → verify/status。任何一步失败即停止并报告，不重试写入。**

### 2.1 确认当日日报存在且是当天的

日报由 FinanceMCP 每日流水线在收盘后生成（通常 19:30–20:30 Asia/Shanghai）：

```bash
DATE=$(TZ=Asia/Shanghai date +%Y%m%d)
BRIEF=~/.local/share/ashare-private/daily-briefs/$DATE.json
ls -l "$BRIEF"
$PY - <<EOF
import json
d=json.load(open("$BRIEF"))
print(d["schema"], d["as_of_trade_date"], d["status"], d["generated_at"])
EOF
```

必须满足：`schema == ashare-daily-brief/1.0`、`as_of_trade_date == $DATE`、
`account_status == REAL_ACCOUNT_VERIFIED`、`generated_at` 的上海时间 `>= 15:00:00`，且
`$DATE` 被受信只读交易日历确认为开市日。**若当天没有日报、日期不符、日报早于 15:00、
日历不可用/未知或当天不是开市日：整次拒绝，当天记为 MISSED，永久不补录；不要用前一交易日
的日报替代，也不要次日补跑。**

### 2.2 追加当日信号 / 建议 / 估值

```bash
CAL=~/.local/share/finance-mcp-ashare/ashare.sqlite   # 受信只读交易日历（trade_cal）
$PY -m research.experiments.v3_prospective_ledger ingest-brief --brief "$BRIEF" --calendar-db "$CAL"
```

- **必须提供 `--calendar-db`**（或设置 `TACTICORE_V3_LEDGER_CALENDAR_DB`）；缺省/不可用时
  `REFUSED: 交易日历未知`，不写任何 event。台账只读该库，不写日历。
- 成功：返回 `INGESTED`，`appended` 里是 SIGNAL / RECOMMENDATION / VALUATION 的数量。
- `IDEMPOTENT_NOOP`：同一份 brief 已追加过，字节未变；正常。
- `CONFLICT`：同一天出现了不同内容的 brief（通常是重新生成的日报）。**不要删除旧行、
  不要换文件重试**；停止并报告所有者。
- `REFUSED`：日期、账户、schema、缺失字段、收盘窗口或时间链不合法；按 error 修正输入或记录 MISSED。
- `POLICY_RELEASE_CHANGED`：规则包与首次 baseline 不一致；停止并报告所有者裁决。
- `APPEND_IO_FAILURE` / `CORRUPT`：写入中断或既有账本不完整；**停止写入**，运行 `verify`
  复核并保留现场，不得截断、删除或重试补行（见 §3）。

### 2.3 只读导入券商确认成交（可晚于成交日）

```bash
$PY -m research.experiments.v3_prospective_ledger ingest-fills
```

- 只导入 `account_event` 中 `source='broker_statement'`、非空撤销标记以外（`reversed_by`
  为 NULL 或空串都按未撤销）的 `TRADE_BUY/TRADE_SELL`；只读该表，不读 `account_meta`。
  `synthetic` 成交永不导入；`recommendation` 永不变成成交。撤销复核只针对**已导入** fill。
- 源行 SHA 只覆盖 `account_event` 原生 19 列；不掺入任何合成 schema 键。
- 若返回 `SOURCE_REVERSED_AFTER_IMPORT` 或 `SOURCE_FILL_MISSING_AFTER_IMPORT`：**暂停**，
  人工核对券商流水；不得改写或删除既有台账行。
- 可在成交发生后任意一天运行；`occurred_on` 必须不早于最早合格日。

### 2.4 显式未执行原因（只在人类确知原因时）

原因输入 JSON（示例）：

```json
{
  "schema": "v3-prospective-unexecuted-reason/1.0",
  "recommendation_event_id": "V3L-xxxxxxxxxxxxxxxxxxxxxxxx",
  "reason_code": "PRICE_INVALIDATED",
  "scope": "FULL",
  "reason_note": "次日高开超过 +2%，按失效条件未执行",
  "decided_on": "YYYYMMDD"
}
```

`reason_code` 只能取：

```text
PRICE_INVALIDATED / PREMIUM_BLOCKED / INSUFFICIENT_CASH / MARKET_STATE_CHANGED
BROKER_REJECTED / USER_DEFERRED / OTHER_EXPLICIT
```

```bash
$PY -m research.experiments.v3_prospective_ledger ingest-unexecuted-reason --input reason-YYYYMMDD.json
```

- 一条 recommendation 至多一条原因；不同原因重复提交会被拒绝（append-only）。
- 不确定原因时**不要编造**；留为 `UNRESOLVED`，由 `status` 显示。
- `decided_on` 不得早于 recommendation 的 signal 日，也不得晚于今天。

### 2.5 只读复核

```bash
$PY -m research.experiments.v3_prospective_ledger verify
$PY -m research.experiments.v3_prospective_ledger status \
  --calendar-db ~/.local/share/finance-mcp-ashare/ashare.sqlite
```

- `verify` 必须返回 `status=OK`；哈希链、schema、batch、policy baseline 任一不一致即 `CORRUPT`。
- `status` 报告：
  - 五类事件计数与日期；
  - `missed`：最早合格日至昨日、交易日历开市但没有 SIGNAL 的日期；**当天截止前不判
    MISSED**（补遗 2 §1）；
  - `recommendation_review`：每条建议的派生**候选重合**状态
    （`COINCIDENT_FILLS_UNATTRIBUTED` / `NO_COINCIDENT_FILL` / `NOT_DUE` /
    `NOT_EXECUTABLE` / `NO_EXPECTED_DATE`），并固定标注 `attribution: NOT_ATTRIBUTED`。
    同日同码同向**不自动匹配、不解除 UNRESOLVED**；这只是人工复核线索，不是执行证明
    （补遗 2 §2 / A2:65）；
  - `unresolved_recommendation_event_ids`：已到期、未给出显式原因的建议（候选重合成交
    不解除它）；
  - `unattributed_fill_event_ids`：未与任何建议形成候选重合的确认成交；
  - `warnings`：信号与建议不一致、reason 与成交矛盾等；
  - `pause.recommended` 与 `pause.reasons`。

## 3. 暂停建议

出现以下任一情况时：停止继续追加，保留现状，报告所有者；**不要**通过编辑 JSONL、
删除行、重建台账或换一份输入来"修复"：

1. `verify` 失败（哈希链 / schema / batch / baseline）；
2. 来源冲突（同日不同 brief）或 `POLICY_RELEASE_CHANGED`；
3. 已导入成交在源库被撤销或消失；
4. 连续 5 个交易日 MISSED；
5. 3 条以上建议已到期超过 3 个交易日，既无确认成交也无显式未执行原因。

恢复需所有者明确指示并记录原因；历史事件保持不变。

## 4. 账本文件

```text
<ledger_root>/
  manifest.json                 不可变：协议版本、commit、最早合格日、账户
  policy_baseline.json          首个非 DATA_INSUFFICIENT 合格 brief 钉住的规则包身份（补遗 1）
  .writer.lock                  单写者 flock；init 创建，不是证据事件
  signals.jsonl                 SIGNAL
  recommendations.jsonl         RECOMMENDATION
  confirmed_fills.jsonl         CONFIRMED_FILL
  unexecuted_reasons.jsonl      UNEXECUTED_REASON
  valuations.jsonl              VALUATION
```

- 只追加；不手工编辑、不排序、不合并、不提交到 git。
- 备份只做目录级复制，不做跨机器重写。
