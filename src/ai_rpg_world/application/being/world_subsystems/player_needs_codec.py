"""Player needs (AgentNeeds = HUNGER / FATIGUE 等) subsystem codec (Phase 9-2)。

scenario が survival 系 (hunger / fatigue が tick 経過で増加し、agent の
行動動機になる) のとき、resume で「30 tick 後の hunger を保持」できなければ
意味的に壊れる。

NeedType は ``str`` ベースの Enum なので value を文字列で保存する。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "player_needs"
SCHEMA_VERSION = 1


class PlayerNeedsSubsystemCodec(WorldSubsystemCodec):
    """各 player の AgentNeeds (= hunger / fatigue 等) を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_status_repo not found; "
                "PlayerNeedsSubsystemCodec requires it"
            )
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            needs = agg._needs
            need_dicts: list[dict[str, Any]] = []
            for n in needs:
                need_dicts.append(
                    {
                        "need_type": n.need_type.value,
                        "value": int(n.value),
                        "max_value": int(n.max_value),
                    }
                )
            entries.append(
                {
                    "player_id": int(pid.value),
                    "needs": need_dicts,
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
        from ai_rpg_world.domain.player.value_object.agent_need import (
            AgentNeed,
            NeedType,
        )
        from ai_rpg_world.domain.player.value_object.agent_needs import (
            AgentNeeds,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_status_repo not found; "
                "PlayerNeedsSubsystemCodec requires it"
            )
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            need_objs: list[AgentNeed] = []
            for n_data in entry.get("needs", []):
                # NeedType は Enum: 未知値は ``ValueError`` で fail-fast
                need_type = NeedType(str(n_data["need_type"]))
                need_objs.append(
                    AgentNeed.create(
                        need_type=need_type,
                        value=int(n_data["value"]),
                        max_value=int(n_data["max_value"]),
                    )
                )
            agg._needs = AgentNeeds(tuple(need_objs))
            if hasattr(agg, "_events"):
                agg._events.clear()
            repo.save(agg)


__all__ = ["PlayerNeedsSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
