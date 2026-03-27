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
