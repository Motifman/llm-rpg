"""モンスターの退役したタイル行動が本番の集約へ戻らないことを保証する。"""

from importlib import import_module

import pytest

from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.event import monster_events


@pytest.mark.parametrize(
    "method",
    [
        "to_behavior_state_snapshot",
        "record_attacked_by",
        "fail_pursuit",
        "apply_behavior_transition",
        "apply_territory_return_if_needed",
        "record_move",
        "record_use_skill",
        "record_interact",
    ],
)
def test_legacy_tile_action_is_absent(method: str) -> None:
    """旧タイル行動の入口はモンスター集約から呼び出せない。"""
    assert not hasattr(MonsterAggregate, method)


@pytest.mark.parametrize(
    "module",
    [
        "service.behavior_state_transition_service",
        "service.monster_behavior_state_machine",
        "value_object.behavior_state_snapshot",
    ],
)
def test_legacy_transition_module_is_absent(module: str) -> None:
    """旧タイル行動に専用の状態遷移モジュールは読み込めない。"""
    with pytest.raises(ModuleNotFoundError) as error:
        import_module(f"ai_rpg_world.domain.monster.{module}")
    assert error.value.name == f"ai_rpg_world.domain.monster.{module}"


@pytest.mark.parametrize(
    "event_name",
    [
        "MonsterDecidedToMoveEvent",
        "MonsterDecidedToUseSkillEvent",
        "MonsterDecidedToInteractEvent",
    ],
)
def test_legacy_decision_event_is_absent(event_name: str) -> None:
    """旧タイル行動を後から実行させる判断イベントは定義されない。"""
    assert not hasattr(monster_events, event_name)
