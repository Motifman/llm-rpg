"""動的遠景 cue の active 状態 subsystem codec。

段階3では、cue の source 条件が false→true になった境界だけを
世界状態変化として観測へ流す。そのためには「前回評価時点で active
だったか」を per-world state として保持する必要がある。snapshot に
載せないと resume 境界で同じ出現イベントが再発火するため、この codec
で runtime の状態を保存・復元する。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "distant_cue_state"
SCHEMA_VERSION = 1


class DistantCueStateSubsystemCodec(WorldSubsystemCodec):
    """cue ごとの active 境界検出状態を JSON 化する。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        states = getattr(runtime, "_distant_cue_states", None) or {}
        entries = []
        for cue_id, raw_state in states.items():
            state = dict(raw_state)
            last_changed_tick = state.get("last_changed_tick")
            entries.append(
                {
                    "cue_id": str(cue_id),
                    "active": bool(state.get("active", False)),
                    "initialized": bool(state.get("initialized", False)),
                    "last_changed_tick": (
                        None
                        if last_changed_tick is None
                        else int(last_changed_tick)
                    ),
                }
            )
        entries.sort(key=lambda e: e["cue_id"])
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
        restored: dict[str, dict[str, Any]] = {}
        for raw_entry in data.get("entries", []):
            entry = dict(raw_entry)
            cue_id = str(entry["cue_id"])
            active = entry.get("active", False)
            initialized = entry.get("initialized", False)
            if not isinstance(active, bool):
                raise ValueError(
                    f"{SUBSYSTEM_KEY} entry cue_id={cue_id!r} active must be bool"
                )
            if not isinstance(initialized, bool):
                raise ValueError(
                    f"{SUBSYSTEM_KEY} entry cue_id={cue_id!r} initialized must be bool"
                )
            last_changed_tick = entry.get("last_changed_tick")
            restored[cue_id] = {
                "active": active,
                "initialized": initialized,
                "last_changed_tick": (
                    None
                    if last_changed_tick is None
                    else int(last_changed_tick)
                ),
            }
        runtime._distant_cue_states = restored


__all__ = [
    "DistantCueStateSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
