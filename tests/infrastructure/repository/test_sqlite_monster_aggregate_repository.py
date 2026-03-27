"""SQLite MonsterRepository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum, MonsterStatusEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.sqlite_monster_aggregate_repository import (
    SqliteMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_physical_map_repository import (
    SqlitePhysicalMapRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _sample_template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Slime",
        base_stats=BaseStats(100, 50, 20, 15, 10, 0.05, 0.03),
        reward_info=RewardInfo(exp=10, gold=5, loot_table_id=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A slime.",
    )


def _loadout(owner_id: int) -> SkillLoadoutAggregate:
    return SkillLoadoutAggregate.create(
        SkillLoadoutId(owner_id), owner_id, normal_capacity=10, awakened_capacity=10
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteMonsterAggregateRepository:
    def test_shared_repository_requires_active_transaction_for_save(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteMonsterAggregateRepository.for_shared_unit_of_work(sqlite_conn)
        monster = MonsterAggregate.create(
            MonsterId(1), _sample_template(), WorldObjectId(1000), skill_loadout=_loadout(1)
        )
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(monster)

    def test_save_and_find_roundtrip(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteMonsterAggregateRepository.for_standalone_connection(sqlite_conn)
        monster = MonsterAggregate.create(
            MonsterId(1), _sample_template(), WorldObjectId(1000), skill_loadout=_loadout(1)
        )
        monster.spawn(Coordinate(1, 2, 0), SpotId(7), WorldTick(0))
        repo.save(monster)

        loaded = repo.find_by_id(MonsterId(1))
        assert loaded is not None
        assert loaded.monster_id == MonsterId(1)
        assert loaded.world_object_id == WorldObjectId(1000)
        assert loaded.coordinate == Coordinate(1, 2, 0)

    def test_find_by_world_object_id_and_spot(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteMonsterAggregateRepository.for_standalone_connection(sqlite_conn)
        m1 = MonsterAggregate.create(
            MonsterId(1), _sample_template(), WorldObjectId(1001), skill_loadout=_loadout(11)
        )
        m1.spawn(Coordinate(1, 1, 0), SpotId(1), WorldTick(0))
        m2 = MonsterAggregate.create(
            MonsterId(2), _sample_template(), WorldObjectId(1002), skill_loadout=_loadout(12)
        )
        m2.spawn(Coordinate(2, 2, 0), SpotId(1), WorldTick(0))
        m3 = MonsterAggregate.create(
            MonsterId(3), _sample_template(), WorldObjectId(1003), skill_loadout=_loadout(13)
        )
        m3.spawn(Coordinate(3, 3, 0), SpotId(2), WorldTick(0))
        m2.apply_damage(100, WorldTick(5))
        repo.save(m1)
        repo.save(m2)
        repo.save(m3)

        found = repo.find_by_world_object_id(WorldObjectId(1002))
        assert found is not None
        assert found.monster_id == MonsterId(2)
        assert found.status == MonsterStatusEnum.DEAD

        spot1 = repo.find_by_spot_id(SpotId(1))
        assert {m.monster_id for m in spot1} == {MonsterId(1), MonsterId(2)}

    def test_world_object_id_sequence_is_shared_with_physical_map(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            map_repo = SqlitePhysicalMapRepository.for_shared_unit_of_work(uow.connection)
            monster_repo = SqliteMonsterAggregateRepository.for_shared_unit_of_work(
                uow.connection
            )
            first = map_repo.generate_world_object_id()
            second = monster_repo.generate_world_object_id_for_npc()

        assert first.value == 100000
        assert second.value == 100001

    def test_monster_id_sequence_rolls_back(self, sqlite_conn: sqlite3.Connection) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with pytest.raises(RuntimeError, match="abort"):
            with uow:
                repo = SqliteMonsterAggregateRepository.for_shared_unit_of_work(uow.connection)
                generated = repo.generate_monster_id()
                assert generated.value == 1
                raise RuntimeError("abort")

        with uow:
            repo = SqliteMonsterAggregateRepository.for_shared_unit_of_work(uow.connection)
            generated2 = repo.generate_monster_id()
        assert generated2.value == 1
