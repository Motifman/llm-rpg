"""Internal snapshot codecs for world-state SQLite repositories."""

from __future__ import annotations

import pickle

from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate


def physical_map_to_blob(physical_map: PhysicalMapAggregate) -> bytes:
    """Serialize a physical map aggregate as an internal binary snapshot."""
    return pickle.dumps(physical_map, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_physical_map(blob: bytes) -> PhysicalMapAggregate:
    """Restore a physical map aggregate from an internal binary snapshot."""
    restored = pickle.loads(blob)
    if not isinstance(restored, PhysicalMapAggregate):
        raise ValueError("physical map payload did not restore a PhysicalMapAggregate")
    return restored


__all__ = ["blob_to_physical_map", "physical_map_to_blob"]
