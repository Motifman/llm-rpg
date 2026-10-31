"""直近の出来事のストア (``UnifiedRecentEventStore``) を保存・復元する subsystem codec。

v2 は、未処理の観測と直近の行動の結果だけを持つ。プロンプトの【直近の出来事】は Being の短期記憶から作り、
Being の snapshot に入るので、世界の側は出来事の並びを持たない (design_decisions D1824-24)。

古い snapshot も読む:

| 形 | 読み方 |
|---|---|
| v1 (``recent_event_store``) | 並びの中の行動の結果と、未処理の観測を戻す。並びの観測と、今の短期記憶の要約 (``mid_summaries``) は捨てる |
| 旧 3 subsystem (``sliding_window`` / ``observation_buffer`` / ``action_result_store``) | ``migrate_legacy_recent_event_subsystems`` で v1 の形にしてから読む |
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)
from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.application.observation.contracts.dtos import ObservationCategory
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

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


def _as_observation_category(raw: Any) -> ObservationCategory:
    """保存された文字列を ObservationCategory に戻す。範囲外は self_only に倒す。"""
    value = str(raw)
    if value in ("self_only", "social", "environment"):
        return cast(ObservationCategory, value)
    return "self_only"


def _dict_to_observation_entry(data: dict[str, Any]) -> Any:
    from ai_rpg_world.application.observation.contracts.dtos import (
        ObservationEntry,
        ObservationOutput,
    )

    out_d = data["output"]
    output = ObservationOutput(
        prose=str(out_d["prose"]),
        structured=dict(out_d.get("structured", {})),
        observation_category=_as_observation_category(out_d.get("observation_category", "self_only")),
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
        "identifier_arguments": dict(entry.identifier_arguments),
        "free_text_argument_names": list(entry.free_text_argument_names),
        "argument_fingerprint": entry.argument_fingerprint,
        "should_reschedule": bool(entry.should_reschedule),
        "game_time_label": entry.game_time_label,
        "omit_result_in_prompt": bool(entry.omit_result_in_prompt),
        "inner_thought": entry.inner_thought,
        "occurred_tick": entry.occurred_tick,
        "execution_provenance": entry.execution_provenance.to_dict() if entry.execution_provenance else None,
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
        # 旧 payload には無いキー。空へ倒し、復元不能な引数を捏造しない。
        identifier_arguments=dict(data.get("identifier_arguments") or {}),
        free_text_argument_names=tuple(data.get("free_text_argument_names") or ()),
        argument_fingerprint=data.get("argument_fingerprint"),
        should_reschedule=bool(data.get("should_reschedule", False)),
        game_time_label=data.get("game_time_label"),
        omit_result_in_prompt=bool(data.get("omit_result_in_prompt", False)),
        inner_thought=data.get("inner_thought"),
        occurred_tick=data.get("occurred_tick"),
        execution_provenance=(
            ExecutionProvenance.from_dict(data["execution_provenance"]) if data.get("execution_provenance") else None
        ),
    )


# ----------------------------------------------------------------------------
# 旧 3 subsystem のキー。読むだけで、もう書かない
# ----------------------------------------------------------------------------
_SW_SUBSYSTEM_KEY = "sliding_window"
_SW_MODE_SLIDING = "sliding_window"
_SW_MODE_ROLLING = "rolling_summary"
_OB_SUBSYSTEM_KEY = "observation_buffer"
_AR_SUBSYSTEM_KEY = "action_result_store"


# ----------------------------------------------------------------------------
# 直近の出来事のストア
# ----------------------------------------------------------------------------
_RECENT_EVENT_SUBSYSTEM_KEY = "recent_event_store"
_RECENT_EVENT_SCHEMA_VERSION = 2
_RECENT_EVENT_SCHEMA_VERSION_WITH_TIMELINE = 1


def migrate_legacy_recent_event_subsystems(
    subsystems: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """旧3 subsystem を新しい統一 payload へ変換する。

    3 キーが一部だけ在る状態は部分 snapshot なので拒否する。変換後は旧キーを
    除き、通常の厳格な coverage 検査へ渡せる形にする。
    """
    legacy_keys = {
        _SW_SUBSYSTEM_KEY,
        _OB_SUBSYSTEM_KEY,
        _AR_SUBSYSTEM_KEY,
    }
    present = legacy_keys & set(subsystems)
    if not present:
        return subsystems
    if present != legacy_keys:
        raise ValueError(f"legacy recent-event snapshot must contain all three subsystems: present={sorted(present)!r}")
    if _RECENT_EVENT_SUBSYSTEM_KEY in subsystems:
        raise ValueError("snapshot contains both legacy and unified recent-event subsystems")

    sw = subsystems[_SW_SUBSYSTEM_KEY]
    ob = subsystems[_OB_SUBSYSTEM_KEY]
    ar = subsystems[_AR_SUBSYSTEM_KEY]
    mode = sw.get("mode", _SW_MODE_SLIDING)
    observation_groups = sw.get("raw_entries", []) if mode == _SW_MODE_ROLLING else sw.get("entries", [])
    events_by_player: dict[int, list[dict[str, Any]]] = {}
    for group in observation_groups:
        pid = int(group["player_id"])
        for payload in group.get("entries", []):
            events_by_player.setdefault(pid, []).append(
                {
                    "occurred_at": payload["occurred_at"],
                    "game_time_label": payload.get("game_time_label"),
                    "kind": "observation",
                    "payload": payload,
                }
            )
    for group in ar.get("entries", []):
        pid = int(group["player_id"])
        for payload in group.get("entries", []):
            events_by_player.setdefault(pid, []).append(
                {
                    "occurred_at": payload["occurred_at"],
                    "game_time_label": payload.get("game_time_label"),
                    "kind": "action_result",
                    "payload": payload,
                }
            )
    event_groups = []
    for pid, entries in sorted(events_by_player.items()):
        entries.sort(key=lambda entry: _iso_to_dt(str(entry["occurred_at"])).timestamp())
        event_groups.append({"player_id": pid, "entries": entries})

    migrated = dict(subsystems)
    for key in legacy_keys:
        migrated.pop(key)
    migrated[_RECENT_EVENT_SUBSYSTEM_KEY] = {
        "schema_version": _RECENT_EVENT_SCHEMA_VERSION_WITH_TIMELINE,
        "mode": mode,
        "entries": event_groups,
        "completed_turn_sizes": [],
        "pending_observations": ob.get("entries", []),
        "mid_summaries": sw.get("mid_summaries", []),
    }
    return migrated


class UnifiedRecentEventStoreSubsystemCodec(WorldSubsystemCodec):
    """未処理の観測と直近の行動の結果を一つの subsystem として往復する。"""

    @property
    def subsystem_key(self) -> str:
        return _RECENT_EVENT_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        store = getattr(runtime, "_recent_event_store", None)
        action_results: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        if store is not None:
            for pid in sorted(store.player_ids()):
                player_id = PlayerId(pid)
                results = store.action_results_in_storage_order(player_id)
                if results:
                    action_results.append(
                        {"player_id": pid, "entries": [_action_result_entry_to_dict(entry) for entry in results]}
                    )
                pending_entries = store.get_pending_observations(player_id)
                if pending_entries:
                    pending.append(
                        {"player_id": pid, "entries": [_observation_entry_to_dict(entry) for entry in pending_entries]}
                    )
        return {
            "schema_version": _RECENT_EVENT_SCHEMA_VERSION,
            "action_results": action_results,
            "pending_observations": pending,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version not in (_RECENT_EVENT_SCHEMA_VERSION_WITH_TIMELINE, _RECENT_EVENT_SCHEMA_VERSION):
            raise ValueError(
                f"{_RECENT_EVENT_SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {_RECENT_EVENT_SCHEMA_VERSION_WITH_TIMELINE} or {_RECENT_EVENT_SCHEMA_VERSION})"
            )
        store = getattr(runtime, "_recent_event_store", None)
        if store is None:
            return
        for pid in store.player_ids():
            store.replace_action_results(PlayerId(pid), [])
            store.replace_pending_observations(PlayerId(pid), [])
        for pid, results in _action_results_by_player(data, version).items():
            store.replace_action_results(PlayerId(pid), results)
        for group in data.get("pending_observations", []):
            store.replace_pending_observations(
                PlayerId(int(group["player_id"])),
                [_dict_to_observation_entry(entry) for entry in group.get("entries", [])],
            )


def _action_results_by_player(data: dict[str, Any], version: int) -> dict[int, list[Any]]:
    """v1 は観測と行動の結果を並べた ``entries`` から、行動の結果だけを並びの順に取り出す。"""
    if version == _RECENT_EVENT_SCHEMA_VERSION:
        return {
            int(group["player_id"]): [_dict_to_action_result_entry(entry) for entry in group.get("entries", [])]
            for group in data.get("action_results", [])
        }
    return {
        int(group["player_id"]): [
            _dict_to_action_result_entry(entry["payload"])
            for entry in group.get("entries", [])
            if entry.get("kind") == "action_result"
        ]
        for group in data.get("entries", [])
    }


__all__ = [
    "UnifiedRecentEventStoreSubsystemCodec",
    "migrate_legacy_recent_event_subsystems",
]
