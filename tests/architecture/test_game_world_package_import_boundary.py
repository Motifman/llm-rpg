"""``ai_rpg_world.game_world`` が、共通のイベント基盤と Being の契約のほかは import しないことを見張る。

設計し直したゲームの世界 (#1978) は、古いゲームのパッケージの横に作ってから切り替える。
古いパッケージへの依存が紛れ込むと切り替えられなくなるので、最初の PR から見張る。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAME_WORLD_ROOT = _REPO_ROOT / "src/ai_rpg_world/game_world"
_GAME_WORLD_PACKAGE = "ai_rpg_world.game_world"

_ALLOWED = (
    _GAME_WORLD_PACKAGE,
    "ai_rpg_world.eventing",
    "ai_rpg_world.being.contract",
)


def _is_within(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _resolve_from(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        return node.module or ""
    parts = package.split(".")
    anchor = parts[: len(parts) - (node.level - 1)]
    return ".".join(anchor + ([node.module] if node.module else []))


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


def _package_of(path: Path, root: Path) -> str:
    directories = path.relative_to(root).parent.parts
    return ".".join([_GAME_WORLD_PACKAGE, *directories])


def _violations(root: Path) -> list[str]:
    found: list[str] = []
    paths = sorted(root.rglob("*.py"))
    assert paths, f"no modules under {root}"
    for path in paths:
        for module in _imported_modules(path, _package_of(path, root)):
            if any(_is_within(module, p) for p in _ALLOWED):
                continue
            if _is_within(module, "ai_rpg_world"):
                found.append(f"{path.relative_to(root)}: {module}")
    return found


def test_game_world_imports_only_eventing_and_being_contract() -> None:
    """game_world 配下のどのモジュールも、eventing と being.contract のほかの ai_rpg_world を import しない。"""
    assert _violations(_GAME_WORLD_ROOT) == []


def test_game_world_has_domain_application_and_infrastructure_layers() -> None:
    """game_world は being と同じく domain・application・infrastructure の 3 つのパッケージに分かれている。"""
    layers = {p.name for p in _GAME_WORLD_ROOT.iterdir() if (p / "__init__.py").is_file()}

    assert {"domain", "application", "infrastructure"} <= layers


@pytest.mark.parametrize(
    "source",
    [
        "from ai_rpg_world.domain.world_graph.value_object.spot_id import SpotId\n",
        "import ai_rpg_world.domain.common.exception\n",
        "from ai_rpg_world.domain import common\n",
        "from ai_rpg_world.application.llm import contracts\n",
        "from ai_rpg_world.infrastructure import scenario\n",
        "from ai_rpg_world import presentation\n",
        "import ai_rpg_world\n",
        "from ai_rpg_world.being.domain.being_id import BeingId\n",
        "from ai_rpg_world.being import domain\n",
        "from ai_rpg_world import being\n",
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from ai_rpg_world.domain.world_graph.value_object.spot_id import SpotId\n",
        "def f():\n    from ai_rpg_world.application.llm import contracts\n",
    ],
)
def test_import_outside_the_allowed_packages_is_reported(tmp_path: Path, source: str) -> None:
    """古いゲームのパッケージや Being の内部を import するファイルがあれば、型検査用や関数内の import も違反として報告される。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    assert len(_violations(tmp_path)) >= 1


def test_relative_import_reaching_old_game_package_is_reported(tmp_path: Path) -> None:
    """game_world の直下から相対 import で古い domain に届くと、解決した名前で違反として報告される。"""
    (tmp_path / "module.py").write_text("from ..domain.common import exception\n", encoding="utf-8")

    assert _violations(tmp_path) == ["module.py: ai_rpg_world.domain.common.exception"]


def test_similarly_named_package_is_not_mistaken_for_allowed(tmp_path: Path) -> None:
    """名前が許可の前方一致にすぎないパッケージ (being.contracts、eventing_legacy) は許可として扱わない。"""
    (tmp_path / "module.py").write_text(
        "from ai_rpg_world.being.contracts import x\nfrom ai_rpg_world.eventing_legacy import y\n",
        encoding="utf-8",
    )

    assert len(_violations(tmp_path)) == 2


@pytest.mark.parametrize(
    "source",
    [
        "from ai_rpg_world.eventing import DomainEvent, AggregateRoot\n",
        "from ai_rpg_world import eventing\n",
        "from ai_rpg_world.being.contract import Observation\n",
        "from ai_rpg_world.being.contract.observation import Observation\n",
        "from ai_rpg_world.being import contract\n",
        "from ai_rpg_world.game_world.domain.value_object import Ticks\n",
        "from .value_object import Ticks\n",
        "from dataclasses import dataclass\n",
    ],
)
def test_allowed_imports_pass(tmp_path: Path, source: str) -> None:
    """eventing、being.contract、game_world 自身、標準ライブラリの import は違反にならない。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    assert _violations(tmp_path) == []
