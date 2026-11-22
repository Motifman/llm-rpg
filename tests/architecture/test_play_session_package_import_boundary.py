"""遊びの進行 (play_session、#2229) が、世界と Being を入口だけで呼ぶよう、層ごとに import を見張る。

- どの層も: play_session の domain、eventing、Being の契約と BeingId、世界の ID の値
- application はさらに: play_session の application と、Being と世界の入口のモジュール。入口でない application の部品
  (世界の作業単位など) には触らない
- infrastructure はさらに: play_session の infrastructure、シナリオの読み込み。シナリオのファイルを読むのは infrastructure の仕事なので
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAY_SESSION_ROOT = _REPO_ROOT / "src/ai_rpg_world/play_session"
_PLAY_SESSION_PACKAGE = "ai_rpg_world.play_session"

_EVERY_LAYER = (
    f"{_PLAY_SESSION_PACKAGE}.domain",
    "ai_rpg_world.eventing",
    "ai_rpg_world.being.contract",
    "ai_rpg_world.being.domain.being_id",
    "ai_rpg_world.game_world.domain.value_object",
)
_BEING_ENTRANCES = tuple(
    f"ai_rpg_world.being.application.{name}" for name in ("prepare_being", "enter_environment", "perceive_observation")
)
_WORLD_ENTRANCES = tuple(
    f"ai_rpg_world.game_world.application.{name}"
    for name in (
        "open_world",
        "name_person",
        "brief_entering_person",
        "check_readiness_to_act",
        "world_has_ended",
        "accept_world_time_passage",
    )
)
_APPLICATION = (*_EVERY_LAYER, f"{_PLAY_SESSION_PACKAGE}.application", *_BEING_ENTRANCES, *_WORLD_ENTRANCES)
_INFRASTRUCTURE = (
    *_APPLICATION,
    f"{_PLAY_SESSION_PACKAGE}.infrastructure",
    "ai_rpg_world.game_world.infrastructure.scenario",
)
_ALLOWED_BY_LAYER = {"domain": _EVERY_LAYER, "application": _APPLICATION, "infrastructure": _INFRASTRUCTURE}


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


def _violations(root: Path, layer: str) -> list[str]:
    allowed = _ALLOWED_BY_LAYER[layer]
    package = f"{_PLAY_SESSION_PACKAGE}.{layer}"
    found: list[str] = []
    paths = sorted(root.rglob("*.py"))
    assert paths, f"no modules under {root}"
    for path in paths:
        directories = path.relative_to(root).parent.parts
        for module in _imported_modules(path, ".".join([package, *directories])):
            if any(_is_within(module, p) for p in allowed):
                continue
            if _is_within(module, "ai_rpg_world"):
                found.append(f"{path.relative_to(root)}: {module}")
    return found


@pytest.mark.parametrize("layer", ["domain", "application", "infrastructure"])
def test_each_layer_imports_only_what_the_layer_is_allowed(layer: str) -> None:
    """play_session の各層のどのモジュールも、その層に許した世界・Being・共通の部品のほかの ai_rpg_world を import しない。"""
    assert _violations(_PLAY_SESSION_ROOT / layer, layer) == []


def test_play_session_has_domain_application_and_infrastructure_layers() -> None:
    """play_session は being と同じく domain・application・infrastructure の 3 つのパッケージに分かれている。"""
    layers = {p.name for p in _PLAY_SESSION_ROOT.iterdir() if (p / "__init__.py").is_file()}

    assert {"domain", "application", "infrastructure"} <= layers


@pytest.mark.parametrize(
    ("layer", "source"),
    [
        ("domain", "from ai_rpg_world.game_world.application.open_world import OpenWorld\n"),
        ("domain", "from ai_rpg_world.being.application.prepare_being import PrepareBeing\n"),
        ("application", "from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario\n"),
        ("application", "from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign\n"),
        ("application", "from ai_rpg_world.being.domain.being import Being\n"),
        (
            "application",
            "from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository\n",
        ),
        ("infrastructure", "from ai_rpg_world.domain.world.aggregate.player_beings import PlayerBeings\n"),
        (
            "infrastructure",
            "from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore\n",
        ),
        ("domain", "def f():\n    from ai_rpg_world.game_world.application import open_world\n"),
        ("application", "from ai_rpg_world.game_world.application.world_store import WorldStore\n"),
        ("application", "from ai_rpg_world.being.application.current_working_memory import CurrentWorkingMemory\n"),
        ("application", "import ai_rpg_world.game_world.application.command_scope\n"),
        ("infrastructure", "import ai_rpg_world.domain.world.aggregate.player_beings\n"),
        ("domain", "from ..application.start_play_session import Role\n"),
        ("application", "from ai_rpg_world.play_session.infrastructure import roles_from_scenario\n"),
    ],
)
def test_import_beyond_the_layer_is_reported(tmp_path: Path, layer: str, source: str) -> None:
    """層に許していない世界や Being の内部、古いゲームのパッケージを import すると、関数内や相対 import でも違反として報告される。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    assert len(_violations(tmp_path, layer)) >= 1


@pytest.mark.parametrize(
    ("layer", "source"),
    [
        ("domain", "from ai_rpg_world.being.contract import EnvironmentEntry\n"),
        ("domain", "from ai_rpg_world.being.domain.being_id import BeingId\n"),
        ("domain", "from ai_rpg_world.game_world.domain.value_object import PersonId\n"),
        ("domain", "from ai_rpg_world.eventing import AggregateRoot\n"),
        ("application", "from ai_rpg_world.game_world.application.open_world import OpenWorld\n"),
        ("application", "from ai_rpg_world.being.application.prepare_being import PrepareBeing\n"),
        ("application", "from ..domain.cast import Cast\n"),
        ("infrastructure", "from ai_rpg_world.play_session.application.start_play_session import Role\n"),
        (
            "infrastructure",
            "from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario\n",
        ),
    ],
)
def test_imports_allowed_for_the_layer_pass(tmp_path: Path, layer: str, source: str) -> None:
    """その層に許した入口・契約・ID の値・play_session 自身の import は違反にならない。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    assert _violations(tmp_path, layer) == []
