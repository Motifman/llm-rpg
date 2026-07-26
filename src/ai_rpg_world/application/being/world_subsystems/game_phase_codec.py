"""ゲームフェーズ (自由時間 / 会議) の subsystem codec。

**store を足す PR で同時に入れる。** per-Being store の checklist
(`design_decisions.md` #27) が定めているのと同じ理由で、「あとで足す」と
長走実験の終了 → 再開で連続性が静かに壊れる。フェーズは per-world なので
`BeingMemorySnapshotService` ではなく world snapshot 側に載る。

会議の途中で snapshot を取って再開したとき、`started_at_tick` と
`last_activity_tick` が失われると、**会議の tick 上限と沈黙上限の起点が
リセットされる**。再開のたびに会議が延びるので、再現性のある実験にならない。
だから derive せず素直に保存する。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.value_object.game_phase_state import (
    GamePhaseState,
)

SUBSYSTEM_KEY = "game_phase"
SCHEMA_VERSION = 1


def _encode(state: GamePhaseState) -> dict[str, Any]:
    return {
        "phase": state.phase.value,
        "started_at_tick": state.started_at_tick,
        "last_activity_tick": state.last_activity_tick,
        "trigger": state.trigger,
        # 招集者も保存する。落とすと、再開後の現在状態から
        # 「誰が呼びかけたか」が消えて議論の出発点が失われる。
        "initiator_player_id": state.initiator_player_id,
    }


def _decode(raw: Any) -> GamePhaseState:
    if not isinstance(raw, dict):
        raise ValueError(f"{SUBSYSTEM_KEY} entry must be an object, got {type(raw)}")
    phase_raw = raw.get("phase")
    try:
        phase = GamePhase(phase_raw)
    except ValueError as exc:
        valid = ", ".join(p.value for p in GamePhase)
        raise ValueError(
            f"{SUBSYSTEM_KEY} phase={phase_raw!r} unknown (expected one of {valid})"
        ) from exc
    return GamePhaseState(
        phase=phase,
        started_at_tick=int(raw.get("started_at_tick", 0)),
        last_activity_tick=int(raw.get("last_activity_tick", 0)),
        trigger=raw.get("trigger"),
        initiator_player_id=(
            int(raw["initiator_player_id"])
            if raw.get("initiator_player_id") is not None
            else None
        ),
    )


class GamePhaseSubsystemCodec(WorldSubsystemCodec):
    """``runtime._game_phase_store`` の現在状態と履歴を保存・復元する。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        store = getattr(runtime, "_game_phase_store", None)
        if store is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "current": None,
                "history": [],
                "used_emergency_buttons": [],
                "reported_bodies": [],
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "current": _encode(store.current),
            "history": [_encode(entry) for entry in store.history],
            # 招集の制限も保存する。落とすと再開のたびに全員の緊急ボタンが
            # 復活し、同じ死体をまた報告できてしまう。
            "used_emergency_buttons": list(store.used_emergency_buttons),
            "reported_bodies": list(store.reported_bodies),
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        store = getattr(runtime, "_game_phase_store", None)
        if store is None:
            return
        current_raw = data.get("current")
        if current_raw is None:
            # フェーズを持たない runtime で取った snapshot。触らない。
            return
        store.replace_all(
            current=_decode(current_raw),
            history=[_decode(entry) for entry in data.get("history", [])],
            used_emergency_buttons=[
                int(pid) for pid in data.get("used_emergency_buttons", [])
            ],
            reported_bodies=[int(pid) for pid in data.get("reported_bodies", [])],
        )


__all__ = ["GamePhaseSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
