"""Internal snapshot codecs for monster-state SQLite repositories."""

from __future__ import annotations

import pickle

from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate


def monster_to_blob(monster: MonsterAggregate) -> bytes:
    """Serialize a monster aggregate as an internal binary snapshot."""
    return pickle.dumps(monster, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_monster(blob: bytes) -> MonsterAggregate:
    """Restore a monster aggregate from an internal binary snapshot."""
    restored = pickle.loads(blob)
    if not isinstance(restored, MonsterAggregate):
        raise ValueError("monster payload did not restore a MonsterAggregate")
    return restored


__all__ = ["blob_to_monster", "monster_to_blob"]
