from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from ai_rpg_world.application.being.player_short_term_memory_copy import (
    PlayerShortTermMemoryCopy,
)
from ai_rpg_world.application.common.execution_provenance import (
    ExecutionProvenance,
    execution_provenance_scope,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
    format_action_result_body,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.being_contract import Observer
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.contract import AgentMove, OwnActionResult, SeenOrHeard
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ADA = PlayerId(1)
ADA_BEING = BeingId("being_p1")
NPC = PlayerId(9)
_AT = datetime(2026, 6, 1, tzinfo=timezone.utc)
_NOT_COPIED = TraceEventKind.BEING_SHORT_TERM_MEMORY_NOT_COPIED


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        self.events: list[tuple[str, int | None, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, tick, player_id, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)

    def not_copied(self) -> list[dict[str, Any]]:
        return [p for k, _, _, p in self.events if k == _NOT_COPIED]


class _World:
    """写す側に渡す世界の事実を 1 か所に集めた試験用の部品。"""

    def __init__(self) -> None:
        self.store = InMemoryShortTermMemoryRepository()
        self.clock = InMemoryMemoryTurnClock()
        self.recorder = _Recorder()
        self.tick = 3
        self.observer_error: Exception | None = None
        self.copy = PlayerShortTermMemoryCopy(
            store=self.store,
            being_id_of=lambda pid: ADA_BEING if pid == ADA else None,
            turn_reader=self.clock,
            observer_of=self._observer,
            current_tick_provider=lambda: self.tick,
            trace_recorder_provider=lambda: self.recorder,
        )

    def _observer(self, player_id: PlayerId) -> Observer:
        if self.observer_error is not None:
            raise self.observer_error
        return Observer(player_id=player_id, name="エイダ", place_name="坑道の入口", seconds_per_tick=300)

    def events(self) -> tuple[Any, ...]:
        return self.store.get(ADA_BEING).events


def _observation(prose: str = "ミオが坑道から戻ってきた", *, label: str | None = "1日目 朝", **structured: Any) -> UnifiedRecentEventEntry:
    return UnifiedRecentEventEntry.from_observation(
        ObservationEntry(occurred_at=_AT, game_time_label=label, output=ObservationOutput(prose=prose, structured=structured))
    )


def _result(provenance: ExecutionProvenance | None, **overrides: Any) -> UnifiedRecentEventEntry:
    fields: dict[str, Any] = {"occurred_at": _AT, "action_summary": "扉を調べた", "result_summary": "鍵がかかっていた", "success": True, "tool_name": "interact", "game_time_label": "1日目 朝", "inner_thought": "鍵を探そう", "occurred_tick": 3, "execution_provenance": provenance}
    return UnifiedRecentEventEntry.from_action_result(ActionResultEntry(**{**fields, **overrides}))


def _provenance(request_id: str = "execution-1") -> ExecutionProvenance:
    return ExecutionProvenance(execution_request_id=request_id, actor_player_id=1, actor_turn=1)


class TestCopyOneTurn:
    """PlayerShortTermMemoryCopy が、1 回の手番で今の短期記憶に入った出来事を、D1824-5 の番号を付けて Being 側の短期記憶に写すことを保証する。"""

    def test_observation_seen_before_the_move_gets_the_next_move_number(self) -> None:
        """時計が 0 のときに取り出された観測は、それを見る 1 手の番号 1 で写り、時刻の秒は今の tick から作る。"""
        world = _World()

        world.copy.on_appended(ADA, _observation())

        (event,) = world.events()
        assert (event.turn, event.observation.body, event.move) == (1, "ミオが坑道から戻ってきた", None)
        assert event.observation.time.seconds == 3 * 300

    def test_own_result_pairs_with_the_noted_move_of_the_same_request(self) -> None:
        """1 手を受け取って時計が 1 に進んだあと、同じ実行の要求の結果は、その 1 手と対になって番号 1 で写る。"""
        world = _World()
        world.clock.advance_turn(ADA_BEING)
        provenance = _provenance()
        with execution_provenance_scope(provenance):
            world.copy.note_move(ADA, "interact", {"target": "扉", "inner_thought": "鍵を探そう", "expected_result": "開く"})
        result = _result(provenance)

        world.copy.on_appended(ADA, result)

        (event,) = world.events()
        assert event.turn == 1
        assert event.observation.route == OwnActionResult(call_id="execution-1", succeeded=True)
        assert event.observation.body == format_action_result_body(result.payload)
        assert event.move == AgentMove(call_id="execution-1", tool_name="interact", arguments={"target": "扉"}, expectation="開く", inner_thought="鍵を探そう")

    def test_result_that_arrives_without_a_move_is_seen_at_the_next_move(self) -> None:
        """移動の到着のように実行の要求を持たない結果は、「見た・聞いた」の経路で、次の 1 手の番号で写る。"""
        world = _World()
        world.clock.advance_turn(ADA_BEING)

        world.copy.on_appended(ADA, _result(None, tool_name="travel_to", action_summary="通信室へ移動した", result_summary="通信室に着いた"))

        (event,) = world.events()
        assert (event.turn, event.observation.route, event.move) == (2, SeenOrHeard(), None)

    def test_a_whole_turn_keeps_one_number_and_the_order_it_arrived(self) -> None:
        """観測、1 手の結果、後から届く到着の順に入ると、前の 2 つは番号 1、到着は番号 2 で、届いた順に並ぶ。"""
        world = _World()
        world.copy.on_appended(ADA, _observation())
        world.clock.advance_turn(ADA_BEING)
        provenance = _provenance()
        with execution_provenance_scope(provenance):
            world.copy.note_move(ADA, "interact", {"target": "扉"})
        world.copy.on_appended(ADA, _result(provenance))
        world.copy.on_appended(ADA, _result(None, tool_name="travel_to"))

        assert [e.turn for e in world.events()] == [1, 1, 2]
        assert world.recorder.not_copied() == []


class TestNotCopied:
    """写せない出来事は Being 側の短期記憶に入れず、理由と種類を being_short_term_memory_not_copied の trace に残すことを保証する (design_decisions D1824-7)。"""

    @pytest.mark.parametrize(
        ("entry", "source", "reason", "kind"),
        [
            (_observation("同じ行動が続いている", loop_guard=True), "observation", "being_inner_record", "loop_guard"),
            (_observation(" ", type="player_spoke"), "observation", "empty_body", "player_spoke"),
            (_observation("あなたは息を吹き返した", label=None, type="player_revived_post_hoc"), "observation", "missing_time_label", "player_revived_post_hoc"),
            (_result(None, tool_name="memo_add"), "action_result", "being_inner_record", "memo_add"),
            (_result(_provenance(), tool_name="hesitation", success=False), "action_result", "no_agent_move", "hesitation"),
        ],
        ids=["loop-guard", "empty-observation", "no-time-label", "memo-result", "no-move"],
    )
    def test_rejected_event_is_traced_and_not_remembered(self, entry: UnifiedRecentEventEntry, source: str, reason: str, kind: str) -> None:
        """記憶の道具や警告、空の本文、時刻の無い観測、1 手の無い結果は写さず、trace に 1 件残す。"""
        world = _World()
        world.clock.advance_turn(ADA_BEING)

        world.copy.on_appended(ADA, entry)

        assert world.events() == ()
        assert world.recorder.not_copied() == [{"being_id": "being_p1", "source": source, "reason": reason, "event_kind": kind}]
        assert [(t, p) for k, t, p, _ in world.recorder.events] == [(3, 1)]

    def test_result_of_another_request_is_not_paired_with_the_noted_move(self) -> None:
        """書き留めた 1 手と実行の要求が違う結果は、対にする 1 手が無いものとして写さない。"""
        world = _World()
        world.clock.advance_turn(ADA_BEING)
        with execution_provenance_scope(_provenance("execution-1")):
            world.copy.note_move(ADA, "interact", {"target": "扉"})

        world.copy.on_appended(ADA, _result(_provenance("execution-2")))

        assert world.events() == ()
        assert [p["reason"] for p in world.recorder.not_copied()] == ["no_agent_move"]

    def test_move_with_non_json_argument_is_traced_as_contract_violation(self) -> None:
        """JSON でない値を引数に持つ 1 手は契約の型にならないので、contract_violation として残し、その結果も 1 手の無い結果になる。"""
        world = _World()
        world.clock.advance_turn(ADA_BEING)
        provenance = _provenance()
        with execution_provenance_scope(provenance):
            world.copy.note_move(ADA, "interact", {"target": object()})
        world.copy.on_appended(ADA, _result(provenance))

        assert [(p["source"], p["reason"]) for p in world.recorder.not_copied()] == [("move", "contract_violation"), ("action_result", "no_agent_move")]

    def test_event_numbered_before_the_last_one_is_traced_as_memory_rule(self) -> None:
        """時計を進めたあとに観測が入り (番号 2)、そのあとで番号 1 の結果が来ると、手番の順が崩れるので memory_rule として残す。"""
        world = _World()
        world.clock.advance_turn(ADA_BEING)
        provenance = _provenance()
        with execution_provenance_scope(provenance):
            world.copy.note_move(ADA, "interact", {"target": "扉"})
        world.copy.on_appended(ADA, _observation())

        world.copy.on_appended(ADA, _result(provenance))

        assert [e.turn for e in world.events()] == [2]
        assert [p["reason"] for p in world.recorder.not_copied()] == ["memory_rule"]

    def test_unexpected_error_does_not_stop_the_turn(self) -> None:
        """思わぬ例外が起きても外へ投げず、unexpected_error と例外の型を残す。"""
        world = _World()
        world.observer_error = RuntimeError("盤にいない")

        world.copy.on_appended(ADA, _observation())

        assert world.recorder.not_copied() == [{"being_id": "being_p1", "source": "observation", "reason": "unexpected_error", "event_kind": None, "error_type": "RuntimeError"}]


class TestPlayersWithoutBeing:
    """Being に結びつかないプレイヤーの出来事を、写さず、trace にも残さないことを保証する。"""

    def test_nothing_is_written_or_traced(self) -> None:
        """Being の無いプレイヤーの観測と 1 手は、どの短期記憶にも入らず、trace も増えない。"""
        world = _World()
        with execution_provenance_scope(_provenance()):
            world.copy.note_move(NPC, "interact", {"target": "扉"})

        world.copy.on_appended(NPC, _observation())

        assert world.events() == ()
        assert world.recorder.events == []
