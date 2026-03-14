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
