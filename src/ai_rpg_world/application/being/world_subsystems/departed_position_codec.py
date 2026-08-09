"""物理グラフ外にある、去った主体の位置を保存・復元する。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import WorldSubsystemCodec
from ai_rpg_world.application.player.services.departed_position_store import DepartedPositionStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

SUBSYSTEM_KEY = "departed_position"
SCHEMA_VERSION = 1


class DepartedPositionSubsystemCodec(WorldSubsystemCodec):
    """DepartedPositionStore を player_id 順の JSON と往復させる。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    @staticmethod
    def _store(runtime: Any) -> DepartedPositionStore:
        store = getattr(runtime, "_departed_position_store", None)
        if not isinstance(store, DepartedPositionStore):
            raise RuntimeError(
                "runtime._departed_position_store not found; "
                "DepartedPositionSubsystemCodec requires it"
            )
        return store

    def capture(self, runtime: Any) -> dict[str, Any]:
        positions = self._store(runtime).snapshot()
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": [
                {"player_id": int(player_id), "spot_id": int(spot_id)}
                for player_id, spot_id in sorted(
                    positions.items(), key=lambda item: int(item[0])
                )
            ],
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise ValueError(f"{SUBSYSTEM_KEY} entries must be a list")
        restored: dict[PlayerId, SpotId] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{SUBSYSTEM_KEY} entry must be an object")
            player_id = PlayerId(int(entry["player_id"]))
            if player_id in restored:
                raise ValueError(
                    f"{SUBSYSTEM_KEY} duplicate player_id={int(player_id)}"
                )
            restored[player_id] = SpotId.create(entry["spot_id"])
        self._store(runtime).replace_all(restored)


__all__ = ["DepartedPositionSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
