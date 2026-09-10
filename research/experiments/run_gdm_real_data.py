#!/usr/bin/env python3
"""在冻结的 Tushare canonical 数据上运行基线和四点回看期比较。"""

import hashlib
import json
from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import run_vectorbt
from tacticore.strategies.global_dual_momentum import (
    build_execution_weights,
    build_month_end_targets,
    load_strategy_config,
)

ROOT = Path(__file__).resolve().parents[2]
LOOKBACKS = (80, 120, 160, 252)
METRIC_NAMES = (
    "cagr",
    "max_drawdown",
    "sharpe",
    "calmar",
    "turnover",
    "trade_count",
    "average_holding_days",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_manifest(prices_path: Path, manifest: dict[str, Any]) -> None:
    recorded = manifest["files"][prices_path.name]["sha256"]
    if _sha256(prices_path) != recorded:
        raise ValueError("canonical 价格文件与来源清单中的 SHA-256 不一致")


def _format_metric(name: str, value: float) -> str:
    if name in {"cagr", "max_drawdown"}:
        return f"{value:.2%}"
    if name in {"turnover", "trade_count", "average_holding_days"}:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _yes(value: bool) -> str:
    return "是" if value else "否"


def _build_report(
    baseline: dict[str, float],
    sweep: pd.DataFrame,
    manifest: dict[str, Any],
    evaluation_start: pd.Timestamp,
    first_execution: pd.Timestamp,
    evaluation_end: pd.Timestamp,
) -> str:
    quality = manifest["quality_checks"]
    symbol_quality = quality["逐标的结果"]
    post_listing_missing = sum(item["上市后区间缺失观测"] for item in symbol_quality.values())
    cagr_signs = "均为正" if (sweep["cagr"] > 0).all() else "并非全部为正"
    metric_rows = "\n".join(
        f"| {name} | {_format_metric(name, baseline[name])} |" for name in METRIC_NAMES
    )
    sweep_rows = "\n".join(
        "| {lookback:.0f} | {cagr:.2%} | {max_drawdown:.2%} | {sharpe:.3f} | "
        "{calmar:.3f} | {turnover:.2f} | {trade_count:.0f} | "
        "{average_holding_days:.2f} |".format(**row)
        for row in sweep.reset_index().to_dict(orient="records")
    )
    return f"""# 全球双动量真实数据研究结果

## 执行摘要

本报告使用 Tushare Pro 场内 ETF 后复权收盘价验证当前 S1 基线。指标区间为
{evaluation_start.date()} 至 {evaluation_end.date()}，首个可执行信号日为
{first_execution.date()}。252 日基线的 CAGR 为
{baseline["cagr"]:.2%}，最大回撤为 {baseline["max_drawdown"]:.2%}。这些结果是历史研究证据，
不是未来收益承诺，也不足以将策略升级为生产候选。

## 基线指标

| 指标 | 结果 |
| --- | ---: |
{metric_rows}

换手率为评价期内累计单边换手；交易次数为 VectorBT 资产级交易记录数；平均持有期按评价期内
交易记录计算。指标从首笔执行前一个交易日的组合价值开始，因此包含首笔交易成本，同时排除
252 日预热期的空仓时间。

## 回看期稳定性准备

本次只比较目标指定的 80、120、160 和 252 个交易日，不搜索最优点。四组结果使用同一个
评价起点，以避免短回看期因更早开始交易而获得不可比样本。

| 回看期 | CAGR | 最大回撤 | Sharpe | Calmar | 累计单边换手 | 交易次数 | 平均持有天数 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{sweep_rows}

四个回看期的 CAGR {cagr_signs}；CAGR 区间为 {sweep["cagr"].min():.2%} 至
{sweep["cagr"].max():.2%}，最大回撤区间为 {sweep["max_drawdown"].min():.2%} 至
{sweep["max_drawdown"].max():.2%}。这只是参数稳定性预检，不是参数优化结论。

## 策略假设

- 基线使用 252 个交易日总收益动量，绝对动量必须大于 0；
- 合格风险资产按同一动量降序排列，等权持有前 2 名；
- 没有合格风险资产时持有 `511010.SS` 国债 ETF 代理；
- 月末收盘生成信号，下一交易日按目标权重执行；
- 每笔订单费率 10 个基点，滑点 5 个基点；
- 标的按各自上市日期进入可选范围，缺失动量的标的不参与排名。

## 数据假设与质量检查

- 来源：Tushare Pro `fund_daily`、`fund_adj`、`trade_cal` 和 `fund_basic`；
- 数据请求区间：{manifest["start_date"]} 至 {manifest["end_date"]}；
- 复权口径：{manifest["adjustment_type"]}；
- 原始收盘价与同日复权因子一对一合并，不向前填充、不猜测、不将未知值置零；
- 日期唯一且递增：{_yes(quality["日期唯一且递增"])}；
- 有效价格均为正数：{_yes(quality["有效价格均为正数"])}；
- 行情日期均属于对应交易所交易日：{_yes(quality["行情日期均属于对应交易所交易日"])}；
- 上市后区间共有 {post_listing_missing} 个交易日无行情，原样保留为缺失值。

后复权采用“原始收盘价 × 当日复权因子”，其收益率包含 Tushare 因子表达的分红再投资效果。
选择后复权而非以查询截止日归一化的前复权，是为了避免仅因延长下载截止日而整体重缩放历史价格。

## 策略解释

结果表明当前透明基线在这组可交易研究代理和历史区间上能够产生正的长期收益，但回撤仍然显著，
不能只凭 CAGR 判断策略成立。四点参数比较用于观察邻近时间尺度是否完全失效；它不能替代滚动前推、
样本外和交易成本敏感性验证。

## 局限

- 当前标的池由现有 ETF 构成，存在上市时间不同、幸存者偏差和事后选择偏差；
- QDII ETF 的人民币场内价格同时受时区、汇率、额度、溢折价和跟踪误差影响；
- 少量停牌或源数据缺口保持为缺失值，其经济原因未逐笔归因；
- Tushare 可能修订历史行情或复权因子；本仓库以文件哈希冻结本次快照；
- 尚未完成滚动前推、样本外、市场状态和交易成本敏感性检验；
- 本机没有 RQAlpha 中国市场数据包，因此尚无事件驱动回测结果。

## 研究结论

本轮已从“研究管线可运行”推进到“存在真实市场历史证据”。证据支持继续验证 S1，但尚不支持生产使用。
下一项唯一推荐方向是：在不增加策略数量的前提下，对 S1 完成滚动前推、样本外和交易成本敏感性验证。
"""


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prices",
        type=Path,
        default=ROOT / "data/canonical/etf_adjusted_close.csv",
        help="canonical 后复权收盘价",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "data/canonical/provenance.json",
        help="数据来源清单",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "research/results",
        help="研究结果输出目录",
    )
    args = parser.parse_args()

    prices = load_price_csv(args.prices)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    _verify_manifest(args.prices, manifest)
    config = load_strategy_config(ROOT / "config/strategy.toml")
    required = set(config.risk_symbols) | {config.fallback_symbol}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"canonical 数据缺少策略资产: {sorted(missing)}")

    baseline_targets = build_month_end_targets(prices, config)
    baseline_executions = build_execution_weights(prices, baseline_targets).dropna(how="all")
    if baseline_executions.empty:
        raise ValueError("真实价格区间不足以生成 252 日可执行信号")
    first_execution = baseline_executions.index[0]
    first_execution_location = int(prices.index.get_indexer(pd.Index([first_execution]))[0])
    evaluation_start = prices.index[max(first_execution_location - 1, 0)]

    rows: list[dict[str, float]] = []
    for lookback in LOOKBACKS:
        result = run_vectorbt(
            prices,
            replace(config, lookback_trading_days=lookback),
            metric_start=evaluation_start,
        )
        rows.append({"lookback": float(lookback), **result.metrics})
    sweep = pd.DataFrame(rows).set_index("lookback")
    baseline = sweep.loc[float(config.lookback_trading_days)].to_dict()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sweep.to_csv(
        args.output_dir / "gdm_lookback_sweep.csv",
        float_format="%.8f",
        lineterminator="\n",
    )
    result_payload = {
        "strategy": "Global Dual Momentum",
        "data_source": "Tushare Pro canonical ETF adjusted close",
        "data_sha256": manifest["files"][args.prices.name]["sha256"],
        "evaluation_start": evaluation_start.date().isoformat(),
        "first_execution": first_execution.date().isoformat(),
        "evaluation_end": prices.index.max().date().isoformat(),
        "baseline_lookback": config.lookback_trading_days,
        "metrics": baseline,
    }
    (args.output_dir / "gdm_baseline_metrics.json").write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = _build_report(
        baseline, sweep, manifest, evaluation_start, first_execution, prices.index.max()
    )
    (args.output_dir / "GDM_REAL_DATA_RESEARCH.md").write_text(report, encoding="utf-8")

    print(f"指标区间: {evaluation_start.date()} 至 {prices.index.max().date()}")
    print(f"首个执行日: {first_execution.date()}")
    for name in METRIC_NAMES:
        print(f"{name}: {baseline[name]:.6f}")
    print(f"研究结果已写入 {args.output_dir}")


if __name__ == "__main__":
    main()
