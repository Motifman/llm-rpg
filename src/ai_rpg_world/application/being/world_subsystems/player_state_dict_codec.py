"""Player state dict subsystem codec (Phase 9-2b)。

PlayerStatusAggregate の ``_state`` は scenario が flat dict で書き込む
自由領域 (Phase 4-D-2)。値型は JSON primitive 限定の規約のため、そのまま
JSON 化できる。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "player_state_dict"
SCHEMA_VERSION = 1


class PlayerStateDictSubsystemCodec(WorldSubsystemCodec):
    """各 player の ``_state`` (= scenario-defined flat dict) を JSON 化。

    値型 (JSON primitive 限定) のバリデーションは
    ``PlayerStatusAggregate.__init__`` 内の ``_validate_player_state_dict``
    が担保。本 codec はそれに従って round-trip するだけ。
    """

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_status_repo not found; "
                "PlayerStateDictSubsystemCodec requires it"
            )
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            # _state は dict[str, Any] (JSON primitive only)。dict() で shallow
            # copy して JSON serializer に渡す。
            entries.append(
                {
                    "player_id": int(pid.value),
                    "state": dict(agg._state),
                }
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
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_status_repo not found; "
                "PlayerStateDictSubsystemCodec requires it"
            )
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            state_dict = dict(entry.get("state", {}))
            # value 型は dict[str, Any] でアプリ層の VO 規約。Aggregate
            # constructor 経由ではなく直接 _state を入れ替える (= restore
            # semantics)。validation は呼出元 (= snapshot 出力者) を信頼する。
            agg._state = state_dict
            if hasattr(agg, "_events"):
                agg._events.clear()
            repo.save(agg)


__all__ = [
    "PlayerStateDictSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
