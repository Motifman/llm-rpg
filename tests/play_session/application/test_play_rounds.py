from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence

from ai_rpg_world.game_world.application.deliver_perception import DeliverPerceptionCommand
from ai_rpg_world.game_world.domain.perception.perception_cause import TimePassed
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from ai_rpg_world.play_session.application.play_rounds import (
    ChoosingKeptFailing,
    FinishedTurn,
    PlayRoundsCommand,
    RoundLimitReached,
    WorldEnded,
)
from ai_rpg_world.play_session.domain.turn_rounds import (
    Acted,
    ChoiceFailed,
    RoundClosedEvent,
    TurnFinishedEvent,
    TurnOutcome,
    Waited,
)
from tests.play_session.mine_village_session import WORLD, MineVillageSession, door_breaks_at

_HARU, _SAYO, _GEN, _MIO = PersonId("haru"), PersonId("sayo"), PersonId("gen"), PersonId("mio")
_EVERYONE = frozenset({_HARU, _SAYO, _GEN, _MIO})


class _TurnTakersForTests:
    """頼まれた順に 1 人ずつターンを終える。ターンの中で世界に何かを起こしたいときは during に渡す。"""

    def __init__(
        self,
        *,
        outcomes: dict[PersonId, TurnOutcome] | None = None,
        during: Callable[[PersonId], None] = lambda person: None,
    ) -> None:
        self._outcomes = outcomes or {}
        self._during = during
        self.asked: list[frozenset[PersonId]] = []
        self.finished: list[PersonId] = []

    def take_turns(self, people: Sequence[PersonId]) -> Iterator[FinishedTurn]:
        self.asked.append(frozenset(people))
        for person in people:
            self._during(person)
            self.finished.append(person)
            yield FinishedTurn(person, self._outcomes.get(person, Acted()))


def _now(session: MineVillageSession) -> WorldTick:
    return session.scope.run(lambda world: world.clock().now())


def _end_world(session: MineVillageSession) -> None:
    session.scope.run(lambda world: world.ending().end(world.clock().now()))


class TestPlayRoundsStops:
    """PlayRounds が、決めた巡りの数か世界の終わりで止まり、止まった理由を返すことを保証する。"""

    def test_stops_after_the_round_limit_and_time_passes_once_per_round(self) -> None:
        """巡りの上限 3 で回すと、4 人に 3 巡りターンを頼み、世界の時刻が 3 進んで RoundLimitReached で止まる。"""
        session = MineVillageSession(round_limit=3).started()
        before = _now(session)
        takers = _TurnTakersForTests()

        stopped = session.play_rounds(takers)(PlayRoundsCommand(WORLD))

        assert stopped == RoundLimitReached()
        assert takers.asked == [_EVERYONE] * 3
        assert _now(session).value - before.value == 3

    def test_world_ending_during_a_turn_stops_before_the_next_turn(self) -> None:
        """最初にターンを終えた人の行為で世界が終わると、残りの 3 人には頼まず、時間も進めずに WorldEnded で止まる。"""
        session = MineVillageSession().started()
        before = _now(session)
        takers = _TurnTakersForTests(during=lambda person: _end_world(session))

        stopped = session.play_rounds(takers)(PlayRoundsCommand(WORLD))

        assert stopped == WorldEnded()
        assert len(takers.finished) == 1
        assert _now(session) == before

    def test_world_already_ended_asks_nobody(self) -> None:
        """始める前に世界が終わっていれば、誰にもターンを頼まずに WorldEnded で止まる。"""
        session = MineVillageSession().started()
        _end_world(session)
        takers = _TurnTakersForTests()

        stopped = session.play_rounds(takers)(PlayRoundsCommand(WORLD))

        assert stopped == WorldEnded()
        assert takers.asked == []

    def test_choosing_that_keeps_failing_stops_the_play(self) -> None:
        """4 人とも LLM の呼び出しに失敗し続けると、8 件目 (2 巡り目の最後) で、8 件の理由を持つ ChoosingKeptFailing で止まり、時間は 1 しか進まない。"""
        session = MineVillageSession().started()
        before = _now(session)
        failed = ChoiceFailed("Timeout: no reply")
        takers = _TurnTakersForTests(outcomes={person: failed for person in _EVERYONE})

        stopped = session.play_rounds(takers)(PlayRoundsCommand(WORLD))

        assert stopped == ChoosingKeptFailing(("Timeout: no reply",) * 8)
        assert len(takers.finished) == 8
        assert _now(session).value - before.value == 1

    def test_play_given_up_on_choosing_asks_nobody_when_called_again(self) -> None:
        """選ぶことを諦めて止まった遊びをもう一度回すと、誰にも頼まずに ChoosingKeptFailing で止まる。"""
        session = MineVillageSession().started()
        failed = ChoiceFailed("Timeout: no reply")
        session.play_rounds(_TurnTakersForTests(outcomes={person: failed for person in _EVERYONE}))(
            PlayRoundsCommand(WORLD)
        )
        again = _TurnTakersForTests()

        stopped = session.play_rounds(again)(PlayRoundsCommand(WORLD))

        assert isinstance(stopped, ChoosingKeptFailing)
        assert again.asked == []


class TestPlayRoundsTurns:
    """PlayRounds が、巡りの決まり (TurnRounds) に従ってターンを頼み、終えた順と巡りの閉じを記録に渡すことを保証する。"""

    def test_person_who_waited_is_not_asked_next_round(self) -> None:
        """巡り 1 でゲンが待つを選ぶと、巡り 2 ではゲンを除く 3 人にだけ頼む。"""
        session = MineVillageSession(round_limit=2).started()
        takers = _TurnTakersForTests(outcomes={_GEN: Waited()})

        session.play_rounds(takers)(PlayRoundsCommand(WORLD))

        assert takers.asked == [_EVERYONE, _EVERYONE - {_GEN}]

    def test_notable_observation_wakes_the_waiting_person_next_round(self) -> None:
        """巡り 2 のあいだに、待っているゲンのいる南の横坑口で扉が壊れると、巡り 3 でゲンにまた頼む。"""
        session = MineVillageSession(round_limit=3, wake_waiting_after=10).started()

        def door_breaks_in_round_two(person: PersonId) -> None:
            if len(takers.asked) == 2 and person == _HARU:
                session.deliver_perception(
                    DeliverPerceptionCommand(
                        cause=TimePassed(), from_actions=(door_breaks_at(SpotId("south_adit_mouth")),), from_states=()
                    )
                )

        takers = _TurnTakersForTests(outcomes={_GEN: Waited()}, during=door_breaks_in_round_two)

        session.play_rounds(takers)(PlayRoundsCommand(WORLD))

        assert [_GEN in asked for asked in takers.asked] == [True, False, True]

    def test_turns_and_round_closings_reach_the_record_in_order(self) -> None:
        """1 巡り回すと、4 人の TurnFinishedEvent が順番 1〜4 で出たあとに、巡り 1 の RoundClosedEvent が出る。"""
        session = MineVillageSession(round_limit=1).started()
        takers = _TurnTakersForTests()

        session.play_rounds(takers)(PlayRoundsCommand(WORLD))

        events = [e for e in session.turn_round_events if isinstance(e, (TurnFinishedEvent, RoundClosedEvent))]
        assert [(type(e), getattr(e, "order", None)) for e in events] == [
            (TurnFinishedEvent, 1),
            (TurnFinishedEvent, 2),
            (TurnFinishedEvent, 3),
            (TurnFinishedEvent, 4),
            (RoundClosedEvent, None),
        ]
        assert [e.person for e in events if isinstance(e, TurnFinishedEvent)] == takers.finished
