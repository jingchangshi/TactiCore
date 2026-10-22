"""ARM / VPS 兼容性诊断的失败先行测试（WP2.5）。

这些测试钉住的是**不许假装测过**：

- 没测过就必须是 `UNRESOLVED`，不能因为"看起来应该兼容"就给 `COMPATIBLE`；
- 关键项失败必须让整体分类变成 `NOT_COMPATIBLE`，不能平均掉；
- 存在已量化的成本差时必须是 `COMPATIBLE_WITH_CAVEAT`，不能说成"无差异"；
- 报告必须自带"本机结论不可外推到 VPS"的声明。

诊断本身要求真实 bundle，因此在没有本地 bundle 时相关用例明确跳过。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.ashare.engines.arm_portability import (
    COMPATIBLE,
    COMPATIBLE_WITH_CAVEAT,
    NOT_COMPATIBLE,
    UNRESOLVED,
    classify,
    environment_fingerprint,
    package_versions,
)

DEFAULT_BUNDLE = Path.home() / ".rqalpha/bundle"


def _has_bundle() -> bool:
    return DEFAULT_BUNDLE.is_dir() and (DEFAULT_BUNDLE / "instruments.pk").is_file()


def _probes(**overrides) -> dict:
    probes: dict = {
        "bundle_read": {"status": "PASSED"},
        "vectorbt": {"status": "PASSED"},
        "rqalpha": {"status": "PASSED"},
        "cross_engine": {"status": "PASSED"},
        "cost_caveat": {"status": "NOT_MEASURED"},
    }
    probes.update(overrides)
    return probes


# --------------------------------------------------------------------------------------
# 分类：没测过不能算兼容
# --------------------------------------------------------------------------------------


def test_AR01_an_unmeasured_critical_probe_is_unresolved_not_compatible() -> None:
    """关键项没测过必须是 UNRESOLVED。

    这是本模块最重要的一条：把"没测"写成"兼容"会让读者以为 ARM 已经验证过，
    而实际上只是没人去看。缺 bundle 时 `probe_*` 返回 NOT_MEASURED，
    分类必须把它变成 UNRESOLVED。
    """
    classification, reasons = classify(_probes(bundle_read={"status": "NOT_MEASURED"}))
    assert classification == UNRESOLVED
    assert any("bundle_read" in reason for reason in reasons)


def test_AR02_a_failed_critical_probe_is_not_compatible() -> None:
    """任一关键项失败必须让整体 NOT_COMPATIBLE，不能被其他通过项平均掉。"""
    classification, reasons = classify(_probes(rqalpha={"status": "FAILED"}))
    assert classification == NOT_COMPATIBLE
    assert any("rqalpha" in reason for reason in reasons)


def test_AR03_a_missing_probe_is_unresolved() -> None:
    """探测项整个缺失（键不存在）同样不得给 COMPATIBLE。"""
    probes = _probes()
    del probes["cross_engine"]
    classification, _ = classify(probes)
    assert classification == UNRESOLVED


def test_AR04_a_quantified_cost_gap_downgrades_to_a_caveat() -> None:
    """全部通过但存在实测成本差 => COMPATIBLE_WITH_CAVEAT。

    不能给 COMPATIBLE：那会让读者以为两个引擎可以互换使用，
    而实测差额（印花税与最低佣金被 RQAlpha 关掉）是真实存在的。
    """
    probes = _probes(
        cost_caveat={
            "status": "MEASURED",
            "gap_return_points": 1.7e-05,
            "gap_yuan": 1.3,
        }
    )
    classification, reasons = classify(probes)
    assert classification == COMPATIBLE_WITH_CAVEAT
    assert any("不可互换" in reason for reason in reasons)


def test_AR05_a_zero_gap_is_plain_compatible() -> None:
    """实测差额恰为 0 时给 COMPATIBLE，不硬造一个 caveat。"""
    probes = _probes(cost_caveat={"status": "MEASURED", "gap_return_points": 0.0, "gap_yuan": 0.0})
    classification, _ = classify(probes)
    assert classification == COMPATIBLE


# --------------------------------------------------------------------------------------
# 环境指纹：必须如实记录，不得把非 ARM 机器说成 ARM
# --------------------------------------------------------------------------------------


def test_AR06_the_environment_fingerprint_reports_the_real_machine() -> None:
    """`is_aarch64` 必须由 platform.machine() 推出，不能硬编码 True。

    硬编码 True 会让报告在 x86 机器上冒充 ARM 实测结论。
    """
    import platform

    fingerprint = environment_fingerprint()
    assert fingerprint["machine"] == platform.machine()
    assert fingerprint["is_aarch64"] is (platform.machine() in {"aarch64", "arm64"})
    assert fingerprint["python_version"]


def test_AR07_the_blas_backend_is_recorded() -> None:
    """BLAS/LAPACK 必须被记录：跨平台数值分歧的主要来源就是它。"""
    fingerprint = environment_fingerprint()
    blas = fingerprint["blas_lapack"]
    assert blas["available"] is True
    assert blas.get("blas")


def test_AR08_package_versions_record_none_instead_of_guessing() -> None:
    """未安装的包记为 None，不用占位字符串冒充版本号。"""
    versions = package_versions()
    assert "numpy" in versions
    assert "rqalpha" in versions
    # 明确不存在的包必须给出 None，而不是 "unknown" 之类看起来像版本的值。
    assert versions.get("definitely_not_a_real_package_xyz") is None


# --------------------------------------------------------------------------------------
# 真实 bundle 上的探测（无 bundle 则明确跳过）
# --------------------------------------------------------------------------------------


def test_AR09_the_real_bundle_probe_passes_on_this_machine() -> None:
    """真实 bundle 必须能在本机构造成价格矩阵。"""
    if not _has_bundle():
        pytest.skip(f"本地 RQAlpha bundle 不存在: {DEFAULT_BUNDLE}")
    from research.ashare.engines.arm_portability import probe_bundle_read

    result = probe_bundle_read(DEFAULT_BUNDLE)
    assert result["status"] == "PASSED", result
    assert result["price_rows"] > 1
    assert result["nan_cells"] == 0, "该窗口的 bundle 数据应完整"


def test_AR10_both_engines_run_on_this_machine() -> None:
    """VectorBT 与 RQAlpha 都必须在本机跑出有限结果。"""
    if not _has_bundle():
        pytest.skip(f"本地 RQAlpha bundle 不存在: {DEFAULT_BUNDLE}")
    from research.ashare.engines.arm_portability import probe_rqalpha, probe_vectorbt

    vectorbt = probe_vectorbt(DEFAULT_BUNDLE)
    rqalpha = probe_rqalpha(DEFAULT_BUNDLE)
    assert vectorbt["status"] == "PASSED", vectorbt
    assert vectorbt["all_finite"] is True
    assert rqalpha["status"] == "PASSED", rqalpha
    assert rqalpha["rqalpha_version"]


def test_AR11_the_report_states_it_cannot_speak_for_the_vps() -> None:
    """报告必须自带"本机结论不可外推到 VPS"的声明。

    这条测试防的是一个很实际的误用：把本机 ARM 结果当成 Oracle VPS 的
    验收证据。本诊断没有 VPS 访问权，结论的适用范围必须写进报告本身。
    """
    if not _has_bundle():
        pytest.skip(f"本地 RQAlpha bundle 不存在: {DEFAULT_BUNDLE}")
    from research.ashare.engines.arm_portability import run_diagnostic

    report = run_diagnostic(DEFAULT_BUNDLE)
    assert "artifacts_modified" in report
    assert report["artifacts_modified"] == []
    assert "VPS" in report["vps_note"]
    assert "未访问" in report["vps_note"]
    # 不得声称跨架构数值等价：那需要第二个架构的对照运行。
    assert "NUMERICALLY_EQUIVALENT" in report["scope"]
    assert report["classification"] in {
        COMPATIBLE,
        COMPATIBLE_WITH_CAVEAT,
        NOT_COMPATIBLE,
        UNRESOLVED,
    }
