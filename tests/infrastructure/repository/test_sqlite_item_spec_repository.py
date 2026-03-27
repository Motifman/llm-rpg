"""SQLite item spec repository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_effect import CompositeItemEffect, HealEffect
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.infrastructure.repository.sqlite_item_spec_repository import (
    SqliteItemSpecRepository,
    SqliteItemSpecWriter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _equipment_spec(item_spec_id: int, name: str, rarity: Rarity) -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(item_spec_id),
        name=name,
        item_type=ItemType.EQUIPMENT,
        rarity=rarity,
        description=f"{name} description",
        max_stack_size=MaxStackSize(1),
        durability_max=100,
        equipment_type=EquipmentType.WEAPON,
    )


def _consumable_spec(item_spec_id: int, name: str) -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(item_spec_id),
        name=name,
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        description=f"{name} description",
        max_stack_size=MaxStackSize(20),
        consume_effect=CompositeItemEffect(effects=(HealEffect(amount=20),)),
    )


def _quest_spec(item_spec_id: int, name: str) -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(item_spec_id),
        name=name,
        item_type=ItemType.QUEST,
        rarity=Rarity.RARE,
        description=f"{name} description",
        max_stack_size=MaxStackSize(1),
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteItemSpecRepository:
    def test_find_by_id_returns_none_when_empty(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteItemSpecRepository.for_connection(sqlite_conn)
        assert repo.find_by_id(ItemSpecId(1)) is None

    def test_writer_replace_and_find_roundtrip_with_consume_effect(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteItemSpecWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteItemSpecRepository.for_connection(sqlite_conn)
        writer.replace_spec(_consumable_spec(1, "回復薬"))

        loaded = repo.find_by_id(ItemSpecId(1))
        assert loaded is not None
        assert loaded.name == "回復薬"
        assert loaded.consume_effect is not None

    def test_finders_use_index_columns(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteItemSpecWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteItemSpecRepository.for_connection(sqlite_conn)
        writer.replace_spec(_equipment_spec(1, "鉄の剣", Rarity.COMMON))
        writer.replace_spec(_equipment_spec(2, "鋼の剣", Rarity.UNCOMMON))
        writer.replace_spec(_quest_spec(3, "王家の証",))

        by_type = repo.find_by_type(ItemType.EQUIPMENT)
        by_rarity = repo.find_by_rarity(Rarity.UNCOMMON)
        tradeable = repo.find_tradeable_items()

        assert [spec.item_spec_id for spec in by_type] == [ItemSpecId(1), ItemSpecId(2)]
        assert [spec.item_spec_id for spec in by_rarity] == [ItemSpecId(2)]
        assert [spec.item_spec_id for spec in tradeable] == [ItemSpecId(1), ItemSpecId(2)]

    def test_find_by_name_supports_trimmed_lookup(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteItemSpecWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteItemSpecRepository.for_connection(sqlite_conn)
        writer.replace_spec(_equipment_spec(1, "鉄の剣", Rarity.COMMON))

        loaded = repo.find_by_name("  鉄の剣 ")
        assert loaded is not None
        assert loaded.item_spec_id == ItemSpecId(1)

    def test_shared_writer_requires_active_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteItemSpecWriter.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="writer"):
            writer.replace_spec(_equipment_spec(1, "鉄の剣", Rarity.COMMON))

    def test_shared_writer_delete_and_read_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteItemSpecWriter.for_standalone_connection(sqlite_conn)
        writer.replace_spec(_equipment_spec(1, "鉄の剣", Rarity.COMMON))

        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            tx_writer = SqliteItemSpecWriter.for_shared_unit_of_work(uow.connection)
            repo = SqliteItemSpecRepository.for_connection(uow.connection)
            assert tx_writer.delete_spec(ItemSpecId(1)) is True
            assert repo.find_by_id(ItemSpecId(1)) is None
