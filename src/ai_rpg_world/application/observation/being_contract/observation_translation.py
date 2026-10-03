"""ゲームの観測とツールの結果を、契約の観測へ変換する。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationCategory,
    ObservationOutput,
)
from ai_rpg_world.being.contract import (
    UNKNOWN,
    EnvironmentNotice,
    Observation,
    ObservedTime,
    OwnActionResult,
    OwnBodyState,
    Route,
    SeenOrHeard,
    ToldOrWritten,
    UnknownValue,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ObservationNotRepresentable(ValueError):
    """ゲームの観測を契約の観測に写せない。"""


@dataclass(frozen=True, kw_only=True)
class Observer:
    """観測を受け取る本人について、変換に要るゲーム側の事実。"""

    player_id: PlayerId
    name: str
    place_name: str | None
    seconds_per_tick: float | None


# 目的の振り返り・改訂は Being が自分で立てた判断を書き戻したもの、ループ警告は
# エージェント側の自己監視で、どちらも環境から届く観測ではない。経路の 5 つの
# どれにも当たらないので、選択肢を足さずに変換を拒む。
_BEING_INNER_RECORD_TYPES: Final = frozenset({"goal_reflect", "goal_revision"})

_ROUTE_BY_CATEGORY: Final[Mapping[ObservationCategory, Route]] = {
    "self_only": OwnBodyState(),
    "social": SeenOrHeard(),
    "environment": EnvironmentNotice(),
}

# observation_category は注意の水準で決めた分類なので、経路と食い違う種類だけを上書きする。
_ROUTE_BY_TYPE: Final[Mapping[str, Route]] = {
    "player_spoke": ToldOrWritten(),
    "sns_post_created": ToldOrWritten(),
    "sns_reply_created": ToldOrWritten(),
    "game_phase_changed": EnvironmentNotice(),
    "meeting_vote_cast": EnvironmentNotice(),
    "meeting_vote_resolved": EnvironmentNotice(),
    "meeting_condition_resolved": EnvironmentNotice(),
    "weather_changed": SeenOrHeard(),
    "time_of_day_changed": SeenOrHeard(),
    "spot_object_state_changed": SeenOrHeard(),
    "connection_state_changed": SeenOrHeard(),
    "monster_appeared_at_spot": SeenOrHeard(),
    "monster_encountered": SeenOrHeard(),
    "monster_left_spot": SeenOrHeard(),
    "distant_cue_appeared": SeenOrHeard(),
}

_SUBJECT_NAME_KEYS: Final = (
    "speaker",
    "actor",
    "actor_name",
    "monster_name",
    "voter_display_name",
    "initiator_display_name",
)


def observation_from_game(
    output: ObservationOutput,
    *,
    tick: int | None,
    game_time_label: str | None,
    observer: Observer,
) -> Observation:
    structured = output.structured
    kind = _kind(structured)
    if kind in _BEING_INNER_RECORD_TYPES or structured.get("loop_guard") is True:
        raise ObservationNotRepresentable(f"being inner record: {kind or 'loop_guard'}")

    targets_self = _targets_self(structured, observer)
    route = _route(kind, output.observation_category, targets_self)
    subject_is_self, subject_name = _subject(structured, output, observer)
    return Observation(
        body=output.prose,
        route=route,
        time=_observed_time(tick, game_time_label, observer),
        subject_is_self=subject_is_self,
        subject_name=subject_name,
        source=_source(route, subject_name, observer),
        place=_place(structured, route, observer),
        addressed_to_self=_addressed_to_self(structured, route, targets_self),
        wants_wake=output.schedules_turn,
    )


def observation_from_action_result(
    entry: ActionResultEntry, *, call_id: str, observer: Observer
) -> Observation:
    """``call_id`` は、この結果を生んだエージェントの 1 手が発行した ID。"""
    return Observation(
        body=entry.result_summary.strip() or entry.action_summary,
        route=OwnActionResult(call_id=call_id, succeeded=entry.success),
        time=_observed_time(entry.occurred_tick, entry.game_time_label, observer),
        subject_is_self=True,
        subject_name=observer.name,
        source=observer.name,
        place=_known(observer.place_name),
        addressed_to_self=True,
        wants_wake=entry.should_reschedule,
    )


def _kind(structured: Mapping[str, Any]) -> str | None:
    kind = structured.get("type") or structured.get("kind")
    return kind if isinstance(kind, str) else None


def _targets_self(structured: Mapping[str, Any], observer: Observer) -> bool | None:
    target = structured.get("target_player_id")
    if target is None:
        return None
    return bool(target == observer.player_id.value)


def _route(
    kind: str | None, category: ObservationCategory, targets_self: bool | None
) -> Route:
    if targets_self:
        return OwnBodyState()
    if kind is not None and kind in _ROUTE_BY_TYPE:
        return _ROUTE_BY_TYPE[kind]
    return _ROUTE_BY_CATEGORY[category]


def _subject(
    structured: Mapping[str, Any], output: ObservationOutput, observer: Observer
) -> tuple[bool, str | UnknownValue]:
    if structured.get("role") == "self" or (
        output.observation_category == "self_only" and _named_subject(structured) is None
    ):
        return True, observer.name
    speaker_id = structured.get("speaker_player_id")
    name = _named_subject(structured)
    if name is None:
        return False, UNKNOWN
    is_self = name == observer.name or speaker_id == observer.player_id.value
    return is_self, name


def _named_subject(structured: Mapping[str, Any]) -> str | None:
    for key in _SUBJECT_NAME_KEYS:
        value = structured.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _source(
    route: Route, subject_name: str | UnknownValue, observer: Observer
) -> str | UnknownValue:
    if isinstance(route, ToldOrWritten):
        return subject_name
    if isinstance(route, EnvironmentNotice):
        return UNKNOWN
    return observer.name


def _place(
    structured: Mapping[str, Any], route: Route, observer: Observer
) -> str | UnknownValue:
    for key in ("source_adjacent_spot_name", "spot_name"):
        value = structured.get(key)
        if isinstance(value, str) and value.strip():
            return value
    if isinstance(route, EnvironmentNotice):
        return UNKNOWN
    return _known(observer.place_name)


def _addressed_to_self(
    structured: Mapping[str, Any], route: Route, targets_self: bool | None
) -> bool | UnknownValue:
    if targets_self is not None:
        return targets_self
    if structured.get("channel") == "whisper":
        return True
    is_target = structured.get("is_target")
    if isinstance(is_target, bool):
        return is_target
    if isinstance(route, OwnBodyState):
        return True
    return UNKNOWN


def _observed_time(
    tick: int | None, game_time_label: str | None, observer: Observer
) -> ObservedTime:
    if game_time_label is None or not game_time_label.strip():
        raise ObservationNotRepresentable("game_time_label is required for the time field")
    seconds = (
        tick * observer.seconds_per_tick
        if tick is not None and observer.seconds_per_tick is not None
        else None
    )
    return ObservedTime(display=game_time_label, seconds=seconds)


def _known(value: str | None) -> str | UnknownValue:
    return value if value is not None and value.strip() else UNKNOWN
