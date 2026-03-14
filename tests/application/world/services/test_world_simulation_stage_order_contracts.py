from types import SimpleNamespace
import unittest.mock as mock

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

from .support.world_simulation_builders import (
    build_world_simulation_test_bed,
    create_autonomous_actor,
    create_physical_map,
    create_player_actor,
    create_player_status,
)


def test_tick_preserves_stage_order_for_representative_world():
    bed = build_world_simulation_test_bed()
    service = bed.service
    order: list[str] = []

    status = create_player_status()
    status.set_destination(
        Coordinate(1, 0, 0),
        [Coordinate(0, 0, 0), Coordinate(1, 0, 0)],
        goal_destination_type="spot",
        goal_spot_id=SpotId(1),
    )
    bed.player_status_repo.save(status)
    bed.repository.save(
        create_physical_map(
            1,
            objects=[create_player_actor(), create_autonomous_actor()],
        )
    )

    service._movement_service = SimpleNamespace()
    service._harvest_command_service = SimpleNamespace()
    service._environment_stage = mock.Mock(
        run=mock.Mock(side_effect=lambda current_tick, maps: order.append("environment"))
    )
    service._movement_stage = mock.Mock(
        run=mock.Mock(side_effect=lambda current_tick: order.append("movement"))
    )
    service._harvest_stage = mock.Mock(
        run=mock.Mock(side_effect=lambda maps, current_tick: order.append("harvest"))
    )
    service._monster_lifecycle_stage = mock.Mock(
        run=mock.Mock(
            side_effect=lambda maps, active_spot_ids, current_tick: order.append("lifecycle") or set()
        )
    )
    service._monster_behavior_stage = mock.Mock(
        run=mock.Mock(
            side_effect=lambda maps, active_spot_ids, current_tick, skipped_actor_ids=None: order.append(
                "behavior"
            )
        )
    )
    service._hit_box_stage = mock.Mock(
        run=mock.Mock(side_effect=lambda maps, active_spot_ids, current_tick: order.append("hitbox"))
    )
    service._llm_turn_trigger = mock.Mock(
        run_scheduled_turns=mock.Mock(side_effect=lambda: order.append("llm"))
    )
    service._reflection_runner = mock.Mock(
        run_after_tick=mock.Mock(side_effect=lambda current_tick: order.append("reflection"))
    )

    current_tick = service.tick()

    assert current_tick == WorldTick(11)
    assert order == [
        "environment",
        "movement",
        "harvest",
        "lifecycle",
        "behavior",
        "hitbox",
        "llm",
        "reflection",
    ]

