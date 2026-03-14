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

    def test_domain_exception_during_update_skips_and_logs(self):
        """DomainException 発生時は当該 HitBox をスキップしてログ出力し、他は継続"""
        from ai_rpg_world.domain.common.exception import DomainException

        hit_box_ok = mock.Mock()
        hit_box_ok.is_active = True
        hit_box_ok.is_activated.return_value = True
        hit_box_ok.hit_box_id = mock.sentinel.ok_id
        hit_box_fail = mock.Mock()
        hit_box_fail.is_active = True
        hit_box_fail.is_activated.return_value = True
        hit_box_fail.hit_box_id = mock.sentinel.fail_id
        hit_box_fail.on_tick.side_effect = DomainException("invalid state")

        repository = mock.Mock(find_active_by_spot_id=mock.Mock(return_value=[hit_box_fail, hit_box_ok]))
        config_service = mock.Mock(
            get_substeps_for_hit_box=mock.Mock(return_value=1),
            get_max_collision_checks_per_tick=mock.Mock(return_value=5),
        )
        collision_service = mock.Mock(resolve_collisions=mock.Mock(return_value=(1, False)))
        logger = mock.Mock()
        updater = WorldSimulationHitBoxUpdater(
            hit_box_repository=repository,
            hit_box_config_service=config_service,
            hit_box_collision_service=collision_service,
            logger=logger,
        )
        physical_map = mock.Mock(spot_id=mock.sentinel.spot_id)

        updater.update_hit_boxes(physical_map, WorldTick(10))

        logger.warning.assert_called_once()
        repository.save.assert_called_once_with(hit_box_ok)

    def test_exception_during_individual_hit_box_update_logs_and_continues(self):
        """個別 HitBox 更新で Exception 発生時はログ出力して他を継続"""
        hit_box_ok = mock.Mock()
        hit_box_ok.is_active = True
        hit_box_ok.is_activated.return_value = True
        hit_box_ok.hit_box_id = mock.sentinel.ok_id
        hit_box_fail = mock.Mock()
        hit_box_fail.is_active = True
        hit_box_fail.is_activated.return_value = True
        hit_box_fail.hit_box_id = mock.sentinel.fail_id
        hit_box_fail.on_tick.side_effect = RuntimeError("unexpected")

        repository = mock.Mock(find_active_by_spot_id=mock.Mock(return_value=[hit_box_fail, hit_box_ok]))
        config_service = mock.Mock(
            get_substeps_for_hit_box=mock.Mock(return_value=1),
            get_max_collision_checks_per_tick=mock.Mock(return_value=5),
        )
        collision_service = mock.Mock(resolve_collisions=mock.Mock(return_value=(1, False)))
        logger = mock.Mock()
        updater = WorldSimulationHitBoxUpdater(
            hit_box_repository=repository,
            hit_box_config_service=config_service,
            hit_box_collision_service=collision_service,
            logger=logger,
        )
        physical_map = mock.Mock(spot_id=mock.sentinel.spot_id)

        updater.update_hit_boxes(physical_map, WorldTick(10))

        logger.error.assert_called_once()
        repository.save.assert_called_once_with(hit_box_ok)

