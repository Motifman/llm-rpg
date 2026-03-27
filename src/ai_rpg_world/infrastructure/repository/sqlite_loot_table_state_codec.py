"""Pickle codec helpers for LootTableAggregate snapshots."""

from __future__ import annotations

import pickle

from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate


def loot_table_to_blob(table: LootTableAggregate) -> bytes:
    return pickle.dumps(table, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_loot_table(blob: bytes) -> LootTableAggregate:
    table = pickle.loads(blob)
    if not isinstance(table, LootTableAggregate):
        raise TypeError(
            "game_loot_tables.aggregate_blob does not contain a LootTableAggregate instance"
        )
    return table


__all__ = ["blob_to_loot_table", "loot_table_to_blob"]
