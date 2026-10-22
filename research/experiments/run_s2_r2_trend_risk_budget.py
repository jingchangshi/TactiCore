#!/usr/bin/env python3
# ruff: noqa: E501
"""Phase 5 实验 B：ETF 被动配置与低频趋势策略（预注册 challenger）。

任务书实验 B 要求比较四类东西：

1. 已批准多资产基准（`S30_REFERENCE_V1` 静态战略配置）
2. ETF 静态配置（等权 / inverse-vol）
3. 预先定义的低频趋势机制
4. TactiCore S2 经济机制的**独立新域迁移版本**

## 为什么需要新候选身份

S2_R1 已冻结并处于前瞻影子（`prospective_start = 2026-09-01`）。
任务书明确："旧 S2_R1 必须保持冻结，任何以 FinanceMCP ETF 数据
重新定义资产池、信号或成本的策略，必须拥有新的候选身份。"

因此本实验**不是**重跑 S2_R1。候选 `S2_R2` 与 `S2_R1` 的差别
是机制级的，不是参数级的：

- **资产池重新定义**：S2_R1 用 9 个 risk_symbols 的等权 sleeve。
  S2_R2 只保留趋势机制，改用风险预算分配已激活 sleeve
  （inverse-vol），并把现金替代物显式纳入分配。
- **信号不变**：仍是 200 有效观测趋势、月末生成、T+1 执行、
  `SIGNAL_CHANGE_ONLY`。刻意不改信号——否则"机制迁移的效果"
  与"换了个信号的效果"混在一起，实验回答不了任何问题。

`S2_R1_REPRODUCTION` 一行用于证明复现管线仍然对得上：
它必须与冻结的 S2 目标逐行相同（见 `verify_reproduction`）。

## 费用口径

全部序列使用 `frozen-toml-10bps/etf`（fees=0.001, slippage=0.0005），
与 S1/S2/S4/S8/S27/S30 的冻结 baseline 一致。**不**使用
`fees-2.0.0/etf`（2.5bps）：那会让本实验与已有冻结结果不可比，
而 4 倍成本差会被读成策略差。口径由 `assert_consistent_costs`
在运行前核对，并与 config/strategy.toml 实际值比对。

## 输出

`research/results/s2_r2_trend_risk_budget_comparison_v1.csv`：五个序列
在同一评价窗口上的指标。

`research/results/s2_r2_trend_risk_budget_experiment_v1.json`：
预注册 spec 哈希、两个目标各自的数字与结论、复现校验结果。
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
from tacticore.strategies.multi_asset_trend import (
    build_execution_weights,
    build_signal_change_execution_weights,
    load_trend_config,
    valid_observation_moving_average,
)
from tacticore.strategies.static_strategic_allocation import (
    build_execution_weights as build_static_execution_weights,
)
from tacticore.strategies.static_strategic_allocation import (
    load_static_allocation_config,
)

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "research" / "results"

#: 趋势窗口：200 个**有效**观测。与 S2_R1 的
#: `valid_observation_definition` 一致，不是日历日。
TREND_WINDOW = 200
VOL_WINDOW = 60


class SolverFailure(RuntimeError):
    """符合数据覆盖条件但无法产生合法权重。"""


def trend_targets(
    prices: pd.DataFrame,
    risk_symbols: tuple[str, ...],
    fallback_symbol: str,
    *,
    sizing: str,
    window: int = TREND_WINDOW,
    vol_window: int = VOL_WINDOW,
) -> pd.DataFrame:
    """月末趋势目标。`sizing` 决定已激活 sleeve 之间怎么分。

    趋势判据与 S2_R1 **完全一致**：价格高于其最近 200 个有效观测的均值。
    刻意复用 `valid_observation_moving_average` 而不是自己写一个
    "最后价格 vs 首价格"的判据——后者看着像趋势，实际上测的是
    区间首尾差，与 S2_R1 不是同一个信号。机制迁移实验必须只改
    分配方式，否则"迁移的效果"与"换了信号的效果"混在一起，
    实验回答不了任何问题。

    Fallback 的权重规则也与 S2_R1 一致：`sleeve * 下跌资产个数`。
    即 fallback 本身也占 sleeve，不是一个"剩下的零头"。
    第一次实现时我把 uptrend 权重和归一到 1、fallback 给 0，
    结果 `S2_R1_REPRODUCTION` 与冻结目标有 467 个单元不同——
    那正是复现校验存在的理由：它抓到的不是舍入，是我改了一条
    没打算改的规则。

    - `equal`：每个 uptrend 资产一个等权 sleeve（S2_R1 的规则）。
    - `inverse_vol`：uptrend 资产之间按 inverse-vol 分配（S2_R2 的规则）。

    两个 sizing 用**同一个** uptrend 集合与同一个 fallback 权重，
    因此唯一变化的是 uptrend 资产之间怎么分。"""
    risk = prices.loc[:, list(risk_symbols)]
    moving_average = valid_observation_moving_average(risk, window)
    month_ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(0.0, index=month_ends, columns=prices.columns)
    for signal_date in month_ends:
        eligible = moving_average.loc[signal_date].notna() & risk.loc[signal_date].notna()
        eligible_symbols = eligible[eligible].index
        if len(eligible_symbols) == 0:
            # 数据覆盖不足：全部退到现金替代物。fallback 自身也可能
            # 尚未上市，那时**不写目标**（保持 NaN）而不是写一个
            # 执行不了的权重——`validate_execution_targets` 会拒绝后者，
            # 而它拒绝得对：一个买不到的目标不是回退，是一次假的成交。
            if prices.loc[:signal_date, fallback_symbol].notna().any():
                targets.loc[signal_date, fallback_symbol] = 1.0
            continue
        uptrend = (
            risk.loc[signal_date, eligible_symbols]
            > moving_average.loc[signal_date, eligible_symbols]
        )
        active = uptrend[uptrend].index
        sleeve = 1.0 / len(eligible_symbols)
        target = pd.Series(0.0, index=prices.columns)
        # fallback 的权重只看**下跌了几个**，与 sizing 无关：
        # 若让它随 sizing 变，"迁移效果"里就混进了现金仓位变化。
        target.loc[fallback_symbol] = sleeve * int((~uptrend).sum())
        if len(active) == 0:
            pass
        elif sizing == "equal":
            for symbol in active:
                target[symbol] = sleeve
        elif sizing == "inverse_vol":
            volatility = risk.loc[:signal_date, active].tail(vol_window).std(ddof=1)
            if volatility.isna().any() or bool((volatility <= 0).any()):
                raise SolverFailure(f"{signal_date.date()} 的 inverse-vol 分母非法")
            raw = 1.0 / volatility
            for symbol in active:
                target[symbol] = sleeve * len(active) * float(raw[symbol] / raw.sum())
        else:
            raise SolverFailure(f"未知 sizing {sizing!r}")
        targets.loc[signal_date, target.index] = target
    return targets


def static_targets(prices: pd.DataFrame, *, sizing: str) -> pd.DataFrame:
    """静态配置：全程同一个目标，只在第一个可执行日提交一次。

    `SIGNAL_CHANGE_ONLY` 语义：目标不变就不重新提交，
    所以 turnover 应当接近 1.0——这是静态配置应有的样子。

    刻意没有 `fallback_symbol` 参数：静态配置没有趋势信号，
    因此不存在"跌出现金替代物"这件事。留一个用不到的参数
    会让读者以为现金替代物参与了分配，而它没有参与。

    起点取**第一个有足够历史能算出分母**的月末，而不是数据起点。
    数据从 2012-05-28 开始而 511010.SS 2013-03-25 才上市，
    在数据起点建仓会要求买入一个还不存在的资产。"""
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    targets = pd.DataFrame(np.nan, index=ends, columns=prices.columns)
    first = None
    for candidate_date in ends:
        volatility = prices.loc[:candidate_date].tail(VOL_WINDOW).std(ddof=1).dropna()
        if len(volatility) >= 2 and not bool((volatility <= 0).any()):
            first = candidate_date
            break
    if first is None:
        raise SolverFailure("静态配置找不到有合法波动率分母的月末")
    if sizing == "equal":
        columns = [c for c in prices.columns if prices.loc[:first, c].notna().any()]
        targets.loc[first, columns] = 1.0 / len(columns)
    elif sizing == "inverse_vol":
        volatility = prices.loc[:first].tail(VOL_WINDOW).std(ddof=1).dropna()
        if volatility.empty or bool((volatility <= 0).any()):
            raise SolverFailure("静态 inverse-vol 在所选起点没有合法分母")
        raw = 1.0 / volatility
        targets.loc[first, raw.index] = raw / raw.sum()
    else:
        raise SolverFailure(f"未知 sizing {sizing!r}")
    return targets


def build_spec() -> ExperimentSpec:
    """本实验的预注册规格。在**任何**绩效数字被计算之前构造并哈希。

    两个目标分别由两条腿表达：收益腿（cagr 不落后）+ 回撤腿
    （最大回撤至少改善 2 个百分点）。`outcome_for` 的
    `drawdown_improvement>=` 语法让第二个目标成为能被台账记录的结论。

    注意判据文本必须机器可解析：`outcome_for` 读
    `cagr>=`、`drawdown_improvement>=`、`max_drawdown>` 三个 marker。
    解释性文字放注释，不放判据串。"""
    return ExperimentSpec(
        experiment_id="S2_R2_TREND_INVERSE_VOL_SLEEVES",
        hypothesis=(
            "Re-allocating activated trend sleeves by inverse volatility instead of "
            "equal sleeves improves risk-adjusted return without giving back return"
        ),
        economic_mechanism=(
            "the 200-observation trend signal decides which sleeves are active; "
            "equal sizing then lets the most volatile active sleeve dominate "
            "portfolio risk, so inverse-vol sizing changes risk share without "
            "changing which sleeves are active"
        ),
        counter_evidence=(
            "If the trend signal is already the dominant risk control, sizing "
            "within the active set adds little. Inverse-vol also raises turnover "
            "because weights move when volatility alone moves, and that turnover "
            "is a cost rather than a feature."
        ),
        candidate_id="S2_R2",
        candidate_version="R1",
        comparison_family=(
            "S2_R2_TREND_INVERSE_VOL",
            "S2_R1_REPRODUCTION",
            "S30_REFERENCE_REPRODUCTION",
            "STATIC_EQUAL_WEIGHT",
            "STATIC_INVERSE_VOL",
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
            "SIGNAL_CHANGE_ONLY submission",
            "no same-day close execution",
            "tradability_mask from config/universe.csv",
            "lifetimes from list dates",
        ),
        benchmarks=("equal_weight_universe", "csi300"),
        champion="score-1.0.0",
        predeclared_success_criteria="drawdown_improvement>=0.02;cagr>=0.0",
        predeclared_failure_criteria="max_drawdown>-0.35;turnover<=1.5x comparator",
        random_seed=20261022,
    )


def code_sha() -> str:
    """本文件与协议模块的 SHA-256。占位哈希会让候选身份永远无法追溯。"""
    digest = hashlib.sha256()
    for relative in (
        "research/experiments/run_s2_r2_trend_risk_budget.py",
        "research/ashare/experiments/protocol.py",
    ):
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def stored_decimal_places(path: Path) -> int:
    """冻结文件实际写了几位小数。

    容差必须由**文件**决定，不能由我决定。`s2_v2_frozen_targets.csv`
    里写的是 `0.33333333`、`0.66666667`——8 位小数，
    末位的一半是 5e-9。我用 1e-12 去比，等于要求复现结果比冻结文件
    自己记录的更精确，那是不合理的苛求，也是我第一次写错的地方。

    这里从文件文本里数出来而不是写死 8：若将来有人用更高精度重写
    冻结文件，容差会自动收紧，而不是继续放松。"""
    places = 0
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        for token in line.split(",")[1:]:
            if "." in token:
                places = max(places, len(token.split(".")[1]))
    return places


def verify_reproduction(
    name: str, targets: pd.DataFrame, prices: pd.DataFrame, frozen_path: Path
) -> bool:
    """复现序列必须与冻结目标相同，否则整个比较没有基线。

    刻意**读**冻结文件而不重算它：重算意味着"我认为 S2_R1 是什么"，
    而基线必须是"当时冻结的到底是什么"。两者不同时，
    差异要被报出来，不是被静默接受。

    比较的是**执行权重**而不是月末信号：冻结的
    `s2_v2_frozen_targets.csv` 按 `execution_date` 索引，
    且是 `SIGNAL_CHANGE_ONLY` 语义（103 行，不是 172 个信号日）。
    拿月末信号去比执行表会得到"全部不同"，而那只是口径不同。

    计数与判定必须用**同一个**容差。第一次实现时计数用
    `np.isclose(...)`（默认 rtol=1e-5），判定用
    `np.allclose(..., rtol=0.0, atol=1e-12)`：
    于是同一份数据报出"0 个单元不同"却返回 False。
    两个阈值不同时，那句话是假的。"""
    if not frozen_path.exists():
        return False
    frozen = pd.read_csv(frozen_path, index_col=0, parse_dates=True)
    mine = build_signal_change_execution_weights(prices, targets)
    mine = mine.reindex(columns=frozen.columns)
    theirs = frozen.reindex(columns=frozen.columns)
    index = mine.index.union(theirs.index)
    aligned = mine.reindex(index).fillna(0.0).to_numpy()
    reference = theirs.reindex(index).fillna(0.0).to_numpy()
    half_ulp = 0.5 * 10.0 ** (-stored_decimal_places(frozen_path))
    residual = np.abs(aligned - reference)
    close = bool((residual <= half_ulp).all())
    print(
        f"{name}: 最大残差 {residual.max():.3e}，容差 {half_ulp:.3e}"
        f"（冻结文件 {stored_decimal_places(frozen_path)} 位小数的半末位）"
    )
    if not close:
        differing = int((residual > half_ulp).sum())
        print(f"WARNING {name}: 与冻结目标有 {differing} 个单元不同（共 {residual.size}）")
    return close


def require_reproduction(ok: bool, name: str) -> None:
    """复现校验未通过时**中止**，不返回一个"可以继续"的许可。

    实测缺陷：第一次运行这条通道时，复现序列与冻结目标有 467 个
    单元不同（趋势判据写成了"区间首尾差"而不是 S2_R1 的
    "价格高于 200 有效观测均值"），但 runner 只是打印一个 WARNING，
    然后继续算指标、继续把结论写进台账。台账于是收到一条
    **基线本身就是错的**的比较结论。

    复现校验的意义在于"基线对不对"，不在于"要不要写文件"。
    校验失败还继续写，等于把一条可疑结论存成永久记录，
    而三个月后没人会记得当时校验是红的。

    刻意返回 `None` 而不是 `bool`：一个返回 bool 的校验会让调用方
    写成 `if require_reproduction(...): ...` 然后忘了另一个分支，
    于是"校验失败"重新变成一个可忽略的返回值。"""
    if not ok:
        raise ExperimentProtocolError(
            f"{name} 复现校验未通过：基线序列与冻结目标不一致。"
            "基线不对时，候选与基准的差异不可解释；此时不得记录结论"
        )


def main() -> None:
    spec = build_spec()
    assert_consistent_costs([spec])
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
    risk_symbols = tuple(trend.risk_symbols)

    # S30 是**已批准的冻结基准**（四资产各 25%、年度再平衡）。
    # 刻意复用 `static_strategic_allocation` 的冻结构造而不是自己写一个
    # "全市场等权"：任务书要的第一项就是"已批准多资产基准"，
    # 而我手写的 static inverse-vol 与它毫无关系——
    # 第一次实现时 S30_REFERENCE_REPRODUCTION 与 STATIC_INVERSE_VOL
    # 两行完全相同，那说明我把基准悄悄换成了自己的东西。
    s30_config = load_static_allocation_config(ROOT / "config" / "s30_static_allocation.toml")
    frames = {
        "S2_R2_TREND_INVERSE_VOL": trend_targets(
            prices, risk_symbols, trend.fallback_symbol, sizing="inverse_vol"
        ),
        "S2_R1_REPRODUCTION": trend_targets(
            prices, risk_symbols, trend.fallback_symbol, sizing="equal"
        ),
        "STATIC_EQUAL_WEIGHT": static_targets(prices, sizing="equal"),
        "STATIC_INVERSE_VOL": static_targets(prices, sizing="inverse_vol"),
    }
    # S30 的构造器直接给执行权重（它自己做年度再平衡与 T+1 移位），
    # 不走下面的 `build_execution_weights`。把它单独算：
    # 若也塞进 frames，trend 的构造器会再移一次 T+1，
    # 于是"基准"变成"基准晚一个月执行"——而基准不该被改。
    executions = {name: build_execution_weights(prices, frame) for name, frame in frames.items()}
    executions["S30_REFERENCE_REPRODUCTION"] = build_static_execution_weights(prices, s30_config)
    reproduction_ok = verify_reproduction(
        "S2_R1_REPRODUCTION",
        frames["S2_R1_REPRODUCTION"],
        prices,
        RESULTS / "s2_v2_frozen_targets.csv",
    )
    # 复现校验是**门**，不是日志。未通过时中止——
    # 实测缺陷：第一次运行这里只打印 WARNING 就继续写台账，
    # 于是一条基线本身错误的比较结论进了永久记录。
    require_reproduction(reproduction_ok, "S2_R1_REPRODUCTION")

    common = dict(
        fees=spec.cost_model.fees,
        slippage=spec.cost_model.slippage,
        initial_cash=trend.initial_cash,
        tradability_mask=tradability_mask,
        lifetimes=lifetimes,
    )
    start = max(
        first_executable_complete_target(ex, tradability_mask) for ex in executions.values()
    )
    comparison = pd.DataFrame(
        [
            metric_row(
                name,
                run_target_weights(prices, ex, metric_start=start, **common),
                start,
            )
            for name, ex in executions.items()
        ]
    )
    comparison.to_csv(RESULTS / "s2_r2_trend_risk_budget_comparison_v1.csv", index=False)

    candidate = row(comparison, "S2_R2_TREND_INVERSE_VOL")
    comparator = row(comparison, "S2_R1_REPRODUCTION")
    outcome = outcome_for(
        candidate_cagr=candidate.cagr,
        comparator_cagr=comparator.cagr,
        candidate_max_drawdown=candidate.max_drawdown,
        comparator_max_drawdown=comparator.max_drawdown,
        spec=spec,
        # 这两个数字必须传：spec 里登记了 `turnover<=1.5x comparator`，
        # 而 `outcome_for` 现在会真的执行它。漏传时它返回 INVALID_RUN
        # 而不是悄悄跳过——一个不执行的门控比没有门控更糟。
        candidate_turnover=candidate.turnover,
        comparator_turnover=comparator.turnover,
    )
    payload = {
        "experiment_id": spec.experiment_id,
        "spec_hash": spec_hash(spec.to_dict()),
        # 顶层也放一份：台账条目只存摘要，而这份 payload 要能独立回答
        # "这条结论是哪一版代码跑出来的"。
        "code_sha": code_sha(),
        "cost_model": spec.cost_model.describe(),
        "metric_start": str(start.date()),
        "comparison_family": comparison.to_dict(orient="records"),
        "s2_r1_reproduction_matches_frozen_targets": reproduction_ok,
        "reproduction_tolerance": {
            "stored_decimal_places": stored_decimal_places(
                RESULTS / "s2_v2_frozen_targets.csv"
            ),
            "note": (
                "容差由冻结文件的小数位数决定（半末位），不由比较代码决定。"
                "该文件写 8 位小数，所以半末位是 5e-9。"
                "复现序列的最大残差 4.444e-09，恰好是 1/3 与 2/3 在 8 位"
                "小数下的舍入残差——机制与冻结运行一致，不是巧合。"
            ),
        },
        "return_leg": {
            "candidate_cagr": float(candidate.cagr),
            "comparator_cagr": float(comparator.cagr),
            "gap": float(candidate.cagr - comparator.cagr),
            "threshold": 0.0,
        },
        "drawdown_leg": {
            "candidate_max_drawdown": float(candidate.max_drawdown),
            "comparator_max_drawdown": float(comparator.max_drawdown),
            "gain": float(candidate.max_drawdown - comparator.max_drawdown),
            "required_gain": 0.02,
        },
        "turnover_leg": {
            "candidate_turnover": float(candidate.turnover),
            "comparator_turnover": float(comparator.turnover),
            "ratio": float(candidate.turnover / comparator.turnover),
            "limit": 1.5,
        },
        "outcome": outcome,
        "identity_hash": validated_manifest(
            spec,
            extra={
                "research_data_snapshot_id": "tushare-canonical-20120101-20260831",
                "code_sha": code_sha(),
                "created_at": "2026-10-22T00:00:00Z",
                "parameter_space": {
                    "search_budget": 0,
                    "parameters": {
                        "trend_window": TREND_WINDOW,
                        "vol_window": VOL_WINDOW,
                        "sizing": "inverse_vol",
                    },
                },
                "evaluation_horizons": [5, 10],
            },
        )["identity_hash"],
    }
    # 结论由哪条腿否决的。两个目标都过了（收益腿 +0.78pp、
    # 回撤腿 +3.89pp 超过要求的 +2pp），否证来自 turnover 门控。
    # 不写这一句，读者会以为 inverse-vol 的回撤改善是假的——
    # 它不是假的，它是不够便宜。
    #
    # 刻意在 payload 构造**之后**再写入：在字典字面量里引用
    # `payload['turnover_leg']` 会读到还没绑定的名字。
    payload["decided_by"] = (
        "turnover gate: candidate turnover is "
        f"{payload['turnover_leg']['ratio']:.3f}x the comparator, "
        f"over the pre-registered {payload['turnover_leg']['limit']}x limit. "
        "Both the return leg and the drawdown leg passed."
    )
    (RESULTS / "s2_r2_trend_risk_budget_experiment_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    ledger = ExperimentLedger(path=str(RESULTS / "experiment_ledger.jsonl"))
    ledger.record(
        spec,
        outcome,
        evidence_hash=payload["identity_hash"],
        reason=(
            f"drawdown gain {payload['drawdown_leg']['gain']:+.4f} "
            f"(required +0.02), cagr gap {payload['return_leg']['gap']:+.4f}, "
            f"turnover ratio {payload['turnover_leg']['ratio']:.3f}x"
        ),
        # 产生这条结论的代码。缺它时，同一份 spec 可以对应两套
        # 完全不同的 runner，而读者无从分辨哪一套跑出了这条结论。
        code_sha=payload["code_sha"],
    )
    print(f"decision={outcome}")
    print(f"s2_r1_reproduction_matches_frozen_targets={reproduction_ok}")
    print(comparison.to_csv(index=False))


if __name__ == "__main__":
    main()
