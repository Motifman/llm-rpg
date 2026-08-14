"""CLEAR_FLAG が一時的な世界フラグだけを冪等に解除することを保証する。"""

from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)


def test_clear_flag_removes_only_the_named_world_flag() -> None:
    """対象フラグが立っていればそれだけを外し、無関係なフラグを維持する。"""
    result = WorldGraphEffectService().apply_effects(
        interior=SpotInterior((), (), (), ()),
        acting_object=None,
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.CLEAR_FLAG,
                parameters={"flag_name": "fuel_restored"},
            ),
        ),
        world_flags=frozenset({"fuel_restored", "task_weather"}),
    )

    assert result.new_flags == frozenset({"task_weather"})


def test_clear_flag_is_idempotent_when_the_named_flag_is_absent() -> None:
    """対象フラグが無くても失敗せず、既存の世界フラグ集合を変えない。"""
    result = WorldGraphEffectService().apply_effects(
        interior=SpotInterior((), (), (), ()),
        acting_object=None,
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.CLEAR_FLAG,
                parameters={"flag_name": "fuel_restored"},
            ),
        ),
        world_flags=frozenset({"task_weather"}),
    )

    assert result.new_flags == frozenset({"task_weather"})
