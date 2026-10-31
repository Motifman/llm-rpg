from __future__ import annotations

from datetime import timezone

import pytest

from ai_rpg_world.being.contract import (
    UNKNOWN,
    AgentMove,
    EnvironmentNotice,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnActionResult,
    OwnBodyState,
    SeenOrHeard,
    ToldOrWritten,
)
from ai_rpg_world.being.domain.short_term_memory import (
    BACKSTORY_GENERATIONS,
    BACKSTORY_OVERDUE_TURNS,
    FOLD_TURNS,
    FORCED_FOLD_TURNS,
    RECENT_TURNS,
    Attempt,
    AwaitedBackstory,
    Backstory,
    Lapse,
    MemoryOperationOutcome,
    ObservedOutcome,
    Perception,
    ShortTermMemory,
    ShortTermMemoryBackstoryAddedEvent,
    ShortTermMemoryBackstoryOverdueEvent,
    ShortTermMemoryOldestTurnsDroppedEvent,
    ShortTermMemoryRangeFilledEvent,
    UnknownOutcome,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    ShortTermMemoryStaleBackstoryException,
    ShortTermMemoryUnpairedResultException,
    ShortTermMemoryValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.eventing import AggregateRoot, DomainEvent

ADA = BeingId("being_p1")

_TIME = ObservedTime(display="1日目 朝")


def _observation(
    route: object = SeenOrHeard(), body: str = "ミオが坑道から戻ってきた", order: OccurrenceOrder | None = None
) -> Observation:
    return Observation(
        body=body,
        route=route,
        time=_TIME,
        subject_is_self=isinstance(route, OwnActionResult),
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
        order=order,
    )


def _own_observation(
    call_id: str = "call-1", body: str = "扉は開かなかった", order: OccurrenceOrder | None = None
) -> Observation:
    return _observation(OwnActionResult(call_id=call_id, succeeded=False), body=body, order=order)


def _result(
    call_id: str = "call-1", body: str = "扉は開かなかった", order: OccurrenceOrder | None = None
) -> ObservedOutcome:
    return ObservedOutcome(_own_observation(call_id, body, order))


def _move(call_id: str = "call-1") -> AgentMove:
    return AgentMove(call_id=call_id, tool_name="interact", arguments={"target": "扉"})


def _memory_result(call_id: str = "call-1") -> MemoryOperationOutcome:
    return MemoryOperationOutcome(call_id=call_id, body="[行動] メモを書いた → [結果] メモを追加しました", time=_TIME)


def _at(value: float, environment: str = "廃坑の山村") -> OccurrenceOrder:
    return OccurrenceOrder(environment=environment, value=value)


def _bodies(memory: ShortTermMemory) -> list[str]:
    return [experience.show_to(_BodyReader()) for experience in memory.recent()]


class _BodyReader:
    """出来事の種類ごとに、どのメソッドが呼ばれたかと本文を返す試験用の読み手。"""

    def perceived(self, perception: Perception) -> str:
        return f"見た:{perception.observation.body}"

    def attempted(self, attempt: Attempt, result: Observation) -> str:
        return f"試みた:{attempt.move.call_id}:{result.body}"

    def attempted_memory_operation(self, attempt: Attempt, result: MemoryOperationOutcome) -> str:
        return f"記憶を扱った:{attempt.move.call_id}:{result.body}"

    def attempted_without_result(self, attempt: Attempt) -> str:
        return f"結果の分からない試み:{attempt.move.call_id}"

    def lapsed(self, lapse: Lapse) -> str:
        return f"出せなかった:{lapse.body}"


def _empty() -> ShortTermMemory:
    return ShortTermMemory.empty(ADA)


def _act_and_answer(memory: ShortTermMemory, call_id: str, turn: int) -> None:
    memory.act(_move(call_id), current_turn=turn)
    memory.receive_result(_result(call_id), current_turn=turn)


def _state(memory: ShortTermMemory) -> tuple[object, ...]:
    return (
        memory.experiences,
        memory.backstories,
        memory.recent_from,
        memory.awaiting,
        memory.awaited_backstory,
        memory.get_events(),
    )


class TestPerceive:
    """ShortTermMemory.perceive が、観測を、それを見る次の 1 手の番号で残すことを保証する (design_decisions D1824-5)。"""

    @pytest.mark.parametrize("route", [SeenOrHeard(), ToldOrWritten(), OwnBodyState(), EnvironmentNotice()])
    def test_observation_is_kept_with_the_next_turn(self, route: object) -> None:
        """今のターンが 5 なら、どの経路の観測も番号 6 の Perception として残る。"""
        memory = _empty()
        observation = _observation(route)

        memory.perceive(observation, current_turn=5)

        assert memory.recent() == (Perception(turn=6, observation=observation),)

    def test_own_action_result_cannot_be_perceived(self) -> None:
        """自分の行動の結果を観測として渡すと、1 手と組にできないので ShortTermMemoryValidationException を投げ、短期記憶は変わらない。"""
        memory = _empty()

        with pytest.raises(ShortTermMemoryValidationException):
            memory.perceive(_own_observation(), current_turn=5)
        assert memory.is_empty()


class TestActAndReceiveResult:
    """ShortTermMemory.act と receive_result が、選んだ 1 手と、その結果を組にして残すことを保証する。"""

    def test_result_is_kept_with_the_move_as_an_attempt(self) -> None:
        """今のターン 5 で 1 手を選び、その結果を受け取ると、番号 5 の Attempt として 1 手と結果の組で残り、待っている 1 手は無くなる。"""
        memory = _empty()
        result = _result()

        memory.act(_move(), current_turn=5)
        memory.receive_result(result, current_turn=5)

        assert memory.recent() == (Attempt(turn=5, move=_move(), result=result),)
        assert memory.awaiting is None

    def test_chosen_move_waits_for_its_result(self) -> None:
        """1 手を選ぶと、結果の無い Attempt として、選んだターンの番号で待つ。出来事にはまだ入らない。"""
        memory = _empty()

        memory.act(_move(), current_turn=5)

        assert memory.awaiting == Attempt(turn=5, move=_move())
        assert memory.recent() == ()

    def test_result_without_awaiting_move_is_rejected(self) -> None:
        """待っている 1 手が無いときに結果を受け取ると ShortTermMemoryUnpairedResultException を投げ、短期記憶は変わらない。"""
        memory = _empty()
        memory.perceive(_observation(), current_turn=4)
        before = _state(memory)

        with pytest.raises(ShortTermMemoryUnpairedResultException):
            memory.receive_result(_result(), current_turn=5)
        assert _state(memory) == before

    def test_result_with_another_call_id_is_rejected(self) -> None:
        """呼び出しの ID が待っている 1 手と違う結果を受け取ると ShortTermMemoryUnpairedResultException を投げ、短期記憶は変わらない。"""
        memory = _empty()
        memory.act(_move("call-1"), current_turn=5)
        before = _state(memory)

        with pytest.raises(ShortTermMemoryUnpairedResultException):
            memory.receive_result(_result("call-2"), current_turn=5)
        assert _state(memory) == before

    def test_second_result_for_the_same_move_is_rejected(self) -> None:
        """結果を受け取ったあと、同じ 1 手への 2 件目の結果は、待っている 1 手が無いので ShortTermMemoryUnpairedResultException を投げる。"""
        memory = _empty()
        _act_and_answer(memory, "call-1", 5)

        with pytest.raises(ShortTermMemoryUnpairedResultException):
            memory.receive_result(_result("call-1"), current_turn=5)

    def test_next_move_keeps_the_unanswered_move_as_an_attempt_without_result(self) -> None:
        """結果が来ないまま次の 1 手を選ぶと、前の 1 手は選んだターンの番号で結果の分からない試みとして残り、新しい 1 手が結果を待つ。"""
        memory = _empty()

        memory.act(_move("call-1"), current_turn=5)
        memory.act(_move("call-2"), current_turn=6)

        assert memory.recent() == (Attempt(turn=5, move=_move("call-1")),)
        assert memory.awaiting == Attempt(turn=6, move=_move("call-2"))

    def test_unanswered_move_goes_before_what_its_next_move_will_see(self) -> None:
        """結果の分からない試みは、そのあとに見た (次のターンの番号を持つ) 観測より前に並ぶ。"""
        memory = _empty()

        memory.act(_move("call-1"), current_turn=5)
        memory.perceive(_observation(body="鐘が鳴った"), current_turn=5)
        memory.act(_move("call-2"), current_turn=6)

        assert _bodies(memory) == ["結果の分からない試み:call-1", "見た:鐘が鳴った"]

    def test_memory_operation_result_is_kept_as_an_attempt(self) -> None:
        """記憶の道具の 1 手と、その結果 (MemoryOperationOutcome) も Attempt として組で残る。"""
        memory = _empty()

        memory.act(_move(), current_turn=5)
        memory.receive_result(_memory_result(), current_turn=5)

        assert memory.recent() == (Attempt(turn=5, move=_move(), result=_memory_result()),)

    def test_memory_operation_result_with_another_call_id_is_rejected(self) -> None:
        """記憶の道具の結果でも、呼び出しの ID が待っている 1 手と違えば ShortTermMemoryUnpairedResultException を投げる。"""
        memory = _empty()
        memory.act(_move("call-1"), current_turn=5)

        with pytest.raises(ShortTermMemoryUnpairedResultException):
            memory.receive_result(_memory_result("call-2"), current_turn=5)

    def test_unknown_outcome_answers_no_move(self) -> None:
        """結果の分からない結果 (UnknownOutcome) は、どの 1 手にも答えないので、受け取ると ShortTermMemoryUnpairedResultException を投げる。"""
        memory = _empty()
        memory.act(_move(), current_turn=5)

        with pytest.raises(ShortTermMemoryUnpairedResultException):
            memory.receive_result(UnknownOutcome(), current_turn=5)


class TestOutcome:
    """1 手の結果の型 (Outcome) が、呼び出しの ID に答えるか、起きた順、読む側への渡し方を、種類ごとに自分で持つことを保証する。"""

    def test_observed_outcome_must_be_an_own_action_result(self) -> None:
        """自分の行動の結果ではない観測は、ゲームが返した結果 (ObservedOutcome) として作れない。"""
        with pytest.raises(ShortTermMemoryValidationException):
            ObservedOutcome(_observation(SeenOrHeard()))

    def test_each_outcome_answers_only_its_own_call(self) -> None:
        """ゲームが返した結果と記憶が返した結果は、自分の呼び出しの ID の 1 手にだけ答える。結果の分からない結果は、どの 1 手にも答えない。"""
        assert (_result("call-1").answers("call-1"), _result("call-1").answers("call-2")) == (True, False)
        assert (_memory_result("call-1").answers("call-1"), _memory_result("call-1").answers("call-2")) == (True, False)
        assert UnknownOutcome().answers("call-1") is False

    def test_attempt_without_result_holds_an_unknown_outcome(self) -> None:
        """結果を渡さずに作った試みは、結果の分からない結果を持ち、答えられていない。結果のある試みは答えられている。"""
        assert Attempt(turn=5, move=_move()).result == UnknownOutcome()
        assert Attempt(turn=5, move=_move()).is_answered() is False
        assert Attempt(turn=5, move=_move(), result=_result()).is_answered() is True

    def test_attempt_result_must_be_an_outcome(self) -> None:
        """結果に Outcome でない値 (観測そのものなど) を渡すと ShortTermMemoryValidationException を投げる。"""
        with pytest.raises(ShortTermMemoryValidationException):
            Attempt(turn=5, move=_move(), result=_own_observation())  # type: ignore[arg-type]


class TestFirstMove:
    """1 手の番号は 1 から付くことを、1 手・結果・出せなかったことの受け取りで保証する (design_decisions D1824-5)。"""

    @pytest.mark.parametrize("call", ["act", "receive_result", "lapse"])
    def test_turn_zero_is_rejected(self, call: str) -> None:
        """時計が 0 のまま 1 手、結果、1 手を出せなかったことを受け取ると、範囲の始まり (1) より前の番号になるので ShortTermMemoryValidationException を投げ、短期記憶は変わらない。最初の 1 手で時計は 1 に進むため。"""
        memory = _empty()
        memory.act(_move(), current_turn=1)
        before = _state(memory)

        with pytest.raises(ShortTermMemoryValidationException):
            if call == "act":
                memory.act(_move("call-2"), current_turn=0)
            elif call == "receive_result":
                memory.receive_result(_result(), current_turn=0)
            else:
                memory.lapse(body="迷った", time=_TIME, current_turn=0)
        assert _state(memory) == before


class TestLapse:
    """ShortTermMemory.lapse が、1 手を出せなかったことを今のターンの番号で残すことを保証する。"""

    def test_lapse_is_kept_with_the_current_turn(self) -> None:
        """今のターンが 5 なら、1 手を出せなかったことは番号 5 の Lapse として残る。待っている 1 手は変わらない。"""
        memory = _empty()
        memory.act(_move(), current_turn=4)

        memory.lapse(body="迷って何もしなかった", time=_TIME, current_turn=5)

        assert memory.recent() == (Lapse(turn=5, body="迷って何もしなかった", time=_TIME),)
        assert memory.awaiting == Attempt(turn=4, move=_move())


class TestShowTo:
    """Experience.show_to が、出来事の種類ごとに読み手の対応するメソッドを呼ぶことを保証する。"""

    def test_each_kind_calls_its_own_method(self) -> None:
        """見たこと、結果のある試み、記憶の道具の試み、結果の分からない試み、出せなかったことは、それぞれ別のメソッドで読まれる。"""
        memory = _empty()
        memory.perceive(_observation(body="鐘が鳴った"), current_turn=0)
        _act_and_answer(memory, "call-1", 1)
        memory.act(_move("call-2"), current_turn=2)
        memory.receive_result(_memory_result("call-2"), current_turn=2)
        memory.act(_move("call-3"), current_turn=3)
        memory.lapse(body="迷った", time=_TIME, current_turn=4)
        memory.act(_move("call-5"), current_turn=5)

        assert _bodies(memory) == [
            "見た:鐘が鳴った",
            "試みた:call-1:扉は開かなかった",
            "記憶を扱った:call-2:[行動] メモを書いた → [結果] メモを追加しました",
            "結果の分からない試み:call-3",
            "出せなかった:迷った",
        ]


class TestRecent:
    """ShortTermMemory.recent が、ターンの順に並べ、同じ環境の中では起きた順 (OccurrenceOrder) に並べ直すことを保証する (design_decisions D1824-8)。"""

    def test_same_environment_is_put_in_occurrence_order(self) -> None:
        """自分の 1 手の結果 (番号 5) より前に起きた他人の行動を次のターンで見たとき (番号 6)、起きた順の値で他人の行動が先に並ぶ。"""
        memory = _empty()
        memory.act(_move(), current_turn=5)
        memory.receive_result(_result(body="奪えなかった", order=_at(20.0)), current_turn=5)
        memory.perceive(_observation(body="ゲンが周囲を探索している", order=_at(10.0)), current_turn=5)

        assert _bodies(memory) == ["見た:ゲンが周囲を探索している", "試みた:call-1:奪えなかった"]

    def test_experience_without_order_stays_in_place(self) -> None:
        """起きた順を持たない出来事は位置を動かさず、その前後の起きた順の値は、またいで比べない。"""
        memory = _empty()
        memory.perceive(_observation(body="一つ目", order=_at(30.0)), current_turn=0)
        memory.perceive(_observation(body="順の無い知らせ"), current_turn=0)
        memory.perceive(_observation(body="三つ目", order=_at(10.0)), current_turn=0)

        assert _bodies(memory) == ["見た:一つ目", "見た:順の無い知らせ", "見た:三つ目"]

    def test_orders_of_different_environments_are_not_compared(self) -> None:
        """別の環境の起きた順が隣り合っても比べず、ターンと受け取った順のまま並ぶ。"""
        memory = _empty()
        memory.perceive(_observation(body="村で起きた", order=_at(30.0, "廃坑の山村")), current_turn=0)
        memory.perceive(_observation(body="町で起きた", order=_at(10.0, "水門の町")), current_turn=0)

        assert _bodies(memory) == ["見た:村で起きた", "見た:町で起きた"]

    def test_attempt_without_result_has_no_order(self) -> None:
        """結果の分からない試みは起きた順を持たない。結果のある試みは結果の起きた順を持つ。"""
        assert Attempt(turn=5, move=_move()).order is None
        assert Attempt(turn=5, move=_move(), result=_result(order=_at(1.0))).order == _at(1.0)


def _backstory(until_turn: int, *, written_turn: int | None = None, flow: str = "坑道で鍵を探していた") -> Backstory:
    return Backstory(
        flow=flow, mood="", written_turn=until_turn if written_turn is None else written_turn, until_turn=until_turn
    )


class TestEndTurn:
    """ShortTermMemory.end_turn が、直近の範囲が埋まったこと、いきさつが遅れていること、上限で古いターンを外したことを、起きた事実のドメインイベントとしてためることを保証する (design_decisions D1824-11、D1824-17)。"""

    @staticmethod
    def _one_result_per_turn(last_turn: int) -> ShortTermMemory:
        memory = _empty()
        for turn in range(1, last_turn + 1):
            _act_and_answer(memory, f"call-{turn}", turn)
        return memory

    def test_nothing_happens_before_the_range_is_full(self) -> None:
        """直近の範囲が 19 ターン (ターン 1 から 19) のとき、end_turn は何も変えず、イベントもためない。"""
        memory = self._one_result_per_turn(19)
        before = _state(memory)

        memory.end_turn(turn=19)

        assert _state(memory) == before
        assert memory.awaited_backstory is None

    def test_full_range_is_reported_without_dropping_experiences(self) -> None:
        """直近の範囲が 20 ターンに届くと、ターン 10 までの出来事と今のいきさつを持つ ShortTermMemoryRangeFilledEvent を 1 件ため、ターン 10 までのいきさつを待ち始める。出来事は外さず、範囲の始まりも動かない。"""
        memory = self._one_result_per_turn(20)
        backstory = _backstory(0)
        memory.add_backstory(backstory)
        memory.clear_events()
        experiences = memory.experiences

        memory.end_turn(turn=20)

        (event,) = memory.get_events()
        assert isinstance(event, ShortTermMemoryRangeFilledEvent)
        assert (event.being_id, event.turn, event.until_turn, event.backstories) == (ADA, 20, 10, (backstory,))
        assert event.experiences == experiences[:10]
        assert isinstance(event.event_id, int) and event.occurred_at.tzinfo is timezone.utc
        assert (memory.experiences, memory.recent_from) == (experiences, 1)
        assert memory.awaited_backstory == AwaitedBackstory(until_turn=10, since_turn=20)

    def test_range_filled_is_not_repeated_while_waiting(self) -> None:
        """いきさつを待ち始めてから BACKSTORY_OVERDUE_TURNS 経つまでのあいだは、もう一度 end_turn を呼んでも何もためない。"""
        memory = self._one_result_per_turn(20)
        memory.end_turn(turn=20)
        memory.clear_events()

        memory.end_turn(turn=20 + BACKSTORY_OVERDUE_TURNS - 1)

        assert memory.get_events() == []

    def test_turns_without_experiences_count_toward_the_range(self) -> None:
        """出来事の無いターンも 1 ターンと数える。ターン 1 と 20 にだけ出来事があっても、ターン 20 で範囲が埋まり、ターン 1 の出来事を材料に持つ。"""
        memory = _empty()
        _act_and_answer(memory, "call-1", 1)
        _act_and_answer(memory, "call-20", 20)

        memory.end_turn(turn=20)

        (event,) = memory.get_events()
        assert [e.turn for e in event.experiences] == [1]

    def test_unanswered_move_in_the_range_is_part_of_the_material(self) -> None:
        """ターン 5 に選んだまま結果の来ない 1 手は、結果の分からない試みとして、範囲が埋まったイベントの出来事に入る。"""
        memory = _empty()
        _act_and_answer(memory, "call-1", 1)
        memory.act(_move("call-5"), current_turn=5)
        memory.perceive(_observation(), current_turn=19)

        memory.end_turn(turn=20)

        (event,) = memory.get_events()
        assert event.experiences == (
            Attempt(turn=1, move=_move("call-1"), result=_result("call-1")),
            Attempt(turn=5, move=_move("call-5")),
        )

    def test_material_follows_the_recent_order(self) -> None:
        """範囲が埋まったイベントの出来事は recent() と同じ順。同じ環境で先に起きた他人の行動 (ターン 6) は、自分の 1 手の結果 (ターン 5) より前に並ぶ。"""
        memory = _empty()
        memory.act(_move(), current_turn=5)
        memory.receive_result(_result(body="奪えなかった", order=_at(20.0)), current_turn=5)
        memory.perceive(_observation(body="ゲンが周囲を探索している", order=_at(10.0)), current_turn=5)

        memory.end_turn(turn=20)

        (event,) = memory.get_events()
        assert [e.turn for e in event.experiences] == [6, 5]

    def test_event_tells_the_latest_backstory(self) -> None:
        """範囲が埋まったイベントは、そのとき持っていたいきさつのうち、いちばん新しいもの (範囲の終わりが最も後) を教える。持っていなければ None。"""
        memory = self._one_result_per_turn(20)
        memory.add_backstory(_backstory(0, flow="古い"))
        memory.clear_events()
        memory.end_turn(turn=20)
        (with_backstory,) = memory.get_events()
        assert with_backstory.latest_backstory is not None and with_backstory.latest_backstory.flow == "古い"

        fresh = _empty()
        fresh.end_turn(turn=20)
        (no_backstory,) = fresh.get_events()
        assert no_backstory.latest_backstory is None

    def test_latest_backstory_is_the_newest_of_several(self) -> None:
        """いきさつを 2 つ持って範囲が埋まると、新しい方 (範囲の終わりが後) を教える。"""
        memory = _empty()
        memory.add_backstory(_backstory(0, flow="古い"))
        memory.add_backstory(_backstory(5, flow="新しい"))
        for turn in range(6, 26):
            _act_and_answer(memory, f"call-{turn}", turn)
        memory.clear_events()

        memory.end_turn(turn=25)

        (event,) = memory.get_events()
        assert event.latest_backstory is not None and event.latest_backstory.flow == "新しい"

    def test_backstory_drops_the_turns_it_covers(self) -> None:
        """ターン 10 までのいきさつが届くと、ターン 10 までの出来事が外れ、範囲の始まりがターン 11 になり、いきさつを待つのをやめる。"""
        memory = self._one_result_per_turn(20)
        memory.end_turn(turn=20)

        memory.add_backstory(_backstory(10, written_turn=21))

        assert [e.turn for e in memory.recent()] == list(range(11, 21))
        assert (memory.recent_from, memory.awaited_backstory) == (11, None)

    def test_backstory_also_drops_an_unanswered_move_in_its_range(self) -> None:
        """いきさつが届いたとき、まとめた範囲に選んだまま結果の来ない 1 手があれば一緒に外れ、待っている 1 手は無くなる。そのあと次の 1 手を選べる。"""
        memory = _empty()
        memory.act(_move("call-5"), current_turn=5)
        memory.perceive(_observation(), current_turn=19)
        memory.end_turn(turn=20)

        memory.add_backstory(_backstory(10, written_turn=21))

        assert memory.awaiting is None
        memory.act(_move("call-21"), current_turn=21)
        assert memory.awaiting == Attempt(turn=21, move=_move("call-21"))

    def test_missing_backstory_is_reported_as_overdue_for_the_same_range(self) -> None:
        """待ち始めてから BACKSTORY_OVERDUE_TURNS (10) 経っても届かなければ、同じターン 10 までの出来事を持つ ShortTermMemoryBackstoryOverdueEvent をため、待ち始めたターンを今のターンに進める。"""
        memory = self._one_result_per_turn(20)
        memory.end_turn(turn=20)
        memory.clear_events()

        memory.end_turn(turn=30)

        (event,) = memory.get_events()
        assert isinstance(event, ShortTermMemoryBackstoryOverdueEvent)
        assert (event.turn, event.until_turn, [e.turn for e in event.experiences]) == (30, 10, list(range(1, 11)))
        assert memory.awaited_backstory == AwaitedBackstory(until_turn=10, since_turn=30)

    def test_overdue_is_reported_even_when_end_turn_skips_turns(self) -> None:
        """end_turn を呼ばないターンがあっても、待ち始めてから BACKSTORY_OVERDUE_TURNS 以上経って次に呼ばれたときに、遅れを知らせる。"""
        memory = self._one_result_per_turn(20)
        memory.end_turn(turn=20)
        memory.clear_events()

        memory.end_turn(turn=33)

        (event,) = memory.get_events()
        assert isinstance(event, ShortTermMemoryBackstoryOverdueEvent)
        assert memory.awaited_backstory == AwaitedBackstory(until_turn=10, since_turn=33)

    def test_second_backstory_for_the_same_range_is_refused(self) -> None:
        """同じ範囲のいきさつが 2 つ届くと、2 つ目は ShortTermMemoryStaleBackstoryException で断り、中身もためたイベントも変えない。"""
        memory = self._one_result_per_turn(20)
        memory.end_turn(turn=20)
        memory.add_backstory(_backstory(10, written_turn=21, flow="先に届いた"))
        memory.clear_events()
        before = _state(memory)

        with pytest.raises(ShortTermMemoryStaleBackstoryException):
            memory.add_backstory(_backstory(10, written_turn=22, flow="遅れて届いた"))

        assert _state(memory) == before

    def test_range_at_the_limit_drops_old_turns_without_waiting(self) -> None:
        """直近の範囲が FORCED_FOLD_TURNS (40) に届くと、いきさつを待たずにターン 10 までを外して ShortTermMemoryOldestTurnsDroppedEvent をため、続けてターン 20 までの範囲が埋まったことをためる。"""
        memory = self._one_result_per_turn(40)
        memory.end_turn(turn=20)
        memory.clear_events()

        memory.end_turn(turn=40)

        dropped, filled = memory.get_events()
        assert isinstance(dropped, ShortTermMemoryOldestTurnsDroppedEvent) and isinstance(
            filled, ShortTermMemoryRangeFilledEvent
        )
        assert (dropped.turn, dropped.until_turn, [e.turn for e in dropped.dropped]) == (40, 10, list(range(1, 11)))
        assert memory.recent_from == 11
        assert (filled.until_turn, memory.awaited_backstory) == (20, AwaitedBackstory(until_turn=20, since_turn=40))

    def test_range_just_below_the_limit_keeps_waiting(self) -> None:
        """いきさつを待ったまま範囲が 39 ターンのときは、待ち続け、出来事は外さない。"""
        memory = self._one_result_per_turn(39)
        memory.end_turn(turn=20)
        memory.end_turn(turn=30)
        memory.clear_events()

        memory.end_turn(turn=39)

        assert (memory.get_events(), memory.recent_from) == ([], 1)

    def test_range_reaching_the_limit_without_waiting_drops_then_fills(self) -> None:
        """一度も範囲が埋まったことを知らせないまま 40 ターンに届くと、まずターン 10 までを外し (ShortTermMemoryOldestTurnsDroppedEvent)、続けてターン 20 までの範囲が埋まったことをためる (ShortTermMemoryRangeFilledEvent)。"""
        memory = self._one_result_per_turn(40)

        memory.end_turn(turn=40)

        dropped, filled = memory.get_events()
        assert (type(dropped), dropped.until_turn, type(filled), filled.until_turn) == (
            ShortTermMemoryOldestTurnsDroppedEvent,
            10,
            ShortTermMemoryRangeFilledEvent,
            20,
        )

    def test_backstory_short_of_the_awaited_range_keeps_waiting(self) -> None:
        """待っている範囲 (ターン 10 まで) より手前 (ターン 5 まで) のいきさつが届くと、ターン 5 までは外れるが、待つのはやめない。"""
        memory = self._one_result_per_turn(20)
        memory.end_turn(turn=20)

        memory.add_backstory(_backstory(5, written_turn=21))

        assert memory.recent_from == 6
        assert memory.awaited_backstory == AwaitedBackstory(until_turn=10, since_turn=20)

    def test_late_backstory_after_the_limit_is_added(self) -> None:
        """上限で外したあとに、その範囲 (ターン 10 まで) のいきさつが遅れて届くと入る。出来事はもう外れているので変わらない。"""
        memory = self._one_result_per_turn(40)
        memory.end_turn(turn=40)
        experiences = memory.experiences

        memory.add_backstory(_backstory(10, written_turn=41))

        assert [b.until_turn for b in memory.backstories] == [10]
        assert memory.experiences == experiences

    def test_late_backstory_does_not_move_the_range_back(self) -> None:
        """上限で 2 回外した (範囲の始まりがターン 21) あとに、ターン 10 までのいきさつが遅れて届いても、範囲の始まりは戻らない。"""
        memory = self._one_result_per_turn(50)
        memory.end_turn(turn=40)
        memory.end_turn(turn=50)
        experiences = memory.experiences

        memory.add_backstory(_backstory(10, written_turn=51))

        assert (memory.recent_from, memory.experiences) == (21, experiences)

    def test_memory_waiting_for_a_backstory_is_not_empty(self) -> None:
        """出来事もいきさつも無くても、届くのを待っているいきさつがあれば、空の短期記憶ではない (snapshot に残す)。"""
        assert (
            ShortTermMemory(ADA, awaited_backstory=AwaitedBackstory(until_turn=10, since_turn=20)).is_empty() is False
        )

    def test_turn_counts_follow_the_rules(self) -> None:
        """外す数は直近の範囲より小さく、上限は外す数の 2 回分を待った長さ。遅れを知らせるまでのターンは外す数と同じ。"""
        assert (RECENT_TURNS, FOLD_TURNS, FORCED_FOLD_TURNS, BACKSTORY_OVERDUE_TURNS) == (20, 10, 40, 10)
        assert 0 < FOLD_TURNS < RECENT_TURNS < FORCED_FOLD_TURNS


class TestBackstoryAdded:
    """ShortTermMemory.add_backstory が、いきさつを入れて出来事を外したことを ShortTermMemoryBackstoryAddedEvent としてためることを保証する (design_decisions D1824-17)。"""

    def test_added_backstory_and_dropped_experiences_are_reported(self) -> None:
        """ターン 10 までのいきさつを入れると、入れたいきさつと、外したターン 10 までの出来事を持つイベントを 1 件ためる。"""
        memory = TestEndTurn._one_result_per_turn(20)
        memory.end_turn(turn=20)
        memory.clear_events()
        backstory = _backstory(10, written_turn=21)

        memory.add_backstory(backstory)

        (event,) = memory.get_events()
        assert isinstance(event, ShortTermMemoryBackstoryAddedEvent)
        assert (event.being_id, event.backstory, [e.turn for e in event.dropped]) == (
            ADA,
            backstory,
            list(range(1, 11)),
        )

    def test_truncation_given_with_the_backstory_is_reported(self) -> None:
        """いきさつと一緒に渡した切り詰めた項目と元の長さを、いきさつが入ったイベントに載せる。渡さなければ空。いきさつ自体は持たない。"""
        memory = _empty()

        memory.add_backstory(_backstory(10), truncated={"flow": 310})
        memory.add_backstory(_backstory(20))

        first, second = memory.get_events()
        assert (first.truncated, second.truncated) == ({"flow": 310}, {})

    def test_backstory_for_turns_already_dropped_reports_nothing_dropped(self) -> None:
        """上限で外したあとに遅れて届いたいきさつを入れると、外した出来事の無いイベントをためる。"""
        memory = TestEndTurn._one_result_per_turn(40)
        memory.end_turn(turn=40)
        memory.clear_events()

        memory.add_backstory(_backstory(10, written_turn=41))

        (event,) = memory.get_events()
        assert isinstance(event, ShortTermMemoryBackstoryAddedEvent) and event.dropped == ()


class TestEvents:
    """ShortTermMemory が、ためたイベントをイベント基盤 (eventing) の AggregateRoot の get_events / clear_events で渡すことを保証する。"""

    def test_memory_and_event_are_on_the_eventing_base(self) -> None:
        """短期記憶はイベント基盤の AggregateRoot を継ぎ、ためたイベントは共通の DomainEvent を継ぐ (design_decisions D1837 の 2・3)。"""
        memory = TestEndTurn._one_result_per_turn(20)

        memory.end_turn(turn=20)

        (event,) = memory.get_events()
        assert isinstance(memory, AggregateRoot) and isinstance(event, DomainEvent)

    def test_clear_events_empties_the_pending_events(self) -> None:
        """clear_events() のあとは get_events() が空になり、中身は変わらない。"""
        memory = TestEndTurn._one_result_per_turn(20)
        memory.end_turn(turn=20)
        experiences = memory.experiences

        memory.clear_events()

        assert memory.get_events() == []
        assert memory.experiences == experiences

    def test_get_events_returns_a_copy(self) -> None:
        """get_events() で受け取った並びを変えても、集約がためたイベントは変わらない。"""
        memory = TestEndTurn._one_result_per_turn(20)
        memory.end_turn(turn=20)

        memory.get_events().clear()

        assert len(memory.get_events()) == 1


class TestBackstory:
    """Backstory (ここまでのいきさつ) が、流れ、気分、書いたターン、まとめた範囲の終わりのターンだけを持つ値であることを保証する。"""

    def test_keeps_flow_mood_written_turn_and_until_turn(self) -> None:
        """流れ、気分、書いたターン、まとめた範囲の終わりのターンをそのまま持ち、ほかの項目は持たない。"""
        backstory = Backstory(flow="坑道の奥で鍵を探していた", mood="少し焦っている", written_turn=21, until_turn=10)

        assert (backstory.flow, backstory.mood, backstory.written_turn, backstory.until_turn) == (
            "坑道の奥で鍵を探していた",
            "少し焦っている",
            21,
            10,
        )
        assert set(Backstory.__dataclass_fields__) == {"flow", "mood", "written_turn", "until_turn"}

    def test_empty_mood_is_allowed(self) -> None:
        """気分は空でもよい。流れだけのいきさつを作れる。"""
        assert _backstory(10).mood == ""

    @pytest.mark.parametrize(
        "fields",
        [
            {"flow": " ", "mood": "", "written_turn": 20, "until_turn": 10},
            {"flow": "鍵を探していた", "mood": None, "written_turn": 20, "until_turn": 10},
            {"flow": "鍵を探していた", "mood": "", "written_turn": -1, "until_turn": 10},
            {"flow": "鍵を探していた", "mood": "", "written_turn": 20, "until_turn": -1},
        ],
        ids=["blank-flow", "mood-not-str", "negative-written-turn", "negative-until-turn"],
    )
    def test_invalid_fields_are_rejected(self, fields: dict[str, object]) -> None:
        """流れが空白だけ、気分が str でない、ターンが負のときは拒む。"""
        with pytest.raises(ShortTermMemoryValidationException):
            Backstory(**fields)  # type: ignore[arg-type]


class TestBackstories:
    """ShortTermMemory.add_backstory が、まとめた範囲の順に新しい世代だけ持つことを保証する。"""

    def test_add_backstory_keeps_only_the_newest_generations(self) -> None:
        """いきさつを 4 つ足すと、いちばん古いものが消えて新しい 3 つが範囲の順に残る。"""
        memory = _empty()
        for until_turn in (10, 20, 30, 40):
            memory.add_backstory(_backstory(until_turn))

        assert BACKSTORY_GENERATIONS == 3
        assert [b.until_turn for b in memory.backstories] == [20, 30, 40]

    def test_backstory_for_an_earlier_range_is_refused(self) -> None:
        """いま持っているいきさつより前の範囲までのいきさつは ShortTermMemoryStaleBackstoryException で断り、いきさつもためたイベントも変わらない。"""
        memory = _empty()
        memory.add_backstory(_backstory(20))
        memory.clear_events()

        with pytest.raises(ShortTermMemoryStaleBackstoryException):
            memory.add_backstory(_backstory(10, written_turn=30))

        assert ([b.until_turn for b in memory.backstories], memory.get_events()) == ([20], [])

    def test_non_backstory_is_rejected(self) -> None:
        """いきさつでない値を足そうとすると ShortTermMemoryValidationException を投げる。"""
        with pytest.raises(ShortTermMemoryValidationException):
            _empty().add_backstory("流れ")  # type: ignore[arg-type]


class TestExperienceRules:
    """出来事の型と短期記憶が、作るときに 1 手と結果の組、経路、番号、範囲の決まりを確かめることを保証する。"""

    def test_attempt_result_with_another_call_id_is_rejected(self) -> None:
        """1 手と呼び出しの ID が違う結果を持つ Attempt は作れない。"""
        with pytest.raises(ShortTermMemoryValidationException):
            Attempt(turn=5, move=_move("call-1"), result=_result("call-2"))

    def test_perception_of_an_own_action_result_is_rejected(self) -> None:
        """自分の行動の結果を Perception として作ることはできない。"""
        with pytest.raises(ShortTermMemoryValidationException):
            Perception(turn=5, observation=_own_observation())

    @pytest.mark.parametrize("turn", [-1, True, "3"])
    def test_invalid_turn_is_rejected(self, turn: object) -> None:
        """番号が 0 以上の int でなければ拒む。"""
        with pytest.raises(ShortTermMemoryValidationException):
            Perception(turn=turn, observation=_observation())  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "fields",
        [
            {
                "experiences": (
                    Perception(turn=3, observation=_observation()),
                    Perception(turn=2, observation=_observation()),
                )
            },
            {"experiences": (Perception(turn=3, observation=_observation()),), "recent_from": 4},
            {"recent_from": 0},
            {"awaiting": Attempt(turn=3, move=_move(), result=_result())},
            {"awaiting": Attempt(turn=3, move=_move()), "recent_from": 4},
            {"backstories": tuple(_backstory(t) for t in (10, 20, 30, 40))},
            {"backstories": (_backstory(20), _backstory(10))},
            {"backstories": (_backstory(20), _backstory(20))},
            {"recent_from": 4, "awaited_backstory": AwaitedBackstory(until_turn=2, since_turn=20)},
            {"experiences": [Perception(turn=3, observation=_observation())]},
        ],
        ids=[
            "experiences-out-of-order",
            "experience-before-the-range",
            "range-starts-at-zero",
            "awaiting-with-result",
            "awaiting-before-the-range",
            "too-many-backstories",
            "backstories-out-of-order",
            "backstories-same-range",
            "awaited-backstory-before-the-range",
            "experiences-not-tuple",
        ],
    )
    def test_direct_construction_checks_the_same_rules(self, fields: dict[str, object]) -> None:
        """snapshot から戻すときのように直に作っても、ターンの順、範囲の始まり、待っている 1 手、いきさつの決まりを確かめる。"""
        with pytest.raises(ShortTermMemoryValidationException):
            ShortTermMemory(ADA, **fields)  # type: ignore[arg-type]

    def test_being_id_is_required(self) -> None:
        """持ち主の BeingId でないものを渡すと拒む。"""
        with pytest.raises(ShortTermMemoryValidationException):
            ShortTermMemory("being_p1")  # type: ignore[arg-type]


