"""SQLite loot table repository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import (
    LootEntry,
    LootTableAggregate,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.infrastructure.repository.sqlite_loot_table_repository import (
    SqliteLootTableRepository,
    SqliteLootTableWriter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _loot_table(loot_table_id: int, name: str, item_spec_id: int) -> LootTableAggregate:
    return LootTableAggregate.create(
        loot_table_id=loot_table_id,
        entries=[LootEntry(ItemSpecId(item_spec_id), weight=100)],
        name=name,
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteLootTableRepository:
    def test_find_by_id_returns_none_when_empty(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteLootTableRepository.for_connection(sqlite_conn)
        assert repo.find_by_id(LootTableId(1)) is None

    def test_writer_replace_and_find_roundtrip(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteLootTableWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteLootTableRepository.for_connection(sqlite_conn)
        writer.replace_table(_loot_table(1, "slime-drop", 10))

        loaded = repo.find_by_id(LootTableId(1))
        assert loaded is not None
        assert loaded.loot_table_id == LootTableId(1)
        assert loaded.name == "slime-drop"
        assert loaded.entries[0].item_spec_id == ItemSpecId(10)

    def test_find_by_ids_and_find_all(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteLootTableWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteLootTableRepository.for_connection(sqlite_conn)
        writer.replace_table(_loot_table(1, "a", 10))
        writer.replace_table(_loot_table(2, "b", 11))

        found = repo.find_by_ids([LootTableId(1), LootTableId(9), LootTableId(2)])
        assert [table.loot_table_id for table in found] == [LootTableId(1), LootTableId(2)]
        assert [table.loot_table_id for table in repo.find_all()] == [LootTableId(1), LootTableId(2)]

    def test_shared_writer_requires_active_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteLootTableWriter.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="writer"):
            writer.replace_table(_loot_table(1, "a", 10))

    def test_shared_writer_delete_and_read_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteLootTableWriter.for_standalone_connection(sqlite_conn)
        writer.replace_table(_loot_table(1, "a", 10))

        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            tx_writer = SqliteLootTableWriter.for_shared_unit_of_work(uow.connection)
            repo = SqliteLootTableRepository.for_connection(uow.connection)
            assert tx_writer.delete_table(LootTableId(1)) is True
            assert repo.find_by_id(LootTableId(1)) is None
