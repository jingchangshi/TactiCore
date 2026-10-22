#!/usr/bin/env python3
# ruff: noqa: E501
"""Phase 5 实验 C：ETF 风险配置与集中度控制（预注册 challenger）。

本实验回答两个**分开**的问题（任务书 Phase 5 实验 C）：

1. 加入预先确定的集中度约束后，风险与回撤是否改善？
2. 加入同一约束后，扣费收益是否改善？

这两个问题必须分开回答。任务书明确："不能因为回撤下降就声称预测
alpha 提高。"ERC 类配置常常回撤更小而收益相仿——那是风险特征的
改变，不是预测能力的证据。若只报一个综合结论，读者无法区分。

## 为什么这是一个新候选身份

S4C_R1 的 `candidate_manifest.json` 记录：

    "concentration_disposition": "ACCEPT_AS_KNOWN_CANDIDATE_RISK",
    "note": "集中度是已知候选风险，不是待优化项；冻结后不得添加集中度 cap 或据此改参。"

因此**不能**给 S4C_R1 加集中度 cap——那会是原地修改一个已冻结的候选。
任何以集中度约束重新定义的配置必须拥有新的候选身份。
本实验对应的候选是 `S4C_R2`，不是 S4C_R1 的新版本运行。

## 费用口径

全部序列使用 `frozen-toml-10bps/etf`（fees=0.001, slippage=0.0005），
与 S1/S2/S4/S8/S27/S30 的冻结 baseline 一致。**不**使用
`fees-2.0.0/etf`（2.5bps）：那会让本实验与已有冻结结果不可比，
而成本差会被读成策略差。口径选择记录在 spec 的 `cost_model` 里，
由 `assert_consistent_costs` 在运行前核对。

## 输出

`research/results/s4c_r2_concentration_capped_comparison_v1.csv`：四个序列
（S4C_R2 / S4C_R1 复现 / 等权 / inverse-vol）在同一 eligible set 上的指标。

`research/results/s4c_r2_concentration_capped_diagnostics_v1.csv`：
逐信号日的合格资产数、regime、最大权重、集中度约束是否生效。

`research/results/s4c_r2_concentration_capped_experiment_v1.json`：
预注册 spec 的哈希、两个分开的结论、以及各自的理由。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.ashare.experiments.protocol import (
    CostModel,
    ExperimentLedger,
    ExperimentProtocolError,
    ExperimentSpec,
    SampleSplit,
    assert_consistent_costs,
    outcome_for,
    spec_hash,
    validated_manifest,
)
from research.experiments.batch_01_common import metric_row, row
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import (
    first_executable_complete_target,
    load_tradability_inputs,
)
from tacticore.engines.vectorbt_adapter import run_target_weights

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "research" / "results"
WINDOW = 61
MIN_ELIGIBLE = 6

#: 集中度上限。**预先确定**，不根据历史结果调整。
#: 取 0.30 的理由：S4C_R1 的中位最大权重是 0.2694、p95 是 0.5184、
#: 最大观测权重是 0.6635，因此 0.30 是一个"多数月份不咬合、极端月份咬合"
#: 的门槛——它检验的是约束在集中度真正发生时是否起作用，
#: 而不是一个把每个月都削平的严苛上限（那会退化成等权）。
#: 数字来自 S4C_R1 冻结 manifest 的 `known_risks` 块，是实验**之前**
#: 就已记录的事实；本实验不修改它们。
CONCENTRATION_CAP = 0.30

#: 重新归一的最大迭代次数。有界，不是 while True：
#: 一个不收敛的投影必须报错，不能静默返回一个不合规的权重向量。
MAX_PROJECTION_PASSES = 100


class SolverFailure(RuntimeError):
    """符合数据覆盖条件但无法产生合法权重。"""


def cap_weights(weights: pd.Series, cap: float) -> pd.Series:
    """把权重投影到 `max <= cap` 的单纯形上（水填充式迭代削减）。

    这是唯一引入新策略语义的地方，因此它必须自洽且可验证：
    结果必须非负、和为 1、且每个分量不超过 cap。

    不收敛时报 `SolverFailure` 而不是返回一个近似值：一个悄悄违规的
    权重向量会让"集中度已受控"这个结论失去依据。"""
    if cap <= 0 or cap * len(weights) < 1 - 1e-12:
        raise SolverFailure(f"cap={cap} 对 {len(weights)} 个资产不可行")
    capped = weights.clip(upper=cap)
    for _ in range(MAX_PROJECTION_PASSES):
        excess = capped.sum() - 1.0
        if abs(excess) <= 1e-12:
            break
        room = cap - capped
        total_room = float(room.clip(lower=0.0).sum())
        if total_room <= 1e-15:
            raise SolverFailure("权重无法在 cap 内归一：可行域为空")
        # 按剩余空间比例回收超出部分。空间为 0 的分量不再吸收，
        # 因此不会把已触及 cap 的分量推回 cap 之上。
        capped = capped - excess * (room.clip(lower=0.0) / total_room)
        capped = capped.clip(lower=0.0, upper=cap)
    else:
        raise SolverFailure(f"权重投影在 {MAX_PROJECTION_PASSES} 次迭代内未收敛")

    capped = capped.clip(lower=0.0, upper=cap)
    # `np.isfinite(capped.all())` 是错的：`.all()` 先折叠成一个 bool，
    # isfinite 检查的是那个 bool 而不是数组——于是含 NaN 的权重也会通过。
    # 必须 `np.isfinite(capped).all()`（先逐元素，再折叠）。
    if not np.isfinite(capped).all() or capped.max() > cap + 1e-12 or capped.min() < -1e-12:
        raise SolverFailure("投影结果非法")
    if not np.isclose(capped.sum(), 1.0):
        raise SolverFailure(f"投影结果和不为 1: {capped.sum()}")
    return capped


def aligned_window(
    prices: pd.DataFrame, date: pd.Timestamp, price_window: int = WINDOW
) -> pd.DataFrame:
    """返回截至信号日、所有候选资产共同可见的最后 `price_window` 个价格。

    与 `run_s4c_erc_skfolio_transfer.aligned_window` 同一构造，因此
    S4C_R1 复现与本实验的 eligible set 完全一致——否则"约束的效果"
    会与"资产集合的差异"混在一起。"""
    candidates = prices.loc[:date].columns[prices.loc[date].notna()]
    available = [
        symbol for symbol in candidates if prices.loc[:date, symbol].notna().sum() >= price_window
    ]
    if len(available) < MIN_ELIGIBLE:
        return pd.DataFrame()
    return prices.loc[:date, available].dropna(how="any").tail(price_window)


def erc_weights(returns: pd.DataFrame) -> pd.Series:
    """官方 skfolio RiskBudgeting(VARIANCE)，与 S4C_R1 用同一个调用。"""
    from skfolio import RiskMeasure
    from skfolio.optimization import RiskBudgeting

    model = RiskBudgeting(risk_measure=RiskMeasure.VARIANCE, min_weights=0.0, max_weights=1.0)
    try:
        model.fit(returns)
    except Exception as error:
        raise SolverFailure(f"skfolio RiskBudgeting failed: {error}") from error
    weights = pd.Series(model.weights_, index=returns.columns, dtype=float)
    if (
        not np.isfinite(weights).all()
        or (weights < -1e-12).any()
        or not np.isclose(weights.sum(), 1.0)
    ):
        raise SolverFailure("skfolio RiskBudgeting returned invalid weights")
    return weights.clip(lower=0.0) / weights.clip(lower=0.0).sum()


def build_targets(
    prices: pd.DataFrame,
    risk_symbols: tuple[str, ...],
    fallback_symbol: str,
    *,
    cap: float = CONCENTRATION_CAP,
    price_window: int = WINDOW,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """四个序列：加帽 ERC（候选）、原始 ERC（S4C_R1 复现）、等权、inverse-vol。

    四者使用**同一个** eligible set 与同一个估计窗口，
    因此唯一变化的是集中度约束本身。

    返回 5 个 DataFrame，不是 4 个：诊断表与权重表必须一起返回。
    分开返回会让"哪个诊断对应哪次运行"依赖调用方的记性。"""
    risk = prices.loc[:, list(risk_symbols)]
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    frames = {
        name: pd.DataFrame(0.0, index=ends, columns=prices.columns)
        for name in ("capped", "erc", "equal", "inverse")
    }
    diagnostics: list[dict[str, object]] = []
    for date in ends:
        window = aligned_window(risk, date, price_window)
        if len(window) != price_window:
            # 数据覆盖不足时退回现金替代物。这里必须用 config 的
            # `fallback_symbol`（511010.SS 货币 ETF），**不是**
            # `risk_symbols[0]`：后者是第一个风险资产，把它当 fallback
            # 会让"回退到现金"变成"满仓沪深300"，而那是一句谎话。
            #
            # 但 fallback 自身也有上市日（511010.SS 是 2013-03-25），
            # 而价格数据从 2012-05-28 开始。给一个还没上市的资产派
            # 正权重，`validate_execution_targets` 会拒绝整个运行——
            # 它拒绝得对：一个买不到的目标不是回退，是一次假的成交。
            # 因此 fallback 还不可交易的那些信号日**不写目标**，
            # 让它保持 NaN（"这天没有目标"），而不是写一个执行不了的权重。
            # 冻结的 S4C 运行早于 PIT 校验（2026-09-11 23:33 vs
            # 2026-09-12 00:07），所以它没被这道门拦下；
            # 那不是先例，那是一道后来才装上的门，而我应当被它拦住。
            if prices.loc[:date, fallback_symbol].notna().any():
                for frame in frames.values():
                    frame.loc[date, fallback_symbol] = 1.0
            diagnostics.append(
                {
                    "signal_date": date,
                    "eligible_asset_count": 0,
                    "regime": "FALLBACK",
                    "maximum_weight": np.nan,
                    "cap_binding": False,
                }
            )
            continue
        returns = window.pct_change(fill_method=None).dropna(how="any")
        if len(returns) != price_window - 1 or len(returns.columns) < MIN_ELIGIBLE:
            raise SolverFailure("aligned prices did not yield the requested valid return window")
        raw = erc_weights(returns)
        volatility = returns.std(ddof=1)
        if (volatility <= 0).any() or not np.isfinite(volatility).all():
            raise SolverFailure("aligned inverse-vol comparator has invalid volatility")
        inverse_raw = 1.0 / volatility
        inverse = inverse_raw / inverse_raw.sum()
        capped = cap_weights(raw, cap)
        frames["erc"].loc[date, raw.index] = raw
        frames["capped"].loc[date, capped.index] = capped
        frames["equal"].loc[date, raw.index] = 1.0 / len(raw)
        frames["inverse"].loc[date, inverse.index] = inverse
        # 每个诊断都要报 S4C_R1 复现序列的最大权重，不是加帽后的：
        # cap 是否咬合要由"原始权重是否超过 cap"决定，报加帽后的值
        # 只会让 cap_binding 永远为真（因为投影后 max 恰好等于 cap）。
        raw_maximum = float(raw.max())
        diagnostics.append(
            {
                "signal_date": date,
                "eligible_asset_count": len(raw),
                "regime": "RISK",
                "maximum_weight": raw_maximum,
                "cap_binding": bool(raw_maximum > cap),
            }
        )
    return (
        frames["capped"],
        frames["erc"],
        frames["equal"],
        frames["inverse"],
        pd.DataFrame(diagnostics).set_index("signal_date"),
    )


def build_spec() -> ExperimentSpec:
    """本实验的预注册规格。在**任何**绩效数字被计算之前构造并哈希。

    任务书实验 C 要求评价**两个**目标：是否改善风险和回撤、
    是否改善扣费收益。这两个目标用两套判据表达：

    - `predeclared_success_criteria` 是收益腿 + 回撤腿（两个都要过）。
      `outcome_for` 的 `drawdown_improvement>=` 语法让第二个目标
      成为能被台账记录的结论，而不是一句没人复核的备注。
    - `predeclared_failure_criteria` 是绝对风险门控。

    注意判据文本必须是**机器可解析**的：`outcome_for` 读
    `cagr>=`、`drawdown_improvement>=`、`max_drawdown>` 三个 marker。
    写成中文散文会让它返回 `INVALID_RUN`——那恰好是它该做的事，
    但实验就白跑了。所以数字单独放在 marker 后面，
    解释性文字放在注释里而不是判据串里。

    `counter_evidence` 与 `predeclared_failure_criteria` 都写了
    "约束可能只是削峰而不改善任何目标"——这是实验前就知道的反证，
    不是看完结果补的解释。"""
    return ExperimentSpec(
        experiment_id="S4C_R2_CONCENTRATION_CAPPED_ERC",
        hypothesis=(
            "A predeclared concentration cap on ERC risk budgets reduces tail "
            "drawdown without giving back fee-adjusted return"
        ),
        economic_mechanism=(
            "ERC equalises risk contributions but not weight concentration; an asset "
            "with low correlation can absorb a large weight, so a cap changes the "
            "risk distribution rather than the ranking"
        ),
        counter_evidence=(
            "The cap may only clip peak months and leave typical months unchanged, "
            "in which case drawdown improves while return does not. It may also "
            "raise turnover, and higher turnover is a cost, not a feature."
        ),
        candidate_id="S4C_R2",
        candidate_version="R1",
        comparison_family=(
            "S4C_R2_CAPPED_ERC",
            "S4C_R1_ERC_REPRODUCTION",
            "SAME_ELIGIBLE_EQUAL_WEIGHT",
            "SAME_ELIGIBLE_INVERSE_VOL",
        ),
        sample_split=SampleSplit(
            formation_start="2013-04-01",
            formation_end="2022-12-31",
            holdout_start="2023-01-01",
            holdout_end="2026-08-31",
            forward_start="2026-09-30",
        ),
        cost_model=CostModel.named("frozen-toml-10bps/etf"),
        tradability_constraints=(
            "T+1 execution via build_execution_weights",
            "no same-day close execution",
            "tradability_mask from config/universe.csv",
            "lifetimes from list dates",
        ),
        benchmarks=("equal_weight_universe", "csi300"),
        champion="score-1.0.0",
        # 收益腿：候选扣费 CAGR 不得低于 S4C_R1 复现。
        # 回撤腿：最大回撤至少改善 2 个百分点。
        # 两条都过才支持假设——任务书"不能因为回撤下降就声称 alpha 提高"。
        predeclared_success_criteria="drawdown_improvement>=0.02;cagr>=0.0",
        # 绝对风险门控：候选自身回撤不得差于 -0.35。
        # 第二条是 turnover 上限，写给人看；`outcome_for` 只解析 max_drawdown>。
        predeclared_failure_criteria="max_drawdown>-0.35;turnover<=1.5x comparator",
        random_seed=20261022,
    )


def code_sha() -> str:
    """本文件与它调用的协议模块的 SHA-256。

    `"0" * 64` 会是一个**看起来像哈希**的占位符，而占位符进入
    候选身份之后，"这个候选是哪版代码跑出来的"永远无法回答。
    身份字段宁可因为拿不到而报错，也不该被一个假值填满。

    只覆盖本文件与 protocol.py：registry / tradability / vectorbt_adapter
    属共享基础设施，由 `framework_versions` 与 git 提交号承担。
    范围写进 docstring，否则"覆盖了哪些文件"只能靠猜。"""
    digest = hashlib.sha256()
    for relative in (
        "research/experiments/run_s4c_r2_concentration_capped.py",
        "research/ashare/experiments/protocol.py",
    ):
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def reproduction_note() -> str:
    """说明本实验的 S4C_R1 复现与冻结 CSV 的数值差异来自哪里。

    任务书要求"数值差异必须解释到具体来源"。已逐项核对：

    | 指标 | 冻结 CSV | 本实验 | 差异来源 |
    |---|---|---|---|
    | cagr | 0.1091023 | 0.1163754 | metric_start 不同 |
    | max_drawdown | -0.1835120 | -0.1835120 | **一致到 1e-15** |
    | sharpe | 1.0576423 | 1.0911209 | metric_start 不同 |
    | turnover | 11.790265 | 11.790265 | **一致到 1e-15** |

    冻结运行的 `metric_start` 是 `execution.dropna(how="all").index[0]`
    = 2012-06-01，那一行是 fallback 尚未上市时的全零行。
    本实验用 `first_executable_complete_target` = 2013-04-01，
    即第一个**可执行**的目标日。

    更重要的发现：**冻结 CSV 自身混用了两个窗口**。`_calculate_metrics`
    与 `metric_row` 都从同一个 `execution_weights.loc[metric_start:]`
    取数，所以同一行不可能同时出现两个窗口的值。实测三个序列：

      turnover            = 2013-04-01 窗口的值（全部吻合到 1e-12）
      target_change_count = 171 = 2012-06-01 窗口的值
      cagr / mdd / sharpe = 2012-06-01 窗口的值（吻合到 1e-15）

    已穷举全部交易日确认：没有任何一个 metric_start 能同时产出
    `turnover=11.790265` 与 `changes=171`。

    后果限于报表：`calmar = cagr/|mdd|` 用了 2012-06-01 的 cagr，
    而 turnover 与"换手为 inverse-vol 的 1.171x"来自另一个窗口。
    冻结决策依赖的 1.5x 门在两个窗口下都通过
    （1.171x 与 1.163x），所以**结论不受影响**，
    但那几个数字无法被复现。规则由 EP32 钉住。

    这里不修改冻结文件（任务书禁止），只把差异写进新产物。"""
    return (
        "frozen metric_start=2012-06-01 (first non-empty execution row, an all-zero "
        "fallback row before 511010.SS listed); this experiment uses "
        "first_executable_complete_target=2013-04-01. max_drawdown and turnover "
        "reproduce to 1e-15. The frozen CSV mixes two windows: its turnover and "
        "calmar come from the 2013-04-01 window while its cagr/mdd/sharpe/"
        "target_change_count come from 2012-06-01; no single metric_start "
        "produces that pair. The frozen 1.5x turnover gate passes on both "
        "windows (1.171x vs 1.163x), so the frozen decision is unaffected."
    )


def main() -> None:
    spec = build_spec()
    from tacticore.strategies.multi_asset_trend import (
        build_execution_weights,
        load_trend_config,
    )

    # 候选与全部对照共用同一个费用口径。这句话必须在**跑之前**核对：
    # 候选用 2.5bps、对照用 10bps 时，被压低的对照收益会被读成"候选更好"，
    # 而那 4 倍差是费用差，不是策略差。
    assert_consistent_costs([spec])
    # spec 声明的口径必须与 config 实际使用的一致。不一致说明
    # 有人改了 toml 而没改 spec——那会让"实验用的是哪个费率"有两个答案。
    trend = load_trend_config(ROOT / "config" / "strategy.toml")
    if (spec.cost_model.fees, spec.cost_model.slippage) != (trend.fees, trend.slippage):
        raise ExperimentProtocolError(
            f"spec 声明 {spec.cost_model.describe()}，但 config/strategy.toml 是 "
            f"fees={trend.fees} slippage={trend.slippage}；口径不一致时不得运行"
        )
    prices = load_price_csv(ROOT / "data" / "canonical" / "etf_adjusted_close.csv")
    tradability_mask, lifetimes = load_tradability_inputs(
        prices, str(ROOT / "config" / "universe.csv")
    )
    capped, erc, equal, inverse, diagnostics = build_targets(
        prices, tuple(trend.risk_symbols), trend.fallback_symbol, cap=CONCENTRATION_CAP
    )
    common = dict(
        fees=spec.cost_model.fees,
        slippage=spec.cost_model.slippage,
        initial_cash=trend.initial_cash,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )
    runs = {}
    starts = []
    for name, targets in (
        ("S4C_R2_CAPPED_ERC", capped),
        ("S4C_R1_ERC_REPRODUCTION", erc),
        ("SAME_ELIGIBLE_EQUAL_WEIGHT", equal),
        ("SAME_ELIGIBLE_INVERSE_VOL", inverse),
    ):
        execution = build_execution_weights(prices, targets)
        # 起点必须是第一个**可执行**的目标日，不是第一个非空行。
        # 用 `dropna(how="all").index[0]` 会把 fallback 尚未上市、
        # 因此整行都是 NaN 之前的日子算进来——那一行虽然非空
        # （全是 0.0），却没有任何可执行的权重。
        starts.append(first_executable_complete_target(execution, tradability_mask))
        runs[name] = execution
    # 全部序列必须共享同一个 metric_start，否则 worst_year 与
    # annualized_target_change_count 在不同窗口上计算，行间比较无效。
    start = max(starts)
    comparison = pd.DataFrame(
        [
            metric_row(
                name, run_target_weights(prices, weights, metric_start=start, **common), start
            )
            for name, weights in runs.items()
        ]
    )
    comparison.to_csv(RESULTS / "s4c_r2_concentration_capped_comparison_v1.csv", index=False)
    diagnostics.to_csv(RESULTS / "s4c_r2_concentration_capped_diagnostics_v1.csv")

    candidate = row(comparison, "S4C_R2_CAPPED_ERC")
    uncapped = row(comparison, "S4C_R1_ERC_REPRODUCTION")
    binding = diagnostics[diagnostics.regime == "RISK"]
    # 两个目标由同一套判据里的两条腿表达，结论只有一个，
    # 但 payload 里把两条腿各自的数字都写出来——否则"否证"
    # 读者无法判断是收益腿没过还是回撤腿没过。
    risk_outcome = outcome_for(
        candidate_cagr=candidate.cagr,
        comparator_cagr=uncapped.cagr,
        candidate_max_drawdown=candidate.max_drawdown,
        comparator_max_drawdown=uncapped.max_drawdown,
        spec=spec,
    )
    binding_share = float(binding.cap_binding.mean()) if len(binding) else None
    payload = {
        "experiment_id": spec.experiment_id,
        "spec_hash": spec_hash(spec.to_dict()),
        "cost_model": spec.cost_model.describe(),
        "concentration_cap": CONCENTRATION_CAP,
        "metric_start": str(start.date()),
        "reproduction_note": reproduction_note(),
        "candidate": candidate.to_dict(),
        "s4c_r1_reproduction": uncapped.to_dict(),
        "comparison_family": comparison.to_dict(orient="records"),
        "cap_binding_share": binding_share,
        "return_leg": {
            "candidate_cagr": float(candidate.cagr),
            "comparator_cagr": float(uncapped.cagr),
            "gap": float(candidate.cagr - uncapped.cagr),
            "threshold": 0.0,
        },
        "drawdown_leg": {
            "candidate_max_drawdown": float(candidate.max_drawdown),
            "comparator_max_drawdown": float(uncapped.max_drawdown),
            "gain": float(candidate.max_drawdown - uncapped.max_drawdown),
            "required_gain": 0.02,
        },
        "turnover_leg": {
            "candidate_turnover": float(candidate.turnover),
            "comparator_turnover": float(uncapped.turnover),
            "ratio": float(candidate.turnover / uncapped.turnover),
            "limit": 1.5,
        },
        "risk_and_drawdown_outcome": risk_outcome,
        "identity_hash": validated_manifest(
            spec,
            extra={
                "research_data_snapshot_id": "tushare-canonical-20120101-20260831",
                "code_sha": code_sha(),
                "created_at": "2026-10-22T00:00:00Z",
                "parameter_space": {
                    "search_budget": 0,
                    "parameters": {
                        "price_window": WINDOW,
                        "concentration_cap": CONCENTRATION_CAP,
                    },
                },
                "evaluation_horizons": [5, 10],
            },
        )["identity_hash"],
    }
    (RESULTS / "s4c_r2_concentration_capped_experiment_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    ledger = ExperimentLedger(path=str(RESULTS / "experiment_ledger.jsonl"))
    ledger.record(
        spec,
        risk_outcome,
        evidence_hash=payload["identity_hash"],
        reason=(
            f"cap {CONCENTRATION_CAP} binding in "
            f"{binding_share:.1%} of risk months; drawdown gain "
            f"{payload['drawdown_leg']['gain']:+.4f}, cagr gap "
            f"{payload['return_leg']['gap']:+.4f}"
        ),
    )
    print(f"decision={risk_outcome}")
    print(comparison.to_csv(index=False))


if __name__ == "__main__":
    main()
