"""「プレイヤー → Being」の対応表 (``PlayerBeings``) を世界の snapshot に入れる (#1928、design_decisions D1928)。

再開したときに、世界と対応表を同じ時点でそろえる。#1339 で環境の集約に移すまでのつなぎ。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import WorldSubsystemCodec
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

SUBSYSTEM_KEY = "player_beings"
SCHEMA_VERSION = 1


def _player_beings_of(runtime: Any) -> Any:
    player_beings = getattr(runtime, "_player_beings", None)
    if player_beings is None:
        raise RuntimeError("runtime._player_beings not found; wire the Being stack before snapshotting")
    return player_beings


class PlayerBeingsSubsystemCodec(WorldSubsystemCodec):
    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "pairs": [
                {"player_id": player_id.value, "being_id": being_id.value}
                for player_id, being_id in _player_beings_of(runtime).pairs()
            ],
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported (expected {SCHEMA_VERSION})")
        pairs = data.get("pairs")
        if not isinstance(pairs, list):
            raise ValueError(f"{SUBSYSTEM_KEY}.pairs must be list, got {type(pairs).__name__}")
        _player_beings_of(runtime).replace_with(
            (PlayerId(int(pair["player_id"])), BeingId(str(pair["being_id"]))) for pair in pairs
        )


__all__ = [
    "SCHEMA_VERSION",
    "SUBSYSTEM_KEY",
    "PlayerBeingsSubsystemCodec",
]
