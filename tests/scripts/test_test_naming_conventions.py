"""テスト名の可読性に関するリポジトリ規約を保証する。"""

from __future__ import annotations

import ast
import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS_DIR = _REPO_ROOT / "tests"
_JAPANESE_RE = re.compile(r"[ぁ-んァ-ン一-龥]")


def _test_functions() -> list[tuple[Path, ast.FunctionDef]]:
    functions: list[tuple[Path, ast.FunctionDef]] = []
    for path in sorted(_TESTS_DIR.rglob("test_*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                functions.append((path, node))
    return functions


def test_function_names_are_english_only() -> None:
    """テスト関数名は英語の識別子だけにし、振る舞いの説明は日本語ドックストリングへ逃がす。"""
    violations = [
        f"{path.relative_to(_REPO_ROOT)}:{node.lineno}:{node.name}"
        for path, node in _test_functions()
        if _JAPANESE_RE.search(node.name)
    ]

    assert violations == []
