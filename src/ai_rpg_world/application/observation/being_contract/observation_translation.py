"""ゲームの観測とツールの結果を、契約の観測へ変換する。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_ASSESS_SITUATION,
    TOOL_NAME_PREFIX_MEMO,
    TOOL_NAME_PREFIX_MEMORY,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationCategory,
    ObservationOutput,
    SubjectUnknownView,
    WithheldFromStrangers,
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


class NotRepresentableReason(Enum):
    BEING_INNER_RECORD = "being_inner_record"
    EMPTY_BODY = "empty_body"
    MISSING_TIME_LABEL = "missing_time_label"


class ObservationNotRepresentable(ValueError):
    """ゲームの観測を契約の観測に写せない。"""

    def __init__(self, reason: NotRepresentableReason, kind: str | None) -> None:
        super().__init__(f"{reason.value}: {kind}")
        self.reason = reason
        self.kind = kind


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

# メモ・記憶・状況評価の道具は、Being が自分の記録を読み書きするもので、環境に働きかけない。
# 結果の文 (「メモを追加しました（ID: …）」など) を自分の行動の結果として写すと、記憶の
# 側が環境で起きたことと取り違える (#1414 の確かめ方で、いま起きたことに混ざっていた)。
_AGENT_SIDE_TOOL_PREFIXES: Final = (TOOL_NAME_PREFIX_MEMO, TOOL_NAME_PREFIX_MEMORY)
_AGENT_SIDE_TOOLS: Final = frozenset({TOOL_NAME_ASSESS_SITUATION})

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

# 標的が本人なら、出来事は自分の体に起きたことになる種類。
_HARM_TO_TARGET_TYPES: Final = frozenset({"monster_attacked_player"})

# 行為者の名前を持たず、本文が一人称で本人の状態を述べる種類。self_only でも
# 取引の提案や拒否のように主体が他人のものがあるので、分類からは推さない。
_SELF_SUBJECT_TYPES: Final = frozenset(
    {
        "action_failed",
        "gold_earned",
        "gold_paid",
        "inventory_overflow",
        "item_added_to_inventory",
        "item_equipped",
        "item_unequipped",
        "level_up",
        "player_revived_post_hoc",
    }
)

_SUBJECT_NAME_KEYS: Final = (
    "speaker",
    "actor",
    "actor_name",
    "monster_name",
    "seller",
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
    if structured.get("loop_guard") is True:
        raise ObservationNotRepresentable(NotRepresentableReason.BEING_INNER_RECORD, "loop_guard")
    if kind in _BEING_INNER_RECORD_TYPES:
        raise ObservationNotRepresentable(NotRepresentableReason.BEING_INNER_RECORD, kind)
    # 同じ出来事の目撃文が別に届くとき、ゲームは重複する汎用文を空にして送る。
    if not output.prose.strip():
        raise ObservationNotRepresentable(NotRepresentableReason.EMPTY_BODY, kind)
    if game_time_label is None or not game_time_label.strip():
        raise ObservationNotRepresentable(NotRepresentableReason.MISSING_TIME_LABEL, kind)

    targets_self = _targets_self(structured, observer)
    route = _route(kind, output.observation_category, targets_self)
    subject_is_self, subject_name = _subject(kind, structured, output.prose, observer)
    return Observation(
        body=output.prose,
        route=route,
        time=_observed_time(tick, game_time_label, observer.seconds_per_tick),
        subject_is_self=subject_is_self,
        subject_name=subject_name,
        source=_source(route, subject_name, observer),
        place=_place(structured, route, output.prose, observer),
        addressed_to_self=_addressed_to_self(structured, route, targets_self),
        wants_wake=output.schedules_turn,
        body_if_subject_unknown=(
            output.if_subject_unknown.prose
            if isinstance(output.if_subject_unknown, SubjectUnknownView)
            and subject_name is not UNKNOWN
            and not subject_is_self
            else None
        ),
        withheld_if_subject_unknown=(
            isinstance(output.if_subject_unknown, WithheldFromStrangers)
            and not subject_is_self
        ),
    )


def observation_from_action_result(
    entry: ActionResultEntry, *, call_id: str, observer: Observer
) -> Observation:
    """``call_id`` は、この結果を生んだエージェントの 1 手が発行した ID。"""
    if _is_agent_side_tool(entry.tool_name):
        raise ObservationNotRepresentable(
            NotRepresentableReason.BEING_INNER_RECORD, entry.tool_name
        )
    body = entry.result_summary.strip() or entry.action_summary.strip()
    if not body:
        raise ObservationNotRepresentable(NotRepresentableReason.EMPTY_BODY, entry.tool_name)
    if entry.game_time_label is None or not entry.game_time_label.strip():
        raise ObservationNotRepresentable(
            NotRepresentableReason.MISSING_TIME_LABEL, entry.tool_name
        )
    return Observation(
        body=body,
        route=OwnActionResult(call_id=call_id, succeeded=entry.success),
        time=_observed_time(
            entry.occurred_tick, entry.game_time_label, observer.seconds_per_tick
        ),
        subject_is_self=True,
        subject_name=observer.name,
        source=observer.name,
        place=_known(observer.place_name),
        addressed_to_self=True,
        wants_wake=entry.should_reschedule,
    )


def _is_agent_side_tool(tool_name: str | None) -> bool:
    if tool_name is None:
        return False
    return tool_name in _AGENT_SIDE_TOOLS or tool_name.startswith(_AGENT_SIDE_TOOL_PREFIXES)


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
    if targets_self and kind in _HARM_TO_TARGET_TYPES:
        return OwnBodyState()
    if kind is not None and kind in _ROUTE_BY_TYPE:
        return _ROUTE_BY_TYPE[kind]
    return _ROUTE_BY_CATEGORY[category]


# 構造化データには、本文で伏せた名前 (妨害の行為者など) も入っている。本人が観測から
# 知り得ない名前を契約に載せないよう、他人の名前は本文に現れるものだけを写す。
# 本人が行為者かどうかは、本文が伏せていても本人には分かるので構造化データで決める。
def _subject(
    kind: str | None, structured: Mapping[str, Any], prose: str, observer: Observer
) -> tuple[bool, str | UnknownValue]:
    if (
        structured.get("role") == "self"
        or kind in _SELF_SUBJECT_TYPES
        or structured.get("speaker_player_id") == observer.player_id.value
        or observer.name in _subject_names(structured)
    ):
        return True, observer.name
    name = next((n for n in _subject_names(structured) if n in prose), None)
    if name is None:
        return False, UNKNOWN
    return False, name


def _subject_names(structured: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        value
        for key in _SUBJECT_NAME_KEYS
        if isinstance(value := structured.get(key), str) and value.strip()
    )


def _source(
    route: Route, subject_name: str | UnknownValue, observer: Observer
) -> str | UnknownValue:
    if isinstance(route, ToldOrWritten):
        return subject_name
    if isinstance(route, EnvironmentNotice):
        return UNKNOWN
    return observer.name


def _place(
    structured: Mapping[str, Any], route: Route, prose: str, observer: Observer
) -> str | UnknownValue:
    for key in ("source_adjacent_spot_name", "spot_name"):
        value = structured.get(key)
        if isinstance(value, str) and value.strip() and value in prose:
            return value
    if structured.get("source_adjacent_spot_name") or isinstance(route, EnvironmentNotice):
        return UNKNOWN
    return _known(observer.place_name)


def _addressed_to_self(
    structured: Mapping[str, Any], route: Route, targets_self: bool | None
) -> bool | UnknownValue:
    if targets_self is not None:
        return targets_self
    if structured.get("channel") == "whisper" and structured.get("role") != "self":
        return True
    is_target = structured.get("is_target")
    if isinstance(is_target, bool):
        return is_target
    if isinstance(route, OwnBodyState):
        return True
    return UNKNOWN


def _observed_time(
    tick: int | None, game_time_label: str, seconds_per_tick: float | None
) -> ObservedTime:
    seconds = (
        tick * seconds_per_tick
        if tick is not None and seconds_per_tick is not None
        else None
    )
    return ObservedTime(display=game_time_label, seconds=seconds)


def _known(value: str | None) -> str | UnknownValue:
    return value if value is not None and value.strip() else UNKNOWN
