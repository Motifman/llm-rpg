"""使われなくなった記憶の種類が本番の宣言へ戻らないことを検査する。"""

import ast
from pathlib import Path

from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind


def test_semantic_is_not_a_declared_memory_kind() -> None:
    """MemoryKindは現役の3種類だけを持ち、SEMANTICという別名も持たない。"""
    assert set(MemoryKind.__members__) == {"SHORT_TERM", "EPISODIC", "MEMO"}
    assert {kind.value for kind in MemoryKind} == {"short_term", "episodic", "memo"}


def test_production_has_no_semantic_enum_access() -> None:
    """srcとscriptsにSEMANTICメンバーを参照する式を残さず、遅延実行時の属性エラーを防ぐ。"""
    root = Path(__file__).resolve().parents[2]
    references = []
    for directory in (root / "src", root / "scripts"):
        for path in directory.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Attribute) and node.attr == "SEMANTIC":
                    references.append(f"{path.relative_to(root)}:{node.lineno}")
    assert references == []
