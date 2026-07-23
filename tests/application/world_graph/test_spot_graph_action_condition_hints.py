"""SpotGraphCurrentStateBuilder が action の時刻・天候制約ヒントを snapshot に載せる。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _build_builder(interior: SpotInterior) -> SpotGraphCurrentStateBuilder:
    graph = MagicMock()
    graph.get_entity_spot.return_value = SpotId(1)
    spot_node = MagicMock()
    spot_node.name = "岩礁"
    spot_node.description = ""
    spot_node.atmosphere = None
    spot_node.is_outdoor = True
    graph.get_spot.return_value = spot_node
    graph.presence_at.return_value.present_entity_ids = frozenset()
    graph.monster_presence_at.return_value.present_monster_ids = frozenset()
    graph.iter_outgoing_connections_from.return_value = []

    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph
    spot_interior_repo = MagicMock()
    spot_interior_repo.find_by_spot_id.return_value = interior
    player_status_repo = MagicMock()
    player_status_repo.find_by_id.return_value = None
    return SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
    )


def test_time_and_weather_preconditions_become_action_condition_hints() -> None:
    """TIME_OF_DAY_IS_NOT / WEATHER_IS_NOT は action 表示用の短い制約ヒントになる。"""
    interaction = InteractionDef(
        action_name="fish_deep",
        display_label="沖で釣りをする",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
                required_time_of_day_phase="night",
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.WEATHER_IS_NOT,
                required_weather_type="STORM",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="沖の釣り場",
                description="沖へ釣り糸を垂らせる。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].condition_hints == ("夜不可", "嵐不可")


def test_unknown_time_and_weather_values_are_not_silently_dropped() -> None:
    """未知の phase/weather 値は raw 値を使い、制約ヒント自体を消さない。"""
    interaction = InteractionDef(
        action_name="ritual",
        display_label="儀式をする",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS,
                required_time_of_day_phase="blue_hour",
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.WEATHER_IS,
                required_weather_type="METEOR_SHOWER",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="儀式場",
                description="空がよく見える。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].condition_hints == (
        "blue_hourのみ",
        "METEOR_SHOWERのみ",
    )
