# EXP-V3-09 V2：修复首日 `DEFENSIVE` 误清仓后的回撤控制架构对比（预注册协议）

状态：`FROZEN_PROTOCOL_V2 / PRE_RESULT`。日期：2026-11-26。

## 1. 修正 V1 缺陷（`EXP_V3_09_DRAWDOWN_CONTROL` 作废说明）

在 V1 回放中，`DrawdownController.step` 将当期宏观上限 `BUDGET["DEFENSIVE"] = 0.15` 混入强制减仓阈值 `cap`，导致 `2024-07-01` 首日零回撤状态下对 `HEAVY70` / `CORE25` 全部 4 组执行 `CTRL_REDUCE` 强平，掩盖了 `EXP-V3-05` 中 `HEAVY70` 触发 5 次 L2 锁与 `-15.74%` 穿线的真实基线。V2 保留 V1 产物不删改，并严格拆分为两个独立控制输出：

- **`ctrl_cap: float | None`（强制减仓硬上限）**：仅由回撤风控状态本身触发，宏观状态切换到 `DEFENSIVE` 且无回撤警报时保持 `None`（仍由四批换马状态机与自然轮动降浓）：
  - `C0_HARD_STEP_LOCK`：仅在 `locked` 期间取 `0.0`（集中）/`0.15`（非集中），其余交易日 `None`；
  - `C1_REANCHOR_15D_RAMP10D`：仅在 `locked` 期间取 `0.0`/`0.15`，解锁当日重锚工作高水位 `work_peak = nav` 并在 10 日内仅通过 `buy_cap` 渐进放行新买入；
  - `C2_CPPI_F15_M5`：锁定期取 `0.0`/`0.10`，非锁定期取连续缓冲上限 `min(1.0, m * cushion_frac)`（首日满 cushion 时为 `0.75 > 0.70`，不触发无端强平）；
  - `C3_TWO_STAGE_GRADUAL`：`work_dd >= 13.5%` 或锁定期取 `0.0`/`0.10`，`>= 11%` 取 `0.25`，`>= 8%` 取 `0.50`，其余 `None`。
- **`buy_cap: float`（新增仓位/再平衡上限）**：`min(base_eq_budget, ctrl_cap)`（若 `ctrl_cap` 非空），解锁 10 日爬坡期再乘以 `0.5 -> 1.0` 线性系数。
