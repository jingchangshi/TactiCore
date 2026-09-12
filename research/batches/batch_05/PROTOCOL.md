# Batch 05 earned stage validation protocol

冻结时间：提交前；起始 HEAD `0a90868`，Phase 0 `de558618859c684affc143db0f0a425df7cf0e05`。

## Immutable inputs

| Input | SHA-256 |
| --- | --- |
| canonical prices | `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93` |
| universe metadata | `190aacbca6feadd2ba825b1f284c06f48f30bdc3b5a4618f405711e5aadb8829` |
| S2 manifest | `e280c60b9a0698e6fd19a2f268913dbb7ac42492b2062e5f3268d2a61bc4326f` |
| S27 config / implementation | `4d5f96a7d1e1c7b38df18d53157601fc6055b18091cab1702f74b129e63e517c` / `83f52203617af70284db3e0b9df0bf6d4d1702a914344c107528508dc2d3d203` |
| S10 config / implementation | `4ef87e42e130b14b8174f391a412969f5543af37c807d3e2930c8c89015d5f0f` / `cac1639220e610f50d8b00a29e2d100de44fedf357c1a6d5987db0770730cfbd` |
| S4C implementation | `77f0061b2cf998d8eea8b653ece03e484a5c436d47dcb816dc3f092a3c1304d7` |

RQAlpha 固定为 6.3.0，skfolio 固定为 1.0.6。外部证据仅引用已有 registry，不新增证据等级。

## Shared contract

所有 VectorBT replay 传入 lifecycle-derived `tradability_mask` 与 `lifetimes`；冻结 targets 必须严格递增、非负、每行合计一，且每个正权重在 execution date 可交易。任何失败均为 INVALID_RUN 或相应 BLOCK，不可通过兼容开关绕过。

## Track A / B: frozen-target native execution

S27 固定 200 trend / 60 vol、月频 signal、下一 canonical observation execution、fallback 与 10/5 bps；S10 固定 25/25/25/25、20/10、[0,1] 无杠杆 scale、bond defensive allocation、月频/下一 observation、10/5 bps。两者均以 PIT contract 自动给出 inception。

先将 PIT-corrected frozen schedule 直接 replay 给 VectorBT，严格重现 Batch 04 的 CAGR、signed MaxDD、Sharpe、Calmar、turnover；失败停止为 reproduction block。RQAlpha callback 只按 execution date 读取 frozen row 并调用 `order_target_portfolio`，使用 native account/matching/fees/slippage 与 `partial_fill_on_insufficient_cash=true`，不计算信号、波动、sizing 或 fallback。

PASS gate（两者）：所有 frozen dates processed、无额外 dates、cash rejection=0、平均 execution-date total absolute deviation <=3%、material dates <=10%、平均 cash <=2%、CAGR>0 且距 VectorBT 不低于 2pp、signed MaxDD 不比 VectorBT 差超过 5pp。所有 >5pp target differences 必须有 native reason，禁止 UNKNOWN。S10 另记录 frozen scale<1 月数、平均 frozen scale、implemented risky/bond exposure。

Allowed decisions：S27 `ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW` / `DO_NOT_ADVANCE_S27A_EXECUTION` / reproduction or environment block；S10 对称。任何 advance 都不创建 candidate 或 shadow。

## Track C: bounded S4C robustness

固定 RiskBudgeting / variance / equal risk budget / long-only / fully invested / no leverage / min eligible 6 / PIT fallback / month-end estimation then next observation execution。唯一变量为 aligned returns 40、60（中心）、80，即价格 windows 41、61、81。每个 case 分别构造同 eligible ERC、inverse-vol、equal-weight，使用同一 eligible set/data/execution dates/costs。中心固定为 60，不择优。

固定既有四个 periods；中心复用 3Y、5Y rolling。中心成本仅 15/30/50bps。记录 concentration：max weight median/P95/max、>50% 月数、effective assets median/P05。

Reproduction：60-return center 必须重现 Batch 04。各窗口 CAGR>0、Sharpe>0、MaxDD>-30%；至少 2/3 相对 same-window inverse-vol 满足 CAGR >= -1.5pp、MaxDD 不差 >2pp，且 Sharpe +.02 或 Calmar +.03。中心所有 fixed periods CAGR>0，至少3/4 Sharpe或Calmar更优；3Y/5Y positive-CAGR shares >=90%/>=95%，至少60% 3Y Sharpe或MaxDD改善；50bps CAGR>0、Sharpe>=.60。集中度是证据，不添加 cap。

Allowed decisions：`ADVANCE_S4C_TO_EXECUTION_REVIEW`、`REJECT_S4C_ROBUSTNESS`、`BLOCK_S4C_ROBUSTNESS_REPRODUCTION`、`BLOCK_S4C_UPSTREAM_EXECUTION`。不运行 S4C RQAlpha。

停止条件：不修改 S2、策略经济语义或 frozen parameters；不添加策略/通用 execution 或 robustness framework；一个 track 的失败不阻断另外两个。结果只能在本 protocol commit 后产生。
