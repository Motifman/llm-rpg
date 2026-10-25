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
    BACKSTORY_RETRY_TURNS,
    FOLD_TURNS,
    FORCED_FOLD_TURNS,
    RECENT_TURNS,
    Attempt,
    Backstory,
    BackstoryRequest,
    BackstoryRequestedAgain,
    FoldForced,
    FoldRequested,
    Lapse,
    MemoryOperationOutcome,
    ObservedOutcome,
    Perception,
    ShortTermMemory,
    StaleBackstoryDiscarded,
    UnknownOutcome,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
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


def _own_observation(call_id: str = "call-1", body: str = "扉は開かなかった", order: OccurrenceOrder | None = None) -> Observation:
    return _observation(OwnActionResult(call_id=call_id, succeeded=False), body=body, order=order)


def _result(call_id: str = "call-1", body: str = "扉は開かなかった", order: OccurrenceOrder | None = None) -> ObservedOutcome:
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
    return (memory.experiences, memory.backstories, memory.recent_from, memory.awaiting, memory.request, memory.get_events())


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
    return Backstory(flow=flow, mood="", written_turn=until_turn if written_turn is None else written_turn, until_turn=until_turn)


class TestFold:
    """ShortTermMemory.fold が、直近の範囲が満ちたらいきさつを頼み、届かなければ頼み直し、上限に届いたら待たずに外すことを保証する (design_decisions D1824-11)。"""

    @staticmethod
    def _one_result_per_turn(last_turn: int) -> ShortTermMemory:
        memory = _empty()
        for turn in range(1, last_turn + 1):
            _act_and_answer(memory, f"call-{turn}", turn)
        return memory

    def test_nothing_happens_before_the_range_is_full(self) -> None:
        """直近の範囲が 19 ターン (ターン 1 から 19) のとき、fold は何も頼まず、イベントもためない。"""
        memory = self._one_result_per_turn(19)
        before = _state(memory)

        memory.fold(current_turn=19)

        assert _state(memory) == before
        assert memory.request is None

    def test_full_range_requests_a_backstory_without_dropping_experiences(self) -> None:
        """直近の範囲が 20 ターンに届くと、ターン 10 までのいきさつを頼む FoldRequested を 1 件ためる。出来事は外さず、範囲の始まりも動かない。"""
        memory = self._one_result_per_turn(20)
        backstory = _backstory(0)
        memory.add_backstory(backstory)
        experiences = memory.experiences

        memory.fold(current_turn=20)

        (event,) = memory.get_events()
        assert isinstance(event, FoldRequested)
        assert (event.being_id, event.turn, event.until_turn, event.backstories) == (ADA, 20, 10, (backstory,))
        assert event.experiences == experiences[:10]
        assert isinstance(event.event_id, int) and event.occurred_at.tzinfo is timezone.utc
        assert (memory.experiences, memory.recent_from) == (experiences, 1)
        assert memory.request == BackstoryRequest(until_turn=10, requested_turn=20)

    def test_request_is_not_repeated_while_waiting(self) -> None:
        """頼んだあと、頼み直すまでのターン (BACKSTORY_RETRY_TURNS) のあいだは、もう一度 fold を呼んでも何もためない。"""
        memory = self._one_result_per_turn(20)
        memory.fold(current_turn=20)
        memory.clear_events()

        memory.fold(current_turn=20 + BACKSTORY_RETRY_TURNS - 1)

        assert memory.get_events() == []

    def test_turns_without_experiences_count_toward_the_range(self) -> None:
        """出来事の無いターンも 1 ターンと数える。ターン 1 と 20 にだけ出来事があっても、ターン 20 で範囲が満ち、ターン 1 の出来事をまとめるよう頼む。"""
        memory = _empty()
        _act_and_answer(memory, "call-1", 1)
        _act_and_answer(memory, "call-20", 20)

        memory.fold(current_turn=20)

        (event,) = memory.get_events()
        assert [e.turn for e in event.experiences] == [1]

    def test_unanswered_move_in_the_range_is_part_of_the_request(self) -> None:
        """ターン 5 に選んだまま結果の来ない 1 手は、結果の分からない試みとして、頼む出来事に入る。"""
        memory = _empty()
        _act_and_answer(memory, "call-1", 1)
        memory.act(_move("call-5"), current_turn=5)
        memory.perceive(_observation(), current_turn=19)

        memory.fold(current_turn=20)

        (event,) = memory.get_events()
        assert event.experiences == (
            Attempt(turn=1, move=_move("call-1"), result=_result("call-1")),
            Attempt(turn=5, move=_move("call-5")),
        )

    def test_requested_experiences_follow_the_recent_order(self) -> None:
        """頼む出来事は recent() と同じ順。同じ環境で先に起きた他人の行動 (ターン 6) は、自分の 1 手の結果 (ターン 5) より前に並ぶ。"""
        memory = _empty()
        memory.act(_move(), current_turn=5)
        memory.receive_result(_result(body="奪えなかった", order=_at(20.0)), current_turn=5)
        memory.perceive(_observation(body="ゲンが周囲を探索している", order=_at(10.0)), current_turn=5)

        memory.fold(current_turn=20)

        (event,) = memory.get_events()
        assert [e.turn for e in event.experiences] == [6, 5]

    def test_request_tells_the_latest_backstory(self) -> None:
        """頼みごとのイベントは、頼んだときに持っていたいきさつのうち、いちばん新しいもの (範囲の終わりが最も後) を教える。持っていなければ None。"""
        memory = self._one_result_per_turn(20)
        memory.add_backstory(_backstory(0, flow="古い"))
        memory.fold(current_turn=20)
        (with_backstory,) = memory.get_events()
        assert with_backstory.latest_backstory is not None and with_backstory.latest_backstory.flow == "古い"

        fresh = _empty()
        fresh.fold(current_turn=20)
        (no_backstory,) = fresh.get_events()
        assert no_backstory.latest_backstory is None

    def test_latest_backstory_is_the_newest_of_several(self) -> None:
        """いきさつを 2 つ持って頼むと、新しい方 (範囲の終わりが後) を教える。"""
        memory = _empty()
        memory.add_backstory(_backstory(0, flow="古い"))
        memory.add_backstory(_backstory(5, flow="新しい"))
        for turn in range(6, 26):
            _act_and_answer(memory, f"call-{turn}", turn)

        memory.fold(current_turn=25)

        (event,) = memory.get_events()
        assert event.latest_backstory is not None and event.latest_backstory.flow == "新しい"

    def test_backstory_drops_the_turns_it_covers(self) -> None:
        """ターン 10 までのいきさつが届くと、ターン 10 までの出来事が外れ、範囲の始まりがターン 11 になり、頼みごとは済む。"""
        memory = self._one_result_per_turn(20)
        memory.fold(current_turn=20)

        memory.add_backstory(_backstory(10, written_turn=21))

        assert [e.turn for e in memory.recent()] == list(range(11, 21))
        assert (memory.recent_from, memory.request) == (11, None)

    def test_backstory_also_drops_an_unanswered_move_in_its_range(self) -> None:
        """いきさつが届いたとき、まとめた範囲に選んだまま結果の来ない 1 手があれば一緒に外れ、待っている 1 手は無くなる。そのあと次の 1 手を選べる。"""
        memory = _empty()
        memory.act(_move("call-5"), current_turn=5)
        memory.perceive(_observation(), current_turn=19)
        memory.fold(current_turn=20)

        memory.add_backstory(_backstory(10, written_turn=21))

        assert memory.awaiting is None
        memory.act(_move("call-21"), current_turn=21)
        assert memory.awaiting == Attempt(turn=21, move=_move("call-21"))

    def test_missing_backstory_is_requested_again_for_the_same_range(self) -> None:
        """頼んでから BACKSTORY_RETRY_TURNS (10) 過ぎても届かなければ、同じターン 10 までのいきさつを頼み直す BackstoryRequestedAgain をためる。"""
        memory = self._one_result_per_turn(20)
        memory.fold(current_turn=20)
        memory.clear_events()

        memory.fold(current_turn=30)

        (event,) = memory.get_events()
        assert isinstance(event, BackstoryRequestedAgain)
        assert (event.turn, event.until_turn, [e.turn for e in event.experiences]) == (30, 10, list(range(1, 11)))
        assert memory.request == BackstoryRequest(until_turn=10, requested_turn=30)

    def test_second_backstory_for_the_same_range_is_discarded(self) -> None:
        """同じ範囲のいきさつが 2 つ届くと、2 つ目は入れず、StaleBackstoryDiscarded をためる。"""
        memory = self._one_result_per_turn(20)
        memory.fold(current_turn=20)
        memory.add_backstory(_backstory(10, written_turn=21, flow="先に届いた"))
        memory.clear_events()

        memory.add_backstory(_backstory(10, written_turn=22, flow="遅れて届いた"))

        assert [b.flow for b in memory.backstories] == ["先に届いた"]
        (event,) = memory.get_events()
        assert isinstance(event, StaleBackstoryDiscarded)
        assert (event.backstory.flow, event.latest_until_turn) == ("遅れて届いた", 10)

    def test_range_at_the_limit_drops_old_turns_without_waiting(self) -> None:
        """直近の範囲が FORCED_FOLD_TURNS (40) に届くと、いきさつを待たずにターン 10 までを外して FoldForced をため、続けてターン 20 までのいきさつを頼む。"""
        memory = self._one_result_per_turn(40)
        memory.fold(current_turn=20)
        memory.clear_events()

        memory.fold(current_turn=40)

        forced, requested = memory.get_events()
        assert isinstance(forced, FoldForced) and isinstance(requested, FoldRequested)
        assert (forced.until_turn, [e.turn for e in forced.dropped]) == (10, list(range(1, 11)))
        assert memory.recent_from == 11
        assert (requested.until_turn, memory.request) == (20, BackstoryRequest(until_turn=20, requested_turn=40))

    def test_range_just_below_the_limit_keeps_waiting(self) -> None:
        """頼んだまま範囲が 39 ターンのときは、いきさつを待ち続け、出来事は外さない。"""
        memory = self._one_result_per_turn(39)
        memory.fold(current_turn=20)
        memory.fold(current_turn=30)
        memory.clear_events()

        memory.fold(current_turn=39)

        assert (memory.get_events(), memory.recent_from) == ([], 1)

    def test_range_reaching_the_limit_without_a_request_drops_then_requests(self) -> None:
        """一度も頼まないまま範囲が 40 ターンに届くと、まずターン 10 までを外し (FoldForced)、続けてターン 20 までを頼む (FoldRequested)。"""
        memory = self._one_result_per_turn(40)

        memory.fold(current_turn=40)

        forced, requested = memory.get_events()
        assert (type(forced), forced.until_turn, type(requested), requested.until_turn) == (FoldForced, 10, FoldRequested, 20)

    def test_backstory_short_of_the_request_keeps_the_request(self) -> None:
        """頼んだ範囲 (ターン 10 まで) より手前 (ターン 5 まで) のいきさつが届くと、ターン 5 までは外れるが、頼みごとは済まない。"""
        memory = self._one_result_per_turn(20)
        memory.fold(current_turn=20)

        memory.add_backstory(_backstory(5, written_turn=21))

        assert memory.recent_from == 6
        assert memory.request == BackstoryRequest(until_turn=10, requested_turn=20)

    def test_late_backstory_after_the_limit_is_added(self) -> None:
        """上限で外したあとに、その範囲 (ターン 10 まで) のいきさつが遅れて届くと入る。出来事はもう外れているので変わらない。"""
        memory = self._one_result_per_turn(40)
        memory.fold(current_turn=40)
        experiences = memory.experiences

        memory.add_backstory(_backstory(10, written_turn=41))

        assert [b.until_turn for b in memory.backstories] == [10]
        assert memory.experiences == experiences

    def test_late_backstory_does_not_move_the_range_back(self) -> None:
        """上限で 2 回外した (範囲の始まりがターン 21) あとに、ターン 10 までのいきさつが遅れて届いても、範囲の始まりは戻らない。"""
        memory = self._one_result_per_turn(50)
        memory.fold(current_turn=40)
        memory.fold(current_turn=50)
        experiences = memory.experiences

        memory.add_backstory(_backstory(10, written_turn=51))

        assert (memory.recent_from, memory.experiences) == (21, experiences)

    def test_memory_waiting_for_a_backstory_is_not_empty(self) -> None:
        """出来事もいきさつも無くても、届くのを待っている頼みごとがあれば、空の短期記憶ではない (snapshot に残す)。"""
        assert ShortTermMemory(ADA, request=BackstoryRequest(until_turn=10, requested_turn=20)).is_empty() is False

    def test_turn_counts_follow_the_rules(self) -> None:
        """外す数は直近の範囲より小さく、上限は外す数の 2 回分を待った長さ。頼み直すまでのターンは外す数と同じ。"""
        assert (RECENT_TURNS, FOLD_TURNS, FORCED_FOLD_TURNS, BACKSTORY_RETRY_TURNS) == (20, 10, 40, 10)
        assert 0 < FOLD_TURNS < RECENT_TURNS < FORCED_FOLD_TURNS


