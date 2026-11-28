from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard, UnknownValue
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
    ChoiceFailed,
    ChoosingKeptFailing,
    ChoseNoAction,
    ObservationPassedOnEvent,
    RoundClosedEvent,
    RoundCount,
    RoundLimitReached,
    RoundOpenedEvent,
    SkippedTurn,
    TurnFinishedEvent,
    TurnOutcome,
    TurnRounds,
    TurnSkipReason,
    Waited,
)

_WORLD = WorldId("mine_village_v2#1")
_HARU, _SAYO, _GEN, _MIO = PersonId("haru"), PersonId("sayo"), PersonId("gen"), PersonId("mio")
_ALL_FREE: dict[PersonId, ReadinessToAct] = {p: FreeToAct() for p in (_HARU, _SAYO, _GEN, _MIO)}


def _rounds(*, round_limit: int = 100, wake_waiting_after: int = 3) -> TurnRounds:
    return TurnRounds(_WORLD, round_limit=RoundCount(round_limit), wake_waiting_after=RoundCount(wake_waiting_after))


def _play_round(rounds: TurnRounds, readiness: dict[PersonId, ReadinessToAct], **outcomes: TurnOutcome) -> None:
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

    def test_person_in_the_middle_of_action_gets_a_turn_when_addressed(self) -> None:
        """移動中のハルも、前の巡りで自分に向けた観測 (addressed_to_self=True) を受けていれば、ターンが回る。"""
        rounds = _rounds()
        rounds.notice_observation(_HARU, _observation(wants_wake=True, addressed_to_self=True))

        rounds.open_round({_HARU: InTheMiddleOfAction()})

        assert rounds.due_turns() == (_HARU,)

    def test_person_in_the_middle_of_action_is_not_woken_by_what_only_calls_attention(self) -> None:
        """移動中のハルは、目立つだけで自分に向けたものではない観測 (wants_wake=True、addressed_to_self=False) では、ターンが回らない。"""
        rounds = _rounds()
        rounds.notice_observation(_HARU, _observation(wants_wake=True, addressed_to_self=False))

        rounds.open_round({_HARU: InTheMiddleOfAction()})

        assert rounds.due_turns() == ()

    def test_being_addressed_is_used_up_by_the_turn(self) -> None:
        """自分に向けた観測で回ったターンを終えたら、次の巡りでは、移動中のハルにはもう回らない。"""
        rounds = _rounds()
        rounds.notice_observation(_HARU, _observation(wants_wake=True, addressed_to_self=True))
        _play_round(rounds, {_HARU: InTheMiddleOfAction()})

        rounds.open_round({_HARU: InTheMiddleOfAction()})

        assert rounds.due_turns() == ()

    def test_being_addressed_while_unable_is_not_carried_over(self) -> None:
        """気を失っているあいだに受けた自分に向けた観測は、その後に移動中になった巡りへ持ち越されない。"""
        rounds = _rounds()
        rounds.notice_observation(_SAYO, _observation(wants_wake=True, addressed_to_self=True))
        _play_round(rounds, {_SAYO: UnableToAct()})

        rounds.open_round({_SAYO: InTheMiddleOfAction()})

        assert rounds.due_turns() == ()

    def test_unable_person_gets_no_turn_even_when_addressed(self) -> None:
        """気を失っているサヨには、自分に向けた観測を受けてもターンは回らない。"""
        rounds = _rounds()
        rounds.notice_observation(_SAYO, _observation(wants_wake=True, addressed_to_self=True))

        rounds.open_round({_SAYO: UnableToAct()})

        assert rounds.due_turns() == ()

    def test_round_opened_event_tells_who_was_skipped_and_why(self) -> None:
        """D2225 の場面で巡りを開くと、RoundOpenedEvent に、ハルは行為の最中で自分に向けたものが無い、サヨは動けない、ゲンは待っている、と飛ばした理由が人ごとに残る。"""
        rounds = _rounds()
        _play_round(rounds, _ALL_FREE, gen=Waited())
        rounds.notice_observation(_HARU, _observation(wants_wake=True, addressed_to_self=False))

        rounds.open_round({_HARU: InTheMiddleOfAction(), _SAYO: UnableToAct(), _GEN: FreeToAct(), _MIO: FreeToAct()})

        [opened] = [e for e in rounds.get_events() if isinstance(e, RoundOpenedEvent)][-1:]
        assert opened.due == (_MIO,)
        assert opened.skipped == (
            SkippedTurn(_HARU, TurnSkipReason.IN_THE_MIDDLE_OF_ACTION_AND_NOT_ADDRESSED),
            SkippedTurn(_SAYO, TurnSkipReason.UNABLE_TO_ACT),
            SkippedTurn(_GEN, TurnSkipReason.WAITING),
        )


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
        rounds.notice_observation(_GEN, _observation(wants_wake=True))

        rounds.open_round({_GEN: FreeToAct()})

        assert rounds.due_turns() == (_GEN,)

    def test_acting_after_being_woken_ends_the_wait(self) -> None:
        """起こされたゲンが待つ以外を選ぶと、次の巡りからは毎回ターンが回る。"""
        rounds = _rounds(wake_waiting_after=3)
        _play_round(rounds, {_GEN: FreeToAct()}, gen=Waited())
        rounds.notice_observation(_GEN, _observation(wants_wake=True))
        _play_round(rounds, {_GEN: FreeToAct()})

        rounds.open_round({_GEN: FreeToAct()})

        assert rounds.due_turns() == (_GEN,)


