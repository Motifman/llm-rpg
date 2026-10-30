"""未使用の小さな型と旧天候の観測経路を再導入しない。"""

import ast
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("module", "name"),
    [
        ("ai_rpg_world.domain.common.value_object", "Gold"),
        ("ai_rpg_world.domain.player.enum.player_enum", "PlayerState"),
    ],
)
def test_unused_type_is_absent(module: str, name: str) -> None:
    """未使用型は元のモジュールに定義・再公開されない。"""
    assert not hasattr(import_module(module), name)


@pytest.mark.parametrize(
    "module",
    [
        "ai_rpg_world.domain.world.event.map_events",
        "ai_rpg_world.application.observation.services.formatters.world_formatter",
    ],
)
def test_retired_weather_module_is_absent(module: str) -> None:
    """発火元のない旧天候イベントと専用formatterのモジュールは存在しない。"""
    assert find_spec(module) is None


def test_production_sources_do_not_reference_retired_names() -> None:
    """旧天候と未使用状態の識別子・文字列・型importをsrcに残さない。"""
    root = Path(__file__).resolve().parents[2] / "src"
    forbidden = {"SpotWeatherChangedEvent", "WorldObservationFormatter", "PlayerState"}
    violations = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = {
                value
                for field in ("id", "attr", "name", "value")
                if isinstance(value := getattr(node, field, None), str)
            }
            if names & forbidden:
                violations.append(f"{path.relative_to(root)}:{node.lineno}")
            if isinstance(node, ast.ImportFrom) and node.module == "ai_rpg_world.domain.common.value_object":
                if any(alias.name in {"Gold", "*"} for alias in node.names):
                    violations.append(f"{path.relative_to(root)}:{node.lineno}")
    assert violations == []
