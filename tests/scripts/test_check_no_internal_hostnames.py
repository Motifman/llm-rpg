"""scripts/check_no_internal_hostnames.sh をシェル経由で実行する統合テスト。"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHELL_TEST = Path(__file__).with_suffix(".sh")


def _ensure_executable(path: Path) -> None:
    """テストランナーの環境で +x が落ちている場合に備えて補正。"""
    st = path.stat().st_mode
    path.chmod(st | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.mark.skipif(
    not (_REPO_ROOT / "scripts" / "check_no_internal_hostnames.sh").exists(),
    reason="hostname check script not present in this checkout",
)
def test_check_no_internal_hostnames_shell_scenarios_すべて_passed() -> None:
    """安全 / 漏洩 / allow-listed / staged モードを bash シェルで end-to-end 確認する。"""
    _ensure_executable(_SHELL_TEST)
    result = subprocess.run(
        ["bash", str(_SHELL_TEST)],
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    assert result.returncode == 0, (
        f"shell scenarios failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


@pytest.mark.skipif(
    not (_REPO_ROOT / "scripts" / "check_no_internal_hostnames.sh").exists(),
    reason="hostname check script not present in this checkout",
)
def test_リポジトリ全体は_漏洩パターン無しで_passed() -> None:
    """本リポジトリ自身が漏洩パターンを含まないことを継続的に保証する (CI gate)。"""
    script = _REPO_ROOT / "scripts" / "check_no_internal_hostnames.sh"
    _ensure_executable(script)
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"hostname leak detected in repo. Fix and re-run.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