class TestEvents:
    """ShortTermMemory が、ためたイベントをイベント基盤 (eventing) の AggregateRoot の get_events / clear_events で渡すことを保証する。"""

    def test_memory_and_event_are_on_the_eventing_base(self) -> None:
        """短期記憶はイベント基盤の AggregateRoot を継ぎ、ためたイベントは共通の DomainEvent を継ぐ (design_decisions D1837 の 2・3)。"""
        memory = TestFold._one_result_per_turn(20)

        memory.fold(current_turn=20)

        (event,) = memory.get_events()
        assert isinstance(memory, AggregateRoot) and isinstance(event, DomainEvent)

    def test_clear_events_empties_the_pending_events(self) -> None:
        """clear_events() のあとは get_events() が空になり、中身は変わらない。"""
        memory = TestFold._one_result_per_turn(20)
        memory.fold(current_turn=20)
        experiences = memory.experiences

        memory.clear_events()

        assert memory.get_events() == []
        assert memory.experiences == experiences

    def test_get_events_returns_a_copy(self) -> None:
        """get_events() で受け取った並びを変えても、集約がためたイベントは変わらない。"""
        memory = TestFold._one_result_per_turn(20)
        memory.fold(current_turn=20)

        memory.get_events().clear()

        assert len(memory.get_events()) == 1


