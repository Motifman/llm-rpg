"""InMemoryMonsterAggregateRepository のテスト（generate_monster_id, find_by_spot_id）"""

import pytest
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum, MonsterStatusEnum
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)


def _sample_template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Slime",
        base_stats=BaseStats(100, 50, 20, 15, 10, 0.05, 0.03),
        reward_info=RewardInfo(exp=10, gold=5, loot_table_id="loot_01"),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A slime.",
    )


class TestInMemoryMonsterAggregateRepository:
    """InMemoryMonsterAggregateRepository のテスト"""

    @pytest.fixture
    def data_store(self) -> InMemoryDataStore:
        store = InMemoryDataStore()
        store.clear_all()
        return store

    @pytest.fixture
    def repo(self, data_store: InMemoryDataStore) -> InMemoryMonsterAggregateRepository:
        return InMemoryMonsterAggregateRepository(data_store=data_store)

    def test_generate_monster_id_returns_unique_ids(self, repo: InMemoryMonsterAggregateRepository):
        """generate_monster_id は一意の ID を返す"""
        id1 = repo.generate_monster_id()
        id2 = repo.generate_monster_id()
        assert id1 != id2
        assert isinstance(id1, MonsterId)
        assert isinstance(id2, MonsterId)

    def test_generate_world_object_id_for_npc_returns_unique_ids(
        self, repo: InMemoryMonsterAggregateRepository
    ):
        """generate_world_object_id_for_npc は一意の ID を返す"""
        id1 = repo.generate_world_object_id_for_npc()
        id2 = repo.generate_world_object_id_for_npc()
        assert id1 != id2
        assert isinstance(id1, WorldObjectId)
        assert isinstance(id2, WorldObjectId)

    def test_find_by_spot_id_returns_empty_when_none(self, repo: InMemoryMonsterAggregateRepository):
        """該当スポットにモンスターがいないときは空リスト"""
        result = repo.find_by_spot_id(SpotId(1))
        assert result == []

    def test_find_by_spot_id_returns_monsters_for_spot(
        self, repo: InMemoryMonsterAggregateRepository
    ):
        """find_by_spot_id は指定スポットに紐づくモンスターのみ返す"""
        template = _sample_template()
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1001), 1001, normal_capacity=10, awakened_capacity=10
        )
        m1 = MonsterAggregate.create(
            MonsterId(1), template, WorldObjectId(1001), skill_loadout=loadout
        )
        m1.spawn(Coordinate(1, 1, 0), SpotId(1), WorldTick(0))
        loadout2 = SkillLoadoutAggregate.create(
            SkillLoadoutId(1002), 1002, normal_capacity=10, awakened_capacity=10
        )
        m2 = MonsterAggregate.create(
            MonsterId(2), template, WorldObjectId(1002), skill_loadout=loadout2
        )
        m2.spawn(Coordinate(2, 2, 0), SpotId(1), WorldTick(0))
        loadout3 = SkillLoadoutAggregate.create(
            SkillLoadoutId(1003), 1003, normal_capacity=10, awakened_capacity=10
        )
        m3 = MonsterAggregate.create(
            MonsterId(3), template, WorldObjectId(1003), skill_loadout=loadout3
        )
        m3.spawn(Coordinate(3, 3, 0), SpotId(2), WorldTick(0))
        repo.save(m1)
        repo.save(m2)
        repo.save(m3)
        result_spot1 = repo.find_by_spot_id(SpotId(1))
        result_spot2 = repo.find_by_spot_id(SpotId(2))
        assert len(result_spot1) == 2
        assert len(result_spot2) == 1
        spot1_ids = {m.monster_id for m in result_spot1}
        assert spot1_ids == {MonsterId(1), MonsterId(2)}
        assert result_spot2[0].monster_id == MonsterId(3)

    def test_find_by_spot_id_includes_dead_monsters(
        self, repo: InMemoryMonsterAggregateRepository
    ):
        """find_by_spot_id は DEAD のモンスターも含む"""
        template = _sample_template()
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1001), 1001, normal_capacity=10, awakened_capacity=10
        )
        m = MonsterAggregate.create(
            MonsterId(1), template, WorldObjectId(1001), skill_loadout=loadout
        )
        m.spawn(Coordinate(1, 1, 0), SpotId(1), WorldTick(0))
        m.apply_damage(100, WorldTick(10))
        repo.save(m)
        result = repo.find_by_spot_id(SpotId(1))
        assert len(result) == 1
        assert result[0].status == MonsterStatusEnum.DEAD

    def test_save_then_find_by_id_returns_same_aggregate(
        self, repo: InMemoryMonsterAggregateRepository
    ):
        """save 後に find_by_id で同一集約を取得できる"""
        template = _sample_template()
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1001), 1001, normal_capacity=10, awakened_capacity=10
        )
        monster_id = MonsterId(1)
        world_object_id = WorldObjectId(1001)
        m = MonsterAggregate.create(
            monster_id, template, world_object_id, skill_loadout=loadout
        )
        m.spawn(Coordinate(0, 0, 0), SpotId(1), WorldTick(0))
        repo.save(m)
        found = repo.find_by_id(monster_id)
        assert found is not None
        assert found.monster_id == monster_id
        assert found.world_object_id == world_object_id
        assert found.status == MonsterStatusEnum.ALIVE
        assert found.coordinate == Coordinate(0, 0, 0)

    def test_save_then_find_by_world_object_id_returns_same_aggregate(
        self, repo: InMemoryMonsterAggregateRepository
    ):
        """save 後に find_by_world_object_id で同一集約を取得できる"""
        template = _sample_template()
        loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1001), 1001, normal_capacity=10, awakened_capacity=10
        )
        monster_id = MonsterId(1)
        world_object_id = WorldObjectId(1001)
        m = MonsterAggregate.create(
            monster_id, template, world_object_id, skill_loadout=loadout
        )
        m.spawn(Coordinate(2, 3, 0), SpotId(1), WorldTick(0))
        repo.save(m)
        found = repo.find_by_world_object_id(world_object_id)
        assert found is not None
        assert found.monster_id == monster_id
        assert found.world_object_id == world_object_id
        assert found.spot_id == SpotId(1)
        assert found.coordinate == Coordinate(2, 3, 0)
