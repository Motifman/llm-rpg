import unittest.mock as mock

from ai_rpg_world.application.world.services.world_simulation_hit_box_updater import (
    WorldSimulationHitBoxUpdater,
)
from ai_rpg_world.domain.common.value_object import WorldTick


class TestWorldSimulationHitBoxUpdater:
    def test_updates_and_saves_active_hit_boxes(self):
        hit_box = mock.Mock()
        hit_box.is_active = True
        hit_box.is_activated.return_value = True
        repository = mock.Mock(find_active_by_spot_id=mock.Mock(return_value=[hit_box]))
        config_service = mock.Mock(
            get_substeps_for_hit_box=mock.Mock(return_value=1),
            get_max_collision_checks_per_tick=mock.Mock(return_value=5),
        )
        collision_service = mock.Mock(
            resolve_collisions=mock.Mock(return_value=(1, False))
        )
        updater = WorldSimulationHitBoxUpdater(
            hit_box_repository=repository,
            hit_box_config_service=config_service,
            hit_box_collision_service=collision_service,
            logger=mock.Mock(),
        )
        physical_map = mock.Mock(spot_id=mock.sentinel.spot_id)

        updater.update_hit_boxes(physical_map, WorldTick(10))

        hit_box.on_tick.assert_called_once_with(WorldTick(10), step_ratio=1.0)
        repository.save.assert_called_once_with(hit_box)

    def test_returns_when_hit_box_load_fails(self):
        logger = mock.Mock()
        updater = WorldSimulationHitBoxUpdater(
            hit_box_repository=mock.Mock(
                find_active_by_spot_id=mock.Mock(side_effect=RuntimeError("load failed"))
            ),
            hit_box_config_service=mock.Mock(),
            hit_box_collision_service=mock.Mock(),
            logger=logger,
        )

        updater.update_hit_boxes(mock.Mock(spot_id=mock.sentinel.spot_id), WorldTick(10))

        logger.error.assert_called_once()
