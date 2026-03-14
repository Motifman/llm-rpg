import unittest.mock as mock

from ai_rpg_world.application.world.services.world_simulation_hit_box_stage_service import (
    WorldSimulationHitBoxStageService,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

from .support.world_simulation_builders import (
    build_world_simulation_test_bed,
    create_autonomous_actor,
    create_physical_map,
    create_player_actor,
    create_player_status,
)


def test_tick_only_processes_and_saves_active_spots():
    bed = build_world_simulation_test_bed()
    service = bed.service

    bed.player_status_repo.save(create_player_status(player_id=1, current_spot_id=1))
    bed.repository.save(
        create_physical_map(
            1,
            objects=[create_player_actor(player_id=1), create_autonomous_actor(200)],
        )
    )
    bed.repository.save(
        create_physical_map(
            2,
            objects=[create_autonomous_actor(300)],
        )
    )

    observed: dict[str, object] = {}
    original_save = bed.repository.save
    save_spot_ids: list[SpotId] = []

    def capture_save(physical_map):
        save_spot_ids.append(physical_map.spot_id)
        return original_save(physical_map)

    bed.repository.save = mock.Mock(side_effect=capture_save)
    service._monster_lifecycle_stage = mock.Mock(
        run=mock.Mock(
            side_effect=lambda maps, active_spot_ids, current_tick: observed.setdefault(
                "lifecycle_active_spots", set(active_spot_ids)
            )
            or set()
        )
    )
    service._monster_behavior_stage = mock.Mock(
        run=mock.Mock(
            side_effect=lambda maps, active_spot_ids, current_tick, skipped_actor_ids=None: observed.setdefault(
                "behavior_active_spots", set(active_spot_ids)
            )
        )
    )
    service._hit_box_stage = WorldSimulationHitBoxStageService(
        physical_map_repository=bed.repository,
        update_hit_boxes=lambda physical_map, current_tick: observed.setdefault(
            "hit_box_spots", []
        ).append(physical_map.spot_id),
    )

    service.tick()

    assert observed["lifecycle_active_spots"] == {SpotId(1)}
    assert observed["behavior_active_spots"] == {SpotId(1)}
    assert observed["hit_box_spots"] == [SpotId(1)]
    assert save_spot_ids == [SpotId(1)]

