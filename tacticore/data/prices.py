from pathlib import Path

import numpy as np
import pandas as pd


def load_price_csv(path: str | Path) -> pd.DataFrame:
    """读取 date × symbol 的复权收盘价宽表。

    缺失价格（空字段）保持 NaN：那是"未知/不可交易"，有明确语义。除此之外的
    非数值文本、`inf` / `-inf` 一律拒绝：它们会静默变成 NaN 或进入下游数学，
    让坏数据冒充缺失或正常价格。宁可失败，也不替数据发明数值。
    """
    prices = pd.read_csv(path, index_col="date", parse_dates=["date"])
    if prices.empty:
        raise ValueError("价格数据不能为空")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("价格日期必须唯一且严格递增")
    if prices.columns.duplicated().any():
        raise ValueError("价格列 symbol 必须唯一")
    numeric = prices.apply(pd.to_numeric, errors="coerce")
    # 原始单元格有内容、却转不成数字 = 非数值文本（例如 "oops"）。不能当成缺失。
    non_numeric = prices.notna() & numeric.isna()
    if non_numeric.any().any():
        row, column = non_numeric.stack().loc[lambda s: s].index[0]
        raise ValueError(
            f"价格数据包含非数值文本: date={row} symbol={column} value={prices.at[row, column]!r}"
        )
    # ±inf 能通过 `<= 0` 检查并污染收益/权重的数学，必须显式拒绝。
    non_finite = numeric.notna() & ~np.isfinite(numeric)
    if non_finite.any().any():
        row, column = non_finite.stack().loc[lambda s: s].index[0]
        raise ValueError(f"价格必须是有限值，得到 inf/-inf: date={row} symbol={column}")
    if (numeric <= 0).any().any():
        raise ValueError("有效价格必须大于零")
    return numeric
