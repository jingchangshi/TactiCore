# EXP-V3-04B 折价门（门②）消融 — 预注册协议 V1

- 日期：2026-11-25（运行前提交；本协议提交后只授权**一次**完整运行）。
- 对象：`EXP-V3-04` `V32_GUARDED_BOTTOM_GRIND_25` 的战术回补四门槛之门②
  （`disc_ok`：90 日内有卖出价时 `close <= last_sell_px * (1 - 7%)`，否则 `close <= high60 * 0.85`）。
- 动机：`EXP-V3-04` 3×3 高原中 `disc = 6% / 7% / 8%` 三行结果逐位相同，提示门②可能从未起约束作用。
- 结果身份：只能形成新版本候选（`NOT_APPROVED`）；不改 `v3.2.0` / `v3.2.1`、不改 `EXP-V3-04` 原脚本与产物、不改账本。

## External Evidence Gate

- Canonical mapping: `EXP-V3-04B` -> `V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION`（registry 既有条目；本实验是该条目四门槛中门②的单因素消融，不是新策略）。
- External tier: `E4_OPEN_LOCAL`（沿用 registry 条目；单门约束是否生效属本地路径依赖问题，外部文献不回答）。
- External conclusion: 外部证据只支持“深跌后低吸需要趋势/折价/止稳过滤”这一族的一般结论，不对“折价门在 MA60 斜率 + 超卖 + 右侧止稳三门已存在时是否冗余”给出结论。
- Relevant contradictions: `EXP-V3-04` 高原 `disc` 维度完全不敏感，与“门②是独立护栏”的规格表述（`v3.2.0` rules 第 6 条“>=7% discount”）矛盾；本实验只检验这一矛盾。
- Upstream implementation: VectorBT 经 `tacticore/engines/vectorbt_adapter.py:run_target_weights`；原生整手复核经 `research/ashare/experiments/exp_v3_04_bottom_grind_cost_reduction.py:_run_rqalpha_check`（RQAlpha 6.3.0）。不新增回测、撮合或会计实现。
- Existing TactiCore evidence: `RL-055`（`PASS_GUARDED_BOTTOM_GRIND_25`，15/0 RT，3×3 高原）与 `EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.md/.json`。
- Remaining local gap: 门②在原 9 窗口 V32 路径上是否曾是**唯一否决条件**；若是，去掉它对 IS/OOS 超额、MDD、RT 胜负与原生整手的影响。
- Research action: `BOUNDED_ABLATION`（单门消融 + 约束计数诊断；不调参、不扩窗、不换标的）。

## PIT Tradability Gate

1. Date-aware universe：与 `EXP-V3-04` 完全相同的 9 个窗口与标的（`512480.SH` / `515790.SH` / `512170.SH` / `159558.SZ` + `511010.SH`），`etf_tradability_mask` 原样传入 VectorBT。
2. Asset lifetime metadata：`research/ashare/v3_data.py` 的 `etf_lifetimes`（只读 import，不修改）。
3. Pre-listing fallback handling：不回填；`159558.SZ` 仅从 `2024-07-16` 起评估，与原实验一致。
4. Missing execution price / suspension：`NaN` 不补零；`T` 日收盘信号、`T+1` 执行，沿用原状态机。
5. Strategy inception：每窗 `25%` 目标 ETF + `75%` `511010.SH` 起步，与原实验一致。
6. Executability of every positive target：VectorBT 适配器内 `validate_execution_targets`；原生 RQAlpha 4 窗口（`IS_512480_19_23`、`OOS_512480_24_26`、`OOS_159558_24_26`、`OOS_159558_2026`，截至 bundle `2026-08-31`）报告拒单数。

## 臂

| 臂 | 定义 |
| --- | --- |
| `V32` | 原规则（四门槛全开），由原脚本 `_simulate_sleeve(cfg=V32_GUARDED_BOTTOM_GRIND_25)` 产生 |
| `V32_REPRO` | 新文件中带门②开关的等价状态机，门②开启；**必须**与 `V32` 在 9 窗口逐位一致（权重表含 NaN 位置、全部指标） |
| `V32_NO_GATE2` | 同 `V32_REPRO`，仅令 `disc_ok = True`；其他门槛、止盈、漂移兑现、成本、窗口全部相同 |
| `C0_STATIC_25` | 原脚本静态基线，用于超额与 MDD 差 |

实现：新文件 `research/ashare/experiments/exp_v3_04b_discount_gate_ablation.py` import 原脚本的 `WINDOWS`、`VARIANTS`、`VariantConfig`、`_compute_rsi14`、`_simulate_sleeve`、`_run_rqalpha_check`，仅在新文件中复写 `GUARDED_GRIND` 分支以加入门②开关与逐日门槛记录。原脚本不修改。

## 诊断（先于消融）

在 `V32_REPRO` 路径上，对每个“回补评估日”（无在途战术槽、非漂移兑现日、过冷却期）记录四门结果：

- `candidate_days`：门①（MA60 斜率盾）、门③（超卖）、门④（右侧止稳）均通过的日数；
- `binding_count`：上述候选日中门②失败的日数（门②为**唯一否决**）；按分支拆分 `recent_sell_branch`（90 日内卖出价 × (1-7%)）与 `high60_branch`（60 日高点 × 0.85）；
- 辅助：门②单独失败总日数（不论其他门）。

## 预注册裁决

1. 有效性：任一窗口 `V32_REPRO != V32` → `INVALID_RUN`（不报告消融结论）。
2. 一致性：`binding_count == 0` 而 `V32_NO_GATE2` 与 `V32` 有任何差异，或 `binding_count > 0` 而 VectorBT 权重表在全部窗口相同 → `INVALID_RUN`（逻辑矛盾，须查实现）。
3. `binding_count == 0` 且 `V32_NO_GATE2` 在 9 窗口 VectorBT 权重与指标逐位一致、4 窗口原生 RQAlpha 收益/MDD/拒单逐位一致 → `GATE2_INERT_SIMPLIFICATION_ELIGIBLE`。
4. `binding_count > 0`：如实报告逐窗差异，并按以下全部条件判定：IS 均值超额 `>=` V32、OOS 均值超额 `>=` V32、IS 与 OOS 均值 MDD 差 `>=` V32、RT 亏损笔数 `<=` V32、原生 RQAlpha 0 拒单 → `GATE2_BINDING_REMOVAL_NOT_WORSE`；否则 `GATE2_BINDING_RETAIN`。
5. 所有裁决均为 `NOT_APPROVED` 候选；不得据此修改 `v3.2.0` / `v3.2.1` 或 FinanceMCP 运行参数。

## 运行与产物

- 命令：`nice -n 10 python -m research.ashare.experiments.exp_v3_04b_discount_gate_ablation`（worktree 根）。
- 产物（新文件，存在则拒绝覆盖）：`research/results/EXP_V3_04B_DISCOUNT_GATE_ABLATION.md`、`.json`。
- 不重跑 `EXP-V3-04`、不改高原、不加新窗口或新门槛值；运行失败须新协议版本（`PROTOCOL_V2.md`）说明原因后重跑。
