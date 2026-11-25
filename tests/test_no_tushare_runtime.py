"""所有者 2026-11-25 指令：现行代码不得再依赖 Tushare（数据源已退役）。

只扫描现行代码路径；历史证据（research/results、research/batches/transfer_v1 等冻结域）
提到 Tushare 是历史出处，不在此断言范围内。
"""

from __future__ import annotations

import ast
from pathlib import Path

import tomli

ROOT = Path(__file__).resolve().parents[1]
SCANNED_ROOTS = ("tacticore", "research/experiments", "research/ashare", "tests")
FORBIDDEN_MODULES = ("tushare", "tacticore.data.tushare")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _is_forbidden(module: str) -> bool:
    return any(module == name or module.startswith(name + ".") for name in FORBIDDEN_MODULES)


def test_current_code_does_not_import_tushare() -> None:
    offenders: list[str] = []
    for relative_root in SCANNED_ROOTS:
        for path in sorted((ROOT / relative_root).rglob("*.py")):
            for module in _imported_modules(path):
                if _is_forbidden(module):
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}: {module}")
    assert offenders == []


def test_tushare_client_module_is_removed() -> None:
    assert not (ROOT / "tacticore/data/tushare.py").exists()


def test_project_dependencies_exclude_tushare() -> None:
    project = tomli.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(extra)
    assert not [spec for spec in declared if spec.strip().lower().startswith("tushare")]
    assert "tushare" not in (ROOT / "uv.lock").read_text(encoding="utf-8").lower()
