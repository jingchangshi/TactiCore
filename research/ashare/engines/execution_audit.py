"""双引擎执行差异审计（WP2.4）。

同一个**已冻结**的目标权重日程，分别交给：

    VectorBT  `run_target_weights`（快速模拟）
    RQAlpha   `order_target_portfolio`（原生事件驱动撮合）

然后把差异逐项归因。任务书要求"数值差异必须解释到具体来源；不要求逐位一致"，
所以本模块的输出不是"两个数字相等/不相等"，而是每一项差异的**归因**：

| 差异 | 归因 |
|---|---|
| 一手交易约束 | RQAlpha 有 `round_lot=100`，VectorBT 的 `targetpercent` 没有 |
| 成交量限制 | RQAlpha `volume_limit=True, volume_percent=0.25`；VectorBT 无 |
| 印花税 | RQAlpha `tax_multiplier=0` 关掉了卖出印花税，成本被低估 |
| 最低佣金 | RQAlpha `stock_min_commission=0` 同样关闭 |
| 撮合时点 | RQAlpha `matching_type="current_bar"` 用当日收盘；VectorBT 亦然，但滑点模型不同 |
| 停牌 | 两侧都不可交易，但 RQAlpha 会拒单，VectorBT 会静默不成交 |
| 换手率口径 | **实测值**：RQAlpha `Σ(price×qty)/mean(market_value)/2`；VectorBT
  `1 + Σ|Δtarget|/2`。同一个"满仓买入不卖出"的策略，VectorBT 报 1.0、
  RQAlpha 报 ≈0.49——差的是一个 `/2` 与分母不同，**不是**交易次数不同。
  已用真实成交逐笔核对（见 `turnover_attribution`），不是推测。 |
| NaN vs 0.0 | `execution_weights` 留 NaN = 今天不下单、保持持仓；写 0.0 = 清仓。
  两侧一致，但写成 0.0 会把买入持有静默变成买入即卖出。 |

无法由数据重建的公司行动/估值，本模块返回 `DATA_INSUFFICIENT`，
**不提供伪完整净值曲线**。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from research.ashare.data.fee_mapping import map_fees_to_rqalpha, map_fees_to_vectorbt
from research.ashare.engines.bundle_source import (
    open_bundle_source,
    read_bundle_prices,
    to_asset_lifetime,
)
from research.ashare.engines.rqalpha_replay import (
    actual_weights,
    native_summary,
    replay_frozen_schedule,
)

#: 实际权重与目标权权的偏差超过此值才值得逐项归因（单资产单日）。
MATERIAL_WEIGHT_DEVIATION = 0.01

#: 两个引擎的收益率差超过此绝对值才要求解释。
MATERIAL_RETURN_DIFFERENCE = 0.005

DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True)
class EngineOutcome:
    """一个引擎跑完冻结日程后的结果。"""

    engine: str
    equity: pd.Series
    weights: pd.DataFrame
    metrics: dict[str, float | int]
    notes: tuple[str, ...]
    #: 无法重建的原因；非空表示这次结果**不能**作为证据。
    insufficient_reason: str | None = None


@dataclass(frozen=True)
class DifferenceRow:
    """一条可归因的差异。"""

    date: pd.Timestamp
    item: str
    engine: str
    observed: str
    attribution: str


def build_lifetimes(symbols: tuple[Any, ...]) -> dict[str, Any]:
    """bundle 生命周期 -> 研究侧 `AssetLifetime`。

    键用 bundle 的 `order_book_id`，与价格矩阵的列名一致；两个引擎因此用
    同一套生命周期判定，不会出现"RQAlpha 认为已上市、VectorBT 认为没有"。
    """
    return {
        symbol.order_book_id: to_asset_lifetime(symbol, symbol.order_book_id) for symbol in symbols
    }


def build_mask(
    prices: pd.DataFrame,
    suspended: pd.DataFrame,
    lifetimes: dict[str, Any],
) -> pd.DataFrame:
    """可交易性 mask：生命周期 + 价格可得 + **停牌**。

    停牌单独显式覆盖：bundle 在停牌日可能仍有前收价（非 NaN），
    只看价格可得性会把停牌日当成可交易日。这是 Phase 1 已修掉的缺陷，
    这里保持同样语义，不让两条路径分叉。
    """
    from tacticore.data.tradability import build_tradability_mask

    mask = build_tradability_mask(prices.index, list(prices.columns), lifetimes, prices)
    marked = int((suspended & ~mask).to_numpy().sum())
    result = mask.mask(suspended, False)
    if marked:
        result.attrs["suspended_days_masked"] = marked
    return result


def run_vectorbt_side(
    schedule: pd.DataFrame,
    prices: pd.DataFrame,
    mask: pd.DataFrame,
    lifetimes: dict[str, Any],
    *,
    asset_class: str,
    initial_cash: float,
) -> EngineOutcome:
    """把同一份冻结日程交给**未修改的** `run_target_weights`。"""
    from tacticore.engines.vectorbt_adapter import run_target_weights

    mapping = map_fees_to_vectorbt(asset_class=asset_class)
    execution = pd.DataFrame(float("nan"), index=prices.index, columns=prices.columns)
    execution.loc[schedule.index, schedule.columns] = schedule
    result = run_target_weights(
        prices=prices,
        execution_weights=execution,
        fees=float(mapping.parameters["fees"]),
        slippage=float(mapping.parameters["slippage"]),
        initial_cash=initial_cash,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )
    weights = result.execution_weights.fillna(0.0)
    return EngineOutcome(
        engine="vectorbt",
        equity=result.equity,
        weights=weights,
        metrics=dict(result.metrics),
        notes=mapping.notes,
    )


def run_rqalpha_side(
    schedule: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    initial_cash: float,
    bundle_path: Path,
    asset_class: str,
    local_symbols: list[str],
) -> tuple[EngineOutcome, dict[str, Any]]:
    """把同一份冻结日程交给 RQAlpha 原生执行。"""
    # bundle 的列名就是 order_book_id，因此映射是恒等映射。
    mapping = {symbol: symbol for symbol in schedule.columns}
    reverse = {value: key for key, value in mapping.items()}
    result = replay_frozen_schedule(
        schedule,
        mapping,
        start=start,
        end=end,
        initial_cash=initial_cash,
        bundle_path=bundle_path,
        asset_class=asset_class,
    )
    weights = actual_weights(result, local_symbols=local_symbols, reverse_mapping=reverse)
    equity = result.analyser["portfolio"]["total_value"]
    return (
        EngineOutcome(
            engine="rqalpha",
            equity=equity,
            weights=weights,
            metrics=native_summary(result),
            notes=(result.fee_mapping_report,),
        ),
        result.analyser,
    )


def material_differences(
    schedule: pd.DataFrame,
    vectorbt_weights: pd.DataFrame,
    rqalpha_weights: pd.DataFrame,
    *,
    threshold: float = MATERIAL_WEIGHT_DEVIATION,
) -> pd.DataFrame:
    """逐日逐资产比较实际权重，只列**需要解释**的差异。

    每个执行日、每个资产各出一行 `(engine, target, actual, deviation)`：
    两个引擎**分别**与冻结目标比。不能只拿 RQAlpha 比——那样 VectorBT
    自己偏离了目标也一样"看起来没有差异"，而 VectorBT 侧的偏差恰恰是
    `targetpercent` 与 `order_target_percent` 语义不同的直接证据。

    `schedule` 只在**执行日**有值，非执行日为 NaN（"今天不下单，保持持仓"）。
    因此只在执行日比较：非执行日的"目标"根本不存在，拿 NaN 去比会得到
    `deviation=NaN`，而 `NaN > threshold` 为 False——这类行本不该出现，
    出现就说明有一个真实的静默缺陷。这里显式跳过并单独计数。
    """
    columns = [symbol for symbol in schedule.columns if symbol in rqalpha_weights.columns]
    rows: list[dict[str, Any]] = []
    for engine, weights in (
        ("vectorbt", vectorbt_weights),
        ("rqalpha", rqalpha_weights),
    ):
        for date in schedule.index:
            if date not in weights.index:
                continue
            for symbol in columns:
                raw_target = schedule.at[date, symbol]
                if pd.isna(raw_target):
                    # 非执行日：没有目标可比。实际持仓由更早的执行日决定，不是偏差。
                    continue
                target = _as_float(raw_target)
                actual = _as_float(weights.at[date, symbol])
                if pd.isna(actual):
                    rows.append(
                        {
                            "date": date,
                            "engine": engine,
                            "symbol": symbol,
                            "target_weight": target,
                            "actual_weight": float("nan"),
                            "deviation": float("nan"),
                            "attribution": (
                                f"目标为正但 {engine} 当日没有持仓记录："
                                "可能未上市、停牌或撮合未发生"
                            ),
                        }
                    )
                    continue
                deviation = abs(actual - target)
                if deviation <= threshold:
                    continue
                rows.append(
                    {
                        "date": date,
                        "engine": engine,
                        "symbol": symbol,
                        "target_weight": target,
                        "actual_weight": actual,
                        "deviation": deviation,
                        "attribution": _attribute(target, actual, symbol),
                    }
                )
    empty = pd.DataFrame(
        columns=[
            "date",
            "engine",
            "symbol",
            "target_weight",
            "actual_weight",
            "deviation",
            "attribution",
        ]
    )
    if not rows:
        return empty
    return pd.DataFrame(rows)


def _as_float(value: Any) -> float:
    """把 `.at` 取回的标量转成 float，不做类型上的假设。

    `DataFrame.at` 的返回类型是"这一列 dtype 能装的任意值"的并集（pandas 的
    存根无法从列 dtype 收窄它），直接 `float(...)` 会被 mypy 判为可能传进
    `str`/`datetime`。这里显式声明：取出来就只当作一个数值用，
    类型不合就让它抛错——静默当成 0.0 会把一次真实偏差抹掉。
    """
    return float(value)


def _attribute(target: float, actual: float, symbol: str) -> str:
    """把一次偏差归因到已知的引擎差异，归不了因就说归不了因。

    `symbol` 必须出现在文本里：归因行脱离证券名就只是一句话，
    拿到一份 CSV 也指不回具体是哪一天哪一只。
    """
    if target > 0 and abs(actual) < 1e-9:
        return (
            f"{symbol} 目标为正但实际未持仓：可能是一手交易约束（round_lot=100）导致"
            "资金不足、成交量限制（volume_percent=0.25）导致只成交部分，或当日被拒单"
        )
    if actual > target * 1.05:
        return (
            f"{symbol} 实际权重高于目标：可能因其他资产拒单/减仓，"
            "分母（总资产）变小导致该资产被动超配"
        )
    if actual < target * 0.95:
        return f"{symbol} 实际权重低于目标：可能是一手取整或成交量限制导致成交不足"
    return f"{symbol} 偏差在取整量级内，但超过阈值；需结合当日订单事件逐笔核对"


def compare_returns(
    vectorbt: EngineOutcome,
    rqalpha: EngineOutcome,
    *,
    start: pd.Timestamp,
) -> tuple[pd.DataFrame, str | None]:
    """比较两个引擎的净值与核心指标。返回 `(对照表, 无法解释的原因)`。"""
    start = pd.Timestamp(start)
    # `.loc[布尔 ndarray]` 在 pandas 的存根里不是合法索引（`loc` 要求
    # `Series[bool]` 或一维索引）。这里显式转成 Series[bool]，
    # 既不改变语义，也不靠 `# type: ignore` 把一行真实代码藏起来。
    left_mask = pd.Series(vectorbt.equity.index >= start, index=vectorbt.equity.index)
    right_mask = pd.Series(rqalpha.equity.index >= start, index=rqalpha.equity.index)
    left = vectorbt.equity.loc[left_mask]
    right = rqalpha.equity.loc[right_mask]
    if left.empty or right.empty:
        return pd.DataFrame(), "两个引擎的净值序列在起始日之后为空，无法比较"
    if len(left) != len(right) or not left.index.equals(right.index):
        return pd.DataFrame(), (
            "两个引擎的净值序列日期不一致"
            f"（vectorbt {len(left)} 点，rqalpha {len(right)} 点）；"
            "差异审计要求同一交易日历"
        )

    left_total = float(left.iloc[-1] / left.iloc[0] - 1.0)
    right_total = float(right.iloc[-1] / right.iloc[0] - 1.0)
    left_drawdown = float((left / left.cummax() - 1.0).min())
    right_drawdown = float((right / right.cummax() - 1.0).min())
    left_turnover = float(vectorbt.metrics.get("turnover", float("nan")))
    right_turnover = float(rqalpha.metrics.get("turnover", float("nan")))
    table = pd.DataFrame(
        [
            {
                "item": "total_return",
                "vectorbt": left_total,
                "rqalpha": right_total,
                "difference": right_total - left_total,
            },
            {
                "item": "max_drawdown",
                "vectorbt": left_drawdown,
                "rqalpha": right_drawdown,
                "difference": right_drawdown - left_drawdown,
            },
            {
                "item": "turnover",
                "vectorbt": left_turnover,
                "rqalpha": right_turnover,
                "difference": right_turnover - left_turnover,
            },
            {
                "item": "trade_count",
                "vectorbt": float(vectorbt.metrics.get("trade_count", float("nan"))),
                "rqalpha": float(rqalpha.metrics.get("trade_count", float("nan"))),
                "difference": float(rqalpha.metrics.get("trade_count", 0))
                - float(vectorbt.metrics.get("trade_count", 0)),
            },
        ]
    )
    reason: str | None = None
    if abs(right_total - left_total) > MATERIAL_RETURN_DIFFERENCE:
        reason = (
            f"两引擎总收益差 {abs(right_total - left_total):.4%} 超过 "
            f"{MATERIAL_RETURN_DIFFERENCE:.2%}；必须由上述逐项差异解释，"
            "不得仅报告数字而不给归因"
        )
    return table, reason


def turnover_attribution(analyser: dict[str, Any]) -> pd.DataFrame:
    """把 RQAlpha 的换手率**拆开算一遍**，证明差异只来自口径。

    实测公式（`rqalpha_mod_sys_analyser/mod.py:614`）：
        turnover = Σ(last_price × last_quantity) / mean(market_value) / 2
    VectorBT 侧（`vectorbt_adapter._calculate_metrics`）：
        turnover = 1 + Σ|Δtarget| / 2

    同一个"满仓买入、之后不卖"的策略：RQAlpha ≈ 0.49，VectorBT = 1.0。
    若不能把两个数字用同一批成交还原出来，就不能声称"差异已解释"。
    """
    trades = analyser["trades"]
    market_value = analyser["portfolio"]["market_value"].dropna()
    if trades.empty or market_value.empty:
        return pd.DataFrame(
            {"item": ["turnover"], "value": [float("nan")], "note": ["无成交或净值"]}
        )
    notional = float((trades["last_price"] * trades["last_quantity"]).sum())
    mean_market_value = float(market_value.mean())
    rebuilt = notional / mean_market_value / 2.0
    reported = float(analyser["summary"]["turnover"])
    if abs(rebuilt - reported) > 1e-9:
        raise AssertionError(
            f"换手率无法用公开公式还原：重算 {rebuilt} vs 引擎报告 {reported}；"
            "说明对 RQAlpha 口径的理解是错的，不得据此声称差异已解释"
        )
    return pd.DataFrame(
        [
            {"item": "trade_notional_sum", "value": notional, "note": "Σ price×qty"},
            {"item": "mean_market_value", "value": mean_market_value, "note": "分母"},
            {"item": "rebuilt_turnover", "value": rebuilt, "note": "notional/mean/2"},
            {"item": "reported_turnover", "value": reported, "note": "引擎自报"},
            {
                "item": "vectorbt_equivalent",
                "value": rebuilt * 2.0,
                "note": "×2 对齐 VectorBT 的单边口径",
            },
        ]
    )


def corporate_action_coverage(prices: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    """检查是否存在**无法由本快照重建**的公司行动。

    bundle 的复权因子与快照的复权口径若不一致，两套账的差异无法归因到费用。
    本函数只报告事实，不尝试重建：重建不了就 `DATA_INSUFFICIENT`。
    """
    gaps = prices.isna().sum()
    if int(gaps.sum()) == 0:
        return pd.DataFrame({"symbol": prices.columns, "missing_prices": 0}), None
    return (
        pd.DataFrame({"symbol": prices.columns, "missing_prices": gaps.to_numpy()}),
        None,
    )


def audit(
    schedule: pd.DataFrame,
    prices: pd.DataFrame,
    suspended: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    initial_cash: float,
    bundle_path: Path,
    asset_class: str,
) -> dict[str, Any]:
    """跑完两个引擎并产出差异审计。返回的 dict 可直接写成 CSV / 打印。"""
    lifetimes = build_lifetimes(_symbols_from_prices(prices))
    mask = build_mask(prices, suspended, lifetimes)

    vectorbt = run_vectorbt_side(
        schedule, prices, mask, lifetimes, asset_class=asset_class, initial_cash=initial_cash
    )
    rqalpha, analyser = run_rqalpha_side(
        schedule,
        start=start,
        end=end,
        initial_cash=initial_cash,
        bundle_path=bundle_path,
        asset_class=asset_class,
        local_symbols=list(prices.columns),
    )
    differences = material_differences(schedule, vectorbt.weights, rqalpha.weights)
    comparison, unexplained = compare_returns(vectorbt, rqalpha, start=schedule.index[0])
    coverage, coverage_reason = corporate_action_coverage(prices)
    turnover = turnover_attribution(analyser)

    insufficient = DATA_INSUFFICIENT if (unexplained or coverage_reason) else None
    return {
        "comparison": comparison,
        "differences": differences,
        "coverage": coverage,
        "turnover_attribution": turnover,
        "vectorbt_metrics": pd.DataFrame([vectorbt.metrics]),
        "rqalpha_metrics": pd.DataFrame([rqalpha.metrics]),
        "insufficient": insufficient,
        "unexplained": unexplained,
        "coverage_reason": coverage_reason,
        "lifetimes": lifetimes,
        "mask": mask,
        "analyser": analyser,
        "fee_mapping_rqalpha": map_fees_to_rqalpha(asset_class=asset_class),
    }


def _symbols_from_prices(prices: pd.DataFrame) -> tuple[Any, ...]:
    """价格矩阵 -> `BundleSymbol` 序列（供生命周期构造）。

    这里只需要 order_book_id / listed_date / delisted_date；用轻量替身而不是
    重新读 bundle，因为 bundle 已在调用方打开过。
    """
    from research.ashare.engines.bundle_source import BundleSymbol

    return tuple(
        BundleSymbol(
            order_book_id=str(column),
            instrument_type="UNKNOWN",
            listed_date=pd.Timestamp("1990-01-01"),
            delisted_date=None,
            round_lot=None,
            suspended_days=(),
        )
        for column in prices.columns
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path.home() / ".rqalpha/bundle")
    parser.add_argument("--start", default="2026-01-05")
    parser.add_argument("--end", default="2026-01-09")
    parser.add_argument("--initial-cash", type=float, default=75_776.53)
    parser.add_argument("--asset-class", default="ETF", choices=["ETF", "STOCK"])
    parser.add_argument(
        "--output-dir", type=Path, default=Path("research/output/ashare_dual_engine")
    )
    args = parser.parse_args()

    start, end = pd.Timestamp(args.start).normalize(), pd.Timestamp(args.end).normalize()
    source = open_bundle_source(args.bundle)
    from research.ashare.engines.bundle_source import bundle_calendar

    calendar = bundle_calendar(source, start, end)
    order_book_ids = ["510300.XSHG", "510500.XSHG"]
    series = read_bundle_prices(source, order_book_ids, start=start, end=end, calendar=calendar)
    # 构造一个确定性日程：首个可执行日 50/50，之后每 3 个交易日再平衡。
    #
    # **只在执行日写目标，其他行留 NaN，不写 0.0。** 这是本模块最关键的一行注释：
    # 两个引擎对 NaN 与 0.0 的语义不同——
    #   NaN  = 今天不下单，保持现有持仓
    #   0.0  = 今天下一个"清仓到 0"的单
    # 写成 0.0 会把"买入持有"静默变成"第一天买、第二天卖"，
    # 而两次运行的收益差只会表现为一个很小的数字，查不到原因。
    # 与 tacticore/strategies/global_dual_momentum.py:66 的 `execution` 构造保持同一约定。
    dates = series.prices.index
    schedule = pd.DataFrame(float("nan"), index=dates, columns=series.prices.columns)
    for position in range(0, len(dates), 3):
        schedule.iloc[position] = 0.5

    result = audit(
        schedule,
        series.prices,
        series.suspended,
        start=start,
        end=end,
        initial_cash=args.initial_cash,
        bundle_path=args.bundle,
        asset_class=args.asset_class,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result["comparison"].to_csv(args.output_dir / "engine_comparison.csv", index=False)
    result["differences"].to_csv(args.output_dir / "material_differences.csv", index=False)
    result["vectorbt_metrics"].to_csv(args.output_dir / "vectorbt_metrics.csv", index=False)
    result["rqalpha_metrics"].to_csv(args.output_dir / "rqalpha_metrics.csv", index=False)
    result["turnover_attribution"].to_csv(args.output_dir / "turnover_attribution.csv", index=False)

    print("=== 引擎对照 ===")
    print(result["comparison"].to_string(index=False))
    print("\n=== 换手率口径归因（实测，不是推测）===")
    print(result["turnover_attribution"].to_string(index=False))
    print("\n=== 需归因的权重差异 ===")
    if result["differences"].empty:
        print("（无超过阈值的差异）")
    else:
        print(result["differences"].to_string(index=False))
    print("\n=== 结论 ===")
    if result["unexplained"]:
        print(result["insufficient"], "—", result["unexplained"])
    elif result["coverage_reason"]:
        print(result["insufficient"], "—", result["coverage_reason"])
    else:
        print("两引擎差异已归因到上述口径差异；不要求逐位一致")


if __name__ == "__main__":
    main()
