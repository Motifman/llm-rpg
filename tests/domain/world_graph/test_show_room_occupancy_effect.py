"""SHOW_ROOM_OCCUPANCY が動的表示要求を application 層まで運ぶことを保証する。"""

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


def test_effect_carries_one_runtime_occupancy_request_without_static_text() -> None:
    """表示効果は作成時の人数を固定せず、実行時に解く要求を一件だけ返す。"""
    result = WorldGraphEffectService().apply_effects(
        interior=SpotInterior((), (), (), ()),
        acting_object=None,
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.SHOW_ROOM_OCCUPANCY,
                parameters={},
            ),
        ),
        world_flags=frozenset(),
    )

    assert result.messages == ()
    assert len(result.room_occupancy_display_specs) == 1
    assert (
        result.room_occupancy_display_specs[0].scope
        == "living_players_and_fallen_bodies"
    )
