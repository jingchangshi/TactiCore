# Tushare Pro canonical 数据

本目录保存 S1 全球双动量研究使用的冻结市场数据快照。

## 文件契约

- `etf_adjusted_close.csv`：首列为 `date`，其余列为 `config/universe.csv` 中的策略 symbol；日期唯一、递增，有效值大于零，缺失值留空。
- `trading_calendar.csv`：自然日索引以及上交所、深交所是否开市的 0/1 标志。
- `provenance.json`：逐标的来源、Tushare 代码、请求参数、复权口径、数据时间、下载时间、基金元数据、质量检查和文件 SHA-256。

请求区间固定为 2012-01-01 至 2026-08-31。由于首只标的在 2012-05-28 上市，价格文件实际从该日开始。

## 复权与缺失假设

规范化价格按以下公式计算：

```text
后复权收盘价 = fund_daily.close × fund_adj.adj_factor
```

研究将复权因子变化解释为分红再投资。后复权避免前复权价格因查询截止日延长而整体重缩放，但 Tushare 仍可能修订历史行情或因子，因此每次快照必须使用来源清单中的 SHA-256 标识。

日线与复权因子按同一 `trade_date` 一对一合并。重复日期、缺失因子、非正价格、非正因子、非交易日行情或配置上市日期不一致都会终止下载。上市前空白以及上市后的停牌/缺口保持为空，不做前向填充、插值或零填充。

接口定义参考 Tushare 官方文档：[ETF 日线行情](https://tushare.pro/document/2?doc_id=127)、[基金复权因子](https://tushare.pro/document/2?doc_id=199)、[交易日历](https://tushare.pro/document/2?doc_id=26)和[基金列表](https://tushare.pro/document/1?doc_id=19)。API 返回并不自动等同于经济口径正确，因此来源清单仍保留全部假设和检查结果。

## 重建命令

在环境变量 `TUSHARE_TOKEN` 已设置时运行：

```bash
uv run python research/experiments/download_tushare_data.py \
  --start-date 20120101 \
  --end-date 20260831
```

相同 API 响应会按固定列顺序、日期排序、八位小数和 LF 换行生成相同价格及日历文件；`download_timestamp` 会如实记录每次下载时间。token 不会写入任何产物。
