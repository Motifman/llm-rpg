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
    FOLD_TURNS,
    RECENT_TURNS,
    Attempt,
    Backstory,
    ExperiencesFolded,
    Lapse,
    MemoryOperationResult,
    Perception,
    ShortTermMemory,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    ShortTermMemoryUnpairedResultException,
    ShortTermMemoryValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

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


def _result(call_id: str = "call-1", body: str = "扉は開かなかった", order: OccurrenceOrder | None = None) -> Observation:
    return _observation(OwnActionResult(call_id=call_id, succeeded=False), body=body, order=order)


def _move(call_id: str = "call-1") -> AgentMove:
    return AgentMove(call_id=call_id, tool_name="interact", arguments={"target": "扉"})


def _memory_result(call_id: str = "call-1") -> MemoryOperationResult:
    return MemoryOperationResult(call_id=call_id, body="[行動] メモを書いた → [結果] メモを追加しました", time=_TIME)


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

    def attempted_memory_operation(self, attempt: Attempt, result: MemoryOperationResult) -> str:
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
    return (memory.experiences, memory.backstories, memory.recent_from, memory.awaiting, memory.get_events())


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
            memory.perceive(_result(), current_turn=5)
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
        """記憶の道具の 1 手と、その結果 (MemoryOperationResult) も Attempt として組で残る。"""
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

    def test_observation_from_another_route_is_not_a_result(self) -> None:
        """自分の行動の結果ではない観測を結果として渡すと ShortTermMemoryValidationException を投げる。"""
        memory = _empty()
        memory.act(_move(), current_turn=5)

        with pytest.raises(ShortTermMemoryValidationException):
            memory.receive_result(_observation(SeenOrHeard()), current_turn=5)


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


class TestFold:
    """ShortTermMemory.fold が、直近の範囲が満ちたときに古いターンの出来事を外し、「出来事を外した」イベントをためることを保証する。"""

    @staticmethod
    def _one_result_per_turn(last_turn: int) -> ShortTermMemory:
        memory = _empty()
        for turn in range(1, last_turn + 1):
            _act_and_answer(memory, f"call-{turn}", turn)
        return memory

    def test_nothing_is_folded_before_the_range_is_full(self) -> None:
        """直近の範囲が 19 ターン (ターン 1 から 19) のとき、fold は何も外さず、イベントもためない。"""
        memory = self._one_result_per_turn(19)
        before = _state(memory)

        memory.fold(current_turn=19)

        assert _state(memory) == before
        assert memory.get_events() == []

    def test_oldest_turns_are_folded_when_the_range_is_full(self) -> None:
        """直近の範囲が 20 ターンのとき、fold はターン 1 から 10 の出来事を外し、範囲の始まりのターンが 10 進み、外した出来事とそのときのいきさつを持つイベントを 1 件ためる。"""
        memory = self._one_result_per_turn(20)
        backstory = Backstory(flow="坑道で鍵を探していた", mood="", written_turn=0)
        memory.add_backstory(backstory)
        folded = memory.experiences[:10]

        memory.fold(current_turn=20)

        assert [e.turn for e in memory.recent()] == list(range(11, 21))
        assert memory.recent_from == 11
        (event,) = memory.get_events()
        assert isinstance(event, ExperiencesFolded)
        assert (event.being_id, event.turn, event.folded, event.backstories) == (ADA, 20, folded, (backstory,))
        assert isinstance(event.event_id, int) and event.occurred_at.tzinfo is timezone.utc
        assert [e.turn for e in folded] == list(range(1, 11))

    def test_turns_without_experiences_count_toward_the_range(self) -> None:
        """出来事の無いターンも 1 ターンと数える。ターン 1 と 20 にだけ出来事があっても、ターン 20 で範囲が満ち、ターン 1 の出来事が外れる。"""
        memory = _empty()
        _act_and_answer(memory, "call-1", 1)
        _act_and_answer(memory, "call-20", 20)

        memory.fold(current_turn=20)

        (event,) = memory.get_events()
        assert [e.turn for e in event.folded] == [1]

    def test_unanswered_move_in_the_folded_turns_is_folded_as_an_attempt_without_result(self) -> None:
        """ターン 5 に選んだまま結果の来ない 1 手は、ターン 20 の fold でターン 5 の結果の分からない試みとして外れてイベントに入り、待っている 1 手は無くなる。そのあと次の 1 手を選べる。"""
        memory = _empty()
        _act_and_answer(memory, "call-1", 1)
        memory.act(_move("call-5"), current_turn=5)
        memory.perceive(_observation(), current_turn=19)

        memory.fold(current_turn=20)

        (event,) = memory.get_events()
        assert event.folded == (
            Attempt(turn=1, move=_move("call-1"), result=_result("call-1")),
            Attempt(turn=5, move=_move("call-5")),
        )
        assert memory.awaiting is None
        memory.act(_move("call-21"), current_turn=21)
        assert memory.awaiting == Attempt(turn=21, move=_move("call-21"))

    def test_full_range_without_old_experiences_moves_the_range_without_event(self) -> None:
        """範囲が満ちても外すターンに出来事が無ければ、範囲の始まりだけが 10 進み、イベントはためない。"""
        memory = _empty()
        _act_and_answer(memory, "call-15", 15)

        memory.fold(current_turn=20)

        assert (memory.recent_from, len(memory.experiences), memory.get_events()) == (11, 1, [])

    def test_fold_count_is_smaller_than_the_range(self) -> None:
        """一度に外すターン数は、直近として持つターン数より小さい。等しいと直近の出来事が空になる。"""
        assert (RECENT_TURNS, FOLD_TURNS) == (20, 10)
        assert 0 < FOLD_TURNS < RECENT_TURNS


