"""Short-term memory subsystem codec 群 (Phase 9-4c)。

LLM agent の prompt context に乗る短期記憶を 3 subsystem 分 save / restore する:

| Codec | 対象 | 内容 |
|---|---|---|
| ``SlidingWindowMemorySubsystemCodec`` | ``_sliding_window`` | player_id → recent ObservationEntry list |
| ``ObservationBufferSubsystemCodec`` | ``_obs_buffer`` | player_id → pending ObservationEntry list (= LLM turn で drain される) |
| ``ActionResultStoreSubsystemCodec`` | ``_action_result_store`` | player_id → recent ActionResultEntry list (= 直近の tool 実行結果) |

resume 時にこれらが空だと agent は **「直前の出来事を覚えていない」** 状態で
再開する (= 前 run の最終 tick で何が起きたかが prompt に乗らない)。

すべて ObservationEntry / ActionResultEntry の dataclass を JSON 化する
共通ヘルパを使う。datetime → ISO 8601 文字列で正規化。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)


# ----------------------------------------------------------------------------
# 共通 serializer / deserializer
# ----------------------------------------------------------------------------

def _dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def _iso_to_dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _observation_entry_to_dict(entry: Any) -> dict[str, Any]:
    out = entry.output
    return {
        "occurred_at": _dt_to_iso(entry.occurred_at),
        "game_time_label": entry.game_time_label,
        "output": {
            "prose": out.prose,
            "structured": dict(out.structured),
            "observation_category": out.observation_category,
            "schedules_turn": bool(out.schedules_turn),
            "breaks_movement": bool(out.breaks_movement),
        },
    }


def _dict_to_observation_entry(data: dict[str, Any]) -> Any:
    from ai_rpg_world.application.observation.contracts.dtos import (
        ObservationEntry,
        ObservationOutput,
    )

    out_d = data["output"]
    output = ObservationOutput(
        prose=str(out_d["prose"]),
        structured=dict(out_d.get("structured", {})),
        observation_category=str(out_d.get("observation_category", "self_only")),
        schedules_turn=bool(out_d.get("schedules_turn", False)),
        breaks_movement=bool(out_d.get("breaks_movement", False)),
    )
    return ObservationEntry(
        occurred_at=_iso_to_dt(str(data["occurred_at"])),
        output=output,
        game_time_label=data.get("game_time_label"),
    )


def _action_result_entry_to_dict(entry: Any) -> dict[str, Any]:
    return {
        "occurred_at": _dt_to_iso(entry.occurred_at),
        "action_summary": entry.action_summary,
        "result_summary": entry.result_summary,
        "success": bool(entry.success),
        "error_code": entry.error_code,
        "tool_name": entry.tool_name,
        "argument_fingerprint": entry.argument_fingerprint,
        "should_reschedule": bool(entry.should_reschedule),
        "game_time_label": entry.game_time_label,
        "omit_result_in_prompt": bool(entry.omit_result_in_prompt),
        "scene_boundary": bool(entry.scene_boundary),
        "occurred_tick": entry.occurred_tick,
    }


def _dict_to_action_result_entry(data: dict[str, Any]) -> Any:
    from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry

    return ActionResultEntry(
        occurred_at=_iso_to_dt(str(data["occurred_at"])),
        action_summary=str(data["action_summary"]),
        result_summary=str(data["result_summary"]),
        success=bool(data.get("success", True)),
        error_code=data.get("error_code"),
        tool_name=data.get("tool_name"),
        argument_fingerprint=data.get("argument_fingerprint"),
        should_reschedule=bool(data.get("should_reschedule", False)),
        game_time_label=data.get("game_time_label"),
        omit_result_in_prompt=bool(data.get("omit_result_in_prompt", False)),
        scene_boundary=bool(data.get("scene_boundary", False)),
        occurred_tick=data.get("occurred_tick"),
    )


def _check_version(data: dict[str, Any], key: str, expected: int) -> None:
    version = data.get("schema_version")
    if version != expected:
        raise ValueError(
            f"{key} schema_version={version!r} unsupported (expected {expected})"
        )


def _capture_dict_store(
    store_dict: dict[int, list[Any]],
    entry_to_dict,
) -> list[dict[str, Any]]:
    """共通 capture: ``{player_id: [Entry, ...]}`` を JSON-serializable に。"""
    return sorted(
        (
            {
                "player_id": int(pid),
                "entries": [entry_to_dict(e) for e in entries],
            }
            for pid, entries in store_dict.items()
        ),
        key=lambda d: d["player_id"],
    )


def _restore_dict_store(
    store_dict: dict[int, list[Any]],
    entries_data: list[dict[str, Any]],
    dict_to_entry,
) -> None:
    """共通 restore: store_dict を clear + repopulate。"""
    store_dict.clear()
    for entry in entries_data:
        pid = int(entry["player_id"])
        store_dict[pid] = [dict_to_entry(d) for d in entry.get("entries", [])]


# ----------------------------------------------------------------------------
# 1. Sliding window
# ----------------------------------------------------------------------------
_SW_SUBSYSTEM_KEY = "sliding_window"
_SW_SCHEMA_VERSION = 1


class SlidingWindowMemorySubsystemCodec(WorldSubsystemCodec):
    """``_sliding_window._store`` (= ObservationEntry list per player) を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return _SW_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        sw = getattr(runtime, "_sliding_window", None)
        if sw is None:
            return {"schema_version": _SW_SCHEMA_VERSION, "entries": []}
        return {
            "schema_version": _SW_SCHEMA_VERSION,
            "entries": _capture_dict_store(
                sw._store, _observation_entry_to_dict
            ),
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _SW_SUBSYSTEM_KEY, _SW_SCHEMA_VERSION)
        sw = getattr(runtime, "_sliding_window", None)
        if sw is None:
            return
        _restore_dict_store(
            sw._store, data.get("entries", []), _dict_to_observation_entry
        )


