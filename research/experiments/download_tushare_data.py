#!/usr/bin/env python3
"""下载并验证 S1 所需的 Tushare Pro 场内基金数据。"""

import os
from argparse import ArgumentParser
from pathlib import Path

import tushare as ts

from tacticore.data.tushare import download_tushare_dataset, write_tushare_dataset
from tacticore.data.universe import load_universe

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, help="起始日期，格式 YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="截止日期，格式 YYYYMMDD")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "data/canonical", help="规范化数据输出目录"
    )
    parser.add_argument(
        "--universe", type=Path, default=ROOT / "config/universe.csv", help="标的 universe CSV"
    )
    args = parser.parse_args()

    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("环境变量 TUSHARE_TOKEN 未设置")
    universe = load_universe(args.universe)
    dataset = download_tushare_dataset(ts.pro_api(token), universe, args.start_date, args.end_date)
    write_tushare_dataset(dataset, args.output_dir)
    print(f"已写入 {args.output_dir}")
    print(f"价格区间: {dataset.prices.index.min().date()} 至 {dataset.prices.index.max().date()}")
    print(f"价格行数: {len(dataset.prices)}，标的数: {len(dataset.prices.columns)}")


if __name__ == "__main__":
    main()
