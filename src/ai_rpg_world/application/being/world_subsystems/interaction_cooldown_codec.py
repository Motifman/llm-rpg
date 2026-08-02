"""対人行為の再使用間隔の subsystem codec。

**store を足す PR で同時に入れる。** `game_phase_codec` と同じ理由で、
「あとで足す」と長走実験の終了 → 再開で連続性が静かに壊れる。

ここで落とすと、**再開のたびに全員の間隔がリセットされる**。snapshot を
挟んだ run では連続殺害が復活し、挟まない run とは違う結果になる。
再現性のある実験にならない。

間隔は tick 基準で PlayerId をキーにする world 局所の状態なので、
`BeingMemorySnapshotService` ではなく world snapshot 側に載る。Being は
世界をまたいで永続するが、「tick 12 に使った」を別の世界へ持ち越しても
tick の採番が違うので意味が無い。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "interaction_cooldown"
SCHEMA_VERSION = 1


class InteractionCooldownSubsystemCodec(WorldSubsystemCodec):
    """``runtime._interaction_cooldown_store`` を保存・復元する。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        store = getattr(runtime, "_interaction_cooldown_store", None)
        if store is None:
            return {"schema_version": SCHEMA_VERSION, "entries": []}
        return {
            "schema_version": SCHEMA_VERSION,
            # (player_id, action_name, tick) の平坦な列にする。入れ子の dict を
            # JSON に落とすと、player_id が文字列 key に化けて復元で int に
            # 戻し忘れる。平坦なら型が 1 か所で決まる。
            "entries": [
                [int(player_id), str(action_name), int(tick)]
                for player_id, actions in store.snapshot().items()
                for action_name, tick in actions.items()
            ],
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        store = getattr(runtime, "_interaction_cooldown_store", None)
        if store is None:
            return
        raw_entries = data.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValueError(
                f"{SUBSYSTEM_KEY} entries must be a list, got {type(raw_entries)}"
            )
        entries = []
        for entry in raw_entries:
            if not isinstance(entry, (list, tuple)) or len(entry) != 3:
                raise ValueError(
                    f"{SUBSYSTEM_KEY} entry must be [player_id, action_name, tick], "
                    f"got {entry!r}"
                )
            entries.append((int(entry[0]), str(entry[1]), int(entry[2])))
        store.replace_all(entries)


__all__ = [
    "InteractionCooldownSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
