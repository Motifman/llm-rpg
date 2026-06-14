"""WorldTick subsystem codec (Phase 9-2)。

world tick は world snapshot の最も基本的な要素。これがないと「tick=30 から
続行」が成立しない。``runtime._time_provider`` が ``InMemoryGameTimeProvider``
で、Phase 9-2 で ``set_current_tick`` を追加済。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "world_tick"
SCHEMA_VERSION = 1


class WorldTickSubsystemCodec(WorldSubsystemCodec):
    """``runtime._time_provider`` の current_tick を save / restore する。

    ``set_current_tick`` は Phase 9-2 で追加した restore 専用の入口。
    通常の simulation 経路は ``advance_tick`` だけを使う。
    """

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        time_provider = getattr(runtime, "_time_provider", None)
        if time_provider is None:
            raise RuntimeError(
                "runtime._time_provider not found; "
                "WorldTickSubsystemCodec requires it"
            )
        tick = time_provider.get_current_tick()
        return {
            "schema_version": SCHEMA_VERSION,
            "world_tick": int(tick.value),
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        time_provider = getattr(runtime, "_time_provider", None)
        if time_provider is None:
            raise RuntimeError(
                "runtime._time_provider not found; "
                "WorldTickSubsystemCodec requires it"
            )
        if not hasattr(time_provider, "set_current_tick"):
            raise RuntimeError(
                "runtime._time_provider does not support set_current_tick; "
                "Phase 9-2 expected InMemoryGameTimeProvider with restore setter"
            )
        time_provider.set_current_tick(int(data["world_tick"]))


__all__ = ["WorldTickSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
