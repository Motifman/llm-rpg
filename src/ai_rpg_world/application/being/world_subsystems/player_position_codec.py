"""Player position subsystem codec (Phase 9-2)。

各 player の current_spot_id を save / restore する。restore 時は
``SpotGraphAggregate`` の内部 dict (``_entity_spot`` / ``_presences``) を
直接書き換えることで ``EntityEnteredSpotEvent`` の emit を避ける
(= snapshot restore は「世界をこの状態に *なっている* と宣言」する操作で
あり、「これから *動かす*」操作ではないため event を発行しない方針)。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "player_position"
SCHEMA_VERSION = 1


class PlayerPositionSubsystemCodec(WorldSubsystemCodec):
    """各 player の現在 spot_id を runtime ↔ JSON で往復させる。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        """各 player の (player_id, spot_id) を集める。"""
        entries: list[dict[str, Any]] = []
        spot_graph_repo = getattr(runtime, "_spot_graph_repo", None)
        if spot_graph_repo is None:
            raise RuntimeError(
                "runtime._spot_graph_repo not found; "
                "PlayerPositionSubsystemCodec requires it"
            )
        graph = spot_graph_repo.find_graph()
        # 全 player について現 spot_id を集める。
        for pid in runtime.get_player_ids():
            spot_id_raw = runtime.get_player_spot_id(pid)
            # spot_id_raw は SpotId.value (= str / int)。未配置なら None。
            entries.append(
                {
                    "player_id": int(pid.value),
                    "spot_id": spot_id_raw,
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
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import (
            EntityId,
        )
        from ai_rpg_world.domain.world_graph.value_object.spot_presence import (
            SpotPresence,
        )

        spot_graph_repo = getattr(runtime, "_spot_graph_repo", None)
        if spot_graph_repo is None:
            raise RuntimeError(
                "runtime._spot_graph_repo not found; "
                "PlayerPositionSubsystemCodec requires it"
            )
        graph = spot_graph_repo.find_graph()

        for entry in data.get("entries", []):
            player_id_value = int(entry["player_id"])
            spot_id_raw = entry.get("spot_id")
            entity_id = EntityId.create(player_id_value)

            # 既存配置を内部 dict から直接削除 (= event を emit しない)。
            old_spot = graph._entity_spot.pop(entity_id, None)
            if old_spot is not None:
                old_presence = graph._presences.get(old_spot)
                if old_presence is not None:
                    new_presence = old_presence.remove(entity_id)
                    graph._presences[old_spot] = new_presence

            if spot_id_raw is None:
                continue  # 未配置なら新たに配置しない

            # SpotId 復元: source 側で int / str どちらかで保存されている。
            try:
                new_spot_id = SpotId(int(spot_id_raw))
            except (TypeError, ValueError):
                new_spot_id = SpotId(str(spot_id_raw))

            # graph に対象 spot がないと scenario mismatch (= scenario fail-fast
            # で先に弾かれているはずだが、保険として明示)。
            if new_spot_id not in graph._spots:
                raise RuntimeError(
                    f"PlayerPositionSubsystemCodec: spot_id={spot_id_raw!r} "
                    f"not in scenario graph; scenario mismatch?"
                )

            graph._entity_spot[entity_id] = new_spot_id
            presence = graph._presences.get(
                new_spot_id, SpotPresence.empty(new_spot_id)
            )
            graph._presences[new_spot_id] = presence.add(entity_id)


__all__ = ["PlayerPositionSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
