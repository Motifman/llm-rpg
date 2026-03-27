"""SQLite item write repository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)


def _equipment_item(item_instance_id: int, item_spec_id: int) -> ItemAggregate:
    spec = ItemSpec(
        item_spec_id=ItemSpecId(item_spec_id),
        name=f"item-{item_spec_id}",
        item_type=ItemType.EQUIPMENT,
        rarity=Rarity.COMMON,
        description="test item",
        max_stack_size=MaxStackSize(1),
        durability_max=100,
        equipment_type=EquipmentType.WEAPON,
    )
    return ItemAggregate.create(ItemInstanceId(item_instance_id), spec, quantity=1)


def _status(player_id: int) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(100),
        hp=Hp.create(10, 10),
        mp=Mp.create(10, 10),
        stamina=Stamina.create(10, 10),
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_game_write_schema(conn)
    conn.commit()
    return conn


class TestSqliteItemWriteRepository:
    def test_find_by_owner_id_returns_inventory_equipment_reserved_union(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        item_repo = SqliteItemWriteRepository.for_standalone_connection(sqlite_conn)
        inventory_repo = SqlitePlayerInventoryWriteRepository.for_standalone_connection(
            sqlite_conn
        )

        item_a = _equipment_item(1001, 11)
        item_b = _equipment_item(1002, 12)
        item_c = _equipment_item(1003, 13)
        item_repo.save(item_a)
        item_repo.save(item_b)
        item_repo.save(item_c)

        inventory_slots = {SlotId(i): None for i in range(3)}
        inventory_slots[SlotId(0)] = item_a.item_instance_id
        inventory_slots[SlotId(1)] = item_c.item_instance_id
        equipment_slots = {slot: None for slot in EquipmentSlotType}
        equipment_slots[EquipmentSlotType.WEAPON] = item_b.item_instance_id
        equipment_slots[EquipmentSlotType.ACCESSORY] = item_c.item_instance_id
        inventory = PlayerInventoryAggregate.restore_from_data(
            player_id=PlayerId(1),
            max_slots=3,
            inventory_slots=inventory_slots,
            equipment_slots=equipment_slots,
            reserved_item_ids={item_c.item_instance_id},
        )
        inventory_repo.save(inventory)

        owned = item_repo.find_by_owner_id(1)
        assert [int(item.item_instance_id) for item in owned] == [1001, 1002, 1003]

    def test_find_by_owner_id_returns_empty_when_owner_not_found(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        item_repo = SqliteItemWriteRepository.for_standalone_connection(sqlite_conn)
        assert item_repo.find_by_owner_id(9999) == []

    def test_inventory_save_rolls_back_when_multi_table_write_fails(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        inventory_repo = SqlitePlayerInventoryWriteRepository.for_standalone_connection(
            sqlite_conn
        )
        inventory = PlayerInventoryAggregate.create_new_inventory(PlayerId(10), max_slots=2)
        sqlite_conn.execute("DROP TABLE game_player_reserved_items")

        with pytest.raises(sqlite3.OperationalError):
            inventory_repo.save(inventory)

        cur = sqlite_conn.execute(
            "SELECT COUNT(*) FROM game_player_inventories WHERE player_id = ?",
            (10,),
        )
        assert int(cur.fetchone()[0]) == 0

    def test_status_save_rolls_back_when_multi_table_write_fails(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        status_repo = SqlitePlayerStatusWriteRepository.for_standalone_connection(sqlite_conn)
        sqlite_conn.execute("DROP TABLE game_player_active_effects")

        with pytest.raises(sqlite3.OperationalError):
            status_repo.save(_status(20))

        cur = sqlite_conn.execute(
            "SELECT COUNT(*) FROM game_player_statuses WHERE player_id = ?",
            (20,),
        )
        assert int(cur.fetchone()[0]) == 0
