#!/usr/bin/env python3
"""把一个 as-of 市场快照冻结成 candidate-specific 前瞻 vintage。

这是**极薄的编排层**：它不实现下载、复权、规范化或版本数据库，只复用既有的
`download_tushare_dataset` / `write_tushare_dataset`，把结果写到候选 canonical vintage
目录，并立即用与 decision 路径相同的 provenance 校验证明该 vintage 是真实且可验证的。
它不实现 scheduler、daemon、provider abstraction 或通用数据快照服务。

本工具在真实数据缺失/不一致时 fail closed：不覆盖既有 evidence，也不留下半成品目录。

Production 路径只有 `candidate + --as-of + TUSHARE_TOKEN`：universe 与下载起点都来自
manifest-hash-bound 的 repository 冻结契约，不暴露任何 universe / start-date 覆盖。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path

import pandas as pd

from research.experiments.prospective_evidence import (
    REQUIRED_VINTAGE_FILES,
    UNIVERSE_RELATIVE_PATH,
    load_calendar,
    load_frozen_universe,
    load_prospective_vintage,
    sha256_file,
    verify_canonical_vintage_location,
)
from tacticore.data.prices import load_price_csv
from tacticore.data.tushare import (
    ADJUSTMENT_TYPE,
    SOURCE,
    download_tushare_dataset,
    write_tushare_dataset,
)
from tacticore.data.universe import load_universe

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = {
    "S2_R1": "research/shadow/s2_r1",
    "S4C_R1": "research/shadow/s4c_r1",
}


def candidate_manifest(relative_shadow_dir: str, root: Path = ROOT) -> dict[str, object]:
    path = root / relative_shadow_dir / "candidate_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_vintage(
    api: object,
    *,
    candidate_id: str,
    as_of: object,
    root: Path = ROOT,
    downloaded_at: str | None = None,
) -> Path:
    """下载并冻结一个 candidate-specific vintage，返回其 canonical 目录。

    universe 身份与 canonical 下载起点只能来自 repository 冻结契约：
    `config/universe.csv` 与 `data/canonical/provenance.json`。没有第二生产入口。
    `downloaded_at` 只是 `tmp_path` fixture 的 dependency injection：生产 CLI 不暴露它，
    生产 snapshot 的 download_timestamp 只能来自真实下载完成时刻。
    """
    if candidate_id not in CANDIDATES:
        raise ValueError(f"未知 candidate: {candidate_id}")
    shadow_dir = root / CANDIDATES[candidate_id]
    manifest = candidate_manifest(CANDIDATES[candidate_id], root)
    as_of_day = pd.Timestamp(as_of).normalize()
    cutoff = pd.Timestamp(str(manifest["historical_cutoff"])).normalize()
    if as_of_day <= cutoff:
        raise ValueError("prospective --as-of 必须严格晚于 historical_cutoff")
    canonical_parent = shadow_dir / "vintages"
    destination = verify_canonical_vintage_location(
        canonical_parent / as_of_day.date().isoformat(),
        as_of_day,
        canonical_parent=canonical_parent,
    )
    if destination.exists():
        raise ValueError(
            "candidate vintage 目录已存在，拒绝覆盖既有 evidence: "
            f"{destination.relative_to(root).as_posix()}"
        )
    universe = load_universe(root / UNIVERSE_RELATIVE_PATH)
    frozen_universe = load_frozen_universe(root, universe=universe)
    dataset = download_tushare_dataset(
        api,
        universe,
        frozen_universe.start_date,
        as_of_day.strftime("%Y%m%d"),
        downloaded_at=downloaded_at,
    )
    dataset = replace(
        dataset, provenance={**dataset.provenance, "universe": frozen_universe.identity()}
    )
    if dataset.prices.index.max().normalize() != as_of_day:
        raise ValueError("--as-of 必须是该快照实际覆盖到的 canonical 价格观测日")

    canonical_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=canonical_parent))
    try:
        write_tushare_dataset(dataset, staging)
        load_prospective_vintage(
            staging,
            as_of=as_of_day,
            historical_cutoff=cutoff,
            historical_prices=load_price_csv(root / "data/canonical/etf_adjusted_close.csv"),
            historical_calendar=load_calendar(root / "data/canonical/trading_calendar.csv"),
            expected_source=SOURCE,
            expected_adjustment_type=ADJUSTMENT_TYPE,
            frozen_universe=frozen_universe,
        )
        if destination.exists():
            raise ValueError("candidate vintage 目录在冻结过程中被创建，拒绝覆盖")
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, choices=sorted(CANDIDATES))
    parser.add_argument("--as-of", required=True, help="as-of，YYYY-MM-DD")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("环境变量 TUSHARE_TOKEN 未设置")
    import tushare as ts

    vintage = freeze_vintage(
        ts.pro_api(token),
        candidate_id=args.candidate,
        as_of=args.as_of,
    )
    print(f"已冻结 {args.candidate} prospective vintage: {vintage.relative_to(ROOT).as_posix()}")
    for name in REQUIRED_VINTAGE_FILES:
        print(f"{name}: sha256={sha256_file(vintage / name)}")


if __name__ == "__main__":
    main()
