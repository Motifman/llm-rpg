"""Being の memory store の VO ↔ JSON dict 変換ヘルパ。

Phase 4 Step 4-2b (Issue #470): ``BeingMemorySnapshotService`` が `BeingSnapshot`
の ``memory_payload_json`` に詰める JSON の **内部 schema を版管理する** ための
serializer 群。

各 ``_<vo>_to_dict`` / ``_dict_to_<vo>`` は 1:1 の VO ↔ dict 変換を提供する。
**Enum は ``.value``** で表現する (= JSON 標準型のみ)。
これにより snapshot JSON は他言語 / 外部ツールでも読みやすい。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.being.contract import (
    UNKNOWN,
    AgentMove,
    EnvironmentNotice,
    FrozenJsonObject,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnActionResult,
    OwnBodyState,
    SeenOrHeard,
    ToldOrWritten,
)
from ai_rpg_world.being.domain.acquaintance import Acquaintance, HowKnown
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex, IndexRevision
from ai_rpg_world.being.domain.memo_book import (
    Memo,
    MemoCertainty,
    MemoKind,
    MemoProvenance,
    MemoSource,
)
from ai_rpg_world.being.domain.short_term_memory import (
    Attempt,
    Backstory,
    Lapse,
    MemoryOperationResult,
    Perception,
    ShortTermMemory,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.common.exception import DomainException


def acquaintance_to_dict(acquaintance: Acquaintance) -> dict[str, Any]:
    return {
        "environment_name": acquaintance.environment_name,
        "name": acquaintance.name,
        "how_known": acquaintance.how_known.name,
        "known_since_turn": acquaintance.known_since_turn,
        "name_learned_turn": acquaintance.name_learned_turn,
        "relation_note": acquaintance.relation_note,
        "met_count": acquaintance.met_count,
        "first_met_turn": acquaintance.first_met_turn,
        "last_met_turn": acquaintance.last_met_turn,
    }


def dict_to_acquaintance(data: dict[str, Any]) -> Acquaintance:
    return Acquaintance(
        environment_name=data["environment_name"],
        name=data["name"],
        how_known=HowKnown[data["how_known"]],
        known_since_turn=data["known_since_turn"],
        name_learned_turn=data["name_learned_turn"],
        relation_note=data["relation_note"],
        met_count=data["met_count"],
        first_met_turn=data["first_met_turn"],
        last_met_turn=data["last_met_turn"],
    )


def _episode_index_to_dict(index: EpisodeIndex) -> dict[str, Any]:
    return {"summary": index.summary, "recall_when": index.recall_when}


def _dict_to_episode_index(data: dict[str, Any]) -> EpisodeIndex:
    return EpisodeIndex(summary=data["summary"], recall_when=data["recall_when"])


def being_episode_to_dict(episode: Episode) -> dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "handle": episode.handle,
        "environment_name": episode.environment_name,
        "written_turn": episode.written_turn,
        "index": _episode_index_to_dict(episode.index),
        "body": episode.body,
        "recall_count": episode.recall_count,
        "last_recalled_turn": episode.last_recalled_turn,
        "index_history": [
            {
                "previous": _episode_index_to_dict(revision.previous),
                "revised_turn": revision.revised_turn,
            }
            for revision in episode.index_history
        ],
    }


def dict_to_being_episode(data: dict[str, Any], *, being_id: BeingId) -> Episode:
    """呼び名は ID から作り直さない。伸ばした呼び名が 6 文字に戻ると、前の呼び名が別の記録を指す。

    持ち主は payload に書かず、戻す先の Being の ID を使う。payload は Being ごとに 1 本なので。
    """
    try:
        return Episode(
            being_id=being_id,
            episode_id=data["episode_id"],
            handle=data["handle"],
            environment_name=data["environment_name"],
            written_turn=data["written_turn"],
            index=_dict_to_episode_index(data["index"]),
            body=data["body"],
            recall_count=data["recall_count"],
            last_recalled_turn=data["last_recalled_turn"],
            index_history=tuple(
                IndexRevision(
                    previous=_dict_to_episode_index(revision["previous"]),
                    revised_turn=revision["revised_turn"],
                )
                for revision in data["index_history"]
            ),
        )
    except DomainException as exc:
        raise ValueError(f"invalid being episode payload: {exc}") from exc


def being_memo_to_dict(memo: Memo) -> dict[str, Any]:
    provenance = memo.provenance
    return {
        "memo_id": memo.memo_id,
        "handle": memo.handle,
        "kind": memo.kind.value,
        "text": memo.text,
        "provenance": None
        if provenance is None
        else {
            "source": provenance.source.value,
            "certainty": provenance.certainty.value,
            "source_from": provenance.source_from,
        },
        "written_turn": memo.written_turn,
        "edited_turn": memo.edited_turn,
        "environment_name": memo.environment_name,
    }


def dict_to_being_memo(data: dict[str, Any]) -> Memo:
    """呼び名は ID から作り直さない (エピソードと同じ理由)。"""
    try:
        provenance = data["provenance"]
        return Memo(
            memo_id=data["memo_id"],
            handle=data["handle"],
            kind=MemoKind(data["kind"]),
            text=data["text"],
            provenance=None
            if provenance is None
            else MemoProvenance(
                source=MemoSource(provenance["source"]),
                certainty=MemoCertainty(provenance["certainty"]),
                source_from=provenance["source_from"],
            ),
            written_turn=data["written_turn"],
            edited_turn=data["edited_turn"],
            environment_name=data["environment_name"],
        )
    except DomainException as exc:
        raise ValueError(f"invalid being memo payload: {exc}") from exc


_ROUTE_KINDS: dict[type, str] = {
    SeenOrHeard: "seen_or_heard",
    ToldOrWritten: "told_or_written",
    OwnBodyState: "own_body_state",
    OwnActionResult: "own_action_result",
    EnvironmentNotice: "environment_notice",
}
_ROUTES_WITHOUT_FIELDS: dict[str, Any] = {
    "seen_or_heard": SeenOrHeard,
    "told_or_written": ToldOrWritten,
    "own_body_state": OwnBodyState,
    "environment_notice": EnvironmentNotice,
}


def _route_to_dict(route: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": _ROUTE_KINDS[type(route)]}
    if isinstance(route, OwnActionResult):
        out["call_id"] = route.call_id
        out["succeeded"] = route.succeeded
    return out


def _dict_to_route(data: dict[str, Any]) -> Any:
    kind = data["kind"]
    if kind == "own_action_result":
        return OwnActionResult(call_id=data["call_id"], succeeded=data["succeeded"])
    return _ROUTES_WITHOUT_FIELDS[kind]()


def _known_or_none(value: Any) -> Any:
    """「不明」は JSON の null で表す。分かっている欄は空でない文字列か bool なので、null と重ならない。"""
    return None if value is UNKNOWN else value


def _none_to_unknown(value: Any) -> Any:
    return UNKNOWN if value is None else value


def _order_to_dict(order: OccurrenceOrder | None) -> dict[str, Any] | None:
    return None if order is None else {"environment": order.environment, "value": order.value}


def _dict_to_order(data: dict[str, Any] | None) -> OccurrenceOrder | None:
    """起きた順を足す前に保存した出来事は持たない (design_decisions D1824-8)。"""
    return None if data is None else OccurrenceOrder(environment=data["environment"], value=data["value"])


def _observation_to_dict(observation: Observation) -> dict[str, Any]:
    return {
        "body": observation.body,
        "route": _route_to_dict(observation.route),
        "time": {"display": observation.time.display, "seconds": observation.time.seconds},
        "subject_is_self": observation.subject_is_self,
        "subject_name": _known_or_none(observation.subject_name),
        "source": _known_or_none(observation.source),
        "place": _known_or_none(observation.place),
        "addressed_to_self": _known_or_none(observation.addressed_to_self),
        "wants_wake": observation.wants_wake,
        "body_if_subject_unknown": observation.body_if_subject_unknown,
        "withheld_if_subject_unknown": observation.withheld_if_subject_unknown,
        "order": _order_to_dict(observation.order),
    }


def _dict_to_observation(data: dict[str, Any]) -> Observation:
    return Observation(
        body=data["body"],
        route=_dict_to_route(data["route"]),
        time=ObservedTime(display=data["time"]["display"], seconds=data["time"]["seconds"]),
        subject_is_self=data["subject_is_self"],
        subject_name=_none_to_unknown(data["subject_name"]),
        source=_none_to_unknown(data["source"]),
        place=_none_to_unknown(data["place"]),
        addressed_to_self=_none_to_unknown(data["addressed_to_self"]),
        wants_wake=data["wants_wake"],
        body_if_subject_unknown=data["body_if_subject_unknown"],
        withheld_if_subject_unknown=data["withheld_if_subject_unknown"],
        order=_dict_to_order(data.get("order")),
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, FrozenJsonObject):
        return {name: _thaw_json(item) for name, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _move_to_dict(move: AgentMove) -> dict[str, Any]:
    return {
        "call_id": move.call_id,
        "tool_name": move.tool_name,
        "arguments": _thaw_json(move.arguments),
        "expectation": move.expectation,
        "inner_thought": move.inner_thought,
    }


def _dict_to_move(data: dict[str, Any]) -> AgentMove:
    return AgentMove(
        call_id=data["call_id"],
        tool_name=data["tool_name"],
        arguments=data["arguments"],
        expectation=data["expectation"],
        inner_thought=data["inner_thought"],
    )


def _time_to_dict(time: ObservedTime) -> dict[str, Any]:
    return {"display": time.display, "seconds": time.seconds}


def _dict_to_time(data: dict[str, Any]) -> ObservedTime:
    return ObservedTime(display=data["display"], seconds=data["seconds"])


class _ExperienceToDict:
    def perceived(self, perception: Perception) -> dict[str, Any]:
        return {
            "kind": "perception",
            "turn": perception.turn,
            "observation": _observation_to_dict(perception.observation),
        }

    def attempted(self, attempt: Attempt, result: Observation) -> dict[str, Any]:
        return {**self.attempted_without_result(attempt), "result": {"observation": _observation_to_dict(result)}}

    def attempted_memory_operation(self, attempt: Attempt, result: MemoryOperationResult) -> dict[str, Any]:
        return {
            **self.attempted_without_result(attempt),
            "result": {
                "memory_operation": {
                    "call_id": result.call_id,
                    "body": result.body,
                    "time": _time_to_dict(result.time),
                    "order": _order_to_dict(result.order),
                }
            },
        }

    def attempted_without_result(self, attempt: Attempt) -> dict[str, Any]:
        return {"kind": "attempt", "turn": attempt.turn, "move": _move_to_dict(attempt.move), "result": None}

    def lapsed(self, lapse: Lapse) -> dict[str, Any]:
        return {
            "kind": "lapse",
            "turn": lapse.turn,
            "body": lapse.body,
            "time": _time_to_dict(lapse.time),
            "order": _order_to_dict(lapse.order),
        }


def _dict_to_attempt_result(data: dict[str, Any] | None) -> Observation | MemoryOperationResult | None:
    if data is None:
        return None
    if "observation" in data:
        return _dict_to_observation(data["observation"])
    operation = data["memory_operation"]
    return MemoryOperationResult(
        call_id=operation["call_id"],
        body=operation["body"],
        time=_dict_to_time(operation["time"]),
        order=_dict_to_order(operation["order"]),
    )


def _dict_to_attempt(data: dict[str, Any]) -> Attempt:
    return Attempt(turn=data["turn"], move=_dict_to_move(data["move"]), result=_dict_to_attempt_result(data["result"]))


def _dict_to_experience(data: dict[str, Any]) -> Perception | Attempt | Lapse:
    kind = data["kind"]
    if kind == "perception":
        return Perception(turn=data["turn"], observation=_dict_to_observation(data["observation"]))
    if kind == "attempt":
        return _dict_to_attempt(data)
    if kind == "lapse":
        return Lapse(
            turn=data["turn"],
            body=data["body"],
            time=_dict_to_time(data["time"]),
            order=_dict_to_order(data["order"]),
        )
    raise KeyError(f"unknown experience kind {kind!r}")


def _event_to_experience(data: dict[str, Any]) -> Perception | Attempt:
    """短期記憶を集約に作り直す前の形 (観測と、自分の行動の結果なら 1 手) を読む (design_decisions D1824-9)。"""
    observation = _dict_to_observation(data["observation"])
    if data["move"] is None:
        return Perception(turn=data["turn"], observation=observation)
    return Attempt(turn=data["turn"], move=_dict_to_move(data["move"]), result=observation)


def being_short_term_memory_to_dict(memory: ShortTermMemory) -> dict[str, Any]:
    to_dict = _ExperienceToDict()
    return {
        "experiences": [experience.show_to(to_dict) for experience in memory.experiences],
        "recent_from": memory.recent_from,
        "awaiting": None if memory.awaiting is None else _move_and_turn_to_dict(memory.awaiting),
        "backstories": [
            {"flow": b.flow, "mood": b.mood, "written_turn": b.written_turn}
            for b in memory.backstories
        ],
    }


def _move_and_turn_to_dict(attempt: Attempt) -> dict[str, Any]:
    return {"turn": attempt.turn, "move": _move_to_dict(attempt.move)}


def dict_to_being_short_term_memory(data: dict[str, Any], *, being_id: BeingId) -> ShortTermMemory:
    try:
        experiences = (
            tuple(_event_to_experience(event) for event in data["events"])
            if "events" in data
            else tuple(_dict_to_experience(experience) for experience in data["experiences"])
        )
        awaiting = data.get("awaiting")
        return ShortTermMemory(
            being_id,
            experiences=experiences,
            backstories=tuple(
                Backstory(flow=b["flow"], mood=b["mood"], written_turn=b["written_turn"])
                for b in data["backstories"]
            ),
            recent_from=data.get("recent_from", 1),
            awaiting=None
            if awaiting is None
            else Attempt(turn=awaiting["turn"], move=_dict_to_move(awaiting["move"])),
        )
    except DomainException as exc:
        raise ValueError(f"invalid being short-term memory payload: {exc}") from exc
