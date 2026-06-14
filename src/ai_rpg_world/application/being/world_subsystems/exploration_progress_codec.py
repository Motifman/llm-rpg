"""Spot exploration progress subsystem codec (Phase 9-3)。

``runtime._exploration_progress`` (``InMemorySpotExplorationProgressStore``)
は (player_id, spot_id) → 探索回数 の dict。scenario によっては
「N 回 explore してから何かが起きる」設計があり、resume で count をリセット
すると意味が変わる。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "exploration_progress"
SCHEMA_VERSION = 1


class SpotExplorationProgressSubsystemCodec(WorldSubsystemCodec):
    """(player_id, spot_id) → 探索回数 を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        store = getattr(runtime, "_exploration_progress", None)
        if store is None:
            raise RuntimeError(
                "runtime._exploration_progress not found; "
                "SpotExplorationProgressSubsystemCodec requires it"
            )
        # 内部 dict は (player_id_int, spot_id_int) -> count。
        # 決定的順序のため (player_id, spot_id) でソート。
        entries = sorted(
            (
                {
                    "player_id": int(pid),
                    "spot_id": int(sid),
                    "count": int(count),
                }
                for (pid, sid), count in store._counts.items()
            ),
            key=lambda d: (d["player_id"], d["spot_id"]),
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": entries,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        store = getattr(runtime, "_exploration_progress", None)
        if store is None:
            raise RuntimeError(
                "runtime._exploration_progress not found; "
                "SpotExplorationProgressSubsystemCodec requires it"
            )
        store._counts.clear()
        for entry in data.get("entries", []):
            key = (int(entry["player_id"]), int(entry["spot_id"]))
            store._counts[key] = int(entry["count"])


__all__ = [
    "SpotExplorationProgressSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
