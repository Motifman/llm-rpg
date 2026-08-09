"""倒れた身体の位置と時刻を保存・復元する world subsystem codec。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)
from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRecord,
    FallenBodyRegistry,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

SUBSYSTEM_KEY = "fallen_body"
SCHEMA_VERSION = 1


class FallenBodySubsystemCodec(WorldSubsystemCodec):
    """FallenBodyRegistry を player_id 順の JSON と往復させる。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    @staticmethod
    def _registry(runtime: Any) -> FallenBodyRegistry:
        registry = getattr(runtime, "_fallen_body_registry", None)
        if not isinstance(registry, FallenBodyRegistry):
            raise RuntimeError(
                "runtime._fallen_body_registry not found; "
                "FallenBodySubsystemCodec requires it"
            )
        return registry

    def capture(self, runtime: Any) -> dict[str, Any]:
        records = self._registry(runtime).snapshot()
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": [
                {
                    "player_id": int(record.player_id),
                    "spot_id": int(record.spot_id),
                    "downed_at_tick": record.downed_at_tick.value,
                }
                for _, record in sorted(
                    records.items(), key=lambda item: int(item[0])
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
        restored: dict[PlayerId, FallenBodyRecord] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{SUBSYSTEM_KEY} entry must be an object")
            player_id = PlayerId(int(entry["player_id"]))
            if player_id in restored:
                raise ValueError(
                    f"{SUBSYSTEM_KEY} duplicate player_id={int(player_id)}"
                )
            restored[player_id] = FallenBodyRecord(
                player_id=player_id,
                spot_id=SpotId.create(entry["spot_id"]),
                downed_at_tick=WorldTick(int(entry["downed_at_tick"])),
            )
        self._registry(runtime).replace_all(restored)


__all__ = ["FallenBodySubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