class TestDroppedOrder:
    """外した出来事を持つイベントが、出来事を recent() と同じ順で持つことを保証する。"""

    @staticmethod
    def _other_before_own_result() -> ShortTermMemory:
        memory = _empty()
        memory.act(_move(), current_turn=5)
        memory.receive_result(_result(body="奪えなかった", order=_at(20.0)), current_turn=5)
        memory.perceive(_observation(body="ゲンが周囲を探索している", order=_at(10.0)), current_turn=5)
        return memory

    def test_oldest_turns_dropped_follow_the_recent_order(self) -> None:
        """上限で外した出来事は、同じ環境で先に起きた他人の行動 (ターン 6) が、自分の 1 手の結果 (ターン 5) より前に並ぶ。"""
        memory = self._other_before_own_result()

        memory.end_turn(turn=40)

        dropped = memory.get_events()[0]
        assert isinstance(dropped, ShortTermMemoryOldestTurnsDroppedEvent)
        assert [e.turn for e in dropped.dropped] == [6, 5]

    def test_backstory_added_dropped_follow_the_recent_order(self) -> None:
        """いきさつが入って外した出来事も、recent() と同じ順に並ぶ。"""
        memory = self._other_before_own_result()

        memory.add_backstory(_backstory(10, written_turn=20))

        (added,) = memory.get_events()
        assert [e.turn for e in added.dropped] == [6, 5]