class TestEvents:
    """ShortTermMemory が、ためたイベントをゲームの集約と同じ口 (get_events / clear_events) で渡すことを保証する。"""

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
    """Backstory (ここまでのいきさつ) が、流れと気分の 2 つだけを持つ値であることを保証する。"""

    def test_keeps_flow_mood_and_written_turn(self) -> None:
        """流れ、気分、書いた手番をそのまま持ち、ほかの項目は持たない。"""
        backstory = Backstory(flow="坑道の奥で鍵を探していた", mood="少し焦っている", written_turn=20)

        assert (backstory.flow, backstory.mood, backstory.written_turn) == ("坑道の奥で鍵を探していた", "少し焦っている", 20)
        assert set(Backstory.__dataclass_fields__) == {"flow", "mood", "written_turn"}

    def test_empty_mood_is_allowed(self) -> None:
        """気分は空でもよい。流れだけのいきさつを作れる。"""
        assert Backstory(flow="鍵を探していた", mood="", written_turn=20).mood == ""

    @pytest.mark.parametrize(
        "fields",
        [
            {"flow": " ", "mood": "", "written_turn": 20},
            {"flow": "鍵を探していた", "mood": None, "written_turn": 20},
            {"flow": "鍵を探していた", "mood": "", "written_turn": -1},
        ],
        ids=["blank-flow", "mood-not-str", "negative-turn"],
    )
    def test_invalid_fields_are_rejected(self, fields: dict[str, object]) -> None:
        """流れが空白だけ、気分が str でない、書いた手番が負のときは拒む。"""
        with pytest.raises(ShortTermMemoryValidationException):
            Backstory(**fields)  # type: ignore[arg-type]


class TestBackstories:
    """ShortTermMemory.add_backstory が、いきさつを書いた順に新しい世代だけ持つことを保証する。"""

    def test_add_backstory_keeps_only_the_newest_generations(self) -> None:
        """いきさつを 4 つ足すと、いちばん古いものが消えて新しい 3 つが書いた順に残る。"""
        memory = _empty()
        for turn in (10, 20, 30, 40):
            memory.add_backstory(Backstory(flow=f"{turn} 手番までの流れ", mood="", written_turn=turn))

        assert BACKSTORY_GENERATIONS == 3
        assert [b.written_turn for b in memory.backstories] == [20, 30, 40]

    def test_add_backstory_rejects_an_older_written_turn(self) -> None:
        """前のいきさつより前の手番に書いたいきさつを足すと拒み、いきさつは変わらない。"""
        memory = _empty()
        memory.add_backstory(Backstory(flow="流れ", mood="", written_turn=20))

        with pytest.raises(ShortTermMemoryValidationException):
            memory.add_backstory(Backstory(flow="流れ", mood="", written_turn=10))
        assert [b.written_turn for b in memory.backstories] == [20]


class TestExperienceRules:
    """出来事の型と短期記憶が、作るときに 1 手と結果の組、経路、番号、範囲の決まりを確かめることを保証する。"""

    def test_attempt_result_with_another_call_id_is_rejected(self) -> None:
        """1 手と呼び出しの ID が違う結果を持つ Attempt は作れない。"""
        with pytest.raises(ShortTermMemoryValidationException):
            Attempt(turn=5, move=_move("call-1"), result=_result("call-2"))

    def test_perception_of_an_own_action_result_is_rejected(self) -> None:
        """自分の行動の結果を Perception として作ることはできない。"""
        with pytest.raises(ShortTermMemoryValidationException):
            Perception(turn=5, observation=_result())

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
            {"backstories": tuple(Backstory(flow="流れ", mood="", written_turn=t) for t in (10, 20, 30, 40))},
            {"backstories": (Backstory(flow="流れ", mood="", written_turn=20), Backstory(flow="流れ", mood="", written_turn=10))},
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
