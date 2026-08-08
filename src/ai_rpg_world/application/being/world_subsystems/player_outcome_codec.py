"""プレイヤーごとの終局 outcome を保存・復元する world subsystem codec。

``is_down`` は身体の可動状態であり、勝敗上の確定状態ではない。DEAD と
蘇生可能な UNRESOLVED、EJECTED と初期未配置は他の subsystem から推定
できないため、PlayerOutcomeRegistry を独立した真実の源として保存する。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

SUBSYSTEM_KEY = "player_outcome"
SCHEMA_VERSION = 1


class PlayerOutcomeSubsystemCodec(WorldSubsystemCodec):
    """PlayerOutcomeRegistry の全 player を JSON と往復させる。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    @staticmethod
    def _registry(runtime: Any) -> PlayerOutcomeRegistry:
        registry = getattr(runtime, "_player_outcome_registry", None)
        if not isinstance(registry, PlayerOutcomeRegistry):
            raise RuntimeError(
                "runtime._player_outcome_registry not found; "
                "PlayerOutcomeSubsystemCodec requires it"
            )
        return registry

    def capture(self, runtime: Any) -> dict[str, Any]:
        """全 player の outcome を player_id 順に保存する。"""
        registry = self._registry(runtime)
        outcomes = registry.snapshot()
        expected_ids = {int(player_id) for player_id in runtime.get_player_ids()}
        if set(outcomes) != expected_ids:
            missing = sorted(expected_ids - set(outcomes))
            extra = sorted(set(outcomes) - expected_ids)
            raise RuntimeError(
                "player outcome registry does not match runtime players: "
                f"missing={missing!r}, extra={extra!r}"
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": [
                {"player_id": player_id, "outcome": outcomes[player_id].value}
                for player_id in sorted(outcomes)
            ],
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        """callback を発火させず、検証後に registry 全体を置換する。"""
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise ValueError(f"{SUBSYSTEM_KEY} entries must be a list")

        restored: dict[PlayerId, PlayerOutcomeEnum] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{SUBSYSTEM_KEY} entry must be an object")
            player_id = PlayerId(int(entry["player_id"]))
            if player_id in restored:
                raise ValueError(
                    f"{SUBSYSTEM_KEY} duplicate player_id={int(player_id)}"
                )
            outcome_raw = entry.get("outcome")
            try:
                outcome = PlayerOutcomeEnum(outcome_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{SUBSYSTEM_KEY} unknown outcome={outcome_raw!r}"
                ) from exc
            restored[player_id] = outcome

        self._registry(runtime).replace_all(restored)


__all__ = ["PlayerOutcomeSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