class TestUnsummarized:
    """ShortTermMemory.unsummarized が、範囲が埋まったときにまとめる材料として渡していない出来事だけを返すことを保証する (環境を離れるときの書き起こし、design_decisions D1824-23)。"""

    def test_all_experiences_before_any_range_fills(self) -> None:
        """範囲がまだ 1 度も埋まっていなければ、すべての出来事を recent() と同じ順で返す。"""
        memory = TestEndTurn._one_result_per_turn(3)

        assert memory.unsummarized() == memory.recent()

    def test_experiences_after_the_awaited_range(self) -> None:
        """範囲が埋まっていきさつを待っているあいだは、待っている範囲 (ターン 10 まで) より後のターン 11 から 21 の出来事だけを返す。"""
        memory = TestEndTurn._one_result_per_turn(20)
        memory.end_turn(turn=20)
        _act_and_answer(memory, "call-21", 21)

        assert [e.turn for e in memory.unsummarized()] == list(range(11, 22))

    def test_experiences_after_the_backstory_arrived(self) -> None:
        """いきさつが届いて範囲を外したあとは、残ったターン 11 から 20 の出来事を全部返す。"""
        memory = TestEndTurn._one_result_per_turn(20)
        memory.end_turn(turn=20)
        memory.add_backstory(_backstory(10, written_turn=20))

        assert [e.turn for e in memory.unsummarized()] == list(range(11, 21))

    def test_awaiting_move_is_included_as_an_attempt_without_result(self) -> None:
        """結果を待っている 1 手も、結果の分からない試みとして末尾に含める。"""
        memory = _empty()
        memory.act(_move("call-1"), current_turn=1)

        (attempt,) = memory.unsummarized()
        assert isinstance(attempt, Attempt) and not attempt.is_answered()

    def test_experiences_after_the_oldest_turns_are_dropped_at_the_limit(self) -> None:
        """いきさつが届かないまま上限 (FORCED_FOLD_TURNS) に届くと、古いターン 1 から 10 を外し、続けて次の範囲 (ターン 20 まで) を待ち始める。返すのは、その範囲より後のターン 21 から 40 の出来事。"""
        memory = TestEndTurn._one_result_per_turn(FORCED_FOLD_TURNS)
        memory.end_turn(turn=20)
        memory.end_turn(turn=FORCED_FOLD_TURNS)

        assert (memory.recent_from, memory.awaited_backstory) == (
            11,
            AwaitedBackstory(until_turn=20, since_turn=FORCED_FOLD_TURNS),
        )
        assert [e.turn for e in memory.unsummarized()] == list(range(21, FORCED_FOLD_TURNS + 1))

    def test_boundary_does_not_move_when_the_backstory_is_overdue(self) -> None:
        """いきさつが遅れて待ち直しても、待っている範囲 (ターン 10 まで) は変わらず、返すのはターン 11 からの出来事のまま。"""
        memory = TestEndTurn._one_result_per_turn(20 + BACKSTORY_OVERDUE_TURNS)
        memory.end_turn(turn=20)
        memory.end_turn(turn=20 + BACKSTORY_OVERDUE_TURNS)

        assert memory.awaited_backstory == AwaitedBackstory(until_turn=10, since_turn=20 + BACKSTORY_OVERDUE_TURNS)
        assert [e.turn for e in memory.unsummarized()] == list(range(11, 20 + BACKSTORY_OVERDUE_TURNS + 1))

    def test_awaiting_move_inside_the_awaited_range_is_left_out(self) -> None:
        """待っている範囲 (ターン 10 まで) の中で選んだまま結果の来ない 1 手は、範囲の材料に入っているので返さない。"""
        memory = TestEndTurn._one_result_per_turn(9)
        memory.act(_move("call-10"), current_turn=10)
        for turn in range(11, 21):
            memory.perceive(_observation(SeenOrHeard(), body=f"ターン {turn} の出来事"), current_turn=turn - 1)
        memory.end_turn(turn=20)

        unsummarized = memory.unsummarized()
        assert all(e.turn > 10 for e in unsummarized)
        assert not any(isinstance(e, Attempt) for e in unsummarized)

    def test_asking_changes_nothing(self) -> None:
        """問い合わせても、中身もためたイベントも変わらない。"""
        memory = TestEndTurn._one_result_per_turn(20)
        memory.end_turn(turn=20)
        before = _state(memory)

        memory.unsummarized()

        assert _state(memory) == before