# ----------------------------------------------------------------------------
# 2. Observation buffer
# ----------------------------------------------------------------------------
_OB_SUBSYSTEM_KEY = "observation_buffer"
_OB_SCHEMA_VERSION = 1


class ObservationBufferSubsystemCodec(WorldSubsystemCodec):
    """``_obs_buffer._buffer`` (= pending ObservationEntry list per player)。"""

    @property
    def subsystem_key(self) -> str:
        return _OB_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        ob = getattr(runtime, "_obs_buffer", None)
        if ob is None:
            return {"schema_version": _OB_SCHEMA_VERSION, "entries": []}
        return {
            "schema_version": _OB_SCHEMA_VERSION,
            "entries": _capture_dict_store(
                ob._buffer, _observation_entry_to_dict
            ),
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _OB_SUBSYSTEM_KEY, _OB_SCHEMA_VERSION)
        ob = getattr(runtime, "_obs_buffer", None)
        if ob is None:
            return
        _restore_dict_store(
            ob._buffer, data.get("entries", []), _dict_to_observation_entry
        )


# ----------------------------------------------------------------------------
# 3. Action result store
# ----------------------------------------------------------------------------
_AR_SUBSYSTEM_KEY = "action_result_store"
_AR_SCHEMA_VERSION = 1


class ActionResultStoreSubsystemCodec(WorldSubsystemCodec):
    """``_action_result_store._store`` (= ActionResultEntry list per player)。"""

    @property
    def subsystem_key(self) -> str:
        return _AR_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        ar = getattr(runtime, "_action_result_store", None)
        if ar is None:
            return {"schema_version": _AR_SCHEMA_VERSION, "entries": []}
        return {
            "schema_version": _AR_SCHEMA_VERSION,
            "entries": _capture_dict_store(
                ar._store, _action_result_entry_to_dict
            ),
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _AR_SUBSYSTEM_KEY, _AR_SCHEMA_VERSION)
        ar = getattr(runtime, "_action_result_store", None)
        if ar is None:
            return
        _restore_dict_store(
            ar._store, data.get("entries", []), _dict_to_action_result_entry
        )


__all__ = [
    "SlidingWindowMemorySubsystemCodec",
    "ObservationBufferSubsystemCodec",
    "ActionResultStoreSubsystemCodec",
]
