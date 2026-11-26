# EXP-V3-09：回撤控制架构对比——硬锁死阶梯 vs 解锁后工作高水位重锚 vs CPPI 连续缓冲（预注册协议）

状态：`FROZEN_PROTOCOL_V1 / PRE_RESULT`。日期：2026-11-26。针对 `EXP-V3-05` / `EXP-V3-05B` 揭示的现行 L2 锁死痛点——仅凭**固定全周期历史最高点（HWM）+15 日解锁直接跳回目标上限**，在 `HEAVY70` 下出现连续 5 次“解锁次日因旧 HWM 未重置立即再度触发 L2”死锁循环，或触发“低位刚砍光、解锁缺缓冲”损耗——严格同窗对比四套预注册回撤控制机制。

## 1. External Evidence Gate

- **Canonical mapping**: `DRAWDOWN_CONTROL`（`STRATEGY_EVIDENCE_REGISTRY.yaml` 既有 `NOT_STARTED` / `E3_MIXED_CONDITIONAL`）。
- **External tier**: `E3_MIXED_CONDITIONAL`（Black & Jones 1987 CPPI；Moreira & Muir 2017 vs Cederburg et al. 2020）。
- **External conclusion**: 阶梯止损易受“旧高水位重触循环”影响；CPPI 通过动态乘数 `m * (NAV - F)` 平滑压缩风险敞口，但乘数过小在 A 股震荡期会导致过度现金拖累。
- **Relevant contradictions**: 必须同时度量真实历史峰值回撤（禁止借“重锚”掩盖真实 `-15%` 红线击穿），并在含集中遗留仓与纯底盘两种账户场景下检验。
- **Upstream implementation**: `VectorBT`（全窗 `2018-01-02..2026-11-26` 底盘测试）+ 原生 `RQAlpha 6.3.0`（OOS `2024-07-01..2026-10-30` 单账户重演 & `2018-01-02..2026-10-30` 全窗底盘，`¥69,000` / `¥100,000`）。
- **Existing TactiCore evidence**: `EXP_V3_03`、`EXP_V3_05`、`EXP_V3_05B`。
- **Remaining local gap**: 四套预注册方案（`C0` 现行硬锁死、`C1` 解锁重锚+10日爬坡、`C2` CPPI `F∈{13%,15%,17%}×m∈{4,5,6}`、`C3` 两级渐进减速+重锚）的锁死次数、二次重锁循环数、真实 `-15%` 穿线与净卡玛比率。
- **Research action**: `LOCAL_ADJUDICATION`。

## 2. PIT Tradability Gate

1. **Date-aware universe**: 全窗底盘使用 V3 33 只超级 ETF + PIT 替补链 + `511010.SH`；单账户延续 `EXP-V3-05B` 标的与规则。
2. **Asset lifetime metadata**: `bundle_202611` + `v3_snapshot_20261126`。
3. **Pre-listing fallback**: 同 `EXP-V3-05B` 与 `V3_COMPLEXITY_HURDLE_V2`。
4. **Missing execution price / suspension**: 全部风控乘数按 `T` 日收盘计算并于 `T+1` 开盘执行（单账户）或次日调仓执行，零未来函数。
5. **Strategy inception**: 全窗 ETF 底盘 `2018-01-02..2026-11-26`（RQAlpha `..2026-10-30`）；单账户集中场景 `2024-07-01..2026-10-30`（`CORE25` & `HEAVY70` × `¥69k` & `¥100k`）。
6. **Executability of every positive target**: 真实分层佣金、印花税与 100 股/份整手执行；双口径报告“真实全期 Peak DD（不可重锚）”与“工作控制高水位 DD”。
