"""``ai_rpg_world.being`` がゲームのパッケージを import しないことを見張る。

移し替え (#1469) が終わるまでは、``ai_rpg_world.domain.being`` だけを
一時的な例外として許す。例外は移し替えの PR ごとに減らし、最後に消す。契約 (``being.contract``) には例外を適用しない。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BEING_ROOT = _REPO_ROOT / "src/ai_rpg_world/being"
_CONTRACT_ROOT = _BEING_ROOT / "contract"

_TEMPORARY_EXCEPTIONS = (
    "ai_rpg_world.domain.being",
)


def _is_within(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _imported_modules(path: Path, package: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(node, package)
            # 親の名前空間ではなく、実際に参照する名前で依存先を判定する。
            modules.extend(f"{base}.{alias.name}" for alias in node.names)
    return modules


def _resolve_from(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        return node.module or ""
    parts = package.split(".")
    anchor = parts[: len(parts) - (node.level - 1)]
    return ".".join(anchor + ([node.module] if node.module else []))


def _package_of(path: Path, root: Path, root_package: str) -> str:
    directories = path.relative_to(root).parent.parts
    return ".".join([root_package, *directories])


def _violations(
    root: Path,
    *,
    allowed: tuple[str, ...],
    forbidden: tuple[str, ...],
    root_package: str = "ai_rpg_world.being",
) -> list[str]:
    found: list[str] = []
    paths = sorted(root.rglob("*.py"))
    assert paths, f"no modules under {root}"
    for path in paths:
        for module in _imported_modules(path, _package_of(path, root, root_package)):
            if any(_is_within(module, p) for p in allowed):
                continue
            if any(_is_within(module, p) for p in forbidden):
                found.append(f"{path.relative_to(root)}: {module}")
    return found


def _game_package_violations(root: Path) -> list[str]:
    return _violations(
        root,
        allowed=(*_TEMPORARY_EXCEPTIONS, "ai_rpg_world.being", "ai_rpg_world.eventing"),
        forbidden=("ai_rpg_world",),
    )


def _contract_violations(root: Path) -> list[str]:
    return _violations(
        root,
        allowed=("ai_rpg_world.being.contract",),
        forbidden=("ai_rpg_world",),
        root_package="ai_rpg_world.being.contract",
    )


def test_being_package_does_not_import_game_packages() -> None:
    """being 配下のどのモジュールも、一時的な例外以外のゲームのパッケージを import しない。"""
    assert _game_package_violations(_BEING_ROOT) == []


def test_contract_imports_nothing_outside_the_contract() -> None:
    """契約のモジュールは、契約の外の ai_rpg_world を一時的な例外も含めて import しない。"""
    assert _contract_violations(_CONTRACT_ROOT) == []


@pytest.mark.parametrize(
    "source",
    [
        "from ai_rpg_world.domain.player.value_object.player_id import PlayerId\n",
        "import ai_rpg_world.application.observation.contracts.dtos\n",
        "from ai_rpg_world.infrastructure import scenario\n",
        "from ai_rpg_world import presentation\n",
        "import ai_rpg_world.domain.memory.short_term\n",
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from ai_rpg_world.domain.world_graph.value_object.spot_id import SpotId\n",
        "def f():\n    from ai_rpg_world.application.llm import contracts\n",
    ],
)
def test_game_package_import_is_reported(tmp_path: Path, source: str) -> None:
    """ゲームのパッケージを import するファイルがあれば、型検査用や関数内の import も違反として報告される。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    assert len(_game_package_violations(tmp_path)) >= 1


@pytest.mark.parametrize(
    "source",
    [
        "from ai_rpg_world.domain.being.value_object.being_id import BeingId\n",
        "from ai_rpg_world.being.contract import Observation\n",
    ],
)
def test_temporary_exceptions_and_being_itself_pass(tmp_path: Path, source: str) -> None:
    """一時的な例外と being 自身の import は違反にならない。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    assert _game_package_violations(tmp_path) == []


@pytest.mark.parametrize(
    "source",
    [
        "from ai_rpg_world.domain.being.value_object.being_id import BeingId\n",
        "from ai_rpg_world.being.domain import x\n",
    ],
)
def test_contract_rejects_even_temporary_exceptions(tmp_path: Path, source: str) -> None:
    """契約のモジュールは、一時的な例外や being の内部を import しても違反になる。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    assert len(_contract_violations(tmp_path)) >= 1


def test_relative_import_reaching_game_package_is_reported(tmp_path: Path) -> None:
    """相対 import で being の外のゲームのパッケージに届くと違反として報告される。"""
    (tmp_path / "module.py").write_text(
        "from ..application.llm import contracts\n", encoding="utf-8"
    )

    assert _game_package_violations(tmp_path) == [
        "module.py: ai_rpg_world.application.llm.contracts",
    ]


def test_relative_import_within_contract_passes(tmp_path: Path) -> None:
    """契約の中の相対 import は違反にならない。"""
    (tmp_path / "module.py").write_text(
        "from .observation import Observation\n", encoding="utf-8"
    )

    assert _contract_violations(tmp_path) == []


def test_similarly_named_package_is_not_mistaken_for_exception(tmp_path: Path) -> None:
    """名前が例外の前方一致にすぎないパッケージ (domain.beings) は例外として扱わない。"""
    (tmp_path / "module.py").write_text(
        "from ai_rpg_world.domain.beings import x\n", encoding="utf-8"
    )

    assert len(_game_package_violations(tmp_path)) >= 1


@pytest.mark.parametrize(
    "source",
    [
        "from ai_rpg_world.eventing import DomainEvent, AggregateRoot\n",
        "from ai_rpg_world import eventing\n",
        "from ai_rpg_world.eventing.domain_event import DomainEvent\n",
        "from ..eventing import DomainEvent\n",
    ],
)
def test_being_can_import_eventing(tmp_path: Path, source: str) -> None:
    """Being は、共通のイベント基盤を絶対 import と相対 import のどちらでも使える。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")
    assert _game_package_violations(tmp_path) == []


def test_contract_cannot_import_eventing(tmp_path: Path) -> None:
    """契約に eventing の import があれば、契約外への依存として報告する。"""
    (tmp_path / "module.py").write_text(
        "from ai_rpg_world.eventing import DomainEvent\n", encoding="utf-8"
    )
    assert _contract_violations(tmp_path)
