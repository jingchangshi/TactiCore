# EXP-V3-08：8.1% 极端冰点后的非对称右侧复苏与仓位爬坡（预注册协议）

状态：`FROZEN_PROTOCOL_V1 / PRE_RESULT`。日期：2026-11-26。针对现行 V3 在 `2020-02` 疫情 V 反中捕获率仅 `39.2%`（IS Bull1 踏空）以及当前全市场站上 `MA60` 占比跌至 `8.1%` 极端冰点后既怕踏空主升又怕被 `2026-11` 死猫跳反杀的两难局面，严格固定现行退场规则不变，仅检验冰点后的非对称右侧试探档（`RECOVERY`）。

## 1. External Evidence Gate

- **Canonical mapping**: `BREADTH_THRUST_RECOVERY`（`STRATEGY_EVIDENCE_REGISTRY.yaml` 新增条目）。
- **External tier**: `E3_MIXED_CONDITIONAL`。
- **External conclusion**: Zweig (1986) 宽度推力在美股极度超卖后具强指示意义，但 Yang/Gebka/Hudson (2019) 证明 A 股熊市存在剧烈短期反抽（死猫跳），无保护试探仓容易反复止损。
- **Relevant contradictions**: 坚决区隔于已关闭 `S3B`（11 只行业 ETF 月频 50% 广度对称开关）：本研究基于全市场 ~5,500 只股票日频宽度与双锚指数，且只作用于“已确认深度冰点之后”的非对称试探建仓。
- **Upstream implementation**: `VectorBT`（`2018-01-02..2026-11-26`，含 `2026-10~11` 全部高频死猫跳）+ 原生 `RQAlpha 6.3.0`（`2018-01-02..2026-10-30`）。
- **Existing TactiCore evidence**: `EXP_V3_01_REGIME_SUPER_ETF.*`（明确披露 `IS Bull1` 39.2% 滞回踏空）。
- **Remaining local gap**: 深度冰点（近 20 日曾有 `pct_above_ma60 < ice_th`）后，比较 `MA20` 连续放量站上 vs `pct_above_ma20` 5 日宽度推力触发 `RECOVERY` 试探档（并绑定破触发 5 日低点硬退回）对 V 反捕获与假突破回撤的净影响。
- **Research action**: `LOCAL_ADJUDICATION`。

## 2. PIT Tradability Gate

1. **Date-aware universe**: 沿用 `EXP-V3-01` 33 只超级 ETF + PIT 替补链 + `511010.SH` 蓄水池。
2. **Asset lifetime metadata**: `bundle_202611` + `v3_snapshot_20261126`。
3. **Pre-listing fallback**: 同 `EXP-V3-01`。
4. **Missing execution price / suspension**: `T` 日收盘确认信号，`T+1` 执行，`validate_execution_targets` 零容忍。
5. **Strategy inception**: `2018-01-02..2026-11-26`，重点切片 `2020-02..07`、`2022-04..07`、`2024-02..05`、`2024-09..11` 与 `2026-09..11-26` 熊市反抽期。
6. **Executability of every positive target**: RQAlpha 原生整手与分层费率检验，限制最短持仓/防频繁震荡。

## 3. 对照臂与 3×3 参数高原

- `M0_V3_BASELINE`：现行三档（`15% / 60% / 85%`）；
- `M1_MA20_RIGHT_REENTRY`：处于 `DEFENSIVE` 且近 20 日曾出现 `pct_above_ma60 < 15%`，当沪深 300 或成长锚至少一侧连续 2 日收盘 `> MA20` 且 `amount_vs_ma20 >= 1.05` 时切入 `RECOVERY 35%`（跌破触发前 5 日区间低点或再出现双锚空头恶化即退回 `DEFENSIVE`）；
- `M2_BREADTH_THRUST_REENTRY`：处于 `DEFENSIVE` 且近 10 日曾出现 `pct_above_ma60 < 15%` 且 `pct_above_ma20 < 15%`，5 日内 `pct_above_ma20` 跃升至 `>= 45%` 且 `amount_vs_ma20 >= 1.15` 时切入 `RECOVERY 40%`（同等低点退回保护）；
- 3×3 高原：`ice_th ∈ {12%, 15%, 18%}` × `recovery_weight ∈ {30%, 35%, 40%}`。