class TestBackstory:
    """Backstory (ここまでのいきさつ) が、流れ、気分、書いたターン、まとめた範囲の終わりのターンだけを持つ値であることを保証する。"""

    def test_keeps_flow_mood_written_turn_and_until_turn(self) -> None:
        """流れ、気分、書いたターン、まとめた範囲の終わりのターンをそのまま持ち、ほかの項目は持たない。"""
        backstory = Backstory(flow="坑道の奥で鍵を探していた", mood="少し焦っている", written_turn=21, until_turn=10)

        assert (backstory.flow, backstory.mood, backstory.written_turn, backstory.until_turn) == ("坑道の奥で鍵を探していた", "少し焦っている", 21, 10)
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

    def test_backstory_for_an_earlier_range_is_discarded(self) -> None:
        """いま持っているいきさつより前の範囲までのいきさつは入れず、StaleBackstoryDiscarded をためる。いきさつは変わらない。"""
        memory = _empty()
        memory.add_backstory(_backstory(20))

        memory.add_backstory(_backstory(10, written_turn=30))

        assert [b.until_turn for b in memory.backstories] == [20]
        (event,) = memory.get_events()
        assert isinstance(event, StaleBackstoryDiscarded)

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
            {"experiences": (Perception(turn=3, observation=_observation()), Perception(turn=2, observation=_observation()))},
            {"experiences": (Perception(turn=3, observation=_observation()),), "recent_from": 4},
            {"recent_from": 0},
            {"awaiting": Attempt(turn=3, move=_move(), result=_result())},
            {"awaiting": Attempt(turn=3, move=_move()), "recent_from": 4},
            {"backstories": tuple(_backstory(t) for t in (10, 20, 30, 40))},
            {"backstories": (_backstory(20), _backstory(10))},
            {"backstories": (_backstory(20), _backstory(20))},
            {"recent_from": 4, "request": BackstoryRequest(until_turn=2, requested_turn=20)},
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
            "request-before-the-range",
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
