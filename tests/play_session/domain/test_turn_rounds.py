from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.game_world.domain.value_object.readiness_to_act import (
    FreeToAct,
    InTheMiddleOfAction,
    ReadinessToAct,
    UnableToAct,
)
from ai_rpg_world.play_session.domain.play_session_exception import (
    RoundAlreadyOpenException,
    RoundNotOpenException,
    RoundStillHasTurnsException,
    RoundValidationException,
    TurnNotDueException,
)
from ai_rpg_world.play_session.domain.turn_rounds import (
    Acted,
    RoundClosedEvent,
    RoundCount,
    RoundOpenedEvent,
    TurnFinishedEvent,
    TurnRounds,
    Waited,
)

_WORLD = WorldId("mine_village_v2#1")
_HARU, _SAYO, _GEN, _MIO = PersonId("haru"), PersonId("sayo"), PersonId("gen"), PersonId("mio")
_ALL_FREE: dict[PersonId, ReadinessToAct] = {p: FreeToAct() for p in (_HARU, _SAYO, _GEN, _MIO)}


def _rounds(*, round_limit: int = 100, wake_waiting_after: int = 3) -> TurnRounds:
    return TurnRounds(_WORLD, round_limit=RoundCount(round_limit), wake_waiting_after=RoundCount(wake_waiting_after))


def _play_round(rounds: TurnRounds, readiness: dict[PersonId, ReadinessToAct], **outcomes: Waited) -> None:
    rounds.open_round(readiness)
    for person in rounds.due_turns():
        rounds.finish_turn(person, outcomes.get(person.value, Acted()))
    rounds.close_round()


class TestWhoGetsATurn:
    """TurnRounds.open_round が、世界の答えた動ける度合いと、待つ・呼びかけから、その巡りでターンを回す人を決めることを保証する。"""

    def test_everyone_free_to_act_gets_a_turn(self) -> None:
        """4 人とも何もしていなければ、4 人ともターンが回る。"""
        rounds = _rounds()

        rounds.open_round(_ALL_FREE)

        assert rounds.due_turns() == (_HARU, _SAYO, _GEN, _MIO)

    def test_only_mio_gets_a_turn_in_the_d2225_scene(self) -> None:
        """ハルは移動中、サヨは気を失っていて、ゲンは前の巡りで待つを選んだとき、ターンはミオにだけ回る (D2225 の場面)。"""
        rounds = _rounds()
        _play_round(rounds, _ALL_FREE, gen=Waited())

        rounds.open_round({_HARU: InTheMiddleOfAction(), _SAYO: UnableToAct(), _GEN: FreeToAct(), _MIO: FreeToAct()})

        assert rounds.due_turns() == (_MIO,)

    def test_person_in_the_middle_of_action_gets_a_turn_after_a_call(self) -> None:
        """移動中のハルも、前の巡りで呼びかけ (wants_wake の観測) を受けていれば、ターンが回る。"""
        rounds = _rounds()
        rounds.hear_call(_HARU)

        rounds.open_round({_HARU: InTheMiddleOfAction()})

        assert rounds.due_turns() == (_HARU,)

    def test_call_is_used_up_by_the_turn(self) -> None:
        """呼びかけで回ったターンを終えたら、次の巡りでは、移動中のハルにはもう回らない。"""
        rounds = _rounds()
        rounds.hear_call(_HARU)
        _play_round(rounds, {_HARU: InTheMiddleOfAction()})

        rounds.open_round({_HARU: InTheMiddleOfAction()})

        assert rounds.due_turns() == ()

    def test_call_heard_while_unable_is_not_carried_over(self) -> None:
        """気を失っているあいだに受けた呼びかけは、その後に移動中になった巡りへ持ち越されない。"""
        rounds = _rounds()
        rounds.hear_call(_SAYO)
        _play_round(rounds, {_SAYO: UnableToAct()})

        rounds.open_round({_SAYO: InTheMiddleOfAction()})

        assert rounds.due_turns() == ()

    def test_unable_person_gets_no_turn_even_after_a_call(self) -> None:
        """気を失っているサヨには、呼びかけを受けてもターンは回らない。"""
        rounds = _rounds()
        rounds.hear_call(_SAYO)

        rounds.open_round({_SAYO: UnableToAct()})

        assert rounds.due_turns() == ()


class TestWaiting:
    """待つを選んだ人が、呼びかけか、決めた巡りの数が経つまでターンを受けないことを保証する。"""

    def test_waiting_person_is_skipped_for_the_set_number_of_rounds(self) -> None:
        """起こすまでの長さが 3 のとき、巡り 1 で待つを選んだゲンは、巡り 2〜4 は飛ばされ、巡り 5 でターンが戻る。"""
        rounds = _rounds(wake_waiting_after=3)
        _play_round(rounds, {_GEN: FreeToAct()}, gen=Waited())
        skipped = []
        for _ in range(3):
            rounds.open_round({_GEN: FreeToAct()})
            skipped.append(rounds.due_turns())
            rounds.close_round()

        rounds.open_round({_GEN: FreeToAct()})

        assert skipped == [(), (), ()]
        assert rounds.due_turns() == (_GEN,)

    def test_call_wakes_waiting_person_on_the_next_round(self) -> None:
        """待っているゲンが呼びかけを受けると、次の巡りでターンが回る。"""
        rounds = _rounds(wake_waiting_after=3)
        _play_round(rounds, {_GEN: FreeToAct()}, gen=Waited())
        rounds.hear_call(_GEN)

        rounds.open_round({_GEN: FreeToAct()})

        assert rounds.due_turns() == (_GEN,)

    def test_acting_after_being_woken_ends_the_wait(self) -> None:
        """起こされたゲンが待つ以外を選ぶと、次の巡りからは毎回ターンが回る。"""
        rounds = _rounds(wake_waiting_after=3)
        _play_round(rounds, {_GEN: FreeToAct()}, gen=Waited())
        rounds.hear_call(_GEN)
        _play_round(rounds, {_GEN: FreeToAct()})

        rounds.open_round({_GEN: FreeToAct()})

        assert rounds.due_turns() == (_GEN,)


