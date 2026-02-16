"""Phase 6: MonsterDiedMapRemovalHandler のテスト"""

import pytest
from ai_rpg_world.application.world.handlers.monster_died_map_removal_handler import (
    MonsterDiedMapRemovalHandler,
)
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.common.value_object import WorldTick


class _FakeUow:
    pass


def _create_map(spot_id_int: int) -> PhysicalMapAggregate:
    tiles = [
        Tile(Coordinate(x, y, 0), TerrainType.grass())
        for x in range(5)
        for y in range(5)
    ]
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)


def _sample_template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(1),
        name="Slime",
        base_stats=BaseStats(50, 0, 5, 3, 4, 0, 0),
        reward_info=RewardInfo(10, 5, "loot_slime"),
        respawn_info=RespawnInfo(respawn_interval_ticks=60, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A slime.",
    )


class TestMonsterDiedMapRemovalHandler:
    """MonsterDiedMapRemovalHandler の正常・スキップ・例外ケース"""

    @pytest.fixture
    def map_repo(self):
        return InMemoryPhysicalMapRepository()

    @pytest.fixture
    def monster_repo(self):
        return InMemoryMonsterAggregateRepository()

    @pytest.fixture
    def handler(self, map_repo, monster_repo):
        return MonsterDiedMapRemovalHandler(map_repo, monster_repo, _FakeUow())

    def test_removes_dead_monster_object_from_map(self, handler, map_repo, monster_repo):
        """死亡イベントで該当 WorldObject がマップから削除されること"""
        spot_id = SpotId(1)
        pmap = _create_map(1)
        world_object_id = WorldObjectId.create(200)
        monster = MonsterAggregate.create(
            monster_id=MonsterId.create(1),
            template=_sample_template(),
            world_object_id=world_object_id,
            skill_loadout=SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=1001, normal_capacity=5, awakened_capacity=5
            ),
        )
        monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
        monster.apply_damage(100, WorldTick(10))
        comp = AutonomousBehaviorComponent()
        obj = WorldObject(
            world_object_id,
            Coordinate(2, 2, 0),
            ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        pmap.add_object(obj)
        monster_repo.save(monster)
        map_repo.save(pmap)

        event = MonsterDiedEvent.create(
            aggregate_id=monster.monster_id,
            aggregate_type="MonsterAggregate",
            respawn_tick=70,
            exp=10,
            gold=5,
            loot_table_id="loot_slime",
            killer_player_id=None,
            killer_world_object_id=None,
            cause=None,
            spot_id=spot_id,
        )
        handler.handle(event)

        pmap_after = map_repo.find_by_spot_id(spot_id)
        with pytest.raises(ObjectNotFoundException):
            pmap_after.get_object(world_object_id)

    def test_skip_when_spot_id_none(self, handler):
        """spot_id が None のとき何もしない"""
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId.create(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=10,
            gold=5,
            loot_table_id=None,
            killer_player_id=None,
            killer_world_object_id=None,
            cause=None,
            spot_id=None,
        )
        handler.handle(event)

    def test_skip_when_map_not_found(self, handler, monster_repo):
        """マップが存在しないときはスキップ（例外にならない）"""
        monster = MonsterAggregate.create(
            monster_id=MonsterId.create(1),
            template=_sample_template(),
            world_object_id=WorldObjectId.create(99),
            skill_loadout=SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=1001, normal_capacity=5, awakened_capacity=5
            ),
        )
        monster_repo.save(monster)
        event = MonsterDiedEvent.create(
            aggregate_id=monster.monster_id,
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=10,
            gold=5,
            loot_table_id=None,
            killer_player_id=None,
            killer_world_object_id=None,
            cause=None,
            spot_id=SpotId(999),
        )
        handler.handle(event)  # マップが無いのでスキップ、例外なし
