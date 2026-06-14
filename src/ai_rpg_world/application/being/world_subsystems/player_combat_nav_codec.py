"""Player combat / navigation sub-state codec (Phase 9-4a)。

PlayerStatusAggregate の以下 4 field を JSON 化:

| Codec | 対象 field | 内容 |
|---|---|---|
| ``PlayerActiveEffectsSubsystemCodec`` | ``_active_effects`` | List[StatusEffect] (= 戦闘 buff/debuff) |
| ``PlayerAttentionLevelSubsystemCodec`` | ``_attention_level`` | AttentionLevel Enum (= 観測フィルタ) |
| ``PlayerPursuitStateSubsystemCodec`` | ``_pursuit_state`` | Optional[PursuitState] (= 追跡中の target) |
| ``PlayerSpotNavigationStateSubsystemCodec`` | ``_spot_navigation_state`` | 移動中の route / leg / 残 tick |

これで PlayerStatusAggregate の **全ての dynamic field** が snapshot 可能に
なる (= Phase 9-2 + 9-2b + 本 PR で完成)。

## 静的 vs 動的

これらの field はすべて run 中に変化しうる:
- ``active_effects``: 戦闘でかかる / 切れる
- ``attention_level``: scenario / 状況に応じて変わる
- ``pursuit_state``: 戦闘開始/解除で active/None
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
# 3. PlayerPursuitState (= Optional[PursuitState] wrapper)
# ----------------------------------------------------------------------------
_PS_SUBSYSTEM_KEY = "player_pursuit_state"
_PS_SCHEMA_VERSION = 1


class PlayerPursuitStateSubsystemCodec(WorldSubsystemCodec):
    """``_pursuit_state`` の往復。

    PursuitState は actor_id / target_id / Optional[target_snapshot] /
    Optional[last_known] / Optional[failure_reason] を持つ。それぞれを
    nested dict で表現。``pursuit is None`` (= 追跡なし) は ``pursuit: null``。
    """

    @property
    def subsystem_key(self) -> str:
        return _PS_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = _player_status_repo_or_raise(runtime, self.subsystem_key)
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            ps = agg._pursuit_state
            entries.append(
                {
                    "player_id": int(pid.value),
                    "pursuit": _pursuit_to_dict(ps.pursuit) if ps.pursuit else None,
                }
            )
        return {"schema_version": _PS_SCHEMA_VERSION, "entries": entries}

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _PS_SUBSYSTEM_KEY, _PS_SCHEMA_VERSION)
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.value_object.player_pursuit_state import (
            PlayerPursuitState,
        )

        repo = _player_status_repo_or_raise(runtime, self.subsystem_key)
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            agg = repo.find_by_id(pid)
            if agg is None:
                continue
            pursuit_data = entry.get("pursuit")
            pursuit_obj = _dict_to_pursuit(pursuit_data) if pursuit_data else None
            agg._pursuit_state = PlayerPursuitState(pursuit=pursuit_obj)
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
                        int(sn.current_sub_location_id.value)
                        if sn.current_sub_location_id is not None
                        else None
                    ),
                    "is_traveling": bool(sn.is_traveling),
                    "route": [int(s.value) for s in sn.route],
                    "leg_index": int(sn.leg_index),
                    "leg_connection_ids": [
                        int(c.value) for c in sn.leg_connection_ids
                    ],
                    "leg_travel_ticks": list(sn.leg_travel_ticks),
                    "ticks_remaining_on_current_leg": int(
                        sn.ticks_remaining_on_current_leg
                    ),
                }
            entries.append(
                {"player_id": int(pid.value), "state": state_data}
            )
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
                    current_sub_location_id=(
                        SubLocationId(int(sub_raw)) if sub_raw is not None else None
                    ),
                    is_traveling=bool(sd["is_traveling"]),
                    route=tuple(SpotId(int(s)) for s in sd.get("route", [])),
                    leg_index=int(sd.get("leg_index", 0)),
                    leg_connection_ids=tuple(
                        ConnectionId(int(c))
                        for c in sd.get("leg_connection_ids", [])
                    ),
                    leg_travel_ticks=tuple(
                        int(t) for t in sd.get("leg_travel_ticks", [])
                    ),
                    ticks_remaining_on_current_leg=int(
                        sd.get("ticks_remaining_on_current_leg", 0)
                    ),
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
        raise RuntimeError(
            f"runtime._player_status_repo not found; {key} codec requires it"
        )
    return repo


def _check_version(data: dict[str, Any], key: str, expected: int) -> None:
    version = data.get("schema_version")
    if version != expected:
        raise ValueError(
            f"{key} schema_version={version!r} unsupported (expected {expected})"
        )


def _pursuit_to_dict(pursuit: Any) -> dict[str, Any]:
    """PursuitState を JSON-serializable dict に変換する。"""
    return {
        "actor_id": int(pursuit.actor_id.value),
        "target_id": int(pursuit.target_id.value),
        "target_snapshot": (
            _target_snapshot_to_dict(pursuit.target_snapshot)
            if pursuit.target_snapshot is not None
            else None
        ),
        "last_known": (
            _last_known_to_dict(pursuit.last_known)
            if pursuit.last_known is not None
            else None
        ),
        "failure_reason": (
            pursuit.failure_reason.value
            if pursuit.failure_reason is not None
            else None
        ),
    }


def _dict_to_pursuit(data: dict[str, Any]) -> Any:
    from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
        PursuitFailureReason,
    )
    from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
    from ai_rpg_world.domain.world.value_object.world_object_id import (
        WorldObjectId,
    )

    return PursuitState(
        actor_id=WorldObjectId(int(data["actor_id"])),
        target_id=WorldObjectId(int(data["target_id"])),
        target_snapshot=(
            _dict_to_target_snapshot(data["target_snapshot"])
            if data.get("target_snapshot") is not None
            else None
        ),
        last_known=(
            _dict_to_last_known(data["last_known"])
            if data.get("last_known") is not None
            else None
        ),
        failure_reason=(
            PursuitFailureReason(data["failure_reason"])
            if data.get("failure_reason") is not None
            else None
        ),
    )


def _target_snapshot_to_dict(ts: Any) -> dict[str, Any]:
    return {
        "target_id": int(ts.target_id.value),
        "spot_id": int(ts.spot_id.value),
        "coordinate": {
            "x": int(ts.coordinate.x),
            "y": int(ts.coordinate.y),
            "z": int(ts.coordinate.z),
        },
    }


def _dict_to_target_snapshot(data: dict[str, Any]) -> Any:
    from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
        PursuitTargetSnapshot,
    )
    from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId
    from ai_rpg_world.domain.world.value_object.world_object_id import (
        WorldObjectId,
    )

    coord = data["coordinate"]
    return PursuitTargetSnapshot(
        target_id=WorldObjectId(int(data["target_id"])),
        spot_id=SpotId(int(data["spot_id"])),
        coordinate=Coordinate(
            x=int(coord["x"]), y=int(coord["y"]), z=int(coord.get("z", 0))
        ),
    )


def _last_known_to_dict(lk: Any) -> dict[str, Any]:
    return {
        "target_id": int(lk.target_id.value),
        "spot_id": int(lk.spot_id.value),
        "coordinate": {
            "x": int(lk.coordinate.x),
            "y": int(lk.coordinate.y),
            "z": int(lk.coordinate.z),
        },
        "observed_at_tick": (
            int(lk.observed_at_tick.value)
            if lk.observed_at_tick is not None
            else None
        ),
    }


def _dict_to_last_known(data: dict[str, Any]) -> Any:
    from ai_rpg_world.domain.common.value_object import WorldTick
    from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
        PursuitLastKnownState,
    )
    from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId
    from ai_rpg_world.domain.world.value_object.world_object_id import (
        WorldObjectId,
    )

    coord = data["coordinate"]
    obs = data.get("observed_at_tick")
    return PursuitLastKnownState(
        target_id=WorldObjectId(int(data["target_id"])),
        spot_id=SpotId(int(data["spot_id"])),
        coordinate=Coordinate(
            x=int(coord["x"]), y=int(coord["y"]), z=int(coord.get("z", 0))
        ),
        observed_at_tick=WorldTick(int(obs)) if obs is not None else None,
    )


__all__ = [
    "PlayerActiveEffectsSubsystemCodec",
    "PlayerAttentionLevelSubsystemCodec",
    "PlayerPursuitStateSubsystemCodec",
    "PlayerSpotNavigationStateSubsystemCodec",
]
