from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import (
    UNKNOWN,
    AgentMove,
    EnvironmentNotice,
    Observation,
    ObservedTime,
    OwnActionResult,
    OwnBodyState,
    SeenOrHeard,
    ToldOrWritten,
)
from ai_rpg_world.being.domain.short_term_memory import (
    BACKSTORY_GENERATIONS,
    Backstory,
    RememberedEvent,
    ShortTermMemory,
    turn_for_event,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    ShortTermMemoryValidationException,
)


def _observation(route: object = SeenOrHeard(), body: str = "ミオが坑道から戻ってきた") -> Observation:
    return Observation(
        body=body,
        route=route,
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=isinstance(route, OwnActionResult),
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


def _move(call_id: str = "call-1") -> AgentMove:
    return AgentMove(call_id=call_id, tool_name="speak", arguments={"text": "おはよう"})


class TestTurnForEvent:
    """turn_for_event が、出来事を受け取った経路と時計の値から、出来事の手番の番号を決める規則 (design_decisions D1824-5) を保証する。"""

    @pytest.mark.parametrize(
        ("route", "current_turn", "expected"),
        [
            (SeenOrHeard(), 0, 1),
            (SeenOrHeard(), 4, 5),
            (ToldOrWritten(), 4, 5),
            (OwnBodyState(), 4, 5),
            (EnvironmentNotice(), 4, 5),
            (OwnActionResult(call_id="call-1", succeeded=True), 5, 5),
            (OwnActionResult(call_id="call-1", succeeded=False), 1, 1),
        ],
        ids=[
            "seen-before-first-move",
            "seen",
            "told",
            "own-body",
            "environment-notice",
            "own-result-succeeded",
            "own-result-failed-first-move",
        ],
    )
    def test_number_follows_the_table(self, route: object, current_turn: int, expected: int) -> None:
        """自分の行動の結果は時計の値のまま、それ以外の経路は時計の値に 1 を足した番号になる。"""
        assert turn_for_event(route, current_turn=current_turn) == expected

    def test_own_result_before_any_move_is_rejected(self) -> None:
        """時計が 0 のまま自分の行動の結果が届くと、結果を生んだ手が無いので ShortTermMemoryValidationException を投げる。"""
        with pytest.raises(ShortTermMemoryValidationException):
            turn_for_event(OwnActionResult(call_id="call-1", succeeded=True), current_turn=0)

    @pytest.mark.parametrize("current_turn", [-1, True, 1.0])
    def test_invalid_clock_value_is_rejected(self, current_turn: object) -> None:
        """時計の値が 0 以上の int でなければ ShortTermMemoryValidationException を投げる。"""
        with pytest.raises(ShortTermMemoryValidationException):
            turn_for_event(SeenOrHeard(), current_turn=current_turn)  # type: ignore[arg-type]


class TestRememberedEvent:
    """RememberedEvent が、自分の行動の結果と、それを生んだ 1 手との対を守ることを保証する。"""

    def test_own_result_keeps_the_move_with_the_same_call_id(self) -> None:
        """自分の行動の結果に、同じ call_id の 1 手を添えると、両方をそのまま持つ。"""
        observation = _observation(OwnActionResult(call_id="call-1", succeeded=True))
        move = _move("call-1")

        event = RememberedEvent(turn=3, observation=observation, move=move)

        assert (event.turn, event.observation, event.move) == (3, observation, move)

    def test_own_result_without_move_is_rejected(self) -> None:
        """自分の行動の結果に 1 手が添えられていなければ、何をした結果か分からないので拒む。"""
        with pytest.raises(ShortTermMemoryValidationException):
            RememberedEvent(turn=3, observation=_observation(OwnActionResult(call_id="call-1", succeeded=True)))

    def test_move_with_other_call_id_is_rejected(self) -> None:
        """添えた 1 手の call_id が結果の call_id と違えば拒む。"""
        with pytest.raises(ShortTermMemoryValidationException):
            RememberedEvent(
                turn=3,
                observation=_observation(OwnActionResult(call_id="call-1", succeeded=True)),
                move=_move("call-2"),
            )

    def test_move_on_other_route_is_rejected(self) -> None:
        """自分の行動の結果ではない観測に 1 手を添えると拒む。"""
        with pytest.raises(ShortTermMemoryValidationException):
            RememberedEvent(turn=3, observation=_observation(SeenOrHeard()), move=_move())

    @pytest.mark.parametrize("turn", [-1, True, "3"])
    def test_invalid_turn_is_rejected(self, turn: object) -> None:
        """手番の番号が 0 以上の int でなければ拒む。"""
        with pytest.raises(ShortTermMemoryValidationException):
            RememberedEvent(turn=turn, observation=_observation())  # type: ignore[arg-type]


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


class TestShortTermMemory:
    """ShortTermMemory が、出来事を手番の順に、いきさつを新しい順に上限まで持つことを保証する。"""

    def test_empty_has_no_events_and_no_backstories(self) -> None:
        """空の短期記憶は、出来事もいきさつも持たない。"""
        memory = ShortTermMemory.empty()

        assert (memory.events, memory.backstories) == ((), ())

    def test_remember_appends_in_turn_order(self) -> None:
        """同じ手番か後の手番の出来事は、受け取った順に後ろへ足す。"""
        first = RememberedEvent(turn=2, observation=_observation(body="一つ目"))
        second = RememberedEvent(turn=2, observation=_observation(body="二つ目"))
        third = RememberedEvent(turn=3, observation=_observation(body="三つ目"))

        memory = ShortTermMemory.empty().remember(first).remember(second).remember(third)

        assert memory.events == (first, second, third)

    def test_remember_rejects_an_earlier_turn(self) -> None:
        """前の出来事より前の手番の出来事を足すと拒み、元の短期記憶は変わらない。"""
        memory = ShortTermMemory.empty().remember(RememberedEvent(turn=3, observation=_observation()))

        with pytest.raises(ShortTermMemoryValidationException):
            memory.remember(RememberedEvent(turn=2, observation=_observation()))
        assert [e.turn for e in memory.events] == [3]

    def test_add_backstory_keeps_only_the_newest_generations(self) -> None:
        """いきさつを上限 (3 世代) より多く足すと、古いものから捨て、新しい 3 つを書いた順に持つ。"""
        memory = ShortTermMemory.empty()
        for turn in (10, 20, 30, 40):
            memory = memory.add_backstory(Backstory(flow=f"{turn} 手番までの流れ", mood="", written_turn=turn))

        assert BACKSTORY_GENERATIONS == 3
        assert [b.written_turn for b in memory.backstories] == [20, 30, 40]

    def test_add_backstory_rejects_an_older_written_turn(self) -> None:
        """前のいきさつより前の手番に書いたいきさつを足すと拒む。"""
        memory = ShortTermMemory.empty().add_backstory(Backstory(flow="流れ", mood="", written_turn=20))

        with pytest.raises(ShortTermMemoryValidationException):
            memory.add_backstory(Backstory(flow="流れ", mood="", written_turn=10))

    @pytest.mark.parametrize(
        "fields",
        [
            {"events": (RememberedEvent(turn=3, observation=_observation()), RememberedEvent(turn=2, observation=_observation()))},
            {"backstories": tuple(Backstory(flow="流れ", mood="", written_turn=t) for t in (10, 20, 30, 40))},
            {"backstories": (Backstory(flow="流れ", mood="", written_turn=20), Backstory(flow="流れ", mood="", written_turn=10))},
            {"events": [RememberedEvent(turn=3, observation=_observation())]},
        ],
        ids=["events-out-of-order", "too-many-backstories", "backstories-out-of-order", "events-not-tuple"],
    )
    def test_direct_construction_checks_the_same_rules(self, fields: dict[str, object]) -> None:
        """戻すときのように直に作っても、手番の順、いきさつの上限と順、tuple であることを確かめる。"""
        with pytest.raises(ShortTermMemoryValidationException):
            ShortTermMemory(**fields)  # type: ignore[arg-type]
