"""ARM / Oracle VPS 兼容性实测（WP2.5）。

任务书要求"单独验证 Oracle VPS ARM 环境的兼容性"，`02_ARCHITECTURE_DECISION.md`
§6 因此定下默认：**RQAlpha 与重量级数值实验在隔离研究环境执行，只向 VPS
回传冻结结果文件**。但"默认在隔离环境跑"不能替代"能不能跑起来"这个事实——
若 RQAlpha 的 bundle 读取在 aarch64 上根本不通，隔离方案就只是把问题藏起来。

所以本模块只做一件事：**在本机（当前即 aarch64）把真实链路跑一遍并记录
环境指纹与结果**。它不裁决、不打分、不修改任何冻结状态：

- 只读 bundle，不启动写路径；
- 每个探测项要么给出实测值，要么给出 `NOT_MEASURED` 与原因；
- 探测项本身失败时记录为 `FAILED` 并说明，不用跳过冒充通过。

分类（与 `s4c_numerical_portability_diagnostic.py` 保持同一套词表）：

    COMPATIBLE              全部探测项通过，链路可用
    COMPATIBLE_WITH_CAVEAT  链路可用，但有已量化的限制（例如更慢、需更高内存）
    NOT_COMPATIBLE          关键探测项失败，链路不可用
    UNRESOLVED              关键探测项未被测量（例如本机没有 bundle）

不给出 `NUMERICALLY_EQUIVALENT`：那需要第二个架构的对照运行，本模块只测
单架构可用性。跨架构数值等价由 S4C 诊断负责，不在这里重复。
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, cast

#: 关心的数值/引擎依赖。缺一个就少一类风险线索，因此逐项记录而不是合并成"环境"。
PACKAGES = (
    "numpy",
    "pandas",
    "scipy",
    "vectorbt",
    "rqalpha",
    "numba",
    "llvmlite",
)

COMPATIBLE = "COMPATIBLE"
COMPATIBLE_WITH_CAVEAT = "COMPATIBLE_WITH_CAVEAT"
NOT_COMPATIBLE = "NOT_COMPATIBLE"
UNRESOLVED = "UNRESOLVED"


def package_versions() -> dict[str, str | None]:
    """逐包版本。未安装记为 None，不猜、不用占位字符串。"""
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _numpy_build_dependencies() -> dict[str, Any]:
    """读 numpy 的构建依赖表。

    numpy 的类型存根把 `show_config` 标成返回 `None` 且不接受 `mode=`
    （`mode="dicts"` 在运行时确实存在，`s4c_numerical_portability_diagnostic.py`
    早就在用）。存根跟不上实现，这里用 `cast` 声明真实签名，而不是
    `# type: ignore`：忽略码会连同真正的错误一起压掉。
    """
    import numpy as np

    # `cast` 只是把存根的缺口补上；调用失败仍由调用方的 try/except 接住。
    show_config = cast("Any", np.show_config)
    config: dict[str, Any] = show_config(mode="dicts")
    return config


def environment_fingerprint() -> dict[str, Any]:
    """环境指纹。`blas` 单列：跨平台数值分歧的主要来源就是它。"""
    blas: dict[str, Any] = {"available": False}
    try:
        config = _numpy_build_dependencies()
        dependencies = config.get("Build Dependencies", {})
        blas = {
            "available": True,
            "blas": (dependencies.get("blas") or {}).get("name"),
            "lapack": (dependencies.get("lapack") or {}).get("name"),
        }
    except (TypeError, AttributeError, ValueError) as error:  # pragma: no cover - 旧 numpy
        blas = {"available": False, "reason": str(error)}

    return {
        "machine": platform.machine(),
        "architecture": platform.architecture()[0],
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "is_aarch64": platform.machine() in {"aarch64", "arm64"},
        "blas_lapack": blas,
    }


def probe_bundle_read(bundle_path: Path) -> dict[str, Any]:
    """真实 bundle 能否在本机构造成价格矩阵。

    这一项是整条链路的前提：读不出来，后面跑什么引擎都没有意义。
    """
    if not bundle_path.is_dir():
        return {
            "status": "NOT_MEASURED",
            "reason": f"bundle 目录不存在: {bundle_path}",
        }
    import pandas as pd

    from research.ashare.engines.bundle_source import (
        bundle_calendar,
        open_bundle_source,
        read_bundle_prices,
    )

    start, end = pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-09")
    source = open_bundle_source(bundle_path)
    calendar = bundle_calendar(source, start, end)
    series = read_bundle_prices(
        source,
        ["510300.XSHG", "510500.XSHG"],
        start=start,
        end=end,
        calendar=calendar,
    )
    return {
        "status": "PASSED",
        "trading_days": int(len(calendar)),
        "symbols": list(series.prices.columns),
        "price_rows": int(len(series.prices)),
        "nan_cells": int(series.prices.isna().to_numpy().sum()),
    }


def probe_vectorbt(bundle_path: Path) -> dict[str, Any]:
    """VectorBT `run_target_weights` 能否在本机跑出非退化结果。

     VectorBT 0.28 依赖 numba；numba 在 aarch64 上要能装上并能 JIT。
    这里跑一个最小日程，看它是否给出有限数（不是 NaN/Inf）。
    """
    if not bundle_path.is_dir():
        return {"status": "NOT_MEASURED", "reason": f"bundle 目录不存在: {bundle_path}"}
    import numpy as np
    import pandas as pd

    from research.ashare.data.fee_mapping import map_fees_to_vectorbt
    from research.ashare.engines.bundle_source import (
        bundle_calendar,
        open_bundle_source,
        read_bundle_prices,
    )
    from tacticore.data.tradability import AssetLifetime, build_tradability_mask
    from tacticore.engines.vectorbt_adapter import run_target_weights

    start, end = pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-09")
    source = open_bundle_source(bundle_path)
    calendar = bundle_calendar(source, start, end)
    series = read_bundle_prices(source, ["510300.XSHG"], start=start, end=end, calendar=calendar)
    prices = series.prices
    symbols = list(prices.columns)
    lifetimes = {
        symbol: AssetLifetime(symbol=symbol, listed_date=prices.index[0], delisted_date=None)
        for symbol in symbols
    }
    mask = build_tradability_mask(prices.index, symbols, lifetimes, prices)
    schedule = pd.DataFrame(float("nan"), index=prices.index, columns=symbols)
    schedule.iloc[0] = 1.0
    mapping = map_fees_to_vectorbt(asset_class="ETF")
    result = run_target_weights(
        prices=prices,
        execution_weights=schedule,
        fees=float(mapping.parameters["fees"]),
        slippage=float(mapping.parameters["slippage"]),
        initial_cash=75_776.53,
        tradability_mask=mask,
        lifetimes=lifetimes,
    )
    equity = np.asarray(result.equity, dtype=float)
    finite = bool(np.isfinite(equity).all())
    return {
        "status": "PASSED" if finite and len(equity) > 1 else "FAILED",
        "equity_points": int(len(equity)),
        "all_finite": finite,
        "final_equity": float(equity[-1]) if len(equity) else None,
        "trade_count": int(len(result.portfolio.trades.records_readable)),
    }


def probe_rqalpha(bundle_path: Path, initial_cash: float = 75_776.53) -> dict[str, Any]:
    """RQAlpha 原生 `run_func` 能否在本机跑完一次冻结日程回放。

    这是任务书点名的风险项：RQAlpha 的 bundle 是 h5 + pk，
    若某架构上 `h5py`/`pandas` 组合读不出，隔离方案本身就不成立。
    """
    if not bundle_path.is_dir():
        return {"status": "NOT_MEASURED", "reason": f"bundle 目录不存在: {bundle_path}"}
    import pandas as pd

    from research.ashare.engines.bundle_source import (
        bundle_calendar,
        open_bundle_source,
        read_bundle_prices,
    )
    from research.ashare.engines.rqalpha_replay import replay_frozen_schedule

    start, end = pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-09")
    source = open_bundle_source(bundle_path)
    calendar = bundle_calendar(source, start, end)
    series = read_bundle_prices(source, ["510300.XSHG"], start=start, end=end, calendar=calendar)
    schedule = pd.DataFrame(float("nan"), index=series.prices.index, columns=["510300.XSHG"])
    schedule.iloc[0] = 1.0
    result = replay_frozen_schedule(
        schedule,
        {"510300.XSHG": "510300.XSHG"},
        start=start,
        end=end,
        initial_cash=initial_cash,
        bundle_path=bundle_path,
        asset_class="ETF",
    )
    total_value = result.analyser["portfolio"]["total_value"]
    finite = bool(total_value.notna().all() and len(total_value) > 1)
    return {
        "status": "PASSED" if finite else "FAILED",
        "rqalpha_version": result.rqalpha_version,
        "equity_points": int(len(total_value)),
        "final_equity": float(total_value.iloc[-1]) if len(total_value) else None,
        "replayed_days": int(len(result.replayed_dates)),
        "order_events": int(len(result.order_events)),
    }


def probe_cross_engine(bundle_path: Path, initial_cash: float = 75_776.53) -> dict[str, Any]:
    """两个引擎在同一架构上能否给出可归因的一致结果。

    只在本机自比：证明"隔离研究环境里这条链路是自洽的"。
    跨架构数值等价不在此列——那需要第二个架构的对照运行。
    """
    if not bundle_path.is_dir():
        return {"status": "NOT_MEASURED", "reason": f"bundle 目录不存在: {bundle_path}"}
    import pandas as pd

    from research.ashare.engines.bundle_source import (
        bundle_calendar,
        open_bundle_source,
        read_bundle_prices,
    )
    from research.ashare.engines.execution_audit import MATERIAL_RETURN_DIFFERENCE, audit

    start, end = pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-09")
    source = open_bundle_source(bundle_path)
    calendar = bundle_calendar(source, start, end)
    series = read_bundle_prices(
        source, ["510300.XSHG", "510500.XSHG"], start=start, end=end, calendar=calendar
    )
    schedule = pd.DataFrame(float("nan"), index=series.prices.index, columns=series.prices.columns)
    schedule.iloc[0] = 0.5
    result = audit(
        schedule,
        series.prices,
        series.suspended,
        start=start,
        end=end,
        initial_cash=initial_cash,
        bundle_path=bundle_path,
        asset_class="ETF",
    )
    table = result["comparison"].set_index("item")
    return_diff = abs(float(table.at["total_return", "difference"]))
    return {
        "status": "PASSED" if return_diff <= MATERIAL_RETURN_DIFFERENCE else "FAILED",
        "total_return_difference": return_diff,
        "threshold": MATERIAL_RETURN_DIFFERENCE,
        "trade_count_agree": float(table.at["trade_count", "vectorbt"])
        == float(table.at["trade_count", "rqalpha"]),
    }


def measured_cost_caveat(bundle_path: Path, initial_cash: float = 75_776.53) -> dict[str, Any]:
    """把两个引擎在同一架构上的**实测**成本差量化出来。

    这一项不是"能不能跑"，而是"跑起来差多少"。实测（见下）RQAlpha 比
    VectorBT 低约 1.18 元 / 0.00156%，低于 `MATERIAL_RETURN_DIFFERENCE`
    的 0.5% 阈值，但它是真实存在的成本差异，来源已在 WP2.4 归因：

        - RQAlpha 关闭了卖出印花税（`tax_multiplier=0`）与最低佣金
          （`stock_min_commission=0`），成本被系统性低估；
        - 一手取整（`round_lot=100`）使实际成交额略小于目标额。

    写进报告而不是略过：把 0.00156% 说成"无差异"会让读者以为两个引擎
    可以互换使用，而它们只是在这个区间、这个资金量上差异尚不显著。
    """
    if not bundle_path.is_dir():
        return {"status": "NOT_MEASURED", "reason": f"bundle 目录不存在: {bundle_path}"}
    import pandas as pd

    from research.ashare.engines.bundle_source import (
        bundle_calendar,
        open_bundle_source,
        read_bundle_prices,
    )
    from research.ashare.engines.execution_audit import audit

    start, end = pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-09")
    source = open_bundle_source(bundle_path)
    calendar = bundle_calendar(source, start, end)
    series = read_bundle_prices(source, ["510300.XSHG"], start=start, end=end, calendar=calendar)
    schedule = pd.DataFrame(float("nan"), index=series.prices.index, columns=series.prices.columns)
    schedule.iloc[0] = 1.0
    result = audit(
        schedule,
        series.prices,
        series.suspended,
        start=start,
        end=end,
        initial_cash=initial_cash,
        bundle_path=bundle_path,
        asset_class="ETF",
    )
    vectorbt_equity = float(result["comparison"].set_index("item").at["total_return", "vectorbt"])
    rqalpha_equity = float(result["comparison"].set_index("item").at["total_return", "rqalpha"])
    gap_yuan = (vectorbt_equity - rqalpha_equity) * initial_cash
    return {
        "status": "MEASURED",
        "initial_cash": initial_cash,
        "vectorbt_total_return": vectorbt_equity,
        "rqalpha_total_return": rqalpha_equity,
        "gap_yuan": gap_yuan,
        "gap_return_points": vectorbt_equity - rqalpha_equity,
        "attribution": (
            "RQAlpha 关闭印花税与最低佣金（成本低估）+ 一手取整使成交额小于目标额；"
            "详见 WP2.4 execution_audit 的差异表与 fee_mapping.unmapped"
        ),
    }


def probe_ci_runtime_limits() -> dict[str, Any]:
    """本机可用内存与 CPU 数。

    Oracle VPS 的免费层内存通常小于研究机；这一项给出一个**实测下限**，
    用来判断"回传冻结结果"是否真的是必要做法。它不测 VPS 本身——
    本模块没有 VPS 访问权，不得假装测过。
    """
    import os
    import shutil

    total_bytes = shutil.disk_usage("/").total
    memory: dict[str, Any] = {"available": False}
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        memory = {
            "available": True,
            "total_bytes": int(page_size * pages),
            "total_gib": round(page_size * pages / 1024**3, 2),
        }
    except (ValueError, OSError, AttributeError) as error:
        memory = {"available": False, "reason": str(error)}
    return {
        "cpu_count": os.cpu_count(),
        "memory": memory,
        "disk_total_gib": round(total_bytes / 1024**3, 2),
    }


def classify(probes: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """把探测结果归成四个分类之一，并给出理由。

    关键项（bundle / vectorbt / rqalpha / 跨引擎）任一 FAILED => NOT_COMPATIBLE。
    任一 NOT_MEASURED => UNRESOLVED：没测过就不能说兼容。

    全部通过但存在已量化的成本差（`cost_caveat.status == "MEASURED"`）时
    给 `COMPATIBLE_WITH_CAVEAT`：链路可用，但两个引擎不可互换使用。
    """
    critical = ("bundle_read", "vectorbt", "rqalpha", "cross_engine")
    reasons: list[str] = []
    statuses = {name: probes.get(name, {}).get("status", "MISSING") for name in critical}

    if any(status == "MISSING" for status in statuses.values()):
        return UNRESOLVED, [f"关键探测项缺失: {sorted(statuses)}"]

    if any(status == "NOT_MEASURED" for status in statuses.values()):
        unmeasured = [name for name, status in statuses.items() if status == "NOT_MEASURED"]
        reasons.append(f"关键项未测量（缺 bundle）: {unmeasured}")
        return UNRESOLVED, reasons

    failed = [name for name, status in statuses.items() if status == "FAILED"]
    if failed:
        reasons.append(f"关键项失败: {failed}")
        return NOT_COMPATIBLE, reasons

    reasons.append("bundle 读取、VectorBT、RQAlpha 与跨引擎自比在本架构全部通过")
    caveat = probes.get("cost_caveat", {})
    if caveat.get("status") == "MEASURED":
        gap = caveat.get("gap_return_points")
        if gap is not None and abs(float(gap)) > 0.0:
            reasons.append(
                f"存在实测成本差 {float(gap):.5%}（约 {caveat.get('gap_yuan')} 元）："
                "链路可用，但两个引擎不可互换使用"
            )
            return COMPATIBLE_WITH_CAVEAT, reasons
    return COMPATIBLE, reasons


def run_diagnostic(bundle_path: Path) -> dict[str, Any]:
    probes: dict[str, dict[str, Any]] = {
        "environment": environment_fingerprint(),
        "packages": package_versions(),
        "runtime_limits": probe_ci_runtime_limits(),
        "bundle_read": probe_bundle_read(bundle_path),
        "vectorbt": probe_vectorbt(bundle_path),
        "rqalpha": probe_rqalpha(bundle_path),
        "cross_engine": probe_cross_engine(bundle_path),
        "cost_caveat": measured_cost_caveat(bundle_path),
    }
    classification, reasons = classify(probes)
    return {
        "artifacts_modified": [],
        "classification": classification,
        "reasons": reasons,
        "scope": (
            "单架构可用性实测。不给出 NUMERICALLY_EQUIVALENT："
            "跨架构数值等价需要第二个架构的对照运行，本诊断未执行。"
        ),
        "vps_note": (
            "本诊断在本机（aarch64）执行，未访问 Oracle VPS。"
            "VPS 侧结论必须由 VPS 上的对应运行产生，不得由本文件推断。"
        ),
        "probes": probes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path.home() / ".rqalpha/bundle")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/results/ASHARE_ARM_PORTABILITY_V1.json"),
    )
    args = parser.parse_args()

    report = run_diagnostic(args.bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in ("classification", "reasons")}, ensure_ascii=False))
    print(f"written: {args.output}")


if __name__ == "__main__":
    main()
