"""研究候选身份与生命周期管理。

本模块回答一个问题：**这个候选是谁，它现在处于哪一步，以及这一步能不能被推进**。
它不运行策略、不算收益、不接触生产调度，也不判断一个候选是否"好"——
那是 Phase 5 实验与独立审查的事。

设计约束（来自 `docs/research-evolution-20261022/02_ARCHITECTURE_DECISION.md`
与 `docs/goal-1023.md` Phase 4）：

1. **身份不可变。** `candidate_id` + `candidate_version` 一旦登记，内容即冻结。
   同一 ID 不同内容必须拒绝；同 ID 同内容必须幂等（重复提交不是错误，是同一事实）。
2. **旧结果不得静默替换。** 每次状态推进都追加一条带哈希的转移记录，
   不允许 UPDATE 历史行。
3. **策略代码、输入或协议改变即新候选版本。** 因此 `code_sha`、
   `research_data_snapshot_id`、`cost_model_version` 是身份的一部分，
   任一变化都意味着这不是同一个候选。
4. **`RECOMMENDED_FOR_APPROVAL` 不代表自动生产晋级。** 它是"值得人工批准"，
   不是"已获批准"；本模块没有任何路径能把它变成后者。
5. **不建设通用策略插件平台。** 只做轻量 manifest、生命周期与不可变记录。

状态机（可结合既有契约调整，但含义必须保留）：

    PROPOSED → REGISTERED → HISTORICAL_TESTED → EXECUTION_VERIFIED
             → FROZEN → SHADOW_ACTIVE → REVIEW_ELIGIBLE → RECOMMENDED_FOR_APPROVAL

以及四个终止/阻塞状态：INSUFFICIENT_DATA、REJECTED、INVALIDATED、RETIRED。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.experiments.prospective_evidence import (
    parse_iso_date,
    require_timezone_aware_instant,
    verify_hex_digest,
)

REGISTRY_MODULE_VERSION = "ashare-candidate-registry-1.0.0"

#: 身份字段。这些字段共同决定"这是同一个候选的同一个版本"，
#: 任一变化都必须是新的 candidate_version，而不是原地修改。
IDENTITY_FIELDS = (
    "candidate_id",
    "candidate_version",
    "strategy_family",
    "economic_hypothesis",
    "universe_specification",
    "signal_definition",
    "portfolio_construction",
    "execution_policy",
    "parameter_space",
    "research_data_snapshot_id",
    "code_sha",
    "cost_model_version",
    "benchmark_versions",
    "formation_window",
    "historical_holdout_window",
    "forward_start",
    "evaluation_horizons",
    "multiple_testing_family",
    "success_criteria",
    "failure_criteria",
)

#: 登记时必须存在但不参与身份哈希的元数据字段。
REQUIRED_METADATA_FIELDS = (
    "created_at",
    "champion_version",
    "mechanism_and_counter_evidence",
)

#: 允许的生命周期状态。
LIFECYCLE_STATES = (
    "PROPOSED",
    "REGISTERED",
    "HISTORICAL_TESTED",
    "EXECUTION_VERIFIED",
    "FROZEN",
    "SHADOW_ACTIVE",
    "REVIEW_ELIGIBLE",
    "RECOMMENDED_FOR_APPROVAL",
)

#: 终止与阻塞状态。进入后不得再推进到任何活跃状态。
TERMINAL_STATES = (
    "INSUFFICIENT_DATA",
    "REJECTED",
    "INVALIDATED",
    "RETIRED",
)

#: 非终止的重开状态：`SHADOW_ACTIVE` 在这里回到"需要重新验证历史证据"。
#:
#: 它是必需的，而且必须**不是**一条捷径：真实前瞻观察中发现统计 Foundation 缺陷时，
#: 候选不能继续往前（它拿到的观察可能全部作废），也不能直接报废——
#: 那会把"一次实现错误"记成"策略无效"。唯一诚实的去处是重新验证历史证据。
#:
#: 它是重开状态而非终止状态，所以它不出现在 `TERMINAL_STATES` 里；
#: 但它也不在 `LIFECYCLE_STATES` 里，因为后者被测试与文档当作主链读取。
#: 因此单独列在这里，`ALLOWED_TRANSITIONS` 的完整性测试按 `LIFECYCLE_STATES
#: + TERMINAL_STATES + REOPENING_STATES` 检查——一张漏了一行的表，
#: 比一张多了一行的表更危险，因为前者看起来只是"回退不可能"。
REOPENING_STATES = ("REVALIDATED",)

#: 合法推进。键为当前状态，值为可达状态集合。
#: 这个表是**全部**允许的推进；表里没有的推进一律拒绝，而不是"默认放行"。
ALLOWED_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "PROPOSED": frozenset({"REGISTERED", "REJECTED", "RETIRED"}),
    "REGISTERED": frozenset({"HISTORICAL_TESTED", "INSUFFICIENT_DATA", "REJECTED", "RETIRED"}),
    "HISTORICAL_TESTED": frozenset(
        {"EXECUTION_VERIFIED", "INSUFFICIENT_DATA", "REJECTED", "INVALIDATED", "RETIRED"}
    ),
    "EXECUTION_VERIFIED": frozenset(
        {"FROZEN", "INSUFFICIENT_DATA", "REJECTED", "INVALIDATED", "RETIRED"}
    ),
    "FROZEN": frozenset({"SHADOW_ACTIVE", "REJECTED", "RETIRED"}),
    "SHADOW_ACTIVE": frozenset({"REVIEW_ELIGIBLE", "INSUFFICIENT_DATA", "REVALIDATED"}),
    "REVIEW_ELIGIBLE": frozenset(
        {"RECOMMENDED_FOR_APPROVAL", "REJECTED", "INVALIDATED", "RETIRED"}
    ),
    "RECOMMENDED_FOR_APPROVAL": frozenset({"RETIRED"}),
    # 重开不是回到起点。重新验证历史证据之后，候选必须重新走
    # 执行验证与冻结，而不是直接回到 SHADOW_ACTIVE——它离开前瞻观察的
    # 原因就是已产生的观察不可信，所以那些观察不能重新计入。
    "REVALIDATED": frozenset({"EXECUTION_VERIFIED", "REJECTED", "RETIRED"}),
    "INSUFFICIENT_DATA": frozenset({"REGISTERED", "HISTORICAL_TESTED", "RETIRED"}),
    "REJECTED": frozenset(),
    "INVALIDATED": frozenset(),
    "RETIRED": frozenset(),
}


class CandidateRegistryError(ValueError):
    """候选身份或生命周期契约被违反。

    继承 `ValueError` 以便调用方按值捕获，与
    `SnapshotContractError` 的处理方式一致。"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: Any) -> str:
    """稳定序列化。键排序、无空白，使同一内容总是同一字节序列。

    不做这个规范化的哈希没有意义：字段顺序不同会被误判成"内容已变"，
    于是同一个候选的重复提交看起来像一次篡改。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def identity_hash(manifest: Mapping[str, Any]) -> str:
    """候选身份的 SHA-256。

    只覆盖 `IDENTITY_FIELDS`，不含状态、不含时间戳、不含备注——
    否则每写一条日志都会"改变身份"，身份就不再是身份了。"""
    missing = [name for name in IDENTITY_FIELDS if name not in manifest]
    if missing:
        raise CandidateRegistryError(f"候选缺少身份字段: {', '.join(missing)}")
    payload = {name: manifest[name] for name in IDENTITY_FIELDS}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def manifest_hash(manifest: Mapping[str, Any]) -> str:
    """整个 manifest 的 SHA-256，用于记录"当时提交的到底是什么"。"""
    return hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()


def _require(predicate: bool, message: str) -> None:
    if not predicate:
        raise CandidateRegistryError(message)


def _check(label: str, value: object, validator: Callable[..., object]) -> None:
    """把复用校验器的 `ValueError` 收敛成 `CandidateRegistryError`。

    本模块的调用方按 `CandidateRegistryError` 捕获（与 `SnapshotContractError`
    的处理方式一致）。让 `parse_iso_date` 的 `ValueError` 裸奔出去，
    调用方就得同时捕两种异常——而那两种里有一种它其实处理不了。
    """
    try:
        validator(value, label=label)
    except ValueError as error:
        raise CandidateRegistryError(str(error)) from error


def validate_manifest(manifest: Mapping[str, Any]) -> str:
    """校验 manifest 结构并返回身份哈希。缺字段、类型错、哈希格式错都拒绝。

    刻意**不**在这里检查策略是否合理、参数是否最优、假设是否有经济依据：
    那些是研究与审查的判断，本模块只保证身份是完整且自洽的。"""
    if not isinstance(manifest, Mapping):
        raise CandidateRegistryError("manifest 必须是对象")
    # 缺身份字段与缺元数据分开报：前者意味着"这不是一个可登记的候选"，
    # 后者只是漏填。混成一句"缺少必需字段"会让调用方无法判断该补什么。
    missing_identity = [name for name in IDENTITY_FIELDS if name not in manifest]
    if missing_identity:
        raise CandidateRegistryError(f"候选缺少身份字段: {', '.join(missing_identity)}")
    missing_metadata = [name for name in REQUIRED_METADATA_FIELDS if name not in manifest]
    if missing_metadata:
        raise CandidateRegistryError(f"manifest 缺少元数据字段: {', '.join(missing_metadata)}")

    for name in ("candidate_id", "candidate_version", "strategy_family"):
        value = manifest[name]
        _require(
            isinstance(value, str) and bool(value.strip()),
            f"{name} 必须是非空字符串",
        )
    # `code_sha` 与数据快照 ID 是身份的一部分：格式不对就无法证明"代码没变"。
    _check("code_sha", manifest["code_sha"], verify_hex_digest)
    _require(
        isinstance(manifest["research_data_snapshot_id"], str)
        and bool(manifest["research_data_snapshot_id"].strip()),
        "research_data_snapshot_id 必须是非空字符串",
    )
    _require(
        isinstance(manifest["cost_model_version"], str)
        and bool(manifest["cost_model_version"].strip()),
        "cost_model_version 必须是非空字符串",
    )

    # `created_at` 是一个**时刻**（UTC instant），不是一天。真实冻结候选的
    # `freeze_timestamp` 形如 `2026-09-11T12:55:14Z`——带时区、带时分秒。
    # 用 `parse_iso_date` 校验它必然失败，而那正是这些候选实际使用的格式；
    # 一个把真实 manifest 全部判为非法的契约不是契约，是障碍。
    _check("created_at", manifest["created_at"], require_timezone_aware_instant)
    # 只有 `formation_window` 与 `historical_holdout_window` 是窗口。
    # `forward_start` 在契约里与它们并列而**不是**其中的一部分：
    # 前瞻观察从一个确定的日期开始，不是一个区间。把它也当成窗口校验，
    # 等于要求每个候选申报一个"前瞻开始区间"——而样本外从来只有一个起点。
    for name in ("formation_window", "historical_holdout_window"):
        value = manifest[name]
        _require(
            isinstance(value, Mapping) and "start" in value and "end" in value,
            f"{name} 必须是含 start/end 的对象",
        )
        _check(f"{name}.start", value["start"], parse_iso_date)
        _check(f"{name}.end", value["end"], parse_iso_date)
    _check("forward_start", manifest["forward_start"], parse_iso_date)

    horizons = manifest["evaluation_horizons"]
    if not isinstance(horizons, Sequence) or isinstance(horizons, (str, bytes)) or not horizons:
        raise CandidateRegistryError("evaluation_horizons 必须是非空数组")
    if not all(isinstance(h, int) and h >= 2 for h in horizons):
        raise CandidateRegistryError("evaluation_horizons 的每个元素必须是 >=2 的整数")

    # 冻结之前见过的历史不能称为真正未见的样本外数据。
    holdout_end = parse_iso_date(
        manifest["historical_holdout_window"]["end"], label="historical_holdout_window.end"
    )
    forward_start = parse_iso_date(manifest["forward_start"], label="forward_start")
    if forward_start <= holdout_end:
        raise CandidateRegistryError(
            f"forward_start({manifest['forward_start']}) 必须晚于 historical_holdout_window.end"
            f"({manifest['historical_holdout_window']['end']})；否则前瞻观察与历史回测重叠，"
            "不能称为样本外"
        )

    # 参数搜索预算必须提前记录：事后写预算等于事后挑选参数。
    budget = (
        manifest["parameter_space"].get("search_budget")
        if isinstance(manifest["parameter_space"], Mapping)
        else None
    )
    if not isinstance(budget, int) or budget < 0:
        raise CandidateRegistryError(
            "parameter_space.search_budget 必须是 >=0 的整数（预先记录，不得事后补写）"
        )

    return identity_hash(manifest)


@dataclass
class Transition:
    """一次状态推进的不可变记录。"""

    candidate_id: str
    candidate_version: str
    from_state: str | None
    to_state: str
    at: str
    reason: str
    evidence_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_version": self.candidate_version,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "at": self.at,
            "reason": self.reason,
            "evidence_hash": self.evidence_hash,
        }


#: 这些推进必须附带 `evidence_hash`。
#:
#: 登记簿**不能**验证观察本身是否真实（那是 Phase 5/6 实验与独立审查的事），
#: 但它能拒绝一条没有任何证据指针的晋级记录。没有指针，"已成熟的前瞻观察"
#: 就无法被追溯——三个月后没人能指出那次判断依据的是什么。
#:
#: `REGISTERED` 刻意不在此列：登记只需要 manifest 本身完整，
#: 那时还不存在任何实验产物。
EVIDENCE_REQUIRED_TRANSITIONS = frozenset(
    {
        "HISTORICAL_TESTED",
        "EXECUTION_VERIFIED",
        "FROZEN",
        "SHADOW_ACTIVE",
        "REVIEW_ELIGIBLE",
        "RECOMMENDED_FOR_APPROVAL",
    }
)


@dataclass
class CandidateRegistry:
    """轻量候选登记簿：追加式 JSONL，无数据库，无服务。

    选 JSONL 而不是 SQLite 是刻意的：这个登记簿的价值在于**可被人逐行读、
    可被 git diff**。一旦它变成二进制数据库，"旧结果没有被替换"就得靠信任，
    而不是靠 `git log` 一眼看出来。

    不跟踪 `tacticore/` 冻结目录，也不写生产任何位置；调用方给出路径。"""

    path: Path
    _entries: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict, init=False)
    _transitions: list[Transition] = field(default_factory=list, init=False)
    _loaded: bool = field(default=False, init=False)

    def _load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            for lineno, line in enumerate(
                self.path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:  # pragma: no cover - 防御性
                    raise CandidateRegistryError(
                        f"{self.path}:{lineno} 不是合法 JSON；登记簿不得被手工编辑"
                    ) from exc
                kind = record.get("kind")
                if kind == "candidate":
                    key = (record["candidate_id"], record["candidate_version"])
                    self._entries[key] = record
                elif kind == "transition":
                    self._transitions.append(
                        Transition(**{k: v for k, v in record.items() if k != "kind"})
                    )
                else:
                    raise CandidateRegistryError(f"{self.path}:{lineno} 未知记录类型 {kind!r}")
        self._loaded = True

    def _append(self, record: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical_json(dict(record)) + "\n")

    def register(self, manifest: Mapping[str, Any]) -> tuple[str, bool]:
        """登记候选。返回 `(identity_hash, created)`。

        幂等：同一身份重复登记返回已存在的记录，`created=False`，
        **不是错误**——重复提交同一事实不该被当成事故。

        同一 `candidate_id` 但内容不同则拒绝：那不是重复提交，是试图
        原地修改一个已冻结的身份。"""
        self._load()
        digest = validate_manifest(manifest)
        key = (manifest["candidate_id"], manifest["candidate_version"])
        existing = self._entries.get(key)
        if existing is not None:
            if existing["identity_hash"] != digest:
                # 两种情况都落到这里，但含义不同，措辞必须分开：
                # 提交了一份**不同**的 manifest（内容真的变了），
                # 还是登记簿里的哈希本身被改过（历史被动过）。
                # 混成一句"不得原地修改"会让审查者无法判断该查哪一边。
                raise CandidateRegistryError(
                    f"候选 {key[0]}@{key[1]} 的身份哈希不符：已登记为 "
                    f"{existing['identity_hash'][:12]}…，本次提交为 {digest[:12]}…。"
                    "策略代码、输入或协议改变必须产生新的 candidate_version，不得原地修改"
                )
            return digest, False
        self._append(
            {
                "kind": "candidate",
                "candidate_id": manifest["candidate_id"],
                "candidate_version": manifest["candidate_version"],
                "identity_hash": digest,
                "manifest_hash": manifest_hash(manifest),
                "registered_at": _utc_now(),
                "manifest": dict(manifest),
            }
        )
        self._entries[key] = {"identity_hash": digest, "manifest_hash": manifest_hash(manifest)}
        self._transition(
            manifest["candidate_id"],
            manifest["candidate_version"],
            None,
            "PROPOSED",
            "候选登记",
            None,
        )
        return digest, True

    def _transition(
        self,
        candidate_id: str,
        candidate_version: str,
        from_state: str | None,
        to_state: str,
        reason: str,
        evidence_hash: str | None,
    ) -> None:
        """追加一条转移记录。**这是唯一写转移的地方。**

        内存与磁盘必须同时更新：`register` 调用它写入 PROPOSED，
        而同一个 `CandidateRegistry` 实例随后的 `state()` 必须看得见。
        只写磁盘的话，同一进程内刚登记的候选会被判为"未登记"——
        一个只在重启后才正确的登记簿，会让每个调用方都以为得先重开一次。"""
        record: dict[str, Any] = {
            "candidate_id": candidate_id,
            "candidate_version": candidate_version,
            "from_state": from_state,
            "to_state": to_state,
            "at": _utc_now(),
            "reason": reason,
            "evidence_hash": evidence_hash,
        }
        self._append({"kind": "transition", **record})
        self._transitions.append(Transition(**record))

    def state(self, candidate_id: str, candidate_version: str) -> str:
        """候选当前状态。由转移记录推出，而不是存一个可被覆盖的字段。"""
        self._load()
        states = [
            t.to_state
            for t in self._transitions
            if t.candidate_id == candidate_id and t.candidate_version == candidate_version
        ]
        if not states:
            raise CandidateRegistryError(f"候选 {candidate_id}@{candidate_version} 未登记")
        return states[-1]

    def advance(
        self,
        candidate_id: str,
        candidate_version: str,
        to_state: str,
        reason: str,
        evidence_hash: str | None = None,
    ) -> str:
        """推进状态。非法推进拒绝，不记录。

        `reason` 必填且不得为空：一次没有说明理由的状态变化，
        在三个月后与一次误操作无法区分。"""
        self._load()
        if (candidate_id, candidate_version) not in self._entries:
            raise CandidateRegistryError(f"候选 {candidate_id}@{candidate_version} 未登记")
        if to_state not in LIFECYCLE_STATES + TERMINAL_STATES + REOPENING_STATES:
            raise CandidateRegistryError(f"未知状态 {to_state!r}")
        if not reason or not reason.strip():
            raise CandidateRegistryError("状态推进必须给出 reason")
        current = self.state(candidate_id, candidate_version)
        allowed = ALLOWED_TRANSITIONS[current]
        if to_state not in allowed:
            raise CandidateRegistryError(
                f"{current} → {to_state} 不是合法推进（允许: {sorted(allowed) or '无'}）"
            )
        # 先判合法性，再判证据。顺序反了的话，一次跳步会被报成"缺少 evidence_hash"
        # ——那是在暗示"补一个哈希就能跳步"，而它不能。
        if to_state in EVIDENCE_REQUIRED_TRANSITIONS and evidence_hash is None:
            raise CandidateRegistryError(
                f"{current} → {to_state} 必须附带 evidence_hash；"
                "没有证据指针的晋级记录无法被独立审查追溯"
            )
        if evidence_hash is not None:
            _check("evidence_hash", evidence_hash, verify_hex_digest)
        self._transition(candidate_id, candidate_version, current, to_state, reason, evidence_hash)
        return to_state

    def history(self, candidate_id: str, candidate_version: str) -> list[Transition]:
        """完整转移历史，按时间顺序。用于独立审查。"""
        self._load()
        return [
            t
            for t in self._transitions
            if t.candidate_id == candidate_id and t.candidate_version == candidate_version
        ]

    def verify_identity(self, manifest: Mapping[str, Any]) -> str:
        """校验一份 manifest 与已登记身份一致。用于"参数是否被改过"的核对。"""
        self._load()
        key = (manifest["candidate_id"], manifest["candidate_version"])
        existing = self._entries.get(key)
        if existing is None:
            raise CandidateRegistryError(f"候选 {key[0]}@{key[1]} 未登记，无法核对身份")
        digest = validate_manifest(manifest)
        if digest != existing["identity_hash"]:
            raise CandidateRegistryError(
                f"候选 {key[0]}@{key[1]} 的身份哈希不符；内容在冻结后被改动"
            )
        return digest
