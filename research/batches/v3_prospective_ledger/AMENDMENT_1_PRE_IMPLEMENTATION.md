# V3 前瞻台账协议 V1 — 实现前补遗 1

状态：**实现前澄清**。本补遗单独提交于任何实现之前，不修改
[PROTOCOL_V1.md](PROTOCOL_V1.md) 的既有字节；两者共同构成协议。

## 背景

协议 §9 的暂停条件第 5 条要求"日报 `policy_release.content_hash` 与 manifest 记录不一致"
时暂停，但 §7 的 manifest 字段并不包含 policy 身份（manifest 在首个合格日报之前初始化，
不可能预知 policy hash）。若不澄清，该暂停条件不可实现。

## 补遗内容

1. 台账目录新增一个**非事件**文件 `policy_baseline.json`，与五类事件文件分开：
   - 在**首个**非 `DATA_INSUFFICIENT` 的合格 brief 成功追加时创建一次，权限 0600；
   - 记录 `strategy_id`、`version`、`content_hash`、`production_admission`、
     `first_as_of_trade_date`、`source_sha256`、`created_at`；
   - 创建后不可修改；它不是证据事件，不参与五类事件的计数。
2. 之后每次 brief 的 policy 身份必须与 baseline 的 `strategy_id`、`version`、
   `content_hash` 完全一致。任何差异一律拒绝追加并报
   `POLICY_RELEASE_CHANGED`，由所有者人工裁决；不得静默换包、不得改写既有事件。
3. `status` 只读报告 baseline 身份；`verify` 校验其存在时的 JSON 结构、哈希与
   `created_at`，缺失 baseline 不视为损坏。
4. §9 暂停条件第 5 条中的"manifest 记录"改指本补遗的 `policy_baseline.json`。

## 边界

- 本补遗不改变五类事件定义、自然键、幂等/哈希链、anti-backfill 时间规则或任何安全边界。
- 本补遗仍先于实现提交；本补遗提交时真实前瞻观测数仍为 0。
