"""受控 Challenger 实验协议（Phase 5 / WP5.1–WP5.3）。

本模块回答一个问题：**一次比较实验在跑之前，必须已经固定了什么**。
它不运行策略、不算收益、不挑赢家——那是 runner 与独立审查的事。

设计约束（`docs/goal-1023.md` Phase 5）：

1. **先记录假设，再运行历史实验。** 因此假设与对照集合在结构上先于
   `results`：`ExperimentSpec` 无法在产出之后才被构造出来（它要 hash 自身）。
2. **不能反复改参数寻找样本内高收益。** 因此 `spec_hash` 覆盖全部决策参数；
   任何一个数字变了，hash 就变，`register` 会把它当成**另一个实验**，
   而不是同一个实验的新版本。事后挑参数因此无法伪装成"重跑一次"。
3. **如果真实数据不支持某项实验，标记 `BLOCKED_BY_DATA`，不得制造结果。**
   因此 `BlockedByData` 是一等返回值，不是异常；缺数据必须能被记录，
   不能被当成失败而隐藏。

费用口径：本模块**不**统一两个既有费用模型，而是要求每个实验显式声明用哪一个。
`fees-2.0.0`（FinanceMCP 权威，ETF 佣金 2.5bps）与冻结 TOML 的 10bps
相差 4 倍。把候选用一种、基准用另一种，会让成本差异看起来像策略差异——
那比不做实验更糟。因此 `cost_model` 是身份字段，且 `assert_consistent_costs`
在任何比较前先核对双方口径。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from research.ashare.candidates.registry import (
    CandidateRegistryError,
    _canonical_json,
    identity_hash,
    validate_manifest,
)

EXPERIMENT_MODULE_VERSION = "ashare-experiment-protocol-1.0.0"

#: 实验结论的完整取值。与 Phase 3 诊断的结论分类**不同**：诊断回答
#: "表现为什么是这样"，实验回答 "这个假设在被比较时是否成立"。
#: 两者不得混用——一个 `NO_SIGNIFICANT_INCREMENTAL_FACTOR` 的实验结论
#: 与一个同名的诊断结论不是一回事。
EXPERIMENT_OUTCOMES = (
    "SUPPORTS_HYPOTHESIS",
    "DOES_NOT_SUPPORT_HYPOTHESIS",
    "NO_SIGNIFICANT_DIFFERENCE",
    "INSUFFICIENT_DATA",
    "BLOCKED_BY_DATA",
    "INVALID_RUN",
)

#: 数据不足与实现错误必须分开。`BLOCKED_BY_DATA` 是"这个问题用现有数据
#: 无法回答"，`INVALID_RUN` 是"这次运行本身不可信"。混成一类会让
#: 一个算错的实验看起来像一次诚实的"数据不够"。
TERMINAL_OUTCOMES = (
    "SUPPORTS_HYPOTHESIS",
    "DOES_NOT_SUPPORT_HYPOTHESIS",
    "NO_SIGNIFICANT_DIFFERENCE",
)

#: 实验规格的身份字段。**每个**影响结论的数字都必须在这里。
#: 少一个，事后改它就不会改变 spec_hash，"参数没被事后挑选"就无法被证明。
SPEC_IDENTITY_FIELDS = (
    "experiment_id",
    "hypothesis",
    "economic_mechanism",
    "counter_evidence",
    "candidate_id",
    "candidate_version",
    "comparison_family",
    "sample_split",
    "cost_model",
    "tradability_constraints",
    "benchmarks",
    "champion",
    "predeclared_success_criteria",
    "predeclared_failure_criteria",
    "random_seed",
)

#: 已在本仓库使用的两种费用口径。列出来是为了让选择成为**显式的决定**，
#: 而不是某个配置文件里的默认值。
#:
#: 值的类型标注是刻意的：`fees` / `slippage` 是 `float`，其余是说明文字。
#: 不分开标注的话，`float(entry["fees"])` 会在静态检查里报
#: "object 不可转 float"——而那个报错是对的，它在说
#: "这张表混装了数字与文本，读者无法一眼看出哪个是费率"。
COST_MODELS: Mapping[str, dict[str, Any]] = {
    # FinanceMCP `fees-2.0.0` 权威映射（research/ashare/data/fee_mapping.py）。
    "fees-2.0.0/etf": {
        "fees": 0.00025,
        "slippage": 0.0005,
        "authority": "FinanceMCP src/portfolio/rules.ts DEFAULT_FEE_RULES",
        "note": "ETF 佣金万 2.5，无印花税、无过户费，滑点万 5。",
    },
    # 冻结 baseline 使用的口径（config/*.toml）。
    "frozen-toml-10bps/etf": {
        "fees": 0.001,
        "slippage": 0.0005,
        "authority": "TactiCore config/*.toml（S1/S2/S4/S8/S27/S30 冻结运行）",
        "note": "佣金 10bps。比 fees-2.0.0 贵 4 倍；用于与冻结结果可比。",
    },
}


#: 必须是非空白文本的规格字段。空假设与"没有假设"在记录上无法区分，
#: 而前者看起来更像登记过——这正是任务书要防的"没有预先记录假设"。
NON_BLANK_SPEC_FIELDS = (
    "experiment_id",
    "hypothesis",
    "economic_mechanism",
    "counter_evidence",
    "candidate_id",
    "candidate_version",
    "champion",
    "predeclared_success_criteria",
    "predeclared_failure_criteria",
)


class ExperimentProtocolError(ValueError):
    """实验协议被违反：假设未预先登记、对照集合被事后修改、或成本口径不一致。"""


def _require(predicate: bool, message: str) -> None:
    if not predicate:
        raise ExperimentProtocolError(message)


def spec_hash(spec: Mapping[str, Any]) -> str:
    """实验规格的 SHA-256。

    只覆盖 `SPEC_IDENTITY_FIELDS`。结果、结论、运行时间**不在内**——
    否则同一实验重跑一次就"变成另一个实验"，而它必须能被重复执行。

    刻意复用 `_canonical_json` 而不是另写一个序列化：两套规范化函数
    迟早会给出两种字节序，那时"内容没变"就无法被证明。"""
    missing = [name for name in SPEC_IDENTITY_FIELDS if name not in spec]
    if missing:
        raise ExperimentProtocolError(f"实验规格缺少字段: {', '.join(missing)}")
    for name in NON_BLANK_SPEC_FIELDS:
        value = spec[name]
        _require(
            isinstance(value, str) and bool(value.strip()),
            f"{name} 必须是非空白文本；空白假设与'没有假设'在记录上无法区分",
        )
    _require(
        len(spec["comparison_family"]) >= 2,
        "比较族至少要有一个候选与一个基准；只有一个成员的'比较'无法比较",
    )
    payload = {name: spec[name] for name in SPEC_IDENTITY_FIELDS}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CostModel:
    """一次实验的费用口径。两个字段都必须显式给出。

    `label` 指向 `COST_MODELS` 中的一个键，使口径可被核对而不是被信任；
    `fees` / `slippage` 冗余存储，因为它们必须与标签一致——
    只存标签的话，标签对应的表被改了，历史实验的费率就静默变了。"""

    label: str
    fees: float
    slippage: float

    @classmethod
    def named(cls, label: str) -> CostModel:
        try:
            entry = COST_MODELS[label]
        except KeyError as error:
            raise ExperimentProtocolError(
                f"未知费用口径 {label!r}；已知: {sorted(COST_MODELS)}"
            ) from error
        return cls(label=label, fees=float(entry["fees"]), slippage=float(entry["slippage"]))

    def matches(self, other: CostModel) -> bool:
        """口径是否等价。按**数值**比较，不按标签：两个标签可能恰好同值，
        而"恰好同值"就应当允许比较。"""
        return self.fees == other.fees and self.slippage == other.slippage

    def describe(self) -> str:
        entry = COST_MODELS.get(self.label, {})
        return (
            f"{self.label}: fees={self.fees} slippage={self.slippage}"
            f"（权威来源: {entry.get('authority', '未知')}）"
        )


@dataclass(frozen=True)
class SampleSplit:
    """样本时间切分。三段全部显式，且不许重叠。

    任务书："冻结之前见过的历史不能称为真正未见的样本外数据"。
    因此 `forward_start` 必须严格晚于 `holdout_end`——这条与候选 manifest
    是同一条规则，在这里再查一次是因为实验可以独立于候选被构造。"""

    formation_start: str
    formation_end: str
    holdout_start: str
    holdout_end: str
    forward_start: str

    def __post_init__(self) -> None:
        for name in (
            "formation_start",
            "formation_end",
            "holdout_start",
            "holdout_end",
            "forward_start",
        ):
            value = getattr(self, name)
            _require(
                isinstance(value, str) and len(value) == 10 and value[4] == "-",
                f"SampleSplit.{name} 必须是 YYYY-MM-DD 形式的字符串，得到 {value!r}",
            )
        _require(
            self.formation_start <= self.formation_end,
            "形成期起点必须不晚于终点",
        )
        _require(
            self.holdout_start <= self.holdout_end,
            "holdout 起点必须不晚于终点",
        )
        _require(
            self.formation_end < self.holdout_start,
            "形成期与 holdout 不得重叠；重叠的'样本外'不是样本外",
        )
        _require(
            self.holdout_end < self.forward_start,
            f"forward_start({self.forward_start}) 必须严格晚于 "
            f"holdout_end({self.holdout_end})；否则前瞻观察与历史回测重叠",
        )


@dataclass(frozen=True)
class ExperimentSpec:
    """一次比较实验的预先登记。

    这个对象**不能**在结果出来之后被构造：它要 hash 自身，
    而 hash 覆盖全部决策参数。事后改任何一个数字都会得到不同的
    `digest`，于是"我只是重跑了一次"不再成立。
    """

    experiment_id: str
    hypothesis: str
    economic_mechanism: str
    counter_evidence: str
    candidate_id: str
    candidate_version: str
    comparison_family: tuple[str, ...]
    sample_split: SampleSplit
    cost_model: CostModel
    tradability_constraints: tuple[str, ...]
    benchmarks: tuple[str, ...]
    champion: str
    predeclared_success_criteria: str
    predeclared_failure_criteria: str
    random_seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "economic_mechanism": self.economic_mechanism,
            "counter_evidence": self.counter_evidence,
            "candidate_id": self.candidate_id,
            "candidate_version": self.candidate_version,
            "comparison_family": list(self.comparison_family),
            "sample_split": {
                "formation_start": self.sample_split.formation_start,
                "formation_end": self.sample_split.formation_end,
                "holdout_start": self.sample_split.holdout_start,
                "holdout_end": self.sample_split.holdout_end,
                "forward_start": self.sample_split.forward_start,
            },
            "cost_model": {
                "label": self.cost_model.label,
                "fees": self.cost_model.fees,
                "slippage": self.cost_model.slippage,
            },
            "tradability_constraints": list(self.tradability_constraints),
            "benchmarks": list(self.benchmarks),
            "champion": self.champion,
            "predeclared_success_criteria": self.predeclared_success_criteria,
            "predeclared_failure_criteria": self.predeclared_failure_criteria,
            "random_seed": self.random_seed,
        }

    def digest(self) -> str:
        return spec_hash(self.to_dict())


def assert_consistent_costs(specs: Sequence[ExperimentSpec]) -> None:
    """一组参与同一比较的实验必须用同一费用口径。

    这是本模块最重要的守卫。候选用 2.5bps、基准用 10bps，
    基准的收益被压低的部分会被读成"候选更好"——而那是费用差，
    不是策略差。任务书"交易与维护成本"是晋级门控第 9 条，
    而口径不一致会让第 9 条的核查得出反向结论。

    按数值比较而非标签：两个不同标签恰好同值时，比较是正当的。"""
    _require(len(specs) >= 1, "至少要有一个实验规格")
    first = specs[0].cost_model
    for other in specs[1:]:
        _require(
            first.matches(other.cost_model),
            f"费用口径不一致：{first.describe()} 与 {other.cost_model.describe()}。"
            "同一比较中的候选与基准必须用同一套费用，否则成本差会被误读成策略差",
        )


def _parse_criterion(criteria: str, marker: str) -> float | None:
    """从预先登记的判据文本中取出 `marker` 后面的数字。

    读不出来返回 `None`，由调用方统一转成 `INVALID_RUN`。
    刻意**不**在这里抛异常：三条判据路径（成功、失败、以及未来新增的）
    必须只有一种失败方式，调用方才能用一个分支覆盖全部。
    也刻意不把空串读成 0.0——那会让 `cagr>=` 变成"任意非负收益即支持"，
    而一条没写完整的判据不该变成最宽松的判据。

    `split(marker, 1)` 的 maxsplit=1 是有意的：marker 出现第二次时，
    不限次数的 `split(marker)[1]` 会截在第二个 marker 前，于是一条
    "cagr>=0.02;cagr>=0.05" 这种自相矛盾的判据被**静默**解析成 0.02。
    截住之后它变成不可解析，返回 `None` → `INVALID_RUN`。
    任务书要求"判据说不清就拒绝给结论"，两个阈值正是说不清。

    这里没有 `.strip()`：`float()` 自己就吃掉首尾空白（含 `\\t`、NBSP），
    加一层会让读者以为空白是需要处理的边界情况，而它不是。"""
    if marker not in criteria:
        return None
    fragment = criteria.split(marker, 1)[1].split(";", 1)[0]
    try:
        return float(fragment)
    except ValueError:
        return None


def outcome_for(
    *,
    candidate_cagr: float | None,
    comparator_cagr: float | None,
    candidate_max_drawdown: float | None,
    comparator_max_drawdown: float | None,
    spec: ExperimentSpec,
) -> str:
    """按**预先登记**的判据给出结论。判据不在本函数里，在 spec 里。

    本函数刻意不读取任何绩效数字之外的信息：它不重算收益、不看子区间、
    不挑表现最好的对照组。允许它挑，就等于允许它事后选择比较对象。

    返回 `EXPERIMENT_OUTCOMES` 中的一个。`None` 输入一律
    `INSUFFICIENT_DATA`——缺一个指标就不能给结论，不能用另一个指标顶上。"""
    required = (
        candidate_cagr,
        comparator_cagr,
        candidate_max_drawdown,
        comparator_max_drawdown,
    )
    if any(value is None for value in required):
        return "INSUFFICIENT_DATA"
    if not all(isinstance(value, (int, float)) for value in required):
        return "INSUFFICIENT_DATA"
    # 判据以文本预先登记，本函数只做**可复核**的解释，不做自由裁量。
    # 若判据文本无法被解析成明确规则，返回 INVALID_RUN 而不是猜一个规则：
    # 一个说不清判据的实验，其结论无法被独立审查。
    #
    # 解析必须对**两条**判据都失败才返回 INVALID_RUN。只保护成功判据的
    # `split(...)[1]` 会在失败判据读不懂时抛 IndexError/ValueError——
    # EP30 系列测试实测到的正是那样。一个未捕获的异常会让调用方以为
    # "程序崩了"，于是它去修程序，而该修的是判据。
    threshold = _parse_criterion(spec.predeclared_success_criteria, "cagr>=")
    drawdown_floor = _parse_criterion(spec.predeclared_failure_criteria, "max_drawdown>")
    if threshold is None or drawdown_floor is None:
        return "INVALID_RUN"
    # 第二个目标：回撤**改善幅度**。任务书实验 C 要求评价两个不同目标，
    # 只支持"收益差多少"的语法无法把"是否改善风险和回撤"记成一个结论，
    # 于是它只能退化成一句没人会复核的备注。
    #
    # 它出现与否都合法：不写 `drawdown_improvement>=` 的实验不因此失效
    # （例如纯收益实验），但写了就必须能解析。半途放弃解析会让一个
    # "只看收益的回撤实验"通过——那正是任务书不让做的事。
    drawdown_gain = _parse_criterion(spec.predeclared_success_criteria, "drawdown_improvement>=")
    if "drawdown_improvement>=" in spec.predeclared_success_criteria and drawdown_gain is None:
        return "INVALID_RUN"
    assert candidate_cagr is not None and comparator_cagr is not None
    assert candidate_max_drawdown is not None and comparator_max_drawdown is not None
    if candidate_max_drawdown <= drawdown_floor:
        return "DOES_NOT_SUPPORT_HYPOTHESIS"
    if candidate_cagr >= comparator_cagr + threshold:
        # 收益腿过了。第二个目标（回撤改善幅度）单独判：
        # 过则支持，不过则否证——不是"分不出差别"。回撤是负数，
        # 所以"改善"是向上比较（-0.10 优于 -0.30）。
        gained = candidate_max_drawdown - comparator_max_drawdown
        if drawdown_gain is None or gained >= drawdown_gain:
            return "SUPPORTS_HYPOTHESIS"
        return "DOES_NOT_SUPPORT_HYPOTHESIS"
    if candidate_cagr <= comparator_cagr - threshold:
        return "DOES_NOT_SUPPORT_HYPOTHESIS"
    return "NO_SIGNIFICANT_DIFFERENCE"


@dataclass
class ExperimentLedger:
    """追加式实验台账：一次实验一条记录，不可原地改。

    与候选登记簿同样选 JSONL：实验结论必须能被逐行读、被 git diff。
    一个能被 UPDATE 的结论不是结论，是一段当前意见。"""

    path: str
    _records: list[dict[str, Any]] = field(default_factory=list, init=False)
    _loaded: bool = field(default=False, init=False)

    def _load(self) -> None:
        if self._loaded:
            return
        import os

        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as handle:
                for lineno, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        self._records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise ExperimentProtocolError(
                            f"{self.path}:{lineno} 不是合法 JSON；台账不得被手工编辑"
                        ) from exc
        self._loaded = True

    def _append(self, record: Mapping[str, Any]) -> None:
        import os

        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(_canonical_json(dict(record)) + "\n")

    def record(
        self,
        spec: ExperimentSpec,
        outcome: str,
        *,
        evidence_hash: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """登记一次实验结果。同一 spec 重复记录同一结论是幂等的。

        `outcome` 必须是 `EXPERIMENT_OUTCOMES` 之一。未登记的结论值
        （例如把 `SUPPORTS_HYPOTHESIS` 拼错）必须被拒绝，而不是被存下来——
        一个说不清的结论三个月后与一次笔误无法区分。"""
        self._load()
        if outcome not in EXPERIMENT_OUTCOMES:
            raise ExperimentProtocolError(
                f"未知实验结论 {outcome!r}；已知: {list(EXPERIMENT_OUTCOMES)}"
            )
        digest = spec.digest()
        for existing in self._records:
            if existing["spec_hash"] == digest:
                # 同一实验的重复记录必须是同一结论。结论从支持翻成不支持，
                # 而规格一字未变，这不是新信息，是矛盾——必须被拒绝。
                if existing["outcome"] != outcome:
                    raise ExperimentProtocolError(
                        f"实验 {spec.experiment_id} 的规格未变但结论从 "
                        f"{existing['outcome']} 变为 {outcome}；规格不变则结论不可变，"
                        "结论要改必须改规格并成为另一个实验"
                    )
                return existing
        record = {
            "kind": "experiment",
            "experiment_id": spec.experiment_id,
            "spec_hash": digest,
            "outcome": outcome,
            "reason": reason,
            "evidence_hash": evidence_hash,
            "module_version": EXPERIMENT_MODULE_VERSION,
        }
        self._append(record)
        self._records.append(record)
        return record

    def outcomes(self, experiment_id: str) -> list[dict[str, Any]]:
        """某个实验的全部记录，按追加顺序。用于独立审查。"""
        self._load()
        return [r for r in self._records if r["experiment_id"] == experiment_id]


def candidate_manifest_for(spec: ExperimentSpec, *, extra: Mapping[str, Any]) -> dict[str, Any]:
    """由实验规格派生一份候选 manifest。

    这不是在造新候选，而是在检查"这个实验要评价的东西能否被登记"。
    返回的 manifest 交给 `validate_manifest` 校验；校验失败说明
    实验规格本身不完整（例如没申报参数搜索预算），那必须在跑之前发现。

    `extra` 提供 manifest 中不由实验规格决定的字段（`code_sha`、
    `research_data_snapshot_id` 等）。刻意要求调用方显式传入：
    这些字段是身份的一部分，默认值会让"没申报代码版本"看起来像"版本为空"。"""
    return {
        "candidate_id": spec.candidate_id,
        "candidate_version": spec.candidate_version,
        "strategy_family": spec.experiment_id,
        "economic_hypothesis": spec.hypothesis,
        "mechanism_and_counter_evidence": spec.counter_evidence,
        "universe_specification": dict(extra.get("universe_specification", {})),
        "signal_definition": dict(extra.get("signal_definition", {})),
        "portfolio_construction": dict(extra.get("portfolio_construction", {})),
        "execution_policy": dict(extra.get("execution_policy", {})),
        "parameter_space": dict(extra.get("parameter_space", {})),
        "research_data_snapshot_id": extra["research_data_snapshot_id"],
        "code_sha": extra["code_sha"],
        "cost_model_version": spec.cost_model.label,
        "benchmark_versions": {name: spec.champion for name in spec.benchmarks},
        "champion_version": spec.champion,
        "formation_window": {
            "start": spec.sample_split.formation_start,
            "end": spec.sample_split.formation_end,
        },
        "historical_holdout_window": {
            "start": spec.sample_split.holdout_start,
            "end": spec.sample_split.holdout_end,
        },
        "forward_start": spec.sample_split.forward_start,
        "evaluation_horizons": list(extra.get("evaluation_horizons", [5, 10])),
        "multiple_testing_family": spec.experiment_id,
        "success_criteria": spec.predeclared_success_criteria,
        "failure_criteria": spec.predeclared_failure_criteria,
        "created_at": extra["created_at"],
    }


def manifest_digest(spec: ExperimentSpec, *, extra: Mapping[str, Any]) -> str:
    """实验对应候选的身份哈希。用于把实验结果绑定到一个不可变身份。"""
    manifest = candidate_manifest_for(spec, extra=extra)
    try:
        return identity_hash(manifest)
    except CandidateRegistryError as error:
        raise ExperimentProtocolError(
            f"实验 {spec.experiment_id} 的候选 manifest 不合法: {error}"
        ) from error


def validated_manifest(spec: ExperimentSpec, *, extra: Mapping[str, Any]) -> dict[str, Any]:
    """同 `manifest_digest`，但返回校验后的 manifest 本身（含身份哈希）。"""
    manifest = candidate_manifest_for(spec, extra=extra)
    manifest = dict(manifest)
    manifest["identity_hash"] = validate_manifest(manifest)
    return manifest


__all__ = [
    "COST_MODELS",
    "EXPERIMENT_MODULE_VERSION",
    "EXPERIMENT_OUTCOMES",
    "TERMINAL_OUTCOMES",
    "CostModel",
    "ExperimentLedger",
    "ExperimentProtocolError",
    "ExperimentSpec",
    "SampleSplit",
    "assert_consistent_costs",
    "candidate_manifest_for",
    "manifest_digest",
    "outcome_for",
    "spec_hash",
    "validated_manifest",
]
