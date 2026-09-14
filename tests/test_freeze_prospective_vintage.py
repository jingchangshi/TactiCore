"""前瞻 vintage snapshot 编排的 fail-closed 守卫测试（不下载、不接触真实 2026-09 数据）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import build_candidate_repo, write_prospective_vintage

from research.experiments import freeze_prospective_vintage as freeze


class _UnusedApi:
    """守卫在下载之前就会失败；任何 API 调用都说明顺序错误。"""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"守卫失败前不得调用 Tushare endpoint: {name}")


def test_unknown_candidate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="未知 candidate"):
        freeze.freeze_vintage(_UnusedApi(), candidate_id="X_R9", as_of="2026-09-30", root=tmp_path)


def test_pre_cutoff_as_of_is_rejected_before_download(tmp_path: Path) -> None:
    root = build_candidate_repo(tmp_path / "repo", "S2_R1")

    with pytest.raises(ValueError, match="historical_cutoff"):
        freeze.freeze_vintage(_UnusedApi(), candidate_id="S2_R1", as_of="2026-08-31", root=root)


def test_existing_vintage_directory_refuses_overwrite(tmp_path: Path) -> None:
    root = build_candidate_repo(tmp_path / "repo", "S2_R1")
    write_prospective_vintage(
        root / "research/shadow/s2_r1/vintages/2026-09-30", as_of="2026-09-30"
    )

    with pytest.raises(ValueError, match="拒绝覆盖"):
        freeze.freeze_vintage(_UnusedApi(), candidate_id="S2_R1", as_of="2026-09-30", root=root)


def test_snapshot_target_is_the_candidate_canonical_vintage_path() -> None:
    assert freeze.CANDIDATES == {
        "S2_R1": "research/shadow/s2_r1",
        "S4C_R1": "research/shadow/s4c_r1",
    }
