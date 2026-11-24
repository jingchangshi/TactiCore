"""FinanceMCP research-export 快照契约校验。

本模块只做一件事：**在把任何一行数据交给研究代码之前，证明这份快照是完整的、
未被篡改的、且 as-of 边界就是调用方以为的那个**。它不读行情、不计算指标、
不做任何研究判断。

设计约束（来自 AShareInvestor `docs/research-evolution-20261022/02_ARCHITECTURE_DECISION.md`）：
- 统计机制只在 FinanceMCP `validation.ts`，本模块不实现任何统计；
- 复用 `research/experiments/prospective_evidence.py` 的既有原语
  （`verify_hex_digest` / `parse_iso_date` / `normalize_signal_date`），不重写；
- 读到的每个字段缺失或哈希不符都**拒绝加载**，不降级、不猜测、不填默认值。

失败即抛 `SnapshotContractError`（`ValueError` 子类，便于调用方按值捕获）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 复用既有原语，不重写哈希与日期校验。导入路径与 research/experiments/ 下其他脚本一致。
from research.experiments.prospective_evidence import (
    normalize_signal_date,
    parse_iso_date,
    verify_hex_digest,
)

CONTRACT_MODULE_VERSION = "ashare-snapshot-contract-1.0.0"

#: 导出版本。FinanceMCP `RESEARCH_EXPORT_SCHEMA_VERSION` 与本常量不一致即拒绝。
SUPPORTED_EXPORT_SCHEMA_VERSION = "research-export-1.0.0"

#: manifest 中必须存在的顶层字段。缺任何一个都说明契约已变，不得按旧逻辑解析。
REQUIRED_MANIFEST_FIELDS = (
    "snapshot_id",
    "schema_version",
    "as_of_trade_date",
    "created_at",
    "source_db_fingerprint",
    "dataset_manifest",
    "data_quality",
    "availability_semantics",
    "code_mapping_version",
    "adjustment_policy",
    "content_hashes",
)

#: 每个 dataset 条目必须存在的字段。
REQUIRED_DATASET_FIELDS = (
    "dataset",
    "table",
    "file",
    "rows",
    "sha256",
    "columns",
    "time_column",
    "as_of_filtered",
    "availability",
)

#: 数据质量状态。DEGRADED 允许加载，但调用方必须显式确认，不得静默接受。
KNOWN_QUALITY_STATUS = ("READY", "DEGRADED")

#: FinanceMCP `research-export --financial-availability` 的两种模式。
#: `announcement-date-v1` 承诺财务行满足 valid(end_date) ∧ valid(ann_date)
#: ∧ end_date <= ann_date <= as_of；`legacy` 不承诺，空 ann_date 允许保留。
FINANCIAL_AVAILABILITY_MODES = ("legacy", "announcement-date-v1")
#: 旧版 manifest 没有该后缀，等价于 legacy。
FINANCIAL_AVAILABILITY_MARKER = "financial_availability="


class SnapshotContractError(ValueError):
    """快照契约校验失败。"""


@dataclass(frozen=True)
class DatasetEntry:
    """manifest 中一个数据集条目的已验证视图。"""

    dataset: str
    table: str
    file: str
    rows: int
    sha256: str
    columns: tuple[str, ...]
    time_column: str | None
    as_of_filtered: bool
    availability: str
    as_of_filter_note: str

    @property
    def path(self) -> Path:
        """数据集文件在快照目录中的路径。"""
        return Path(self.file)


@dataclass(frozen=True)
class SnapshotManifest:
    """已验证的 manifest 视图。字段名与 JSON 一致，便于人工对照。"""

    snapshot_id: str
    snapshot_id_algorithm: str
    schema_version: str
    as_of_trade_date: str
    as_of_date: Any  # pd.Timestamp, 上海时区归一化
    created_at: str
    source_db_fingerprint: str
    datasets: tuple[DatasetEntry, ...]
    quality_status: str
    missing_datasets: tuple[str, ...]
    reasons: tuple[str, ...]
    data_cutoff: str | None
    availability_semantics: Mapping[str, Any]
    financial_availability: str
    code_mapping_version: str
    adjustment_policy: Mapping[str, Any]
    content_hashes: Mapping[str, str]
    manifest_path: Path
    snapshot_dir: Path

    def dataset(self, name: str) -> DatasetEntry:
        """按名字取数据集条目；不存在即拒绝。"""
        for entry in self.datasets:
            if entry.dataset == name:
                return entry
        available = ", ".join(entry.dataset for entry in self.datasets)
        raise SnapshotContractError(
            f"数据集 {name!r} 不在 manifest 中（可用: {available}）；不得用别的数据集冒充"
        )


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SnapshotContractError(f"{label} 必须是 JSON 对象，得到 {type(value).__name__}")
    return value


def _require_str(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotContractError(f"{label} 必须是非空字符串，得到 {value!r}")
    return value


def _require_int(value: object, *, label: str) -> int:
    # bool 是 int 的子类，必须排除，否则 rows=true 会静默变成 1。
    if isinstance(value, bool) or not isinstance(value, int):
        raise SnapshotContractError(f"{label} 必须是整数，得到 {value!r}")
    return value


def _require_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise SnapshotContractError(f"{label} 必须是布尔值，得到 {value!r}")
    return value


def _require_digest(value: object, *, label: str) -> str:
    """哈希字段校验。

    复用 `verify_hex_digest` 的判定逻辑，但把它的 `ValueError` 收敛成
    `SnapshotContractError`：调用方按本模块的异常类型捕获时，不应因为底层
    原语抛的是基类而漏掉一个真实的契约失败。
    """
    try:
        return verify_hex_digest(value, label=label)
    except ValueError as error:
        raise SnapshotContractError(str(error)) from error


def _require_iso_date(value: object, *, label: str) -> str:
    """严格校验 YYYYMMDD：必须正好 8 位数字。

    不能用 `value[:4]-value[4:6]-value[6:]` 再交给 pandas：那样 `2026-1-5`
    会被切成 `2026--1--5` 而 pandas 仍能宽松解析，畸形日期就静默通过了。
    """
    text = _require_str(value, label=label)
    if len(text) != 8 or not text.isdigit():
        raise SnapshotContractError(f"{label} 必须是 8 位 YYYYMMDD 数字，得到 {text!r}")
    try:
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    except (ValueError, IndexError) as error:
        raise SnapshotContractError(f"{label} 不是有效日期: {text!r}") from error


def _parse_financial_availability(semantics: Mapping[str, Any]) -> str:
    """从 `availability_semantics.financial_indicator` 解析导出方的财务可得性模式。

    旧版 manifest 没有 `financial_availability=` 后缀，等价于 `legacy`；出现未知
    模式即拒绝，因为读取方无法知道 `ann_date` 是否经过边界过滤。
    """
    raw = semantics.get("financial_indicator")
    if raw is None:
        return "legacy"
    text = _require_str(raw, label="availability_semantics.financial_indicator")
    if FINANCIAL_AVAILABILITY_MARKER not in text:
        return "legacy"
    mode = text.split(FINANCIAL_AVAILABILITY_MARKER, 1)[1].split(";", 1)[0].strip()
    if mode not in FINANCIAL_AVAILABILITY_MODES:
        raise SnapshotContractError(
            f"未知的 financial_availability {mode!r}"
            f"（已知: {', '.join(FINANCIAL_AVAILABILITY_MODES)}）"
        )
    return mode


def _validate_announcement_date_v1_structure(datasets: list[DatasetEntry]) -> None:
    """announcement-date-v1 的结构前提：财务数据集必须按 ann_date 过滤且声明 end_date。"""
    for entry in datasets:
        if entry.dataset != "financial_indicator":
            continue
        if entry.time_column != "ann_date" or not entry.as_of_filtered:
            raise SnapshotContractError(
                "financial_availability=announcement-date-v1 要求 financial_indicator 按 "
                f"ann_date 做 as-of 过滤；实际 time_column={entry.time_column!r}, "
                f"as_of_filtered={entry.as_of_filtered}"
            )
        if "end_date" not in entry.columns or "ann_date" not in entry.columns:
            raise SnapshotContractError(
                "financial_availability=announcement-date-v1 要求 financial_indicator 同时声明 "
                f"end_date 与 ann_date 列；实际 columns={list(entry.columns)}"
            )
        return


def verify_snapshot_manifest(
    manifest: Mapping[str, Any],
    *,
    snapshot_dir: Path,
) -> SnapshotManifest:
    """校验 manifest 结构。只校验结构与身份，不触碰数据文件本身。"""
    manifest = _require_mapping(manifest, label="manifest")

    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        raise SnapshotContractError(
            f"manifest 缺少必需字段: {', '.join(missing)}；契约版本可能已变，拒绝按旧逻辑解析"
        )

    snapshot_id = _require_digest(manifest["snapshot_id"], label="snapshot_id")
    schema_version = _require_str(manifest["schema_version"], label="schema_version")
    if schema_version != SUPPORTED_EXPORT_SCHEMA_VERSION:
        raise SnapshotContractError(
            f"不支持的 schema_version {schema_version!r}（本模块支持 "
            f"{SUPPORTED_EXPORT_SCHEMA_VERSION!r}）；升级读取方之前不得加载"
        )
    fingerprint = _require_digest(manifest["source_db_fingerprint"], label="source_db_fingerprint")

    as_of_text = _require_str(manifest["as_of_trade_date"], label="as_of_trade_date")
    as_of_date = normalize_signal_date(
        parse_iso_date(
            _require_iso_date(as_of_text, label="as_of_trade_date"), label="as_of_trade_date"
        )
    )

    raw_datasets = manifest["dataset_manifest"]
    if not isinstance(raw_datasets, list) or not raw_datasets:
        raise SnapshotContractError("dataset_manifest 必须是非空数组")

    datasets: list[DatasetEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_datasets):
        entry = _require_mapping(raw, label=f"dataset_manifest[{index}]")
        absent = [field for field in REQUIRED_DATASET_FIELDS if field not in entry]
        if absent:
            raise SnapshotContractError(f"dataset_manifest[{index}] 缺少字段: {', '.join(absent)}")
        name = _require_str(entry["dataset"], label=f"dataset_manifest[{index}].dataset")
        if name in seen:
            raise SnapshotContractError(f"数据集 {name!r} 在 manifest 中重复出现")
        seen.add(name)
        file_name = _require_str(entry["file"], label=f"{name}.file")
        # 文件名必须是纯文件名：任何路径分隔符都意味着可以写到快照目录之外。
        if "/" in file_name or "\\" in file_name or file_name in (".", ".."):
            raise SnapshotContractError(
                f"{name}.file 必须是快照目录内的纯文件名，得到 {file_name!r}"
            )
        sha = _require_digest(entry["sha256"], label=f"{name}.sha256")
        columns_raw = entry["columns"]
        if not isinstance(columns_raw, list) or not columns_raw:
            raise SnapshotContractError(f"{name}.columns 必须是非空数组")
        columns = tuple(_require_str(c, label=f"{name}.columns[]") for c in columns_raw)
        datasets.append(
            DatasetEntry(
                dataset=name,
                table=_require_str(entry["table"], label=f"{name}.table"),
                file=file_name,
                rows=_require_int(entry["rows"], label=f"{name}.rows"),
                sha256=sha,
                columns=columns,
                time_column=(
                    None
                    if entry["time_column"] is None
                    else _require_str(entry["time_column"], label=f"{name}.time_column")
                ),
                as_of_filtered=_require_bool(
                    entry["as_of_filtered"], label=f"{name}.as_of_filtered"
                ),
                availability=_require_str(entry["availability"], label=f"{name}.availability"),
                as_of_filter_note=_require_str(
                    entry.get("as_of_filter_note", ""), label=f"{name}.as_of_filter_note"
                ),
            )
        )

    quality = _require_mapping(manifest["data_quality"], label="data_quality")
    status = _require_str(quality.get("status"), label="data_quality.status")
    if status not in KNOWN_QUALITY_STATUS:
        raise SnapshotContractError(
            f"未知的 data_quality.status {status!r}（已知: {', '.join(KNOWN_QUALITY_STATUS)}）"
        )
    missing_datasets_raw = quality.get("missing_datasets")
    if not isinstance(missing_datasets_raw, list):
        raise SnapshotContractError("data_quality.missing_datasets 必须是数组")
    missing_datasets = tuple(
        _require_str(item, label="data_quality.missing_datasets[]") for item in missing_datasets_raw
    )
    reasons_raw = quality.get("reasons")
    if not isinstance(reasons_raw, list):
        raise SnapshotContractError("data_quality.reasons 必须是数组")
    reasons = tuple(_require_str(item, label="data_quality.reasons[]") for item in reasons_raw)
    if status == "DEGRADED" and not reasons:
        raise SnapshotContractError(
            "status=DEGRADED 但 reasons 为空；降级原因必须显式记录，否则调用方无法判断影响"
        )
    data_cutoff = quality.get("data_cutoff")
    if data_cutoff is not None:
        data_cutoff = _require_str(data_cutoff, label="data_quality.data_cutoff")

    content_hashes_raw = _require_mapping(manifest["content_hashes"], label="content_hashes")
    content_hashes: dict[str, str] = {}
    for file_name, digest in content_hashes_raw.items():
        _require_str(file_name, label="content_hashes 键")
        content_hashes[file_name] = _require_digest(digest, label=f"content_hashes[{file_name}]")

    # manifest 声明的每个文件都必须出现在 content_hashes 中，反之亦然。
    # 对不上说明有数据集被加了或删了，按旧清单读取会漏文件或读错文件。
    declared = {entry.file for entry in datasets}
    hashed = set(content_hashes)
    if declared != hashed:
        only_manifest = sorted(declared - hashed)
        only_hashes = sorted(hashed - declared)
        raise SnapshotContractError(
            "dataset_manifest 与 content_hashes 不一致"
            f"（仅 manifest: {only_manifest}; 仅 hashes: {only_hashes}）"
        )

    algorithm = manifest.get("snapshot_id_algorithm", "legacy-source-v1")
    if algorithm not in ("legacy-source-v1", "content-hashes-v1", "dataset-manifest-v2"):
        raise SnapshotContractError(f"不支持的 snapshot_id_algorithm: {algorithm!r}")
    availability_semantics = _require_mapping(
        manifest["availability_semantics"], label="availability_semantics"
    )
    # 只有 dataset-manifest-v2 的 snapshot_id 绑定 availability_semantics 与数据集
    # 元数据。legacy-source-v1 / content-hashes-v1 不覆盖该字段：改动它不会改变
    # snapshot_id，因此其中的 announcement-date-v1 声明不可信，一律按 legacy 处理，
    # 不得仅凭 ID 不变就升级为严格语义。
    if algorithm == "dataset-manifest-v2":
        financial_availability = _parse_financial_availability(availability_semantics)
        if financial_availability == "announcement-date-v1":
            _validate_announcement_date_v1_structure(datasets)
    else:
        financial_availability = "legacy"
    identity: dict[str, Any] = {
        "schema_version": schema_version,
        "as_of": as_of_text,
        "source": fingerprint,
    }
    if algorithm in ("content-hashes-v1", "dataset-manifest-v2"):
        identity["content_hashes"] = dict(sorted(content_hashes.items()))
    if algorithm == "dataset-manifest-v2":
        identity["datasets"] = [
            [
                entry.dataset,
                entry.table,
                entry.file,
                entry.sha256,
                entry.rows,
                list(entry.columns),
                entry.time_column,
                entry.as_of_filtered,
                entry.availability,
                entry.as_of_filter_note,
                raw.get("missing_note"),
            ]
            for entry, raw in sorted(
                zip(datasets, raw_datasets, strict=True), key=lambda pair: pair[0].dataset
            )
        ]
        identity["quality"] = {
            "status": status,
            "missing_datasets": sorted(missing_datasets),
            "reasons": sorted(reasons),
            "as_of_requested": quality.get("as_of_requested"),
            "as_of_resolved": quality.get("as_of_resolved"),
            "data_cutoff": data_cutoff,
        }
        identity["code_mapping_version"] = _require_str(
            manifest["code_mapping_version"], label="code_mapping_version"
        )
        for key in ("adjustment_policy", "availability_semantics"):
            fields = _require_mapping(manifest[key], label=key)
            identity[key] = [
                [_require_str(k, label=key), _require_str(v, label=key)]
                for k, v in sorted(fields.items())
            ]
    expected_id = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if snapshot_id != expected_id:
        raise SnapshotContractError("snapshot_id 与声明的快照身份不一致")
    for entry in datasets:
        if entry.sha256 != content_hashes[entry.file]:
            raise SnapshotContractError(
                f"{entry.file} 在 dataset_manifest 与 content_hashes 中的哈希不一致"
            )

    return SnapshotManifest(
        snapshot_id=snapshot_id,
        snapshot_id_algorithm=algorithm,
        schema_version=schema_version,
        as_of_trade_date=as_of_text,
        as_of_date=as_of_date,
        created_at=_require_str(manifest["created_at"], label="created_at"),
        source_db_fingerprint=fingerprint,
        datasets=tuple(datasets),
        quality_status=status,
        missing_datasets=missing_datasets,
        reasons=reasons,
        data_cutoff=data_cutoff,
        availability_semantics=availability_semantics,
        financial_availability=financial_availability,
        code_mapping_version=_require_str(
            manifest["code_mapping_version"], label="code_mapping_version"
        ),
        adjustment_policy=_require_mapping(
            manifest["adjustment_policy"], label="adjustment_policy"
        ),
        content_hashes=content_hashes,
        manifest_path=Path(snapshot_dir) / "manifest.json",
        snapshot_dir=Path(snapshot_dir),
    )


def sha256_file(path: Path) -> str:
    """文件内容 SHA-256。与 FinanceMCP 侧一致：UTF-8 字节流原样哈希。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_snapshot_content(manifest: SnapshotManifest) -> None:
    """逐个数据集比对文件内容哈希。

    哈希不符即拒绝：这意味着文件在导出之后被改过，研究代码**不得**基于它产生任何
    会被称作"前瞻证据"的结果。
    """
    for entry in manifest.datasets:
        path = manifest.snapshot_dir / entry.file
        if not path.is_file():
            raise SnapshotContractError(f"manifest 声明了 {entry.file} 但快照目录中不存在该文件")
        actual = sha256_file(path)
        expected = manifest.content_hashes[entry.file]
        if actual != expected:
            raise SnapshotContractError(
                f"{entry.file} 内容哈希不符：manifest={expected} 实际={actual}；"
                "快照在导出后被修改，拒绝加载"
            )
        if entry.sha256 != expected:
            raise SnapshotContractError(
                f"{entry.file} 在 dataset_manifest 与 content_hashes 中的哈希不一致"
            )


def load_snapshot_manifest(
    snapshot_dir: str | Path,
    *,
    verify_content: bool = True,
) -> SnapshotManifest:
    """读取并校验一份 FinanceMCP research-export 快照。

    `verify_content=False` 只校验 manifest 结构，不读数据文件。仅用于列出快照内容，
    任何要用于研究的路径都必须 `verify_content=True`。
    """
    directory = Path(snapshot_dir)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise SnapshotContractError(f"快照目录缺少 manifest.json: {directory}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SnapshotContractError(f"manifest.json 不是合法 JSON: {error}") from error

    manifest = verify_snapshot_manifest(raw, snapshot_dir=directory)
    if verify_content:
        verify_snapshot_content(manifest)
    return manifest
