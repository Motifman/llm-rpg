"""予期のパッケージが、環境やほかの層の概念を import せずに閉じていることを保証する。"""

from __future__ import annotations

import ast
from pathlib import Path

import ai_rpg_world.domain.memory.expectation as expectation_package

_PACKAGE_DIR = Path(expectation_package.__file__).resolve().parent
_ALLOWED_PREFIXES = (
    "ai_rpg_world.domain.memory.expectation",
    "ai_rpg_world.domain.being.value_object.being_id",
    "ai_rpg_world.domain.common.exception",
)


def _foreign_imports(source: str) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return [
        module
        for module in modules
        if module.startswith("ai_rpg_world")
        and not module.startswith(_ALLOWED_PREFIXES)
    ]


def test_detects_import_of_world_tick_and_application() -> None:
    """検査そのものが、世界の tick や application 層の import を拾えることを確かめる。"""
    source = (
        "from ai_rpg_world.domain.common.value_object import WorldTick\n"
        "import ai_rpg_world.application.llm\n"
    )

    assert _foreign_imports(source) == [
        "ai_rpg_world.domain.common.value_object",
        "ai_rpg_world.application.llm",
    ]


def test_package_imports_only_being_id_and_domain_exceptions() -> None:
    """domain/memory/expectation は自分自身と BeingId とドメイン例外の基底だけを import し、application / infrastructure や世界の tick を持ち込まない。"""
    sources = sorted(_PACKAGE_DIR.rglob("*.py"))

    violations = {
        str(path.relative_to(_PACKAGE_DIR)): found
        for path in sources
        if (found := _foreign_imports(path.read_text()))
    }

    assert len(sources) > 5
    assert violations == {}