def _observation(wants_wake: bool | None, addressed_to_self: bool | UnknownValue = UNKNOWN) -> Observation:
    return Observation(
        body="扉が壊れた",
        route=SeenOrHeard(),
        time=ObservedTime(display="tick 1"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=addressed_to_self,
        wants_wake=wants_wake,
    )


class TestNoticeObservation:
    """TurnRounds.notice_observation が、wants_wake の立った観測だけを呼びかけとして数えることを保証する。"""

    def test_observation_that_wants_wake_wakes_the_waiting_person(self) -> None:
        """待っているゲンに wants_wake=True の観測が届くと、次の巡りでターンが回る。"""
        rounds = _rounds(wake_waiting_after=3)
        _play_round(rounds, {_GEN: FreeToAct()}, gen=Waited())

        rounds.notice_observation(_GEN, _observation(True))
        rounds.open_round({_GEN: FreeToAct()})

        assert rounds.due_turns() == (_GEN,)

    @pytest.mark.parametrize("wants_wake", [False, None], ids=["not_to_wake", "no_advice"])
    def test_observation_without_wants_wake_does_not_wake(self, wants_wake: bool | None) -> None:
        """待っているゲンに wants_wake が False か None の観測が届いても、次の巡りでターンは回らない。"""
        rounds = _rounds(wake_waiting_after=3)
        _play_round(rounds, {_GEN: FreeToAct()}, gen=Waited())

        rounds.notice_observation(_GEN, _observation(wants_wake))
        rounds.open_round({_GEN: FreeToAct()})

        assert rounds.due_turns() == ()


def _passed_on(rounds: TurnRounds) -> list[tuple[PersonId, str]]:
    return [(e.person, e.observation.body) for e in rounds.get_events() if isinstance(e, ObservationPassedOnEvent)]


class TestObservationsWhileChoosing:
    """TurnRounds が、まだ選んでいる人に届いた観測を預かり、その人のターンを終えたあとで本人に回し、呼びかけを数えることを保証する。"""

    def test_observation_to_someone_not_choosing_is_passed_on_at_once(self) -> None:
        """選んでいないゲンに届いた観測は、その場で本人に回る。"""
        rounds = _rounds()
        rounds.open_round({_GEN: FreeToAct()})

        rounds.notice_observation(_GEN, _observation(False))

        assert _passed_on(rounds) == [(_GEN, "扉が壊れた")]

    def test_observation_to_someone_choosing_is_held_until_the_turn_ends(self) -> None:
        """ミオとゲンが選んでいるあいだにゲンへ届いた観測は、ゲンのターンを終えるまで回らず、終えたあとに 1 回だけ回る。"""
        rounds = _rounds()
        rounds.open_round({_MIO: FreeToAct(), _GEN: FreeToAct()})
        rounds.begin_choosing((_MIO, _GEN))
        rounds.finish_choosing(_MIO)
        rounds.finish_turn(_MIO, Acted())

        rounds.notice_observation(_GEN, _observation(False))
        held = _passed_on(rounds)
        rounds.finish_choosing(_GEN)
        rounds.finish_turn(_GEN, Acted())

        assert held == []
        assert _passed_on(rounds) == [(_GEN, "扉が壊れた")]

    def test_held_observation_comes_after_the_turn_is_finished(self) -> None:
        """預かった観測は、そのターンを終えた記録 (TurnFinishedEvent) より後に回る。"""
        rounds = _rounds()
        rounds.open_round({_GEN: FreeToAct()})
        rounds.begin_choosing((_GEN,))
        rounds.notice_observation(_GEN, _observation(False))

        rounds.finish_turn(_GEN, Acted())

        kinds = [type(e) for e in rounds.get_events()][-2:]
        assert kinds == [TurnFinishedEvent, ObservationPassedOnEvent]

    def test_observation_after_the_choice_came_back_is_passed_on_at_once(self) -> None:
        """選び終えて行為を確定させているあいだのゲンに届いた観測 (自分の行為の結果など) は、預からずに回る。"""
        rounds = _rounds()
        rounds.open_round({_GEN: FreeToAct()})
        rounds.begin_choosing((_GEN,))
        rounds.finish_choosing(_GEN)

        rounds.notice_observation(_GEN, _observation(False))

        assert _passed_on(rounds) == [(_GEN, "扉が壊れた")]

    def test_call_held_while_choosing_wakes_the_person_who_chose_to_wait(self) -> None:
        """選んでいるあいだに目立つ知らせを預かったゲンが待つを選んでも、次の巡りでターンが回る。"""
        rounds = _rounds(wake_waiting_after=3)
        rounds.open_round({_GEN: FreeToAct()})
        rounds.begin_choosing((_GEN,))
        rounds.notice_observation(_GEN, _observation(True))
        rounds.finish_turn(_GEN, Waited())
        rounds.close_round()

        rounds.open_round({_GEN: FreeToAct()})

        assert rounds.due_turns() == (_GEN,)

    def test_call_held_while_choosing_brings_a_turn_back_in_the_middle_of_action(self) -> None:
        """選んでいるあいだに自分に向けた観測を預かったハルが移動を始めても、次の巡りでターンが回る。"""
        rounds = _rounds()
        rounds.open_round({_HARU: FreeToAct()})
        rounds.begin_choosing((_HARU,))
        rounds.notice_observation(_HARU, _observation(True, addressed_to_self=True))
        rounds.finish_turn(_HARU, Acted())
        rounds.close_round()

        rounds.open_round({_HARU: InTheMiddleOfAction()})

        assert rounds.due_turns() == (_HARU,)

    def test_choosing_someone_without_a_turn_is_refused(self) -> None:
        """その巡りにターンの無いサヨを、選んでいる人にはできない。"""
        rounds = _rounds()
        rounds.open_round({_GEN: FreeToAct(), _SAYO: UnableToAct()})

        with pytest.raises(TurnNotDueException):
            rounds.begin_choosing((_SAYO,))

    def test_nothing_is_held_once_the_round_is_closed(self) -> None:
        """全員が選んでいるあいだに観測が届いても、巡りを閉じたときには預かりが残らず、全部回り終えている。"""
        rounds = _rounds()
        rounds.open_round({_MIO: FreeToAct(), _GEN: FreeToAct()})
        rounds.begin_choosing((_MIO, _GEN))
        rounds.notice_observation(_MIO, _observation(False))
        rounds.notice_observation(_GEN, _observation(False))
        rounds.finish_turn(_GEN, Acted())
        rounds.finish_turn(_MIO, Acted())

        rounds.close_round()

        assert sorted(p.value for p, _ in _passed_on(rounds)) == ["gen", "mio"]


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
        after_one = rounds.reason_to_stop()

        _play_round(rounds, _ALL_FREE)

        assert after_one is None
        assert rounds.reason_to_stop() == RoundLimitReached()

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


_FAILED = ChoiceFailed("Timeout: no reply in 95 seconds")


class TestChoiceFailures:
    """選べなかったターン (ChoiceFailed) が、同じ人の 3 回続きで待つ扱いになり、全員の 8 件続きが 2 巡りにまたがると選ぶことを諦めることを保証する。"""

    def test_three_failures_in_a_row_make_the_person_wait(self) -> None:
        """ミオが巡り 1〜3 と続けて選べないと、巡り 4 ではミオにターンが回らない。"""
        rounds = _rounds(wake_waiting_after=3)
        for _ in range(3):
            _play_round(rounds, {_MIO: FreeToAct()}, mio=_FAILED)

        rounds.open_round({_MIO: FreeToAct()})

        assert rounds.due_turns() == ()

    def test_a_choice_in_between_starts_the_count_over(self) -> None:
        """ミオが 2 回続けて選べず、次に選べたあと、また 2 回選べなくても、ミオにはターンが回る。"""
        rounds = _rounds(wake_waiting_after=3)
        for outcome in (_FAILED, _FAILED, Acted(), _FAILED, _FAILED):
            _play_round(rounds, {_MIO: FreeToAct()}, mio=outcome)

        rounds.open_round({_MIO: FreeToAct()})

        assert rounds.due_turns() == (_MIO,)

    def test_failures_after_waiting_are_counted_from_one(self) -> None:
        """3 回続けて選べずに待たされたミオは、戻ってから 1 回選べなくても、次の巡りでまたターンが回る (数え直して 1 回目)。"""
        rounds = _rounds(wake_waiting_after=1)
        for outcome in (_FAILED, _FAILED, _FAILED, None, _FAILED):
            if outcome is None:
                rounds.open_round({_MIO: FreeToAct()})
                rounds.close_round()
                continue
            _play_round(rounds, {_MIO: FreeToAct()}, mio=outcome)

        rounds.open_round({_MIO: FreeToAct()})

        assert rounds.due_turns() == (_MIO,)

    def test_gives_up_after_eight_failures_across_two_rounds(self) -> None:
        """4 人とも 2 巡り続けて選べないと (8 件、2 巡り)、選ぶことを諦める。7 件の時点ではまだ諦めない。"""
        rounds = _rounds()
        _play_round(rounds, _ALL_FREE, haru=_FAILED, sayo=_FAILED, gen=_FAILED, mio=_FAILED)
        rounds.open_round(_ALL_FREE)
        for person in (_HARU, _SAYO, _GEN):
            rounds.finish_turn(person, _FAILED)
        after_seven = rounds.reason_to_stop()

        rounds.finish_turn(_MIO, _FAILED)

        assert after_seven is None
        assert isinstance(rounds.reason_to_stop(), ChoosingKeptFailing)

    def test_eight_failures_within_one_round_do_not_give_up(self) -> None:
        """8 人が同じ巡りで全員選べなくても、1 巡りに収まっているので諦めない。provider が一瞬遅れただけのことがあるため。"""
        rounds = _rounds()
        eight = {PersonId(f"p{i}"): FreeToAct() for i in range(8)}
        rounds.open_round(eight)

        for person in eight:
            rounds.finish_turn(person, _FAILED)

        assert rounds.reason_to_stop() is None

    def test_a_choice_breaks_the_streak_of_failures(self) -> None:
        """7 件続けて選べなかったあとに 1 人が選べると、続きが切れ、そのあと 2 巡りにまたがって 2 件選べなくても諦めない。"""
        rounds = _rounds()
        _play_round(rounds, _ALL_FREE, haru=_FAILED, sayo=_FAILED, gen=_FAILED, mio=_FAILED)
        rounds.open_round(_ALL_FREE)
        for person in (_HARU, _SAYO, _GEN):
            rounds.finish_turn(person, _FAILED)
        rounds.finish_turn(_MIO, Acted())
        rounds.close_round()

        _play_round(rounds, {_MIO: FreeToAct()}, mio=_FAILED)
        _play_round(rounds, {_MIO: FreeToAct()}, mio=_FAILED)

        assert rounds.reason_to_stop() is None

    def test_a_choice_forgets_the_rounds_of_earlier_failures(self) -> None:
        """2 巡りにまたがる 7 件のあとに選べたターンが入ると、そのあと 1 つの巡りで 8 人が選べなくても、巡りが 1 つなので諦めない。"""
        rounds = _rounds()
        _play_round(rounds, _ALL_FREE, haru=_FAILED, sayo=_FAILED, gen=_FAILED, mio=_FAILED)
        rounds.open_round(_ALL_FREE)
        for person in (_HARU, _SAYO, _GEN):
            rounds.finish_turn(person, _FAILED)
        rounds.finish_turn(_MIO, Acted())
        rounds.close_round()
        eight = {PersonId(f"p{i}"): FreeToAct() for i in range(8)}
        rounds.open_round(eight)

        for person in eight:
            rounds.finish_turn(person, _FAILED)

        assert rounds.reason_to_stop() is None

    def test_giving_up_keeps_the_reasons_of_the_failures(self) -> None:
        """8 件続けて選べずに諦めると、その 8 件の理由を起きた順に残し、そのあとにまた選べなくても理由は変わらない。"""
        rounds = _rounds()
        rounds.open_round(_ALL_FREE)
        for person in _ALL_FREE:
            rounds.finish_turn(person, ChoiceFailed(f"Timeout: {person.value}"))
        rounds.close_round()
        rounds.open_round(_ALL_FREE)

        for person in _ALL_FREE:
            rounds.finish_turn(person, ChoiceFailed(f"RateLimit: {person.value}"))
        rounds.close_round()
        rounds.open_round({_HARU: FreeToAct()})
        rounds.finish_turn(_HARU, ChoiceFailed("Timeout: once more"))

        assert rounds.reason_to_stop() == ChoosingKeptFailing(
            (
                *(f"Timeout: {p.value}" for p in _ALL_FREE),
                *(f"RateLimit: {p.value}" for p in _ALL_FREE),
            )
        )

    def test_giving_up_is_kept_even_if_a_choice_comes_later(self) -> None:
        """一度諦めたら、そのあとに選べたターンが届いても諦めたままでいる。"""
        rounds = _rounds()
        _play_round(rounds, _ALL_FREE, haru=_FAILED, sayo=_FAILED, gen=_FAILED, mio=_FAILED)
        _play_round(rounds, _ALL_FREE, haru=_FAILED, sayo=_FAILED, gen=_FAILED, mio=_FAILED)
        rounds.open_round({_HARU: FreeToAct()})

        rounds.finish_turn(_HARU, Acted())

        assert isinstance(rounds.reason_to_stop(), ChoosingKeptFailing)


class TestTurnsWithoutAnAction:
    """世界に渡す行動を選ばなかったターン (ChoseNoAction) が、失敗の続きを切り、待つ扱いにもしないことを保証する。"""

    def test_turn_without_an_action_starts_the_count_of_that_person_over(self) -> None:
        """ミオが 2 回続けて選べず、次に思い出すだけのターンを終え、また 1 回選べなくても、次の巡りでミオにターンが回る。"""
        rounds = _rounds(wake_waiting_after=3)
        for outcome in (_FAILED, _FAILED, ChoseNoAction(), _FAILED):
            _play_round(rounds, {_MIO: FreeToAct()}, mio=outcome)

        rounds.open_round({_MIO: FreeToAct()})

        assert rounds.due_turns() == (_MIO,)

    def test_turn_without_an_action_breaks_the_streak_of_failures(self) -> None:
        """7 件続けて選べなかったあとに思い出すだけのターンが入ると、続きが切れ、そのあと 2 巡りにまたがって 2 件選べなくても止めない。"""
        rounds = _rounds()
        _play_round(rounds, _ALL_FREE, haru=_FAILED, sayo=_FAILED, gen=_FAILED, mio=_FAILED)
        rounds.open_round(_ALL_FREE)
        for person in (_HARU, _SAYO, _GEN):
            rounds.finish_turn(person, _FAILED)
        rounds.finish_turn(_MIO, ChoseNoAction())
        rounds.close_round()

        _play_round(rounds, {_MIO: FreeToAct()}, mio=_FAILED)
        _play_round(rounds, {_MIO: FreeToAct()}, mio=_FAILED)

        assert rounds.reason_to_stop() is None

    def test_turn_without_an_action_is_not_waiting(self) -> None:
        """思い出すだけのターンを終えたゲンには、次の巡りでもターンが回る。"""
        rounds = _rounds()
        _play_round(rounds, {_GEN: FreeToAct()}, gen=ChoseNoAction())

        rounds.open_round({_GEN: FreeToAct()})

        assert rounds.due_turns() == (_GEN,)


class TestWaitingAfterChoicesKeptFailing:
    """3 回続けて選べずに待ちに入った人を、自分から待った人と見分けられる理由で飛ばし、同じ規則で起こすことを保証する。"""

    def test_person_waiting_after_failures_is_skipped_for_a_reason_of_its_own(self) -> None:
        """ミオが 3 回続けて選べず、ゲンが待つを選んだあとの巡りでは、ミオは WAITING_AFTER_CHOICES_KEPT_FAILING、ゲンは WAITING で飛ばされる。"""
        rounds = _rounds()
        _play_round(rounds, {_MIO: FreeToAct()}, mio=_FAILED)
        _play_round(rounds, {_MIO: FreeToAct()}, mio=_FAILED)
        _play_round(rounds, {_MIO: FreeToAct(), _GEN: FreeToAct()}, mio=_FAILED, gen=Waited())

        rounds.open_round({_MIO: FreeToAct(), _GEN: FreeToAct()})

        [opened] = [e for e in rounds.get_events() if isinstance(e, RoundOpenedEvent)][-1:]
        assert opened.skipped == (
            SkippedTurn(_MIO, TurnSkipReason.WAITING_AFTER_CHOICES_KEPT_FAILING),
            SkippedTurn(_GEN, TurnSkipReason.WAITING),
        )

    def test_person_waiting_after_failures_is_woken_by_a_call(self) -> None:
        """3 回続けて選べずに待っているミオも、目立つ知らせ (wants_wake=True) を受けると、次の巡りでターンが戻る。"""
        rounds = _rounds(wake_waiting_after=10)
        for _ in range(3):
            _play_round(rounds, {_MIO: FreeToAct()}, mio=_FAILED)
        rounds.notice_observation(_MIO, _observation(wants_wake=True, addressed_to_self=False))

        rounds.open_round({_MIO: FreeToAct()})

        assert rounds.due_turns() == (_MIO,)

    def test_choosing_to_wait_after_failures_is_plain_waiting(self) -> None:
        """2 回続けて選べなかったゲンが次に待つを選ぶと、次の巡りでは WAITING で飛ばされる。"""
        rounds = _rounds()
        _play_round(rounds, {_GEN: FreeToAct()}, gen=_FAILED)
        _play_round(rounds, {_GEN: FreeToAct()}, gen=_FAILED)
        _play_round(rounds, {_GEN: FreeToAct()}, gen=Waited())

        rounds.open_round({_GEN: FreeToAct()})

        [opened] = [e for e in rounds.get_events() if isinstance(e, RoundOpenedEvent)][-1:]
        assert opened.skipped == (SkippedTurn(_GEN, TurnSkipReason.WAITING),)


class TestReasonToStop:
    """TurnRounds.reason_to_stop が、巡りの上限と選び続けた失敗のどちらで止めるかを決めることを保証する。"""

    def test_there_is_no_reason_to_stop_before_any_round(self) -> None:
        """巡りを 1 つも回していないときは、止める理由は無い。"""
        assert _rounds().reason_to_stop() is None

    def test_choosing_kept_failing_wins_over_the_round_limit(self) -> None:
        """上限 2 で、4 人とも 2 巡り続けて選べずに上限まで閉じると、止める理由は RoundLimitReached ではなく ChoosingKeptFailing になる。
        上限で覆うと、壊れた run が正常に終わったように記録されるため。"""
        rounds = _rounds(round_limit=2)
        _play_round(rounds, _ALL_FREE, haru=_FAILED, sayo=_FAILED, gen=_FAILED, mio=_FAILED)
        _play_round(rounds, _ALL_FREE, haru=_FAILED, sayo=_FAILED, gen=_FAILED, mio=_FAILED)

        assert rounds.reason_to_stop() == ChoosingKeptFailing((_FAILED.reason,) * 8)
