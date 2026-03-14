from types import SimpleNamespace
import unittest.mock as mock

import pytest

from ai_rpg_world.application.world.services.world_simulation_movement_stage_service import (
    WorldSimulationMovementStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def test_run_is_noop_when_movement_service_is_not_injected():
    player_status_repository = mock.Mock(find_all=mock.Mock())
    physical_map_repository = mock.Mock()
    stage = WorldSimulationMovementStageService(
        player_status_repository=player_status_repository,
        physical_map_repository=physical_map_repository,
        movement_service_getter=lambda: None,
        pursuit_continuation_service_getter=lambda: None,
    )

    stage.run(WorldTick(10))

    player_status_repository.find_all.assert_not_called()
    physical_map_repository.find_by_spot_id.assert_not_called()


def test_run_evaluates_pursuit_continuation_before_advancing_movement():
    order: list[str] = []
    status = SimpleNamespace(
        has_active_pursuit=True,
        pursuit_state=object(),
        current_spot_id=SpotId(1),
        goal_spot_id=None,
        player_id=1,
    )
    actor = mock.Mock()
    actor.is_busy.return_value = False
    physical_map = mock.Mock()
    physical_map.get_actor.return_value = actor
    continuation_service = mock.Mock(
        evaluate_tick=mock.Mock(
            side_effect=lambda current_status: order.append("continuation")
            or SimpleNamespace(should_advance_movement=True)
        )
    )
    movement_service = SimpleNamespace(
        tick_movement_in_current_unit_of_work=lambda player_id: order.append(
            f"movement:{player_id}"
        )
    )
    stage = WorldSimulationMovementStageService(
        player_status_repository=mock.Mock(find_all=mock.Mock(return_value=[status])),
        physical_map_repository=mock.Mock(
            find_by_spot_id=mock.Mock(return_value=physical_map)
        ),
        movement_service_getter=lambda: movement_service,
        pursuit_continuation_service_getter=lambda: continuation_service,
    )

    stage.run(WorldTick(10))

    assert order == ["continuation", "movement:1"]


@pytest.mark.parametrize(
    ("status", "physical_map", "actor", "continuation_result"),
    [
        (
            SimpleNamespace(
                has_active_pursuit=False,
                pursuit_state=None,
                current_spot_id=SpotId(1),
                goal_spot_id=None,
                player_id=1,
            ),
            None,
            None,
            None,
        ),
        (
            SimpleNamespace(
                has_active_pursuit=False,
                pursuit_state=None,
                current_spot_id=SpotId(1),
                goal_spot_id=SpotId(2),
                player_id=1,
            ),
            None,
            None,
            None,
        ),
        (
            SimpleNamespace(
                has_active_pursuit=False,
                pursuit_state=None,
                current_spot_id=SpotId(1),
                goal_spot_id=SpotId(2),
                player_id=1,
            ),
            mock.Mock(get_actor=mock.Mock(side_effect=ObjectNotFoundException("missing"))),
            None,
            None,
        ),
        (
            SimpleNamespace(
                has_active_pursuit=False,
                pursuit_state=None,
                current_spot_id=SpotId(1),
                goal_spot_id=SpotId(2),
                player_id=1,
            ),
            mock.Mock(get_actor=mock.Mock(return_value=mock.Mock(is_busy=mock.Mock(return_value=True)))),
            mock.Mock(is_busy=mock.Mock(return_value=True)),
            None,
        ),
        (
            SimpleNamespace(
                has_active_pursuit=True,
                pursuit_state=object(),
                current_spot_id=SpotId(1),
                goal_spot_id=None,
                player_id=1,
            ),
            mock.Mock(get_actor=mock.Mock(return_value=mock.Mock(is_busy=mock.Mock(return_value=False)))),
            mock.Mock(is_busy=mock.Mock(return_value=False)),
            SimpleNamespace(should_advance_movement=False),
        ),
    ],
)
def test_run_skips_movement_for_guard_conditions(
    status,
    physical_map,
    actor,
    continuation_result,
):
    movement_method = mock.Mock()
    continuation_service = mock.Mock()
    continuation_service.evaluate_tick.return_value = continuation_result
    physical_map_repository = mock.Mock(find_by_spot_id=mock.Mock(return_value=physical_map))

    stage = WorldSimulationMovementStageService(
        player_status_repository=mock.Mock(find_all=mock.Mock(return_value=[status])),
        physical_map_repository=physical_map_repository,
        movement_service_getter=lambda: SimpleNamespace(
            tick_movement_in_current_unit_of_work=movement_method
        ),
        pursuit_continuation_service_getter=lambda: continuation_service,
    )

    stage.run(WorldTick(10))

    movement_method.assert_not_called()

