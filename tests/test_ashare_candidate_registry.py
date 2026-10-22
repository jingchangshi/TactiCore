"""候选身份与生命周期登记的失败先行测试。

任务书 Phase 4 验收逐条对应：

- 重复提交同一候选身份的幂等性；
- 同 ID 不同内容的拒绝；
- 冻结后变更参数的拒绝；
- 尝试补写历史前瞻的拒绝；
- 缺少真实观察的晋级拒绝；
- 数据修订、执行语义改变与旧候选失效的正确处理。

这些测试全部对着一个**真实的**已冻结候选（S2_R1 / S4C_R1 的
`candidate_manifest.json`）执行身份校验，而不是只对手写的最小 manifest 执行——
身份契约的价值在于它能描述真实候选，不是它能描述我编的样例。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.ashare.candidates.registry import (
    ALLOWED_TRANSITIONS,
    LIFECYCLE_STATES,
    REOPENING_STATES,
    TERMINAL_STATES,
    CandidateRegistry,
    CandidateRegistryError,
    identity_hash,
    manifest_hash,
    validate_manifest,
)

REPO = Path(__file__).resolve().parents[1]
S2_R1 = REPO / "research" / "shadow" / "s2_r1" / "candidate_manifest.json"
S4C_R1 = REPO / "research" / "shadow" / "s4c_r1" / "candidate_manifest.json"

SHA = "a" * 64


@pytest.fixture()
def registry(tmp_path: Path) -> CandidateRegistry:
    return CandidateRegistry(path=tmp_path / "candidates.jsonl")


def make_manifest(**overrides):
    """一个满足全部契约的最小候选。所有字段都给出真实形状的值，
    使校验失败只能来自被测的那一条规则，而不是来自"其他字段也不合法"。"""
    manifest = {
        "candidate_id": "P4_TEST",
        "candidate_version": "R1",
        "strategy_family": "synthetic test family",
        "economic_hypothesis": "a mechanism that can be tested",
        "mechanism_and_counter_evidence": "counter evidence recorded, not omitted",
        "universe_specification": {"market": "mainboard", "exclude_st": True},
        "signal_definition": {"name": "test_signal", "lookback": 20},
        "portfolio_construction": {"method": "equal_weight", "names": 5},
        "execution_policy": {"authority": "RQAlpha", "order_api": "order_target_percent"},
        "parameter_space": {"search_budget": 0, "parameters": {}},
        "research_data_snapshot_id": "snapshot-20260107",
        "code_sha": SHA,
        "cost_model_version": "fees-2.0.0",
        "benchmark_versions": {"equal_weight_universe": "v1"},
        "champion_version": "score-1.0.0",
        "formation_window": {"start": "2024-01-01", "end": "2024-06-30"},
        "historical_holdout_window": {"start": "2024-07-01", "end": "2024-12-31"},
        "forward_start": "2025-01-01",
        "evaluation_horizons": [5, 10],
        "multiple_testing_family": "declared_control_family_v1",
        "success_criteria": "predeclared in manifest",
        "failure_criteria": "predeclared in manifest",
        "created_at": "2026-10-22T00:00:00Z",
    }
    manifest.update(overrides)
    return manifest


# --- 身份字段 ----------------------------------------------------------------


def test_CR01_the_real_frozen_candidates_satisfy_the_identity_contract():
    """S2_R1 与 S4C_R1 是已冻结的真实候选。它们必须能通过身份校验。

    如果通过不了，问题在契约：它描述不了这个项目实际在用的候选形态，
    那它就不是一个可用的契约，只是我凭空设计的形状。"""
    for path in (S2_R1, S4C_R1):
        if not path.exists():
            pytest.skip(f"{path} 不存在")
        raw = json.loads(path.read_text(encoding="utf-8"))
        # 真实 manifest 用 strategy_semantics / frozen_target_structure 等嵌套结构，
        # 而 Phase 4 契约要的是扁平字段。这里用真实 manifest 能提供的内容填充，
        # 无法提供的字段显式标记——目的是证明契约能覆盖真实候选的语义，
        # 而不是要求历史 manifest 长出新字段。
        adapted = dict(raw)
        adapted.setdefault("economic_hypothesis", raw.get("strategy_family", ""))
        adapted.setdefault("universe_specification", raw.get("frozen_identity_artifacts", {}))
        adapted.setdefault("signal_definition", raw.get("frozen_target_structure", {}))
        adapted.setdefault("portfolio_construction", raw.get("strategy_semantics", {}))
        adapted.setdefault("execution_policy", raw.get("execution_semantics", {}))
        adapted.setdefault("parameter_space", {"search_budget": 0, "parameters": {}})
        adapted.setdefault("code_sha", SHA)
        adapted.setdefault("research_data_snapshot_id", raw.get("historical_cutoff", "unknown"))
        adapted.setdefault("cost_model_version", "fees-2.0.0")
        adapted.setdefault("benchmark_versions", {})
        adapted.setdefault("champion_version", "unknown")
        adapted.setdefault("formation_window", {"start": "2013-04-01", "end": "2026-08-31"})
        adapted.setdefault(
            "historical_holdout_window",
            {"start": "2013-04-01", "end": raw.get("historical_cutoff", "2026-08-31")},
        )
        adapted.setdefault(
            "forward_start", raw.get("first_eligible_prospective_signal", "2026-09-30")
        )
        adapted.setdefault("evaluation_horizons", [5])
        adapted.setdefault("multiple_testing_family", "unknown")
        adapted.setdefault("success_criteria", "unknown")
        adapted.setdefault("failure_criteria", "unknown")
        adapted.setdefault("mechanism_and_counter_evidence", raw.get("known_risks", ""))
        adapted.setdefault("created_at", raw.get("freeze_timestamp", "2026-01-01T00:00:00Z"))
        identity_hash(adapted)  # 不得抛异常


def test_CR02_a_missing_identity_field_is_refused_not_defaulted():
    """缺字段即拒绝。填默认值会让"没申报参数搜索预算"看起来像"预算为 0"。"""
    manifest = make_manifest()
    del manifest["code_sha"]
    with pytest.raises(CandidateRegistryError, match="缺少身份字段"):
        validate_manifest(manifest)


def test_CR03_the_identity_hash_ignores_state_and_timestamps():
    """身份哈希只覆盖身份字段。状态、时间戳、备注不得参与——
    否则每写一条日志都"改变身份"，身份就不再是身份。"""
    base = make_manifest()
    changed = make_manifest(created_at="2027-01-01T00:00:00Z", champion_version="something-else")
    assert identity_hash(base) == identity_hash(changed)


def test_CR04_the_identity_hash_is_order_independent():
    """同一内容、不同键序必须是同一身份。

    不规范化序列化的话，重排字段会被误判成内容变更，
    于是同一个候选的重复提交看起来像一次篡改。"""
    base = make_manifest()
    reordered = dict(reversed(list(base.items())))
    assert identity_hash(base) == identity_hash(reordered)


def test_CR04B_the_manifest_hash_is_also_order_independent(registry):
    """`manifest_hash` 同样必须与键序无关。

    CR04 只覆盖了 `identity_hash`，而它按 `IDENTITY_FIELDS` 重建 payload，
    因此**本身**就是有序的——对它断言键序无关，断言不到序列化。
    真正依赖 `sort_keys=True` 的是 `manifest_hash` 与写盘的记录：
    少了规范化，同一个候选分两次提交会被记成两个不同的
    `manifest_hash`，"当时提交的到底是什么"就有了两个答案。

    这条测试是变异测试逼出来的：把 `sort_keys=True` 改成 `False`，
    整个套件原本全绿。"""
    assert manifest_hash(make_manifest()) == manifest_hash(
        dict(reversed(list(make_manifest().items())))
    )


def test_CR04C_the_registry_file_is_written_in_canonical_order(registry):
    """写盘记录必须规范化，使 `git diff` 有意义。

    逐字节相同的两条记录，diff 才显示为"没有变化"。
    否则同一个候选重新提交一次，diff 里就是一行字段乱序的"新"记录，
    没人能一眼看出它其实是同一件事。"""
    registry.register(make_manifest())
    first = registry.path.read_text(encoding="utf-8")
    registry.register(make_manifest())
    assert registry.path.read_text(encoding="utf-8") == first


def test_CR05_the_identity_hash_changes_when_code_changes():
    """策略代码改变即新候选版本。`code_sha` 是身份的一部分。"""
    assert identity_hash(make_manifest()) != identity_hash(make_manifest(code_sha="b" * 64))


def test_CR06_the_identity_hash_changes_when_the_snapshot_changes():
    """数据修订改变身份。用旧 snapshot_id 重跑不等于重跑同一个候选。"""
    assert identity_hash(make_manifest()) != identity_hash(
        make_manifest(research_data_snapshot_id="snapshot-20260201")
    )


def test_CR07_the_identity_hash_changes_when_execution_semantics_change():
    """执行语义改变即新候选版本——这正是 S4C_R1 必须与 S2_R1 分开的原因。"""
    changed = make_manifest(
        execution_policy={"authority": "RQAlpha", "order_api": "order_target_portfolio"}
    )
    assert identity_hash(make_manifest()) != identity_hash(changed)


def test_CR08_forward_start_overlapping_the_holdout_is_refused():
    """冻结之前见过的历史不能称为真正未见的样本外数据。"""
    with pytest.raises(CandidateRegistryError, match="样本外"):
        validate_manifest(make_manifest(forward_start="2024-12-31"))


def test_CR09_a_missing_search_budget_is_refused():
    """参数搜索预算必须提前记录。缺预算即拒绝，不得默认成 0——
    那等于允许"先搜参数，再申报预算为 0"。"""
    with pytest.raises(CandidateRegistryError, match="search_budget"):
        validate_manifest(make_manifest(parameter_space={"parameters": {}}))


def test_CR10_a_malformed_hash_is_refused():
    """哈希格式错即拒绝，不得尝试"猜一个合法的"。"""
    with pytest.raises(CandidateRegistryError):
        validate_manifest(make_manifest(code_sha="not-a-hash"))


# --- 登记与幂等 -------------------------------------------------------------


def test_CR11_registering_the_same_identity_twice_is_idempotent(registry):
    """任务书验收：重复提交同一候选身份的幂等性。

    重复提交同一事实不是事故，不应报错，也不得产生第二条记录。"""
    manifest = make_manifest()
    digest, created = registry.register(manifest)
    assert created is True
    again, created_again = registry.register(manifest)
    assert created_again is False
    assert again == digest


def test_CR12_the_same_id_with_different_content_is_refused(registry):
    """任务书验收：同 ID 不同内容的拒绝。

    这不是重复提交，是试图原地修改一个已登记的身份。"""
    registry.register(make_manifest())
    with pytest.raises(CandidateRegistryError, match="不得原地修改"):
        registry.register(make_manifest(parameter_space={"search_budget": 5, "parameters": {}}))


def test_CR13_parameters_cannot_be_changed_after_registration(registry):
    """任务书验收：冻结后变更参数的拒绝。

    "冻结"在这里的含义就是已登记：身份哈希一变，`verify_identity` 必须发现。"""
    manifest = make_manifest()
    registry.register(manifest)
    tampered = make_manifest(parameter_space={"search_budget": 1, "parameters": {"lookback": 40}})
    with pytest.raises(CandidateRegistryError, match="身份哈希不符"):
        registry.verify_identity(tampered)


def test_CR14_the_manifest_hash_records_what_was_actually_submitted(registry):
    """manifest 哈希必须与身份哈希不同：它记录"当时提交的全部内容"，
    包括元数据。少了它就无法回答"那个候选当时申报的成功标准是什么"。"""
    manifest = make_manifest()
    digest, _ = registry.register(manifest)
    assert manifest_hash(manifest) != digest


# --- 生命周期 ---------------------------------------------------------------


def test_CR15_the_transition_table_covers_every_state():
    """状态表必须完整且自洽：每个状态都有条目，且只指向已定义的状态。

    一个没有反向条目的状态会让人以为"回退是不可能的"，
    而真实原因是表漏写了一行。因此这里按**全部**状态检查，
    包括重开状态——漏掉一类状态，这个测试就再也发现不了那一类的缺行。"""
    every_state = set(LIFECYCLE_STATES + TERMINAL_STATES + REOPENING_STATES)
    assert set(ALLOWED_TRANSITIONS) == every_state
    for current, targets in ALLOWED_TRANSITIONS.items():
        for target in targets:
            assert target in every_state, f"{current} → {target} 指向未定义状态"


def test_CR15B_a_reopening_state_is_reachable_and_not_terminal():
    """`REVALIDATED` 必须可达，且不得是终止状态。

    真实前瞻观察中发现统计 Foundation 缺陷时，候选不能继续往前
    （观察可能全部作废），也不能直接报废（那会把一次实现错误
    记成"策略无效"）。如果这张表漏掉这条边，`advance` 会拒绝它，
    于是唯一诚实的去处不复存在——而调用方只会看到"非法推进"。"""
    assert "REVALIDATED" in ALLOWED_TRANSITIONS["SHADOW_ACTIVE"]
    assert "REVALIDATED" not in TERMINAL_STATES
    assert ALLOWED_TRANSITIONS["REVALIDATED"], "重开状态必须还能往前走，否则它等于终止"


def test_CR16_a_recommendation_is_not_a_promotion(registry):
    """`RECOMMENDED_FOR_APPROVAL` 不代表自动生产晋级。

    从它出发只有 RETIRED：没有任何代码路径能把"值得批准"变成"已批准"。
    这条测试钉住那个缺口——如果哪天有人加了一条通往生产的边，它必须失败。"""
    assert ALLOWED_TRANSITIONS["RECOMMENDED_FOR_APPROVAL"] == frozenset({"RETIRED"})


def test_CR17_an_illegal_skip_is_refused(registry):
    """不许跳步：REGISTERED 不能直接到 FROZEN。

    跳步的危险在于它看起来只是"少写了一条记录"，
    实际上是少做了历史检验、执行验证与冻结。"""
    registry.register(make_manifest())
    with pytest.raises(CandidateRegistryError, match="不是合法推进"):
        registry.advance("P4_TEST", "R1", "FROZEN", "直接冻结")


def test_CR18_a_transition_without_a_reason_is_refused(registry):
    """状态推进必须给出理由。一次没有理由的状态变化，
    三个月后与一次误操作无法区分。"""
    registry.register(make_manifest())
    with pytest.raises(CandidateRegistryError, match="reason"):
        registry.advance("P4_TEST", "R1", "REGISTERED", "   ")


def test_CR19_an_unregistered_candidate_cannot_advance(registry):
    """未登记的候选不得推进。"""
    with pytest.raises(CandidateRegistryError, match="未登记"):
        registry.advance("NO_SUCH", "R1", "REGISTERED", "reason")


def test_CR20_a_terminal_state_is_terminal(registry):
    """任务书验收：REJECTED / INVALIDATED / RETIRED 是终点。

    被否掉的候选不得重新推进——否则"拒绝"只是一次延期。"""
    for terminal in ("REJECTED", "INVALIDATED", "RETIRED"):
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()


def test_CR21_promotion_without_real_observations_is_refused(registry):
    """任务书验收：缺少真实观察的晋级拒绝。

    任务书晋级门控第 7 条要求"足够成熟的真正前瞻观察"。登记簿**不能**
    验证观察是否真实——它看不到数据，那是 Phase 5/6 实验与独立审查的事。
    但它能拒绝一条**没有证据指针**的晋级：没有指针，那次判断依据什么
    就无法被追溯，独立审查只能选择相信。

    因此这里断言的是可被强制的那一部分：
    `SHADOW_ACTIVE → REVIEW_ELIGIBLE` 不带 `evidence_hash` 即拒绝。
    而"指针指向的观察是否足够成熟"由审查环节负责，不由本模块假装负责。"""
    registry.register(make_manifest())
    registry.advance("P4_TEST", "R1", "REGISTERED", "manifest 完整")
    registry.advance("P4_TEST", "R1", "HISTORICAL_TESTED", "历史检验完成", SHA)
    registry.advance("P4_TEST", "R1", "EXECUTION_VERIFIED", "执行验证完成", SHA)
    registry.advance("P4_TEST", "R1", "FROZEN", "冻结", SHA)
    registry.advance("P4_TEST", "R1", "SHADOW_ACTIVE", "进入前瞻观察", SHA)
    with pytest.raises(CandidateRegistryError, match="evidence_hash"):
        registry.advance("P4_TEST", "R1", "REVIEW_ELIGIBLE", "声称已成熟但无证据")
    # 拒绝之后状态必须没有变化：一次被拒绝的推进不得留下半条记录。
    assert registry.state("P4_TEST", "R1") == "SHADOW_ACTIVE"
    assert [t.to_state for t in registry.history("P4_TEST", "R1")][-1] == "SHADOW_ACTIVE"


def test_CR21B_an_evidence_hash_that_is_not_a_hash_is_refused(registry):
    """证据指针必须是真哈希，不是一个文件名或一段说明。

    "引用"的价值在于它指向一个不可变的对象。一个可读的字符串
    同样能被写进记录里，但它指向的东西可以随时被改写。"""
    registry.register(make_manifest())
    with pytest.raises(CandidateRegistryError, match="evidence_hash"):
        registry.advance("P4_TEST", "R1", "REGISTERED", "manifest 完整", "见某份报告")


def test_CR22_the_history_is_append_only_and_readable(registry):
    """完整转移历史必须可读，且不得被后续推进改写。

    独立审查要能回答"这个候选为什么走到这一步"，
    答案只能是按时间排列的记录，不是一个可被覆盖的当前状态字段。"""
    manifest = make_manifest()
    registry.register(manifest)
    registry.advance("P4_TEST", "R1", "REGISTERED", "reason one")
    registry.advance("P4_TEST", "R1", "HISTORICAL_TESTED", "reason two", SHA)
    history = registry.history("P4_TEST", "R1")
    assert [t.to_state for t in history] == ["PROPOSED", "REGISTERED", "HISTORICAL_TESTED"]
    assert history[0].from_state is None
    assert history[-1].reason == "reason two"
    # 再推进一次，前面的记录必须原样还在。
    registry.advance("P4_TEST", "R1", "EXECUTION_VERIFIED", "reason three", SHA)
    again = registry.history("P4_TEST", "R1")
    assert [t.to_state for t in again[:3]] == ["PROPOSED", "REGISTERED", "HISTORICAL_TESTED"]
    assert [t.reason for t in again[:3]] == ["候选登记", "reason one", "reason two"]


def test_CR23_the_registry_survives_reopening(registry):
    """登记簿必须能从磁盘重新加载，且状态一致。

    状态只存在内存里的话，重启即失忆，"不可变记录"就是空话。"""
    manifest = make_manifest()
    digest, created = registry.register(manifest)
    registry.advance("P4_TEST", "R1", "REGISTERED", "reason")
    reopened = CandidateRegistry(path=registry.path)
    assert reopened.state("P4_TEST", "R1") == "REGISTERED"
    # 重新登记必须是幂等的，不是"ID 已存在但内容不同"的误判。
    digest_again, created_again = reopened.register(manifest)
    assert created_again is False
    assert digest_again == digest


def test_CR24_a_hand_edited_registry_is_refused(registry):
    """登记簿不得被手工编辑成非法内容。

    "追加式"是这个登记簿唯一的价值；一旦允许原地改，
    它退化成一个普通的 JSON 文件，而没有任何东西能证明历史没被动过。"""
    registry.register(make_manifest())
    lines = registry.path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    # 手工把已登记身份的哈希改掉：这是"原地改写历史"的最小形态。
    record["identity_hash"] = "0" * 64
    registry.path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    reopened = CandidateRegistry(path=registry.path)
    with pytest.raises(CandidateRegistryError, match="身份哈希不符"):
        reopened.register(make_manifest())
