# NOTICE：数据抓取脚本已随 Tushare 退役删除

Tushare 数据源已于 2026-11-25 按所有者指令退役（「删除TuShare相关……全面切换，不考虑后向兼容性」）。

- 已删除：`fetch_transfer_data.py` 及其测试 `test_fetch_transfer_data.py`。它们在运行时依赖已删除的 `tacticore.data.tushare` 与 `tushare` 包。
- 冻结快照 `data/transfer_v1/snapshot_20261114T050648Z/` 与本目录 `PROTOCOL_V1.md` 保持字节不变，只作为 `ACCOUNT_TRANSFER_V1`（RL-053）的历史证据。
- **此快照不可再重新抓取。** 原抓取脚本可在 git 历史中查到：`git show 985fb89^:research/batches/transfer_v1/fetch_transfer_data.py`（`985fb89` 之前的任一版本）。
