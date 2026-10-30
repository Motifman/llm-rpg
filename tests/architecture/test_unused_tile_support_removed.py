"""利用側のない旧部品を復活させず、本番に旧参照を戻さないことを保証する。"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REMOVED_MODULES = (
    "domain.world.value_object.connection",
    "domain.world.value_object.movement_cost",
    "domain.world.repository.connected_spots_provider",
    "domain.world.service.weather_config_service",
    "domain.world.service.weather_effect_service",
    "domain.monster.service.monster_config_service",
    "domain.monster.value_object.monster_skill_info",
    "domain.monster.value_object.monster_temperament_preset",
)


@pytest.mark.parametrize("module", REMOVED_MODULES)
def test_unused_support_module_is_absent(module: str) -> None:
    """本番の利用側がなくなった旧部品のソースファイルは存在しない。"""
    assert not (ROOT / "src/ai_rpg_world" / (module.replace(".", "/") + ".py")).exists()


def test_source_has_no_removed_module_imports() -> None:
    """実行時・型検査・再公開のimportに、削除した旧部品への参照が残らない。"""
    removed = {f"ai_rpg_world.{module}" for module in REMOVED_MODULES}
    references = []
    for path in (ROOT / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
                names.extend(f"{node.module}.{alias.name}" for alias in node.names)
            else:
                continue
            if removed.intersection(names):
                references.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert references == []


@pytest.mark.parametrize(
    ("module", "symbol"),
    (
        ("world.exception.map_exception", "MovementCostValidationException"),
        ("world.exception.map_exception", "InvalidConnectionException"),
        ("monster.enum.monster_enum", "TemperamentEnum"),
    ),
)
def test_unused_support_symbol_is_absent(module: str, symbol: str) -> None:
    """旧部品だけが使っていた例外と性格プリセットの列挙型は定義しない。"""
    path = ROOT / "src/ai_rpg_world/domain" / (module.replace(".", "/") + ".py")
    definitions = {node.name for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, ast.ClassDef)}
    assert symbol not in definitions


def test_removed_movement_cost_is_not_configured_as_immutable() -> None:
    """削除した移動コストの構築子は静的検査の不変値設定に残さない。"""
    assert (
        "ai_rpg_world.domain.world.value_object.movement_cost.MovementCost.normal"
        not in (ROOT / "pyproject.toml").read_text()
    )
