from __future__ import annotations

import json
import sqlite3

import pytest

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    ExpEffect,
    GoldEffect,
    HealEffect,
    RecoverMpEffect,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import init_game_write_schema
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_profile_write_repository import (
    SqlitePlayerProfileWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_aggregate_repository import SqliteTradeAggregateRepository
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_codec import (
    item_aggregate_to_storage,
    json_bytes_to_player_status,
    storage_to_item_aggregate,
)


def _make_status(player_id: int) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
    )


def _make_consumable_item(item_id: int) -> ItemAggregate:
    spec = ItemSpec(
        item_spec_id=ItemSpecId(501),
        name="Healing Herb",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.UNCOMMON,
        description="heals and restores",
        max_stack_size=MaxStackSize(99),
        consume_effect=CompositeItemEffect(
            effects=(
                HealEffect(amount=20),
                RecoverMpEffect(amount=5),
                GoldEffect(amount=3),
                ExpEffect(amount=7),
            )
        ),
    )
    return ItemAggregate.create(ItemInstanceId(item_id), spec, quantity=2)


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_game_write_schema(conn)
    conn.commit()
    return conn


class TestSharedWriteRepositoryContract:
    def test_trade_repository_requires_active_transaction_for_generate(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteTradeAggregateRepository.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.generate_trade_id()

    def test_profile_repository_requires_active_transaction_for_save(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqlitePlayerProfileWriteRepository.for_shared_unit_of_work(sqlite_conn)
        profile = PlayerProfileAggregate.create(PlayerId(1), PlayerName("Alice"))
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(profile)

    def test_item_repository_requires_active_transaction_for_save(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqliteItemWriteRepository.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(_make_consumable_item(1001))

    def test_inventory_repository_requires_active_transaction_for_save(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqlitePlayerInventoryWriteRepository.for_shared_unit_of_work(sqlite_conn)
        inventory = PlayerInventoryAggregate.create_new_inventory(PlayerId(1))
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(inventory)

    def test_status_repository_requires_active_transaction_for_save(self, sqlite_conn: sqlite3.Connection) -> None:
        repo = SqlitePlayerStatusWriteRepository.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="for_shared_unit_of_work"):
            repo.save(_make_status(1))


class TestItemConsumeEffectCodec:
    def test_consume_effect_roundtrip_in_game_items_payload(self) -> None:
        aggregate = _make_consumable_item(2001)
        item_id, spec_id, payload = item_aggregate_to_storage(aggregate)

        restored = storage_to_item_aggregate(item_id, spec_id, payload)

        assert restored.item_instance.quantity == aggregate.item_instance.quantity
        assert restored.item_spec.consume_effect == aggregate.item_spec.consume_effect

    def test_unknown_consume_effect_kind_raises(self) -> None:
        payload = {
            "quantity": 1,
            "durability": None,
            "spec": {
                "item_spec_id": 1,
                "name": "broken",
                "item_type": ItemType.CONSUMABLE.value,
                "rarity": Rarity.COMMON.value,
                "description": "x",
                "max_stack_size": 10,
                "durability_max": None,
                "equipment_type": None,
                "is_placeable": False,
                "placeable_object_type": None,
                "consume_effect": {"kind": "unknown", "amount": 1},
            },
        }
        with pytest.raises(ValueError, match="unknown consume_effect kind"):
            storage_to_item_aggregate(1, 1, json.dumps(payload))

    def test_item_storage_spec_id_mismatch_raises(self) -> None:
        payload = {
            "quantity": 1,
            "durability": None,
            "spec": {
                "item_spec_id": 999,
                "name": "broken",
                "item_type": ItemType.CONSUMABLE.value,
                "rarity": Rarity.COMMON.value,
                "description": "x",
                "max_stack_size": 10,
                "durability_max": None,
                "equipment_type": None,
                "is_placeable": False,
                "placeable_object_type": None,
                "consume_effect": None,
            },
        }
        with pytest.raises(ValueError, match="item_spec_id column"):
            storage_to_item_aggregate(1, 1, json.dumps(payload))


class TestPlayerStatusJsonCodec:
    def test_rejects_non_utf8_payload(self) -> None:
        with pytest.raises(ValueError, match="UTF-8 JSON"):
            json_bytes_to_player_status(b"\xff\xfe\xfa")

    def test_rejects_non_object_json_root(self) -> None:
        with pytest.raises(ValueError, match="JSON object"):
            json_bytes_to_player_status(b"[]")

    def test_rejects_unsupported_schema_version(self) -> None:
        payload = {"schema_version": 999, "player_id": 1}
        with pytest.raises(ValueError, match="unsupported player status schema_version"):
            json_bytes_to_player_status(json.dumps(payload).encode("utf-8"))
