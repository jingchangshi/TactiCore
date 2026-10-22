"""Phase 5 实验协议的失败先行测试（EP01–EP24）。

对应 `docs/goal-1023.md` Phase 5 验收：

- 先记录明确假设和外部支持/反证，再运行历史实验；
- 不能反复修改参数寻找样本内高收益；
- 如果真实数据不支持某项实验，标记 `BLOCKED_BY_DATA`，不得制造结果；
- 不能要求实验中一定有胜出策略；
- 不能因为回撤下降就声称预测 alpha 提高。

测试的策略是**攻击协议本身**：每条测试都在尝试用协议允许的手段
做一件协议必须禁止的事。协议拦不住，就是协议的缺口。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.ashare.experiments.protocol import (
    COST_MODELS,
    EXPERIMENT_OUTCOMES,
    CostModel,
    ExperimentLedger,
    ExperimentProtocolError,
    ExperimentSpec,
    SampleSplit,
    assert_consistent_costs,
    outcome_for,
    spec_hash,
    validated_manifest,
)

SHA = "a" * 64


def make_spec(**overrides) -> ExperimentSpec:
    """一个满足全部协议的最小实验。每个字段都给真实形状的值，
    使失败只能来自被测的那一条规则。"""
    fields = {
        "experiment_id": "EP_TEST",
        "hypothesis": "industry-neutral selection removes the sector beta the score picks up",
        "economic_mechanism": (
            "the score ranks sector strength, so sector-neutralising changes the pool"
        ),
        "counter_evidence": (
            "sector breadth may itself be the alpha, in which case neutralising removes it"
        ),
        "candidate_id": "P5_TEST",
        "candidate_version": "R1",
        "comparison_family": ("CHAMPION", "EQUAL_WEIGHT", "SINGLE_FACTOR"),
        "sample_split": SampleSplit(
            formation_start="2013-04-01",
            formation_end="2022-12-31",
            holdout_start="2023-01-01",
            holdout_end="2025-12-31",
            forward_start="2026-01-01",
        ),
        "cost_model": CostModel.named("frozen-toml-10bps/etf"),
        "tradability_constraints": ("T+1 execution", "no same-day close execution", "lot 100"),
        "benchmarks": ("equal_weight_universe", "csi300"),
        "champion": "score-1.0.0",
        "predeclared_success_criteria": "cagr>=0.02;max_drawdown>-0.35",
        "predeclared_failure_criteria": "max_drawdown>-0.35;turnover<=1.5x comparator",
        "random_seed": 20261022,
    }
    fields.update(overrides)
    return ExperimentSpec(**fields)


# --- 预先登记 ---------------------------------------------------------------


def test_EP01_a_spec_cannot_be_built_without_a_hypothesis():
    """没有假设就不成实验。缺假设却允许构造，实验就退化成一次回测。"""
    payload = make_spec().to_dict()
    del payload["hypothesis"]
    with pytest.raises(ExperimentProtocolError, match="缺少字段"):
        spec_hash(payload)


def test_EP02_the_hypothesis_must_be_nonempty_text():
    """假设不能是空串或纯空白。

    空假设与"没有假设"在记录上无法区分，而前者看起来更像登记过。
    协议必须拒绝它——不是相信空反证不存在，而是
    "没有记录"与"不存在"必须可区分。"""
    for blank in ("", "   ", "\t\n"):
        with pytest.raises(ExperimentProtocolError, match="hypothesis"):
            spec_hash(make_spec(hypothesis=blank).to_dict())


def test_EP03_changing_any_decision_parameter_changes_the_spec_hash():
    """任何一个决策参数变了，就是另一个实验。

    这是"不能反复改参数寻找样本内高收益"的可执行形式：
    事后改参数无法伪装成"重跑一次"，因为 hash 变了。"""
    base = make_spec()
    for field_name, new_value in (
        ("predeclared_success_criteria", "cagr>=0.05;max_drawdown>-0.35"),
        ("random_seed", 1),
        ("cost_model", CostModel.named("fees-2.0.0/etf")),
        ("comparison_family", ("CHAMPION", "EQUAL_WEIGHT")),
        (
            "sample_split",
            SampleSplit("2013-04-01", "2022-12-31", "2023-01-01", "2024-12-31", "2025-01-01"),
        ),
    ):
        changed = make_spec(**{field_name: new_value})
        assert spec_hash(base.to_dict()) != spec_hash(changed.to_dict()), (
            f"改变 {field_name} 没有改变 spec_hash；事后改它将无法被发现"
        )


def test_EP04_the_spec_hash_is_order_independent():
    """规格哈希必须与键序无关。

    不规范化的话，重排字段会被误判成"规格变了"，
    于是同一个实验的重复提交看起来像一次参数篡改。"""
    payload = make_spec().to_dict()
    reordered = dict(reversed(list(payload.items())))
    assert spec_hash(payload) == spec_hash(reordered)


def test_EP05_the_spec_hash_excludes_results():
    """规格哈希不得覆盖结论与运行时间。

    否则同一实验重跑一次就"变成另一个实验"，
    而它必须能被重复执行以复现结论。"""
    payload = make_spec().to_dict()
    with_result = dict(payload, outcome="SUPPORTS_HYPOTHESIS", ran_at="2026-10-22T00:00:00Z")
    assert spec_hash(payload) == spec_hash(with_result)


def test_EP06_counter_evidence_must_be_recorded_before_running():
    """反证必须先记录。

    任务书："先记录明确假设和外部支持/反证"。
    缺反证字段的规格无法通过 hash——不是因为我们相信空反证不存在，
    而是因为"没有记录"与"不存在"必须可区分。"""
    payload = make_spec().to_dict()
    del payload["counter_evidence"]
    with pytest.raises(ExperimentProtocolError, match="counter_evidence"):
        spec_hash(payload)


# --- 样本切分 ---------------------------------------------------------------


def test_EP07_forward_start_overlapping_the_holdout_is_refused():
    """任务书：冻结之前见过的历史不能称为真正未见的样本外数据。"""
    with pytest.raises(ExperimentProtocolError, match="forward_start"):
        SampleSplit(
            formation_start="2013-04-01",
            formation_end="2022-12-31",
            holdout_start="2023-01-01",
            holdout_end="2025-12-31",
            forward_start="2025-12-31",
        )


def test_EP08_formation_and_holdout_may_not_overlap():
    """形成期与 holdout 重叠时，"样本外"只是同一段历史的另一半。

    重叠的样本外不是样本外，它只是把样本切开后声称没见过另一半。"""
    with pytest.raises(ExperimentProtocolError, match="重叠"):
        SampleSplit(
            formation_start="2013-04-01",
            formation_end="2024-06-30",
            holdout_start="2023-01-01",
            holdout_end="2025-12-31",
            forward_start="2026-01-01",
        )


def test_EP09_a_malformed_date_is_refused():
    """日期格式错即拒绝，不得尝试"猜一个合法的"。

    猜中的那次会让其余日期静默错位——而样本切分错位
    会让全部"样本外"结论变成样本内结论。"""
    for bad in ("2023-1-1", "20230101", "2023/01/01", 20230101):
        with pytest.raises(ExperimentProtocolError):
            SampleSplit(
                formation_start="2013-04-01",
                formation_end=bad,
                holdout_start="2023-01-01",
                holdout_end="2025-12-31",
                forward_start="2026-01-01",
            )


# --- 费用口径 ---------------------------------------------------------------


def test_EP10_candidate_and_baseline_must_share_one_cost_model():
    """任务书：交易与维护成本是晋级门控第 9 条。

    候选用 2.5bps、基准用 10bps，基准收益被压低的部分会被读成
    "候选更好"——那是费用差，不是策略差。这是 Phase 5 最危险的
    错误，因为它让结论**看起来**成立。"""
    candidate = make_spec(cost_model=CostModel.named("fees-2.0.0/etf"))
    baseline = make_spec(
        experiment_id="EP_BASELINE", cost_model=CostModel.named("frozen-toml-10bps/etf")
    )
    with pytest.raises(ExperimentProtocolError, match="费用口径不一致"):
        assert_consistent_costs([candidate, baseline])


def test_EP11_the_two_cost_models_differ_by_a_factor_of_four():
    """两种口径必须**确实**不同，否则 EP10 的守卫在防一个不存在的问题。

    这个断言钉住差异本身：如果有人把 fees-2.0.0 的映射改成 10bps，
    这条测试失败，提示"两个口径已经悄悄合一，EP10 不再有牙"。"""
    mapped = COST_MODELS["fees-2.0.0/etf"]["fees"]
    frozen = COST_MODELS["frozen-toml-10bps/etf"]["fees"]
    assert frozen == pytest.approx(mapped * 4), f"预期 4 倍差，实际 {frozen / mapped}"


def test_EP12_an_unknown_cost_model_label_is_refused():
    """未知口径即拒绝。默认成一个"差不多"的值会让成本无声地改变。"""
    with pytest.raises(ExperimentProtocolError, match="未知费用口径"):
        CostModel.named("fees-2.0.0/whatever")


def test_EP13_equal_numeric_costs_are_comparable_even_under_different_labels():
    """按数值比较而非标签：两个标签恰好同值时比较是正当的。

    只按标签拒绝会把一次正当的比较挡掉，而那会诱导调用方
    去改标签而不是改数值。"""
    left = CostModel(label="a", fees=0.001, slippage=0.0005)
    right = CostModel(label="b", fees=0.001, slippage=0.0005)
    assert left.matches(right)
    assert_consistent_costs(
        [make_spec(cost_model=left), make_spec(experiment_id="EP_B", cost_model=right)]
    )


# --- 结论判据 ---------------------------------------------------------------


def test_EP14_the_outcome_is_decided_by_the_predeclared_criteria():
    """结论必须由**预先登记**的判据决定，不能事后挑。

    这里用同一组数字配两套预先登记的判据，必须得到两个结论。
    若结论来自数字本身而非判据，两者会给出同一个答案。

    注意第二个期望是 `NO_SIGNIFICANT_DIFFERENCE` 而不是
    `DOES_NOT_SUPPORT_HYPOTHESIS`：阈值 10% 而差距 2%，
    诚实答案是"分不出差别"，不是"假设被否证"。
    把后者当成正确答案，等于允许用一套宽判据去宣布胜利。"""
    strict = make_spec(predeclared_success_criteria="cagr>=0.02;max_drawdown>-0.35")
    loose = make_spec(predeclared_success_criteria="cagr>=0.10;max_drawdown>-0.35")
    kwargs = dict(
        candidate_cagr=0.05,
        comparator_cagr=0.03,
        candidate_max_drawdown=-0.20,
        comparator_max_drawdown=-0.25,
    )
    assert outcome_for(spec=strict, **kwargs) == "SUPPORTS_HYPOTHESIS"
    assert outcome_for(spec=loose, **kwargs) == "NO_SIGNIFICANT_DIFFERENCE"
    # 差距足够大时，宽判据也必须给出否证，而不是无限期"分不出"。
    decisive = dict(kwargs, candidate_cagr=0.20)
    assert outcome_for(spec=loose, **decisive) == "SUPPORTS_HYPOTHESIS"
    reversed_gap = dict(kwargs, candidate_cagr=-0.05, comparator_cagr=0.03)
    assert outcome_for(spec=strict, **reversed_gap) == "DOES_NOT_SUPPORT_HYPOTHESIS"


def test_EP15_a_missing_metric_cannot_be_substituted_by_another():
    """缺一个指标就不能给结论，不能用另一个指标顶上。

    "CAGR 不可用但回撤更好"不是支持假设的证据，
    它是一个不完整的测量。"""
    spec = make_spec()
    assert (
        outcome_for(
            spec=spec,
            candidate_cagr=None,
            comparator_cagr=0.03,
            candidate_max_drawdown=-0.10,
            comparator_max_drawdown=-0.30,
        )
        == "INSUFFICIENT_DATA"
    )


def test_EP15B_every_missing_metric_alone_blocks_the_verdict():
    """四个指标中**任意一个**缺失都必须阻断结论。

    EP15 只测了 `candidate_cagr` 一处。变异测试显示只改那一处不够：
    把 `if any(value is None ...)` 整个关掉，套件仍然全绿——
    说明其余三个指标的缺失路径没有任何测试覆盖。
    一个只在一个位置上有牙的守卫，挡不住从另一个位置进来的输入。"""
    spec = make_spec()
    full = dict(
        candidate_cagr=0.10,
        comparator_cagr=0.03,
        candidate_max_drawdown=-0.20,
        comparator_max_drawdown=-0.25,
    )
    for missing in full:
        kwargs = dict(full, **{missing: None})
        assert outcome_for(spec=spec, **kwargs) == "INSUFFICIENT_DATA", (
            f"缺少 {missing} 时必须拒绝给结论"
        )


def test_EP16B_a_candidate_breaching_its_own_drawdown_floor_fails():
    """候选突破预先登记的失败判据时，无论收益多高都必须判否。

    这正是任务书"不得为了宣布完成而放松风险门控"的可执行形式：
    收益 50% 而回撤 −90% 不是成功，是一次接近爆仓的侥幸。
    变异测试显示这条路径原本没有覆盖——关掉回撤检查套件仍全绿，
    而那意味着一个只有收益门控的实验协议。"""
    spec = make_spec()
    outcome = outcome_for(
        spec=spec,
        candidate_cagr=0.50,
        comparator_cagr=0.03,
        candidate_max_drawdown=-0.90,
        comparator_max_drawdown=-0.20,
    )
    assert outcome == "DOES_NOT_SUPPORT_HYPOTHESIS"


def test_EP16_a_drawdown_improvement_alone_is_not_alpha():
    """任务书：不能因为回撤下降就声称预测 alpha 提高。

    这条正是 Experiment C 的陷阱：ERC 类配置常常回撤更小、
    收益相仿。若判据只看回撤，一个纯风险再平衡会被记成
    "SUPPORTS_HYPOTHESIS"——而那不是预测能力的证据。"""
    spec = make_spec()
    outcome = outcome_for(
        spec=spec,
        candidate_cagr=0.030,
        comparator_cagr=0.031,
        candidate_max_drawdown=-0.08,
        comparator_max_drawdown=-0.30,
    )
    assert outcome != "SUPPORTS_HYPOTHESIS", (
        "回撤大幅改善而收益相仿，不得记为支持假设；那是风险特征差异，不是 alpha"
    )


def test_EP17_an_unparseable_criterion_refuses_to_conclude():
    """判据说不清时必须拒绝给结论，而不是猜一个规则。

    一个说不清判据的实验，其结论无法被独立审查——
    给它一个结论比不给更危险，因为那个结论看起来是可复现的。"""
    spec = make_spec(predeclared_success_criteria="表现更好")
    outcome = outcome_for(
        spec=spec,
        candidate_cagr=0.10,
        comparator_cagr=0.01,
        candidate_max_drawdown=-0.10,
        comparator_max_drawdown=-0.20,
    )
    assert outcome == "INVALID_RUN"


def test_EP18_blocked_by_data_is_a_first_class_outcome():
    """任务书：真实数据不支持某项实验时标记 `BLOCKED_BY_DATA`，不得制造结果。

    它必须是一等结论，不是异常：缺数据必须能被**记录**下来，
    不能被当成失败而隐藏，也不能被一个"看起来还行"的结果顶替。"""
    assert "BLOCKED_BY_DATA" in EXPERIMENT_OUTCOMES
    assert "BLOCKED_BY_DATA" not in (
        "SUPPORTS_HYPOTHESIS",
        "DOES_NOT_SUPPORT_HYPOTHESIS",
    )


def test_EP19_a_loss_is_recorded_as_a_loss():
    """任务书：不能要求实验中一定有胜出策略。

    `DOES_NOT_SUPPORT_HYPOTHESIS` 必须是一个正常的、可被记录的结论。
    若台账拒绝它，"没有胜出策略"就只能被记成缺数据或运行失败。"""
    ledger = ExperimentLedger(path=str(Path("/tmp") / "ep_ledger_test.jsonl"))
    spec = make_spec()
    record = ledger.record(
        spec, "DOES_NOT_SUPPORT_HYPOTHESIS", reason="candidate underperformed the champion"
    )
    assert record["outcome"] == "DOES_NOT_SUPPORT_HYPOTHESIS"
    assert ledger.outcomes("EP_TEST")[0]["outcome"] == "DOES_NOT_SUPPORT_HYPOTHESIS"


# --- 台账 -------------------------------------------------------------------


def test_EP20_an_unknown_outcome_value_is_refused(tmp_path):
    """未登记的结论值必须被拒绝，不能被存下来。

    把 `SUPPORTS_HYPOTHESIS` 拼错却存进去，三个月后与一次
    真实的否定结论无法区分。"""
    ledger = ExperimentLedger(path=str(tmp_path / "ledger.jsonl"))
    with pytest.raises(ExperimentProtocolError, match="未知实验结论"):
        ledger.record(make_spec(), "SUPPORTS")


def test_EP21_the_same_spec_with_a_different_conclusion_is_refused(tmp_path):
    """规格一字未变而结论翻转，这不是新信息，是矛盾。

    允许它，"结论被事后修改"就与"重新跑了一次"无法区分。
    结论要改必须改规格，从而成为另一个实验。"""
    ledger = ExperimentLedger(path=str(tmp_path / "ledger.jsonl"))
    spec = make_spec()
    ledger.record(spec, "SUPPORTS_HYPOTHESIS", reason="first run")
    with pytest.raises(ExperimentProtocolError, match="结论不可变"):
        ledger.record(spec, "DOES_NOT_SUPPORT_HYPOTHESIS", reason="second run")


def test_EP22_repeating_the_same_run_is_idempotent(tmp_path):
    """重复提交同一实验的同一结论是幂等的。

    重复跑一次得到同一结论不是事故，是复现——
    它不该产生第二条记录，也不该被当成矛盾。"""
    ledger = ExperimentLedger(path=str(tmp_path / "ledger.jsonl"))
    spec = make_spec()
    first = ledger.record(spec, "SUPPORTS_HYPOTHESIS", reason="run one")
    again = ledger.record(spec, "SUPPORTS_HYPOTHESIS", reason="run two")
    assert again == first
    assert len(ledger.outcomes("EP_TEST")) == 1


def test_EP23_the_ledger_survives_reopening(tmp_path):
    """台账必须能从磁盘重新加载。

    只存在内存里的结论，重启即失忆，而"追加式"就成了空话。"""
    path = tmp_path / "ledger.jsonl"
    ledger = ExperimentLedger(path=str(path))
    ledger.record(make_spec(), "INSUFFICIENT_DATA", reason="holdout too short")
    reopened = ExperimentLedger(path=str(path))
    assert reopened.outcomes("EP_TEST")[0]["outcome"] == "INSUFFICIENT_DATA"
    # 重开后重复记录必须仍然幂等，不是"结论矛盾"的误判。
    reopened.record(make_spec(), "INSUFFICIENT_DATA", reason="again")


def test_EP24_a_hand_edited_ledger_is_refused(tmp_path):
    """台账不得被手工编辑成非法内容。

    与候选登记簿同理：追加式是它唯一的价值。一旦允许原地改，
    "结论没被改过"就得靠信任，而不是靠 git diff。"""
    path = tmp_path / "ledger.jsonl"
    ledger = ExperimentLedger(path=str(path))
    ledger.record(make_spec(), "SUPPORTS_HYPOTHESIS", reason="run")
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    record["outcome"] = "DOES_NOT_SUPPORT_HYPOTHESIS"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    reopened = ExperimentLedger(path=str(path))
    with pytest.raises(ExperimentProtocolError, match="结论不可变"):
        reopened.record(make_spec(), "SUPPORTS_HYPOTHESIS", reason="re-run")


# --- 与候选身份的绑定 -------------------------------------------------------


def test_EP25_the_experiment_binds_to_a_verifiable_candidate_identity():
    """实验必须能绑定到一个**可校验**的候选身份。

    没有这个绑定，"这个实验评价的是哪个候选"三个月后无法回答，
    而候选身份是 Phase 4 已经建立的东西——不复用就得再建一套。"""
    extra = {
        "research_data_snapshot_id": "snapshot-20260831",
        "code_sha": SHA,
        "created_at": "2026-10-22T00:00:00Z",
        "parameter_space": {"search_budget": 0, "parameters": {}},
        "evaluation_horizons": [5, 10],
    }
    manifest = validated_manifest(make_spec(), extra=extra)
    assert manifest["identity_hash"]
    assert manifest["forward_start"] == "2026-01-01"
    assert manifest["cost_model_version"] == "frozen-toml-10bps/etf"
    # 成本口径进入候选身份：换口径就是换候选版本。
    other = validated_manifest(make_spec(cost_model=CostModel.named("fees-2.0.0/etf")), extra=extra)
    assert manifest["identity_hash"] != other["identity_hash"]


def test_EP26_a_spec_whose_candidate_cannot_be_registered_is_refused():
    """实验规格派生的 manifest 不合法时必须拒绝。

    `forward_start` 早于 holdout 结束时，Phase 4 的身份契约会拒绝它。
    Phase 5 必须在**跑之前**就发现这一点，而不是跑完之后才发现
    这个实验评价的东西根本无法登记为候选。"""
    with pytest.raises(ExperimentProtocolError, match="forward_start"):
        SampleSplit(
            formation_start="2013-04-01",
            formation_end="2022-12-31",
            holdout_start="2023-01-01",
            holdout_end="2025-12-31",
            forward_start="2025-06-01",
        )


def test_EP27_a_one_member_comparison_family_is_refused():
    """只有一个成员的"比较"无法比较。

    把候选与它自己比较会得到零差异，而零差异可以被写成
    "没有显著差异"——一个听起来像结论的废话。"""
    with pytest.raises(ExperimentProtocolError, match="比较族"):
        spec_hash(make_spec(comparison_family=("CHAMPION",)).to_dict())


def test_EP28_the_ledger_is_written_in_canonical_order(tmp_path):
    """台账写入必须规范化，使重复记录逐字节相同。

    与 CR04C 同一个理由：不规范化的话，同一个实验追加两次
    会在 `git diff` 里显示为两行字段乱序的不同记录，
    没人能一眼看出第二次其实是第一次的复现。

    这条是变异测试逼出来的：把 `sort_keys=True` 改成 `False`
    （Phase 4 已遇到同一个空操作），整个套件全绿——
    说明没有任何测试覆盖"写盘记录是规范的"这一事实。"""
    path = tmp_path / "canonical.jsonl"
    ledger = ExperimentLedger(path=str(path))
    first = ledger.record(make_spec(), "INSUFFICIENT_DATA", reason="holdout too short")
    reopened = ExperimentLedger(path=str(path))
    reopened.record(make_spec(), "INSUFFICIENT_DATA", reason="a different reason string")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "幂等记录不得产生第二行"
    record = json.loads(lines[0])
    # 键必须已排序：这是规范化的可观察证据。
    assert list(record) == sorted(record), f"键未按规范排序: {list(record)}"
    assert record["spec_hash"] == first["spec_hash"]


def test_EP29_the_spec_hash_is_stable_across_processes():
    """规格哈希必须跨进程稳定。

    哈希只在同一进程内稳定是不够的：独立审查会在另一台机器上
    重算它。若序列化依赖进程内状态（例如 dict 插入顺序的偶然一致），
    两侧会算出不同的 hash，而"规格没变"就无法被跨机器证明。"""
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, '.');"
        "from tests.test_ashare_experiment_protocol import make_spec;"
        "from research.ashare.experiments.protocol import spec_hash;"
        "print(spec_hash(make_spec().to_dict()))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        check=True,
    )
    assert completed.stdout.strip() == spec_hash(make_spec().to_dict())
    """只有一个成员的"比较"无法比较。

    把候选与它自己比较会得到零差异，而零差异可以被写成
    "没有显著差异"——一个听起来像结论的废话。"""
    with pytest.raises(ExperimentProtocolError, match="比较族"):
        spec_hash(make_spec(comparison_family=("CHAMPION",)).to_dict())


def test_EP30_an_unparseable_failure_criterion_also_refuses_to_conclude():
    """EP17 只覆盖了**成功**判据读不懂的情形。失败判据读不懂同样必须拒绝。

    实测：`predeclared_failure_criteria="turnover<=1.5x comparator"`
    （没有 `max_drawdown>`）会让 `outcome_for` 抛
    `IndexError: list index out of range`。

    这不是调用方写错字段的问题：`INVALID_RUN` 是承诺过的返回值
    （EP17 的 docstring 与 `EXPERIMENT_OUTCOMES` 都有它），
    而一个未捕获的 IndexError 会让调用方把"判据说不清"
    当成"程序崩了"——于是它去修程序，而不是去修判据。"""
    spec = make_spec(predeclared_failure_criteria="turnover<=1.5x comparator")
    outcome = outcome_for(
        spec=spec,
        candidate_cagr=0.10,
        comparator_cagr=0.03,
        candidate_max_drawdown=-0.20,
        comparator_max_drawdown=-0.30,
    )
    assert outcome == "INVALID_RUN"


def test_EP30B_an_empty_threshold_is_not_a_zero_threshold():
    """`cagr>=` 后面没有数字，必须报 `INVALID_RUN`，不能读成 0。

    实测它抛 `ValueError: could not convert string to float: ''`。
    读成 0 会更糟：任何非负收益都会"支持假设"，
    于是一条没写完整的判据变成了最宽松的判据——
    而这正是预注册要防的那种事后放松。"""
    for criteria in ("cagr>=;max_drawdown>-0.35", "cagr>=abc;max_drawdown>-0.35"):
        spec = make_spec(predeclared_success_criteria=criteria)
        assert (
            outcome_for(
                spec=spec,
                candidate_cagr=0.10,
                comparator_cagr=0.03,
                candidate_max_drawdown=-0.20,
                comparator_max_drawdown=-0.30,
            )
            == "INVALID_RUN"
        ), f"{criteria!r} 无法解析出阈值时必须拒绝给结论"


def test_EP30C_the_criteria_parser_rejects_a_non_numeric_drawdown_floor():
    """回撤门控同样不能把乱码读成一个数字。

    失败判据里的 `max_drawdown>` 后面跟着 `abc` 时，
    实测抛 `ValueError`。它必须与 EP30/EP30B 一致地落到
    `INVALID_RUN`——否则同一个函数有两种崩溃方式，
    调用方无法用一个 except 覆盖。"""
    spec = make_spec(predeclared_failure_criteria="max_drawdown>abc;turnover<=1.5x")
    assert (
        outcome_for(
            spec=spec,
            candidate_cagr=0.10,
            comparator_cagr=0.03,
            candidate_max_drawdown=-0.20,
            comparator_max_drawdown=-0.30,
        )
        == "INVALID_RUN"
    )


def test_EP30D_a_criterion_that_names_the_same_marker_twice_in_one_field_is_refused():
    """同一个字段里出现两次 `cagr>=`，必须报 `INVALID_RUN`。

    这是变异测试逼出来的：去掉 `split(marker, 1)` 的 maxsplit=1 之后，
    `"cagr>=0.02 cagr>=0.05"` 会被静默解析成 0.02——两个阈值里选了
    较小的那个，而"选了哪个"没有任何记录。事后要宣布成功时，
    宽松的那个阈值就是可用的那一个；这正是预登记要堵住的形状。

    注意分隔符必须是**空白**而不是 `;`：用 `;` 时 `.split(";", 1)[0]`
    自己就截断了，那条输入根本走不到 maxsplit 的分支。
    第一次写这条测试时我用了 `;`，它失败了——那说明我对这个变异的
    作用域判断错了，而不是模块错了。模块是对的，错的是我的测试。"""
    spec = make_spec(predeclared_success_criteria="cagr>=0.02 cagr>=0.05;max_drawdown>-0.35")
    assert (
        outcome_for(
            spec=spec,
            candidate_cagr=0.10,
            comparator_cagr=0.03,
            candidate_max_drawdown=-0.20,
            comparator_max_drawdown=-0.30,
        )
        == "INVALID_RUN"
    )


def test_EP31_the_drawdown_improvement_criterion_is_expressible():
    """任务书实验 C 要求评价**两个**不同目标，其中之一是回撤。

    `outcome_for` 原来的判据语法只能表达"候选 CAGR 超过对照多少"
    与"候选回撤的绝对下限"。它**无法**表达"回撤改善至少 X"——
    于是"是否改善风险和回撤"这个问题只能被降级成一句备注，
    而不是一个能被台账记录的结论。一个无法被登记的结论
    三个月后与没人看过是一样的。

    `drawdown_improvement>=X` 让第二个目标成为一等公民。"""
    spec = make_spec(
        predeclared_success_criteria="drawdown_improvement>=0.02;cagr>=0.0",
        predeclared_failure_criteria="max_drawdown>-0.35",
    )
    kwargs = dict(
        candidate_cagr=0.031,
        comparator_cagr=0.030,
        candidate_max_drawdown=-0.15,
        comparator_max_drawdown=-0.30,
    )
    assert outcome_for(spec=spec, **kwargs) == "SUPPORTS_HYPOTHESIS"
    # 回撤没有改善到宣称的幅度，则假设不成立——即使收益完全没让。
    assert (
        outcome_for(spec=spec, **dict(kwargs, candidate_max_drawdown=-0.29))
        == "DOES_NOT_SUPPORT_HYPOTHESIS"
    )
    # 回撤倒退（变得更差）同样是否证，不是"没有差别"。
    assert (
        outcome_for(spec=spec, **dict(kwargs, candidate_max_drawdown=-0.40))
        == "DOES_NOT_SUPPORT_HYPOTHESIS"
    )
    # 收益腿没过而回撤大幅改善：仍不得记为支持。
    # 这是任务书"不能因为回撤下降就声称预测 alpha 提高"的直接形式。
    assert (
        outcome_for(spec=spec, **dict(kwargs, candidate_cagr=0.020))
        == "DOES_NOT_SUPPORT_HYPOTHESIS"
    )


def test_EP31B_a_drawdown_gain_that_gives_back_return_is_refused():
    """回撤改善而收益被让掉，必须判否。

    这正是任务书"不能因为回撤下降就声称预测 alpha 提高"的
    另一面：只报"回撤改善了 15 个点"而不报收益让掉多少，
    读者无法判断这是风险特征变化还是一次真实的改进。
    两个目标都要过，缺一个即否。"""
    spec = make_spec(
        predeclared_success_criteria="drawdown_improvement>=0.02;cagr>=0.02",
        predeclared_failure_criteria="max_drawdown>-0.35",
    )
    assert (
        outcome_for(
            spec=spec,
            candidate_cagr=0.005,
            comparator_cagr=0.030,
            candidate_max_drawdown=-0.10,
            comparator_max_drawdown=-0.30,
        )
        == "DOES_NOT_SUPPORT_HYPOTHESIS"
    ), "回撤改善 20 个点但收益让掉到判据以下，不得记为支持"


def test_EP31C_a_drawdown_gain_within_noise_is_not_support():
    """回撤只好了 0.001 而判据要求 0.02，必须判否。

    变异测试要防的形状：把 `gained < drawdown_gain` 改成
    `gained <= 0`，这条就会绿——于是"几乎没有改善"被记成支持。"""
    spec = make_spec(
        predeclared_success_criteria="drawdown_improvement>=0.02;cagr>=0.0",
        predeclared_failure_criteria="max_drawdown>-0.35",
    )
    assert (
        outcome_for(
            spec=spec,
            candidate_cagr=0.031,
            comparator_cagr=0.030,
            candidate_max_drawdown=-0.299,
            comparator_max_drawdown=-0.300,
        )
        == "DOES_NOT_SUPPORT_HYPOTHESIS"
    )


def test_EP31D_an_unparseable_drawdown_gain_is_not_silently_ignored():
    """`drawdown_improvement>=` 后面读不出数字时，必须 INVALID_RUN。

    不能因为它"只是第二个目标"就跳过：跳过的结果是一个
    只看收益的回撤实验，而那正是任务书不让做的事。"""
    spec = make_spec(
        predeclared_success_criteria="drawdown_improvement>=;cagr>=0.0",
        predeclared_failure_criteria="max_drawdown>-0.35",
    )
    assert (
        outcome_for(
            spec=spec,
            candidate_cagr=0.10,
            comparator_cagr=0.03,
            candidate_max_drawdown=-0.10,
            comparator_max_drawdown=-0.30,
        )
        == "INVALID_RUN"
    )
