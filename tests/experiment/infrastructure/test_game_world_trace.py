from __future__ import annotations

from typing import Any

from ai_rpg_world.being.application.choose_action import ActionChoosingReply, LlmExchange, ToolCallReply
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.experiment.infrastructure.game_world_trace import GameWorldTrace, GameWorldTraceKind
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.application.play_rounds import DiscardedChoice
from ai_rpg_world.play_session.domain.turn_rounds import (
    ChoiceFailed,
    ObservationPassedOnEvent,
    RoundOpenedEvent,
    SkippedTurn,
    TurnFinishedEvent,
    TurnSkipReason,
)

_WORLD = WorldId("mine_village_v2#1")
_GEN, _SAYO = PersonId("gen"), PersonId("sayo")


class _Kept:
    def __init__(self) -> None:
        self.records: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any) -> None:
        self.records.append((kind, tick, payload))


def _trace() -> tuple[GameWorldTrace, _Kept]:
    kept = _Kept()
    return GameWorldTrace(kept, names={_GEN: "ゲン", _SAYO: "サヨ"}, now=lambda: 7), kept


class TestTurnRoundsInTheTrace:
    """GameWorldTrace が、巡りのイベントを、人の id と名前つきで、新しい世界の kind の行に写すことを保証する。"""

    def test_round_opened_keeps_who_was_skipped_and_why(self) -> None:
        """探している最中で話しかけられていないゲンを飛ばした巡りは、skipped にゲンと理由が残り、行の tick は今の世界の tick になる。"""
        trace, kept = _trace()
        skipped = SkippedTurn(_GEN, TurnSkipReason.IN_THE_MIDDLE_OF_ACTION_AND_NOT_ADDRESSED)

        trace.record_turn_rounds_events(
            [RoundOpenedEvent(**new_event_stamp(), world=_WORLD, round=8, due=(_SAYO,), skipped=(skipped,))]
        )

        [(kind, tick, payload)] = kept.records
        assert (kind, tick) == (GameWorldTraceKind.ROUND_OPENED, 7)
        assert payload["due"] == [{"person_id": "sayo", "name": "サヨ"}]
        assert payload["skipped"] == [
            {"person_id": "gen", "name": "ゲン", "reason": "in_the_middle_of_action_and_not_addressed"}
        ]

    def test_turn_that_failed_to_choose_keeps_its_order_and_reason(self) -> None:
        """2 番目にターンを終えたゲンが選べなかったら、order=2 と、落ちた理由が残る。"""
        trace, kept = _trace()

        trace.record_turn_rounds_events(
            [
                TurnFinishedEvent(
                    **new_event_stamp(),
                    world=_WORLD,
                    round=8,
                    person=_GEN,
                    order=2,
                    outcome=ChoiceFailed("TimeoutError: no reply"),
                )
            ]
        )

        [(_, _, payload)] = kept.records
        assert (payload["order"], payload["outcome"], payload["reason"]) == (
            2,
            "choice_failed",
            "TimeoutError: no reply",
        )

    def test_observation_passed_on_keeps_why_it_could_wake_the_person(self) -> None:
        """ゲンに渡した観測は、本文と、起こしたい印 (wants_wake) と、自分に向けたか (addressed_to_self) を残す。分からないものは unknown と書く。"""
        trace, kept = _trace()
        observation = Observation(
            body="サヨが「そっちはどう？」とささやいた。",
            route=SeenOrHeard(),
            time=ObservedTime(display="Day 1 9:00"),
            subject_is_self=False,
            subject_name=UNKNOWN,
            source=UNKNOWN,
            place=UNKNOWN,
            addressed_to_self=UNKNOWN,
            wants_wake=True,
        )

        trace.record_turn_rounds_events(
            [ObservationPassedOnEvent(**new_event_stamp(), world=_WORLD, person=_GEN, observation=observation)]
        )

        [(kind, _, payload)] = kept.records
        assert kind == GameWorldTraceKind.OBSERVATION_PASSED_ON
        assert (payload["body"], payload["wants_wake"], payload["addressed_to_self"]) == (
            "サヨが「そっちはどう？」とささやいた。",
            True,
            "unknown",
        )


class TestDiscardedChoicesInTheTrace:
    """GameWorldTrace が、世界が終わって捨てた選択を、呼ぶ前に取り消したものと返ったものを分けて残すことを保証する。"""

    def test_returned_choice_keeps_the_tool_it_chose(self) -> None:
        """返ってきてから捨てたミオの選択は、考え始めていた印と、選んだツールと引数を残す。"""
        trace, kept = _trace()
        reply = ActionChoosingReply(
            tool_call=ToolCallReply(tool_name="speak", arguments={"content": "待って"}, call_id="c1")
        )
        exchange = LlmExchange(messages=(), tools=(), replies=(reply,))

        trace.record_discarded([DiscardedChoice(person=PersonId("mio"), exchange=exchange, failure=None)])

        [(kind, _, payload)] = kept.records
        assert kind == GameWorldTraceKind.CHOICE_DISCARDED
        assert (payload["started_thinking"], payload["tool"], payload["arguments"]) == (
            True,
            "speak",
            {"content": "待って"},
        )

    def test_choice_cancelled_before_thinking_is_marked_as_not_started(self) -> None:
        """呼ぶ前に取り消したゲンの選択は、考え始めていなかった印だけを残す。"""
        trace, kept = _trace()

        trace.record_discarded([DiscardedChoice(person=_GEN, exchange=None, failure=None)])

        [(_, _, payload)] = kept.records
        assert (payload["started_thinking"], payload["tool"]) == (False, None)
