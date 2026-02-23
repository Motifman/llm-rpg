"""Phase 6: MonsterDeathHungerHandler のテスト"""

import pytest
from ai_rpg_world.application.world.handlers.monster_death_hunger_handler import MonsterDeathHungerHandler
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
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
    ActorComponent,
)
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


class _FakeUow:
    pass


def _create_map(spot_id_int: int) -> PhysicalMapAggregate:
    tiles = [
        Tile(Coordinate(x, y, 0), TerrainType.grass())
        for x in range(5)
        for y in range(5)
    ]
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)


def _template_with_prey(
    template_id: int = 1,
    prey_races: frozenset = None,
    hunger_decrease_on_prey_kill: float = 0.3,
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name="Wolf",
        base_stats=BaseStats(100, 20, 15, 10, 12, 0.05, 0.05),
        reward_info=RewardInfo(20, 10, 1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A wolf.",
        prey_races=prey_races or frozenset({"goblin"}),
        hunger_increase_per_tick=0.01,
        hunger_decrease_on_prey_kill=hunger_decrease_on_prey_kill,
        hunger_starvation_threshold=0.9,
        starvation_ticks=50,
    )


class TestMonsterDeathHungerHandler:
    """MonsterDeathHungerHandler の正常・スキップ・例外ケース"""

    @pytest.fixture
    def map_repo(self):
        return InMemoryPhysicalMapRepository()

    @pytest.fixture
    def monster_repo(self):
        return InMemoryMonsterAggregateRepository()

    @pytest.fixture
    def handler(self, monster_repo):
        return MonsterDeathHungerHandler(monster_repo, _FakeUow())

    def test_prey_kill_reduces_killer_hunger(self, handler, monster_repo):
        """獲物（prey_races）を倒したキラーモンスターの飢餓が減少すること（Monster 集約の飢餓を更新）"""
        spot_id = SpotId(1)
        killer_world_id = WorldObjectId.create(100)
        dead_monster_id = MonsterId.create(1)
        killer_template = _template_with_prey(1, frozenset({"goblin"}), 0.4)
        dead_template = MonsterTemplate(
            template_id=MonsterTemplateId(2),
            name="Goblin",
            base_stats=BaseStats(30, 0, 5, 2, 4, 0, 0),
            reward_info=RewardInfo(5, 2, None),
            respawn_info=RespawnInfo(50, True),
            race=Race.GOBLIN,
            faction=MonsterFactionEnum.ENEMY,
            description="A goblin.",
        )
        killer_loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=1001, normal_capacity=5, awakened_capacity=5
        )
        dead_loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(2), owner_id=1002, normal_capacity=5, awakened_capacity=5
        )
        killer_monster = MonsterAggregate.create(
            monster_id=MonsterId.create(2),
            template=killer_template,
            world_object_id=killer_world_id,
            skill_loadout=killer_loadout,
        )
        dead_monster = MonsterAggregate.create(
            monster_id=dead_monster_id,
            template=dead_template,
            world_object_id=WorldObjectId.create(101),
            skill_loadout=dead_loadout,
        )
        from ai_rpg_world.domain.common.value_object import WorldTick
        killer_monster.spawn(
            Coordinate(2, 2, 0),
            spot_id,
            WorldTick(0),
            initial_hunger=0.9,
        )
        monster_repo.save(killer_monster)
        monster_repo.save(dead_monster)

        event = MonsterDiedEvent.create(
            aggregate_id=dead_monster_id,
            aggregate_type="MonsterAggregate",
            respawn_tick=150,
            exp=5,
            gold=2,
            loot_table_id=None,
            killer_player_id=None,
            killer_world_object_id=killer_world_id,
            cause=None,
            spot_id=spot_id,
        )
        handler.handle(event)

        killer_after = monster_repo.find_by_world_object_id(killer_world_id)
        assert killer_after is not None
        assert killer_after.hunger == pytest.approx(0.5)  # 0.9 - 0.4

    def test_skip_when_killer_world_object_id_none(self, handler, map_repo, monster_repo):
        """killer_world_object_id が None のとき何もしない"""
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
            spot_id=SpotId(1),
        )
        handler.handle(event)  # 例外なしで終了

    def test_skip_when_spot_id_none(self, handler):
        """spot_id が None でも killer_world_object_id が有効なら処理する（飢餓は Monster 集約のみ参照するため spot 不要）"""
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId.create(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=10,
            gold=5,
            loot_table_id=None,
            killer_player_id=None,
            killer_world_object_id=WorldObjectId.create(99),
            cause=None,
            spot_id=None,
        )
        handler.handle(event)  # 例外なく終了（キラー未登録の場合はスキップ）

    def test_skip_when_dead_not_prey(self, handler, monster_repo):
        """死亡モンスターの race がキラーの prey_races に含まれないとき飢餓は減らない"""
        from ai_rpg_world.domain.common.value_object import WorldTick
        spot_id = SpotId(1)
        killer_world_id = WorldObjectId.create(100)
        killer_template = _template_with_prey(1, frozenset({"orc"}))  # prey は orc のみ
        dead_template = MonsterTemplate(
            template_id=MonsterTemplateId(2),
            name="Goblin",
            base_stats=BaseStats(30, 0, 5, 2, 4, 0, 0),
            reward_info=RewardInfo(5, 2, None),
            respawn_info=RespawnInfo(50, True),
            race=Race.GOBLIN,
            faction=MonsterFactionEnum.ENEMY,
            description="A goblin.",
        )
        killer_monster = MonsterAggregate.create(
            monster_id=MonsterId.create(2),
            template=killer_template,
            world_object_id=killer_world_id,
            skill_loadout=SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=1001, normal_capacity=5, awakened_capacity=5
            ),
        )
        dead_monster = MonsterAggregate.create(
            monster_id=MonsterId.create(1),
            template=dead_template,
            world_object_id=WorldObjectId.create(101),
            skill_loadout=SkillLoadoutAggregate.create(
                SkillLoadoutId(2), owner_id=1002, normal_capacity=5, awakened_capacity=5
            ),
        )
        killer_monster.spawn(Coordinate(1, 1, 0), spot_id, WorldTick(0), initial_hunger=0.9)
        monster_repo.save(killer_monster)
        monster_repo.save(dead_monster)

        event = MonsterDiedEvent.create(
            aggregate_id=dead_monster.monster_id,
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=5,
            gold=2,
            loot_table_id=None,
            killer_player_id=None,
            killer_world_object_id=killer_world_id,
            cause=None,
            spot_id=spot_id,
        )
        handler.handle(event)

        killer_after = monster_repo.find_by_world_object_id(killer_world_id)
        assert killer_after is not None
        assert killer_after.hunger == pytest.approx(0.9)  # 変化なし（goblin は prey ではない）
