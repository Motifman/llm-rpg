import unittest.mock as mock

from ai_rpg_world.application.world.services.world_simulation_monster_behavior_stage_service import (
    WorldSimulationMonsterBehaviorStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import ActiveTimeType
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _build_stage(actors):
    coordinator = mock.Mock()
    return (
        WorldSimulationMonsterBehaviorStageService(
            world_time_config_service=mock.Mock(
                get_ticks_per_day=mock.Mock(return_value=24)
            ),
            logger=mock.Mock(),
            actors_sorted_by_distance_to_players=lambda physical_map: actors,
            behavior_coordinator=coordinator,
        ),
        coordinator,
    )


def test_run_skips_inactive_spots():
    actor = mock.Mock(object_id=WorldObjectId(1), component=mock.Mock(), is_busy=mock.Mock(return_value=False))
    stage, coordinator = _build_stage([actor])
    inactive_map = mock.Mock(spot_id=SpotId(2))

    stage.run([inactive_map], {SpotId(1)}, WorldTick(10))

    coordinator.process_actor_behavior.assert_not_called()


def test_run_skips_skipped_and_busy_actors():
    skipped_actor = mock.Mock(object_id=WorldObjectId(1), component=mock.Mock(), is_busy=mock.Mock(return_value=False))
    busy_actor = mock.Mock(object_id=WorldObjectId(2), component=mock.Mock(), is_busy=mock.Mock(return_value=True))
    stage, coordinator = _build_stage([skipped_actor, busy_actor])
    active_map = mock.Mock(spot_id=SpotId(1))

    stage.run(
        [active_map],
        {SpotId(1)},
        WorldTick(10),
        skipped_actor_ids={WorldObjectId(1)},
    )

    coordinator.process_actor_behavior.assert_not_called()


def test_run_skips_actor_outside_active_time():
    nocturnal_actor = mock.Mock(
        object_id=WorldObjectId(3),
        component=AutonomousBehaviorComponent(active_time=ActiveTimeType.NOCTURNAL),
        is_busy=mock.Mock(return_value=False),
    )
    stage, coordinator = _build_stage([nocturnal_actor])
    active_map = mock.Mock(spot_id=SpotId(1))

    stage.run([active_map], {SpotId(1)}, WorldTick(12))

    coordinator.process_actor_behavior.assert_not_called()


def test_run_dispatches_eligible_actors_in_sorted_order():
    first_actor = mock.Mock(
        object_id=WorldObjectId(10),
        component=mock.Mock(),
        is_busy=mock.Mock(return_value=False),
    )
    second_actor = mock.Mock(
        object_id=WorldObjectId(11),
        component=mock.Mock(),
        is_busy=mock.Mock(return_value=False),
    )
    stage, coordinator = _build_stage([first_actor, second_actor])
    active_map = mock.Mock(spot_id=SpotId(1))

    stage.run([active_map], {SpotId(1)}, WorldTick(10))

    assert coordinator.process_actor_behavior.call_args_list == [
        mock.call(first_actor, active_map, WorldTick(10)),
        mock.call(second_actor, active_map, WorldTick(10)),
    ]
