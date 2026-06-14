"""World flags subsystem codec (Phase 9-3)。

``runtime._world_flag_state`` (``MutableWorldFlagState``) は scenario が
立てる world-wide flag の集合 (= set[str])。reactive bindings の発火条件や
scenario events の前提条件に使われる。

JSON 化はソート済 string list で行う (= 決定的順序、diff しやすい)。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "world_flags"
SCHEMA_VERSION = 1


class WorldFlagsSubsystemCodec(WorldSubsystemCodec):
    """``MutableWorldFlagState`` を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        flag_state = getattr(runtime, "_world_flag_state", None)
        if flag_state is None:
            raise RuntimeError(
                "runtime._world_flag_state not found; "
                "WorldFlagsSubsystemCodec requires it"
            )
        # frozen set → ソート済 list で出力 (= 決定的)。
        flags = sorted(str(f) for f in flag_state.as_frozen_set())
        return {
            "schema_version": SCHEMA_VERSION,
            "flags": flags,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        flag_state = getattr(runtime, "_world_flag_state", None)
        if flag_state is None:
            raise RuntimeError(
                "runtime._world_flag_state not found; "
                "WorldFlagsSubsystemCodec requires it"
            )
        flags = frozenset(str(f) for f in data.get("flags", []))
        # ``replace_from_interaction`` は名前は interaction 由来だが、本質的
        # に「flag set を完全置換」する API なので restore でも使える。
        flag_state.replace_from_interaction(flags)


__all__ = ["WorldFlagsSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
