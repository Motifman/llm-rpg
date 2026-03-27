"""Pickle codec helpers for SpotSpawnTable snapshots."""

from __future__ import annotations

import pickle

from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable


def spawn_table_to_blob(table: SpotSpawnTable) -> bytes:
    return pickle.dumps(table, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_spawn_table(blob: bytes) -> SpotSpawnTable:
    table = pickle.loads(blob)
    if not isinstance(table, SpotSpawnTable):
        raise TypeError(
            "game_spawn_tables.aggregate_blob does not contain a SpotSpawnTable instance"
        )
    return table


__all__ = ["blob_to_spawn_table", "spawn_table_to_blob"]
