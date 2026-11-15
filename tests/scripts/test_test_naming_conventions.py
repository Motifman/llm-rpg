"""テスト名の可読性に関するリポジトリ規約を保証する。"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS_DIR = _REPO_ROOT / "tests"
_JAPANESE_RE = re.compile(r"[ぁ-んァ-ン一-龥]")
_DEF_TEST_NAME_RE = re.compile(r"def\s+(test_\w*)")


def _japanese_test_function_names(tests_dir: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(tests_dir.rglob("test_*.py")):
        source = path.read_text()
        # 全ファイルを ast で読むと CI で 10 秒かかる。名前に日本語のある def が無いファイルは読まない。
        if not any(_JAPANESE_RE.search(name) for name in _DEF_TEST_NAME_RE.findall(source)):
            continue
        for node in ast.walk(ast.parse(source, filename=str(path))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_") and _JAPANESE_RE.search(node.name):
                violations.append(f"{path.relative_to(tests_dir.parent)}:{node.lineno}:{node.name}")
    return violations


def test_function_names_are_english_only() -> None:
    """テスト関数名は英語の識別子だけにし、振る舞いの説明は日本語ドックストリングへ逃がす。"""
    assert _japanese_test_function_names(_TESTS_DIR) == []


def test_check_reports_japanese_names_but_not_japanese_docstrings(tmp_path: Path) -> None:
    """正の対照: 名前に日本語を含むテスト関数とクラスのメソッドは違反として出て、ドックストリングや文字列にだけ日本語を含む関数は出ない。"""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "def test_名前() -> None:\n"
        "    pass\n"
        "\n"
        "class TestSample:\n"
        "    def test_method_の名前(self) -> None:\n"
        "        pass\n"
        "\n"
        "def test_english() -> None:\n"
        '    """def test_日本語 はドックストリングの中なので数えない。"""\n',
        encoding="utf-8",
    )

    assert _japanese_test_function_names(tests_dir) == [
        "tests/test_sample.py:1:test_名前",
        "tests/test_sample.py:5:test_method_の名前",
    ]
