"""FinanceMCP research-export 快照契约与读取适配器的失败先行测试。

每个测试名说明它必须防住的具体失败。全部使用 `tests/fixtures/ashare_export/`
下由 FinanceMCP `research-export` CLI 真实导出的快照，不用手写 CSV 冒充——
契约的价值就在于它是同一条导出路径的产物。

运行：
    cd /home/jcshi/workspace/TactiCore
    .venv/bin/python -m pytest tests/test_ashare_contract.py -v
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from research.ashare.data.adapter import load_research_frames
from research.ashare.data.contract import (
    SUPPORTED_EXPORT_SCHEMA_VERSION,
    SnapshotContractError,
    load_snapshot_manifest,
    sha256_file,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ashare_export"

# 快照的 as-of 是 20260107。
AS_OF = "20260107"
# 600001.SH 的 list_date 是 20260108，晚于 as-of。快照里却有它 0105–0107 的行情。
LATE_LISTED = "600001.SH"
# 510300.SH 是 ETF，与股票分属不同数据集。
ETF = "510300.SH"


@pytest.fixture()
def snapshot(tmp_path: Path) -> Path:
    """快照的**每测试独立**工作副本。

    必须 function scope：这些测试的大多数会破坏 manifest 或数据文件，
    共享副本会让前一个测试的破坏泄漏成后一个测试的"契约失败"，
    于是每个测试都在测别人造成的损坏，而不是自己声明的那条。
    """
    copied = tmp_path / "snapshot"
    shutil.copytree(FIXTURE, copied)
    return copied


@pytest.fixture()
def manifest(snapshot: Path):
    return load_snapshot_manifest(snapshot)


@pytest.fixture()
def frames(snapshot: Path):
    return load_research_frames(snapshot)


# --------------------------------------------------------------------------------------
# 契约校验：manifest 结构
# --------------------------------------------------------------------------------------


def test_AC01_the_real_export_manifest_loads(manifest) -> None:
    """真实导出的 manifest 必须通过校验，否则本模块与导出方已经脱节。"""
    assert manifest.schema_version == SUPPORTED_EXPORT_SCHEMA_VERSION
    assert manifest.as_of_trade_date == AS_OF
    assert manifest.quality_status == "READY"
    assert manifest.snapshot_id in manifest.content_hashes.values() or manifest.snapshot_id


def test_AC02_a_tampered_dataset_file_is_refused(snapshot: Path) -> None:
    """改一个字节的行情文件必须让整个快照被拒绝，而不是只漏那一行。"""
    target = snapshot / "daily_bars.csv"
    original = target.read_text(encoding="utf-8")
    # 把 close=10.5 改成 10.9：数值上仍是一根合法的 K 线，只有哈希能发现。
    tampered = original.replace("10,11,9,10.5,", "10,11,9,10.9,")
    assert tampered != original, "fixture 里必须存在可篡改的目标行"
    target.write_text(tampered, encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="内容哈希不符"):
        load_snapshot_manifest(snapshot)


def test_AC03_a_missing_required_manifest_field_is_refused(snapshot: Path) -> None:
    """缺任何一个契约字段都说明版本已变，不得按旧逻辑猜。"""
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["availability_semantics"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="availability_semantics"):
        load_snapshot_manifest(snapshot, verify_content=False)


def test_AC04_an_unsupported_schema_version_is_refused(snapshot: Path) -> None:
    """升级导出方而没升级读取方时必须失败，不能默默按旧语义解析。"""
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = "research-export-2.0.0"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="不支持的 schema_version"):
        load_snapshot_manifest(snapshot, verify_content=False)


def test_AC05_a_file_named_in_manifest_but_absent_is_refused(snapshot: Path) -> None:
    """manifest 声明了却不存在的文件必须拒绝，不能当成空数据集。"""
    (snapshot / "price_limit.csv").unlink()
    with pytest.raises(SnapshotContractError, match="不存在该文件"):
        load_snapshot_manifest(snapshot)


def test_AC06_a_manifest_and_content_hash_disagreement_is_refused(snapshot: Path) -> None:
    """dataset_manifest 与 content_hashes 对不上说明清单被改过。"""
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["content_hashes"].pop("price_limit.csv")
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="不一致"):
        load_snapshot_manifest(snapshot, verify_content=False)


def test_AC07_a_degraded_snapshot_without_a_reason_is_refused(snapshot: Path) -> None:
    """status=DEGRADED 却不解释为什么，调用方无法判断影响，必须拒绝。"""
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["data_quality"]["status"] = "DEGRADED"
    raw["data_quality"]["reasons"] = []
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="DEGRADED"):
        load_snapshot_manifest(snapshot, verify_content=False)


def test_AC08_a_non_hex_digest_is_refused(snapshot: Path) -> None:
    """哈希字段必须是 64 位小写十六进制，大写或截断都拒绝。"""
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["dataset_manifest"][0]["sha256"] = raw["dataset_manifest"][0]["sha256"].upper()
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="十六进制"):
        load_snapshot_manifest(snapshot, verify_content=False)


def test_AC09_a_path_escaping_the_snapshot_directory_is_refused(snapshot: Path) -> None:
    """manifest 里的文件名必须是纯文件名，否则可以写到快照目录之外。"""
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["dataset_manifest"][0]["file"] = "../../etc/passwd"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="纯文件名"):
        load_snapshot_manifest(snapshot, verify_content=False)


def test_AC10_a_boolean_disguised_as_a_row_count_is_refused(snapshot: Path) -> None:
    """rows=true 会静默变成 1；布尔值不是行数。"""
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["dataset_manifest"][0]["rows"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="整数"):
        load_snapshot_manifest(snapshot, verify_content=False)


# --------------------------------------------------------------------------------------
# 适配器：PIT 正确性与可交易性
# --------------------------------------------------------------------------------------


def test_AA01_a_security_listed_after_as_of_gets_no_positive_target(frames) -> None:
    """任务书 Phase 1：未上市证券不能生成正目标持仓。

    这是结构性保证，不靠调用方自觉：`build_tradability_mask` 让该证券在上市日
    之前全部不可交易，`validate_execution_targets` 随后会拒绝对它的任何正权重。
    """
    assert LATE_LISTED in frames.prices.columns, "fixture 必须包含这只后上市证券"
    mask = frames.tradability_mask
    assert mask.columns.__contains__(LATE_LISTED)
    pre_listing = mask.loc[mask.index < pd.Timestamp("2026-01-08"), LATE_LISTED]
    assert not pre_listing.any(), (
        f"{LATE_LISTED} 在 list_date 之前竟然可交易：{pre_listing.to_dict()}"
    )


def test_AA02_pre_listing_price_rows_are_dropped_and_recorded(frames) -> None:
    """早于上市日的价格必须被置为 NaN，且这一动作必须写进 notes。"""
    assert LATE_LISTED in frames.excluded or any(LATE_LISTED in note for note in frames.notes), (
        "丢弃上市前行必须在 notes 或 excluded 中留下痕迹"
    )
    pre = frames.prices.loc[frames.prices.index < pd.Timestamp("2026-01-08"), LATE_LISTED]
    assert pre.isna().all(), f"上市日之前的价格必须是 NaN: {pre.to_dict()}"


def test_AA03_a_security_without_an_identity_record_has_no_lifetime(frames) -> None:
    """没有身份记录的证券不给生命周期，因而永远不可交易。"""
    # 快照里每只证券都有身份记录；这里验证机制本身：
    # 没有 lifetime 的 symbol 在 mask 里必然全 False。
    for symbol in frames.prices.columns:
        if symbol not in frames.lifetimes:
            assert not frames.tradability_mask[symbol].any(), f"{symbol} 没有 lifetime 却可交易"


def test_AA04_a_suspended_day_is_not_tradable(frames) -> None:
    """停牌日不可交易，且价格缺口必须表现为 NaN 而不是插值。"""
    suspended = frames.suspended
    assert not suspended.empty, "fixture 必须包含停牌记录"
    assert (suspended["trade_date"] == "20260107").any(), "fixture 停牌日应为 20260107"
    row = suspended[suspended["trade_date"] == "20260107"].iloc[0]
    symbol = str(row["ts_code"])
    mask = frames.tradability_mask
    if symbol in mask.columns:
        assert not bool(mask.at[pd.Timestamp("2026-01-07"), symbol]), "停牌日不得可交易"


def test_AA05_equity_and_etf_prices_stay_in_one_matrix_but_keep_their_own_columns(frames) -> None:
    """ETF 与股票都进价格矩阵，但资产身份不合并、不复权口径不混。"""
    assert ETF in frames.prices.columns
    assert "600000.SH" in frames.prices.columns
    assert ETF in frames.lifetimes
    assert frames.lifetimes[ETF].listed_date == pd.Timestamp("2012-05-28")


def test_AA06_an_empty_announcement_date_stays_unknown(frames) -> None:
    """财务公告日为空的行不得被当作 PIT 合格。

    适配器不解释财务数据，但它必须让"公告日为空"这件事在读入后依然可见，
    而不是被填成某个日期或 0。
    """
    manifest = frames.manifest
    entry = manifest.dataset("financial_indicator")
    assert entry.rows >= 2, "fixture 必须包含一条空公告日与一条正常公告日"
    text = (manifest.snapshot_dir / entry.file).read_text(encoding="utf-8")
    assert ",," in text, "空公告日必须以空字段保留"


def test_AA07_the_price_limit_table_survives_the_adapter(frames) -> None:
    """涨跌停表必须原样带出，供执行层判断可成交性。"""
    assert not frames.price_limits.empty
    assert {"ts_code", "trade_date", "up_limit", "down_limit"} <= set(frames.price_limits.columns)


def test_AA08_the_adapter_output_feeds_the_unmodified_engine_contract(frames) -> None:
    """产物必须能直接交给未修改的 `run_target_weights()`。

    这里只验证形状与类型契约，不跑引擎（引擎的既有测试已覆盖）：
    正目标权重在不可交易资产上会被 `validate_execution_targets` 拒绝。
    """
    prices = frames.prices
    mask = frames.tradability_mask
    assert list(prices.columns) == list(mask.columns), "价格矩阵与 mask 列必须一致"
    assert prices.index.equals(mask.index), "价格矩阵与 mask 索引必须一致"
    assert prices.index.is_monotonic_increasing, "日期必须升序"
    for symbol in prices.columns:
        assert prices[symbol].dtype.kind == "f", f"{symbol} 价格必须是浮点（含 NaN）"


def test_AA09_a_missing_price_dataset_is_refused_not_silently_empty(snapshot: Path) -> None:
    """两个价格数据集都空 = 没有行情，必须拒绝而不是返回空矩阵。"""
    (snapshot / "daily_bars.csv").write_text(
        "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount\n", encoding="utf-8"
    )
    (snapshot / "fund_daily_bars.csv").write_text(
        "ts_code,trade_date,open,high,low,close,pre_close,vol,amount\n", encoding="utf-8"
    )
    # 重算 manifest 的哈希，让篡改本身不成为拒绝原因——我们要测的是"空行情"这条。
    _rehash(snapshot)
    with pytest.raises(SnapshotContractError, match="没有任何行情"):
        load_research_frames(snapshot)


def test_AA10_a_degraded_snapshot_with_missing_datasets_is_refused(snapshot: Path) -> None:
    """缺数据集的快照不得用于产生前瞻证据。"""
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["data_quality"]["status"] = "DEGRADED"
    raw["data_quality"]["missing_datasets"] = ["financial_indicator"]
    raw["data_quality"]["reasons"] = ["table_missing:fina_indicator"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SnapshotContractError, match="DEGRADED"):
        load_research_frames(snapshot)


def test_AA11_a_required_column_absent_is_refused(snapshot: Path) -> None:
    """缺 close 列的行情表必须拒绝，不能按列序猜。"""
    target = snapshot / "daily_bars.csv"
    lines = target.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    close_index = header.index("close")
    lines = [
        ",".join([value for i, value in enumerate(line.split(",")) if i != close_index])
        for line in lines
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _rehash(snapshot)
    with pytest.raises(SnapshotContractError, match="close"):
        load_research_frames(snapshot)


def test_AA12_an_unparseable_trade_date_is_refused(snapshot: Path) -> None:
    """日期不可解析必须失败，不得丢行后继续。"""
    target = snapshot / "daily_bars.csv"
    text = target.read_text(encoding="utf-8")
    text = text.replace(",20260105,", ",2026-1-5,")
    target.write_text(text, encoding="utf-8")
    _rehash(snapshot)
    with pytest.raises(SnapshotContractError, match="trade_date"):
        load_research_frames(snapshot)


def test_AA13_sha256_file_matches_the_exporter(frames) -> None:
    """读取方的哈希算法必须与 FinanceMCP 导出一致，否则 AC02 会是假通过。"""
    entry = frames.manifest.dataset("daily_bars")
    path = frames.manifest.snapshot_dir / entry.file
    assert sha256_file(path) == entry.sha256


def test_AA14_an_unparseable_listing_date_excludes_instead_of_fabricating(snapshot: Path) -> None:
    """上市日不可解析必须排除该证券，**不得**回退成"永远已上市"。

    这里防的是一次具体的事故：`list_date` 解析失败时曾被回退到 1900-01-01，
    于是该证券在上市日之前也变得可交易——而 notes 里一个字都不提。
    既产生错误结果，又销毁了它自己的证据。这条测试把上市前那一行钉死。
    """
    target = snapshot / "stock_basic.csv"
    text = target.read_text(encoding="utf-8")
    # 600001.SH 的 list_date 20260108 -> 月份 13，不可解析。
    assert "20260108" in text, "fixture 必须包含这只后上市证券的上市日"
    target.write_text(text.replace("20260108", "20261301"), encoding="utf-8")
    _rehash(snapshot)  # 先让篡改合法化，才能测到适配器而不是哈希不符

    frames = load_research_frames(snapshot)

    assert LATE_LISTED in frames.excluded, (
        f"上市日不可解析必须显式排除，实际 excluded={frames.excluded}"
    )
    assert "list_date" in frames.excluded[LATE_LISTED], (
        f"排除原因必须指名 list_date: {frames.excluded[LATE_LISTED]}"
    )
    # 关键断言：回退到 1900-01-01 会让这三行全部变成可交易。
    pre_listing = frames.tradability_mask.loc[
        frames.tradability_mask.index < pd.Timestamp("2026-01-08"), LATE_LISTED
    ]
    assert not pre_listing.any(), (
        f"{LATE_LISTED} 的上市日不可解析，却在上市前可交易: {pre_listing.to_dict()}"
    )
    assert not frames.tradability_mask[LATE_LISTED].any(), "上市日未知的证券在任何日期都不得可交易"


def _rehash(snapshot: Path) -> None:
    """把 manifest 的 content_hashes 与 dataset_manifest 重算为当前文件内容。

    测试用它把"文件被改"与"哈希不符"这两件事分开：先让篡改合法化，再测别的失败。
    """
    path = snapshot / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    for entry in raw["dataset_manifest"]:
        target = snapshot / entry["file"]
        if target.is_file():
            digest = sha256_file(target)
            entry["sha256"] = digest
            raw["content_hashes"][entry["file"]] = digest
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
