import unittest.mock as mock

from ai_rpg_world.application.world.services.monster_spawn_slot_service import (
    MonsterSpawnSlotService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


class TestMonsterSpawnSlotService:
    def test_process_respawn_legacy_respawns_only_eligible_dead_monsters(self):
        eligible = mock.Mock(
            status=MonsterStatusEnum.DEAD,
            spot_id=SpotId(1),
            should_respawn=mock.Mock(return_value=True),
            template=mock.Mock(respawn_info=mock.Mock(condition=None)),
            get_respawn_coordinate=mock.Mock(return_value=Coordinate(1, 1, 0)),
            monster_id="m1",
        )
        skipped = mock.Mock(
            status=MonsterStatusEnum.ALIVE,
            spot_id=SpotId(1),
        )
        repository = mock.Mock(find_all=mock.Mock(return_value=[eligible, skipped]))
        service = MonsterSpawnSlotService(
            physical_map_repository=mock.Mock(),
            monster_repository=repository,
            skill_loadout_repository=mock.Mock(),
            spawn_table_repository=None,
            monster_template_repository=None,
            unit_of_work=mock.Mock(),
            logger=mock.Mock(),
        )

        service.process_respawn_legacy({SpotId(1)}, WorldTick(10), TimeOfDay.MORNING)

        eligible.respawn.assert_called_once_with(Coordinate(1, 1, 0), WorldTick(10), SpotId(1))
        repository.save.assert_called_once_with(eligible)

    def test_process_spawn_and_respawn_by_slots_skips_full_slot(self):
        slot = mock.Mock(
            condition=None,
            max_concurrent=1,
            spot_id=SpotId(1),
            coordinate=Coordinate(1, 1, 0),
            template_id=mock.sentinel.template_id,
        )
        table = mock.Mock(slots=[slot])
        alive_monster = mock.Mock(
            status=MonsterStatusEnum.ALIVE,
            spot_id=SpotId(1),
            template=mock.Mock(template_id=mock.sentinel.template_id),
            get_respawn_coordinate=mock.Mock(return_value=Coordinate(1, 1, 0)),
        )
        spawn_table_repository = mock.Mock(find_by_spot_id=mock.Mock(return_value=table))
        monster_repository = mock.Mock(find_by_spot_id=mock.Mock(return_value=[alive_monster]))
        service = MonsterSpawnSlotService(
            physical_map_repository=mock.Mock(
                find_by_spot_id=mock.Mock(return_value=mock.Mock(weather_state=None, area_traits=None))
            ),
            monster_repository=monster_repository,
            skill_loadout_repository=mock.Mock(),
            spawn_table_repository=spawn_table_repository,
            monster_template_repository=mock.Mock(),
            unit_of_work=mock.Mock(),
            logger=mock.Mock(),
        )

        service.process_spawn_and_respawn_by_slots({SpotId(1)}, WorldTick(10), TimeOfDay.MORNING)

        monster_repository.generate_monster_id.assert_not_called()

    def test_process_spawn_and_respawn_by_slots_returns_early_when_spawn_table_repository_is_none(self):
        """spawn_table_repository が None のときは早期 return する"""
        service = MonsterSpawnSlotService(
            physical_map_repository=mock.Mock(),
            monster_repository=mock.Mock(),
            skill_loadout_repository=mock.Mock(),
            spawn_table_repository=None,
            monster_template_repository=mock.Mock(),
            unit_of_work=mock.Mock(),
            logger=mock.Mock(),
        )

        service.process_spawn_and_respawn_by_slots({SpotId(1)}, WorldTick(10), TimeOfDay.MORNING)

        service._physical_map_repository.find_by_spot_id.assert_not_called()

    def test_process_spawn_and_respawn_by_slots_handles_physical_map_none(self):
        """physical_map が None のとき weather_type/area_traits は None でスロット判定し、クラッシュしない"""
        slot_condition = mock.Mock(is_satisfied=mock.Mock(return_value=False))
        slot = mock.Mock(
            condition=slot_condition,
            max_concurrent=1,
            spot_id=SpotId(1),
            coordinate=Coordinate(1, 1, 0),
            template_id=mock.sentinel.template_id,
        )
        table = mock.Mock(slots=[slot])
        spawn_table_repository = mock.Mock(find_by_spot_id=mock.Mock(return_value=table))
        physical_map_repository = mock.Mock(find_by_spot_id=mock.Mock(return_value=None))
        monster_repository = mock.Mock(find_by_spot_id=mock.Mock(return_value=[]))
        service = MonsterSpawnSlotService(
            physical_map_repository=physical_map_repository,
            monster_repository=monster_repository,
            skill_loadout_repository=mock.Mock(),
            spawn_table_repository=spawn_table_repository,
            monster_template_repository=mock.Mock(),
            unit_of_work=mock.Mock(),
            logger=mock.Mock(),
        )

        service.process_spawn_and_respawn_by_slots({SpotId(1)}, WorldTick(10), TimeOfDay.MORNING)

        slot_condition.is_satisfied.assert_called_once_with(
            TimeOfDay.MORNING,
            weather_type=None,
            area_traits=None,
        )
        monster_repository.generate_monster_id.assert_not_called()

    def test_process_respawn_legacy_domain_exception_logged_and_continues(self):
        """respawn で DomainException 発生時はログ出力して継続"""
        from ai_rpg_world.domain.common.exception import DomainException

        dead_monster = mock.Mock(
            status=MonsterStatusEnum.DEAD,
            spot_id=SpotId(1),
            should_respawn=mock.Mock(return_value=True),
            template=mock.Mock(respawn_info=mock.Mock(condition=None)),
            get_respawn_coordinate=mock.Mock(return_value=Coordinate(1, 1, 0)),
            monster_id="m1",
        )
        dead_monster.respawn.side_effect = DomainException("respawn rule violated")
        repository = mock.Mock(find_all=mock.Mock(return_value=[dead_monster]))
        logger = mock.Mock()
        service = MonsterSpawnSlotService(
            physical_map_repository=mock.Mock(),
            monster_repository=repository,
            skill_loadout_repository=mock.Mock(),
            spawn_table_repository=None,
            monster_template_repository=None,
            unit_of_work=mock.Mock(),
            logger=logger,
        )

        service.process_respawn_legacy({SpotId(1)}, WorldTick(10), TimeOfDay.MORNING)

        logger.warning.assert_called_once()
        repository.save.assert_not_called()

    def test_process_respawn_legacy_domain_exception_logged_and_skipped(self):
        """process_respawn_legacy で respawn が DomainException を投げた場合ログしてスキップする"""
        from ai_rpg_world.domain.common.exception import DomainException

        dead_monster = mock.Mock(
            status=MonsterStatusEnum.DEAD,
            spot_id=SpotId(1),
            should_respawn=mock.Mock(return_value=True),
            template=mock.Mock(respawn_info=mock.Mock(condition=None)),
            get_respawn_coordinate=mock.Mock(return_value=Coordinate(1, 1, 0)),
            monster_id="m1",
        )
        dead_monster.respawn.side_effect = DomainException("spawn blocked")
        repository = mock.Mock(find_all=mock.Mock(return_value=[dead_monster]))
        logger = mock.Mock()
        service = MonsterSpawnSlotService(
            physical_map_repository=mock.Mock(),
            monster_repository=repository,
            skill_loadout_repository=mock.Mock(),
            spawn_table_repository=None,
            monster_template_repository=None,
            unit_of_work=mock.Mock(),
            logger=logger,
        )

        service.process_respawn_legacy({SpotId(1)}, WorldTick(10), TimeOfDay.MORNING)

        logger.warning.assert_called_once()
        repository.save.assert_not_called()
