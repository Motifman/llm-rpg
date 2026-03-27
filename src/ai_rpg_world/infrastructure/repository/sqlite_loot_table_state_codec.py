"""Helpers for normalized loot table persistence."""

from __future__ import annotations

from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootEntry, LootTableAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


def build_loot_table(*, loot_table_id: int, name: str, entry_rows: list[object]) -> LootTableAggregate:
    return LootTableAggregate.create(
        loot_table_id=LootTableId(loot_table_id),
        name=name,
        entries=[
            LootEntry(
                item_spec_id=ItemSpecId(int(row["item_spec_id"])),
                weight=int(row["weight"]),
                min_quantity=int(row["min_quantity"]),
                max_quantity=int(row["max_quantity"]),
            )
            for row in entry_rows
        ],
    )

