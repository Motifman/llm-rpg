"""SQLite spawn table repository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.spawn_slot import SpawnSlot
from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_spawn_table_repository import (
    SqliteSpawnTableRepository,
    SqliteSpawnTableWriter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _table(spot_id: int, template_id: int = 1) -> SpotSpawnTable:
    sid = SpotId(spot_id)
    return SpotSpawnTable(
        spot_id=sid,
        slots=[
            SpawnSlot(
                spot_id=sid,
                coordinate=Coordinate(1, 2, 0),
                template_id=MonsterTemplateId.create(template_id),
            )
        ],
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteSpawnTableRepository:
    def test_find_by_spot_id_returns_none_when_empty(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteSpawnTableRepository.for_connection(sqlite_conn)
        assert repo.find_by_spot_id(SpotId(1)) is None

    def test_writer_replace_and_find_roundtrip(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteSpawnTableWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteSpawnTableRepository.for_connection(sqlite_conn)
        writer.replace_table(_table(1))

        result = repo.find_by_spot_id(SpotId(1))
        assert result is not None
        assert result.spot_id == SpotId(1)
        assert len(result.slots) == 1
        assert result.slots[0].coordinate == Coordinate(1, 2, 0)

    def test_writer_replace_updates_existing_table(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteSpawnTableWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteSpawnTableRepository.for_connection(sqlite_conn)
        writer.replace_table(_table(1, template_id=1))
        writer.replace_table(_table(1, template_id=2))

        result = repo.find_by_spot_id(SpotId(1))
        assert result is not None
        assert result.slots[0].template_id == MonsterTemplateId.create(2)

    def test_shared_writer_requires_active_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteSpawnTableWriter.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="writer"):
            writer.replace_table(_table(1))

    def test_shared_writer_is_visible_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            writer = SqliteSpawnTableWriter.for_shared_unit_of_work(uow.connection)
            repo = SqliteSpawnTableRepository.for_connection(uow.connection)
            writer.replace_table(_table(3))
            result = repo.find_by_spot_id(SpotId(3))
            assert result is not None
            assert result.spot_id == SpotId(3)
