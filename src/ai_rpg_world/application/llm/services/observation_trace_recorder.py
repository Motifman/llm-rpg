"""ObservationEntry から ObservationExperienceTrace を作って保存するサービス。"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Tuple
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.dtos import (
    ObservationExperienceTrace,
    ObservationTraceKind,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IObservationExperienceTraceStore,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SPEECH_TYPES = frozenset({
    "player_spoke",
    "conversation_started",
    "conversation_ended",
    "user_directed_speech",
    "sns_post_created",
    "sns_reply_created",
})

_ENVIRONMENT_TYPES = frozenset({
    "weather_changed",
    "connection_state_changed",
    "spot_object_state_changed",
    "monster_spawned",
    "monster_respawned",
    "monster_state_changed",
})

_OTHER_AGENT_ACTION_TYPES = frozenset({
    "entity_entered_spot",
    "entity_left_spot",
    "spot_object_interacted",
    "spot_explored",
    "player_entered_location",
    "player_entered_spot",
    "trade_offered",
    "trade_accepted",
    "trade_declined",
    "sns_content_liked",
    "sns_user_followed",
    "sns_user_subscribed",
})

_INTERVENTION_TYPES = frozenset({
    "player_downed",
    "hitbox_hit",
    "inventory_overflow",
    "monster_damaged",
})


def _string_tuple(values: Iterable[Any]) -> Tuple[str, ...]:
    result = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            result.append(text)
    return tuple(result)


def classify_observation_kind(entry: ObservationEntry) -> ObservationTraceKind:
    """既存 ObservationOutput の structured type / category から粗く分類する。"""

    structured = entry.output.structured
    raw_type = structured.get("type")
    event_type = raw_type if isinstance(raw_type, str) else ""

    if event_type in _SPEECH_TYPES:
        return "speech"
    if event_type in _ENVIRONMENT_TYPES:
        return "environment_change"
    if event_type in _OTHER_AGENT_ACTION_TYPES:
        return "other_agent_action"
    if event_type in _INTERVENTION_TYPES or entry.output.breaks_movement:
        return "intervention_to_self"
    if entry.output.observation_category == "environment":
        return "environment_change"
    if entry.output.observation_category == "social":
        return "other_agent_action"
    if event_type:
        return "world_event"
    return "system_notice"


def _extract_visible_agents(entry: ObservationEntry) -> Tuple[str, ...]:
    structured = entry.output.structured
    candidates = (
        structured.get("actor"),
        structured.get("target"),
        structured.get("speaker"),
        structured.get("sender"),
        structured.get("recipient"),
    )
    return _string_tuple(candidates)


def _extract_world_event_refs(entry: ObservationEntry) -> Tuple[str, ...]:
    structured = entry.output.structured
    keys = (
        "type",
        "spot_id_value",
        "location_id_value",
        "world_object_id_value",
        "monster_id_value",
        "shop_id_value",
        "guild_id_value",
        "quest_id_value",
        "trade_id_value",
    )
    refs = []
    for key in keys:
        value = structured.get(key)
        if value is None:
            continue
        refs.append(f"{key}:{value}")
    return tuple(refs)


def _perceived_salience(entry: ObservationEntry) -> str:
    if entry.output.breaks_movement:
        return "high"
    if entry.output.schedules_turn:
        return "medium"
    return "normal"


def _optional_int_coerce(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ObservationTraceRecorder:
    """append された ObservationEntry を observation trace として別 store に保存する。"""

    def __init__(self, store: IObservationExperienceTraceStore) -> None:
        if not isinstance(store, IObservationExperienceTraceStore):
            raise TypeError("store must be IObservationExperienceTraceStore")
        self._store = store

    def record(self, player_id: PlayerId, entry: ObservationEntry) -> ObservationExperienceTrace:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entry, ObservationEntry):
            raise TypeError("entry must be ObservationEntry")

        trace = ObservationExperienceTrace(
            trace_id=f"observation-trace-{uuid4().hex}",
            agent_id=player_id.value,
            occurred_at=entry.occurred_at,
            game_time_label=entry.game_time_label,
            observation_summary=entry.output.prose.strip(),
            observation_kind=classify_observation_kind(entry),
            structured=dict(entry.output.structured),
            attention_context=str(entry.output.structured.get("type") or ""),
            perceived_salience=_perceived_salience(entry),
            world_event_refs=_extract_world_event_refs(entry),
            visible_agents=_extract_visible_agents(entry),
            context_spot_id=_optional_int_coerce(entry.output.structured.get("spot_id_value")),
        )
        self._store.append(player_id, trace)
        return trace
