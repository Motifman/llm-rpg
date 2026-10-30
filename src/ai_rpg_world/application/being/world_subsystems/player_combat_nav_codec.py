"""Player combat / navigation sub-state codec (Phase 9-4a)。

PlayerStatusAggregate の以下 3 field を JSON 化:

| Codec | 対象 field | 内容 |
|---|---|---|
| ``PlayerActiveEffectsSubsystemCodec`` | ``_active_effects`` | List[StatusEffect] (= 戦闘 buff/debuff) |
| ``PlayerAttentionLevelSubsystemCodec`` | ``_attention_level`` | AttentionLevel Enum (= 観測フィルタ) |
| ``PlayerSpotNavigationStateSubsystemCodec`` | ``_spot_navigation_state`` | 移動中の route / leg / 残 tick |

これで PlayerStatusAggregate の **全ての dynamic field** が snapshot 可能に
なる (= Phase 9-2 + 9-2b + 本 PR で完成)。

## 静的 vs 動的

これらの field はすべて run 中に変化しうる:
- ``active_effects``: 戦闘でかかる / 切れる
- ``attention_level``: scenario / 状況に応じて変わる
- ``spot_navigation_state``: spot 移動中は is_traveling=True で route 進行

特に ``spot_navigation_state`` は **multi-tick travel の途中で snapshot を
取ったとき、再開で正しく続行する** ためにクリティカル。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

# ----------------------------------------------------------------------------
# 1. Active effects
# ----------------------------------------------------------------------------
_AE_SUBSYSTEM_KEY = "player_active_effects"
_AE_SCHEMA_VERSION = 1


class PlayerActiveEffectsSubsystemCodec(WorldSubsystemCodec):
    @property
    def subsystem_key(self) -> str:
        return _AE_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = _player_status_repo_or_raise(runtime, self.subsystem_key)
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            effects = [
                {
                    "effect_type": eff.effect_type.value,
                    "value": float(eff.value),
                    "expiry_tick": int(eff.expiry_tick.value),
                }
                for eff in agg._active_effects
            ]
            entries.append(
                {
                    "player_id": int(pid.value),
                    "effects": effects,
                }
            )
        return {"schema_version": _AE_SCHEMA_VERSION, "entries": entries}

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _AE_SUBSYSTEM_KEY, _AE_SCHEMA_VERSION)
        from ai_rpg_world.domain.combat.enum.combat_enum import (
            StatusEffectType,
        )
        from ai_rpg_world.domain.combat.value_object.status_effect import (
            StatusEffect,
        )
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        repo = _player_status_repo_or_raise(runtime, self.subsystem_key)
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            new_effects = []
            for eff_d in entry.get("effects", []):
                new_effects.append(
                    StatusEffect(
                        effect_type=StatusEffectType(str(eff_d["effect_type"])),
                        value=float(eff_d["value"]),
                        expiry_tick=WorldTick(int(eff_d["expiry_tick"])),
                    )
                )
            agg._active_effects = new_effects
            if hasattr(agg, "_events"):
                agg._events.clear()
            repo.save(agg)


# ----------------------------------------------------------------------------
# 2. AttentionLevel (Enum)
# ----------------------------------------------------------------------------
_AL_SUBSYSTEM_KEY = "player_attention_level"
_AL_SCHEMA_VERSION = 1


class PlayerAttentionLevelSubsystemCodec(WorldSubsystemCodec):
    @property
    def subsystem_key(self) -> str:
        return _AL_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = _player_status_repo_or_raise(runtime, self.subsystem_key)
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            entries.append(
                {
                    "player_id": int(pid.value),
                    "attention_level": agg._attention_level.value,
                }
            )
        return {"schema_version": _AL_SCHEMA_VERSION, "entries": entries}

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _AL_SUBSYSTEM_KEY, _AL_SCHEMA_VERSION)
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        repo = _player_status_repo_or_raise(runtime, self.subsystem_key)
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            agg._attention_level = AttentionLevel(str(entry["attention_level"]))
            if hasattr(agg, "_events"):
                agg._events.clear()
            repo.save(agg)


# ----------------------------------------------------------------------------
# 4. PlayerSpotNavigationState
# ----------------------------------------------------------------------------
_SN_SUBSYSTEM_KEY = "player_spot_navigation_state"
_SN_SCHEMA_VERSION = 1


class PlayerSpotNavigationStateSubsystemCodec(WorldSubsystemCodec):
    """``_spot_navigation_state`` の往復。

    travel mid-flight の状態 (route / leg / ticks_remaining) を保持するので、
    multi-tick travel の途中 snapshot → resume で正しく続行できる。
    Optional な scenario (= 一度も spot_navigation 使ってない) では None なので
    その場合は ``state: null``。
    """

    @property
    def subsystem_key(self) -> str:
        return _SN_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = _player_status_repo_or_raise(runtime, self.subsystem_key)
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            sn = agg._spot_navigation_state
            if sn is None:
                state_data = None
            else:
                state_data = {
                    "current_spot_id": int(sn.current_spot_id.value),
                    "current_sub_location_id": (
                        int(sn.current_sub_location_id.value) if sn.current_sub_location_id is not None else None
                    ),
                    "is_traveling": bool(sn.is_traveling),
                    "route": [int(s.value) for s in sn.route],
                    "leg_index": int(sn.leg_index),
                    "leg_connection_ids": [int(c.value) for c in sn.leg_connection_ids],
                    "leg_travel_ticks": list(sn.leg_travel_ticks),
                    "ticks_remaining_on_current_leg": int(sn.ticks_remaining_on_current_leg),
                }
            entries.append({"player_id": int(pid.value), "state": state_data})
        return {"schema_version": _SN_SCHEMA_VERSION, "entries": entries}

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _SN_SUBSYSTEM_KEY, _SN_SCHEMA_VERSION)
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
            PlayerSpotNavigationState,
        )
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.connection_id import (
            ConnectionId,
        )
        from ai_rpg_world.domain.world_graph.value_object.sub_location_id import (
            SubLocationId,
        )

        repo = _player_status_repo_or_raise(runtime, self.subsystem_key)
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            sd = entry.get("state")
            if sd is None:
                agg._spot_navigation_state = None
            else:
                sub_raw = sd.get("current_sub_location_id")
                agg._spot_navigation_state = PlayerSpotNavigationState(
                    current_spot_id=SpotId(int(sd["current_spot_id"])),
                    current_sub_location_id=(SubLocationId(int(sub_raw)) if sub_raw is not None else None),
                    is_traveling=bool(sd["is_traveling"]),
                    route=tuple(SpotId(int(s)) for s in sd.get("route", [])),
                    leg_index=int(sd.get("leg_index", 0)),
                    leg_connection_ids=tuple(ConnectionId(int(c)) for c in sd.get("leg_connection_ids", [])),
                    leg_travel_ticks=tuple(int(t) for t in sd.get("leg_travel_ticks", [])),
                    ticks_remaining_on_current_leg=int(sd.get("ticks_remaining_on_current_leg", 0)),
                )
            if hasattr(agg, "_events"):
                agg._events.clear()
            repo.save(agg)


# ----------------------------------------------------------------------------
# 共通ヘルパ
# ----------------------------------------------------------------------------
def _player_status_repo_or_raise(runtime: Any, key: str) -> Any:
    repo = getattr(runtime, "_player_status_repo", None)
    if repo is None:
        raise RuntimeError(f"runtime._player_status_repo not found; {key} codec requires it")
    return repo


def _check_version(data: dict[str, Any], key: str, expected: int) -> None:
    version = data.get("schema_version")
    if version != expected:
        raise ValueError(f"{key} schema_version={version!r} unsupported (expected {expected})")


__all__ = [
    "PlayerActiveEffectsSubsystemCodec",
    "PlayerAttentionLevelSubsystemCodec",
    "PlayerSpotNavigationStateSubsystemCodec",
]