class TestTurnsWithinARound:
    """1 つの巡りの中で、ターンを終えた順が記録され、全員が終えるまで巡りを閉じられないことを保証する。"""

    def test_finished_turn_leaves_the_due_turns(self) -> None:
        """ミオがターンを終えると、残りのターンからミオが消える。"""
        rounds = _rounds()
        rounds.open_round(_ALL_FREE)

        rounds.finish_turn(_MIO, Acted())

        assert rounds.due_turns() == (_HARU, _SAYO, _GEN)

    def test_order_of_finishing_is_recorded(self) -> None:
        """ミオ・ゲンの順に返事が返って終えると、TurnFinishedEvent の order は 1・2 になる。"""
        rounds = _rounds()
        rounds.open_round({_GEN: FreeToAct(), _MIO: FreeToAct()})

        rounds.finish_turn(_MIO, Acted())
        rounds.finish_turn(_GEN, Waited())

        finished = [e for e in rounds.get_events() if isinstance(e, TurnFinishedEvent)]
        assert [(e.person, e.order, e.outcome) for e in finished] == [(_MIO, 1, Acted()), (_GEN, 2, Waited())]

    def test_finishing_a_turn_not_due_is_refused(self) -> None:
        """ターンの無いサヨがターンを終えようとすると TurnNotDueException を投げる。"""
        rounds = _rounds()
        rounds.open_round({_SAYO: UnableToAct(), _MIO: FreeToAct()})

        with pytest.raises(TurnNotDueException):
            rounds.finish_turn(_SAYO, Acted())

    def test_finishing_the_same_turn_twice_is_refused(self) -> None:
        """同じ巡りでミオが 2 度ターンを終えようとすると TurnNotDueException を投げる。"""
        rounds = _rounds()
        rounds.open_round({_MIO: FreeToAct()})
        rounds.finish_turn(_MIO, Acted())

        with pytest.raises(TurnNotDueException):
            rounds.finish_turn(_MIO, Acted())

    def test_round_with_turns_left_cannot_be_closed(self) -> None:
        """ゲンのターンが残っているうちに巡りを閉じようとすると RoundStillHasTurnsException を投げ、巡りは開いたまま。"""
        rounds = _rounds()
        rounds.open_round({_GEN: FreeToAct(), _MIO: FreeToAct()})
        rounds.finish_turn(_MIO, Acted())

        with pytest.raises(RoundStillHasTurnsException):
            rounds.close_round()
        assert rounds.due_turns() == (_GEN,)

    def test_round_cannot_be_opened_twice(self) -> None:
        """開いている巡りをもう一度開こうとすると RoundAlreadyOpenException を投げる。"""
        rounds = _rounds()
        rounds.open_round(_ALL_FREE)

        with pytest.raises(RoundAlreadyOpenException):
            rounds.open_round(_ALL_FREE)

    def test_due_turns_before_opening_is_refused(self) -> None:
        """巡りを開く前に残りのターンを問うと RoundNotOpenException を投げる。"""
        with pytest.raises(RoundNotOpenException):
            _rounds().due_turns()

    def test_round_with_no_turns_can_be_closed_at_once(self) -> None:
        """誰にもターンが無い巡りは、開いてすぐ閉じられる (時間だけが進む)。"""
        rounds = _rounds()
        rounds.open_round({_SAYO: UnableToAct()})

        rounds.close_round()

        assert [type(e) for e in rounds.get_events()] == [RoundOpenedEvent, RoundClosedEvent]


class TestRoundLimit:
    """決めた巡りの数を閉じ終えると、TurnRounds が上限に届いたと答えることを保証する。"""

    def test_reaches_the_limit_after_closing_that_many_rounds(self) -> None:
        """上限 2 のとき、1 巡り閉じた時点では届かず、2 巡り閉じると届く。"""
        rounds = _rounds(round_limit=2)
        _play_round(rounds, _ALL_FREE)
        after_one = rounds.has_reached_round_limit()

        _play_round(rounds, _ALL_FREE)

        assert after_one is False
        assert rounds.has_reached_round_limit() is True

    def test_closed_rounds_are_numbered_from_one(self) -> None:
        """2 巡り閉じると、RoundClosedEvent の巡りの番号は 1・2 になる。"""
        rounds = _rounds()
        _play_round(rounds, _ALL_FREE)
        _play_round(rounds, _ALL_FREE)

        assert [e.round for e in rounds.get_events() if isinstance(e, RoundClosedEvent)] == [1, 2]

    @pytest.mark.parametrize("value", [0, -1, True])
    def test_round_count_must_be_a_positive_int(self, value: int) -> None:
        """巡りの数に 0 以下や真偽値を渡すと RoundValidationException を投げる。"""
        with pytest.raises(RoundValidationException):
            RoundCount(value)
