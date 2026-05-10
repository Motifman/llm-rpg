"""SQLite monster template repository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.infrastructure.repository.sqlite_monster_template_repository import (
    SqliteMonsterTemplateRepository,
    SqliteMonsterTemplateWriter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _template(template_id: int, name: str) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name=name,
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        reward_info=RewardInfo(0, 0),
        respawn_info=RespawnInfo(1, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description=f"{name} description",
        skill_ids=[],
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteMonsterTemplateRepository:
    def test_find_by_id_returns_none_when_empty(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteMonsterTemplateRepository.for_connection(sqlite_conn)
        assert repo.find_by_id(MonsterTemplateId(1)) is None

    def test_temperature_comfort_fields_round_trip(
        self, sqlite_conn: sqlite3.Connection,
    ) -> None:
        """Phase 4-O B: 温度 comfort 範囲 + discomfort_damage が SQLite で
        round-trip する (migration v25)。"""
        from ai_rpg_world.domain.world_graph.enum.temperature_enum import (
            TemperatureEnum,
        )

        writer = SqliteMonsterTemplateWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteMonsterTemplateRepository.for_connection(sqlite_conn)
        # 寒地に強い氷狼: COLD-NORMAL 快適、それ以外で 2 ダメージ
        template = MonsterTemplate(
            template_id=MonsterTemplateId(42),
            name="IceWolf",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="An ice wolf.",
            min_comfortable_temperature=TemperatureEnum.FREEZING,
            max_comfortable_temperature=TemperatureEnum.NORMAL,
            temperature_discomfort_damage_per_tick=2,
        )
        writer.replace_template(template)

        loaded = repo.find_by_id(MonsterTemplateId(42))
        assert loaded is not None
        assert loaded.min_comfortable_temperature == TemperatureEnum.FREEZING
        assert loaded.max_comfortable_temperature == TemperatureEnum.NORMAL
        assert loaded.temperature_discomfort_damage_per_tick == 2

    def test_default_template_round_trips_with_default_temperature_fields(
        self, sqlite_conn: sqlite3.Connection,
    ) -> None:
        """default 値 (FREEZING / HOT / 0) が round-trip する。"""
        from ai_rpg_world.domain.world_graph.enum.temperature_enum import (
            TemperatureEnum,
        )

        writer = SqliteMonsterTemplateWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteMonsterTemplateRepository.for_connection(sqlite_conn)
        writer.replace_template(_template(1, "DefaultBeast"))

        loaded = repo.find_by_id(MonsterTemplateId(1))
        assert loaded is not None
        assert loaded.min_comfortable_temperature == TemperatureEnum.FREEZING
        assert loaded.max_comfortable_temperature == TemperatureEnum.HOT
        assert loaded.temperature_discomfort_damage_per_tick == 0

    def test_pack_flee_follower_fields_round_trip(
        self, sqlite_conn: sqlite3.Connection,
    ) -> None:
        """Phase 4-O C #2: pack_flee_follower / pack_flee_follower_duration
        が SQLite で round-trip する (migration v27)。"""
        writer = SqliteMonsterTemplateWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteMonsterTemplateRepository.for_connection(sqlite_conn)
        # follower=True, duration=5 のテンプレ
        template = MonsterTemplate(
            template_id=MonsterTemplateId(50),
            name="WolfFollower",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="A follower wolf.",
            pack_flee_follower=True,
            pack_flee_follower_duration=5,
        )
        writer.replace_template(template)

        loaded = repo.find_by_id(MonsterTemplateId(50))
        assert loaded is not None
        assert loaded.pack_flee_follower is True
        assert loaded.pack_flee_follower_duration == 5

    def test_default_pack_flee_fields_are_disabled(
        self, sqlite_conn: sqlite3.Connection,
    ) -> None:
        """default 値 (False / 0) が round-trip し、機能無効状態を維持する。"""
        writer = SqliteMonsterTemplateWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteMonsterTemplateRepository.for_connection(sqlite_conn)
        writer.replace_template(_template(60, "DefaultBeast"))

        loaded = repo.find_by_id(MonsterTemplateId(60))
        assert loaded is not None
        assert loaded.pack_flee_follower is False
        assert loaded.pack_flee_follower_duration == 0

    def test_writer_replace_and_find_roundtrip(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteMonsterTemplateWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteMonsterTemplateRepository.for_connection(sqlite_conn)
        writer.replace_template(_template(1, "Slime"))

        result = repo.find_by_id(MonsterTemplateId(1))
        assert result is not None
        assert result.template_id == MonsterTemplateId(1)
        assert result.name == "Slime"

    def test_find_by_name_supports_trimmed_lookup(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteMonsterTemplateWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteMonsterTemplateRepository.for_connection(sqlite_conn)
        writer.replace_template(_template(1, "Goblin"))

        result = repo.find_by_name("  Goblin  ")
        assert result is not None
        assert result.template_id == MonsterTemplateId(1)

    def test_writer_replace_updates_existing_name_index(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteMonsterTemplateWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteMonsterTemplateRepository.for_connection(sqlite_conn)
        writer.replace_template(_template(1, "Old"))
        writer.replace_template(_template(1, "New"))

        assert repo.find_by_name("Old") is None
        result = repo.find_by_name("New")
        assert result is not None
        assert result.name == "New"

    def test_shared_writer_requires_active_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteMonsterTemplateWriter.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="writer"):
            writer.replace_template(_template(1, "Slime"))

    def test_shared_writer_delete_and_read_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteMonsterTemplateWriter.for_standalone_connection(sqlite_conn)
        writer.replace_template(_template(1, "Slime"))

        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            tx_writer = SqliteMonsterTemplateWriter.for_shared_unit_of_work(uow.connection)
            repo = SqliteMonsterTemplateRepository.for_connection(uow.connection)
            assert tx_writer.delete_template(MonsterTemplateId(1)) is True
            assert repo.find_by_id(MonsterTemplateId(1)) is None
