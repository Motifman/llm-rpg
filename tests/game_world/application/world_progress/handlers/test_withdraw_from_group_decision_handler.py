from __future__ import annotations

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.world_progress.handlers.withdraw_from_group_decision_handler import (
    WithdrawFromGroupDecisionHandler,
)
from ai_rpg_world.game_world.application.world_progress.withdraw_from_group_decisions import (
    WithdrawFromGroupDecisions,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.person import PersonDiedEvent, PersonFellEvent
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.world_progress import (
    GroupDecision,
    GroupDecisionMemento,
    GroupDecisionReachedEvent,
    VoteFor,
)
from tests.game_world.application.world_for_handler_tests import WiredWorld, falls, falls_and_dies, healthy
from tests.game_world.support.verb_declarations_for_tests import everyone_votes_on
from tests.game_world.support.world_design_for_tests import character, compose_world, group_decision, nouns, spot

AKI = PersonId("aki")
HARU = PersonId("haru")
NATSU = PersonId("natsu")
EVERYONE = frozenset({AKI, HARU, NATSU})
EXILE = group_decision("exile")


class _Reached:
    def __init__(self) -> None:
        self.chosen: list[PersonId] = []
        self.batches = 0

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.batches += 1
        self.chosen += [event.chosen for event in events if isinstance(event, GroupDecisionReachedEvent)]


def _world_where_aki_and_haru_voted_for_natsu() -> tuple[WiredWorld, _Reached]:
    design = compose_world(
        nouns(
            spots=[spot("square")],
            characters=[character(person.value, "square") for person in (AKI, HARU, NATSU)],
            group_decisions=[EXILE],
        ),
        group_decision_rules=[everyone_votes_on(EXILE)],
    )
    decision = GroupDecision.not_started(EXILE)
    decision.start(EVERYONE, EVERYONE)
    decision.cast(AKI, VoteFor(NATSU))
    decision.cast(HARU, VoteFor(NATSU))
    world = WiredWorld(design, decision, healthy(AKI), healthy(HARU), healthy(NATSU))
    handler = WithdrawFromGroupDecisionHandler(WithdrawFromGroupDecisions(world.scope))
    world.distributor.register_handler(PersonFellEvent, handler)
    world.distributor.register_handler(PersonDiedEvent, handler)
    reached = _Reached()
    world.distributor.register_receiver(reached)
    return world, reached


def _exile(session: WorldSession) -> GroupDecisionMemento:
    return session.aggregates().group_decision(EXILE).memento()


class TestWithdrawFromGroupDecisionHandler:
    """倒れた人・死んだ人を、開いている集団の決定から体の状態に合わせて外す挙動を保証する。"""

    def test_ballots_for_person_who_fell_and_died_return_and_they_are_not_chosen(self) -> None:
        """アキとハルがナツに入れ、ナツだけがまだ入れていないときに、ナツが倒れた同じ確定で死ぬと、2 人の票は戻り、ナツは選ばれず、投票は開いたまま。"""
        world, reached = _world_where_aki_and_haru_voted_for_natsu()

        world.scope.run(falls_and_dies(NATSU))

        exile = world.read(_exile)
        assert reached.chosen == []
        assert (exile.open, exile.ballots, exile.voters, exile.choices) == (
            True,
            frozenset(),
            frozenset({AKI, HARU}),
            frozenset({AKI, HARU}),
        )

    def test_person_who_fell_leaves_voters_and_stays_a_choice(self) -> None:
        """アキとハルがナツに入れ、ナツだけがまだ入れていないときに、ナツが倒れるだけだと、ナツは投票する人から外れ、残りの票でナツが選ばれる。"""
        world, reached = _world_where_aki_and_haru_voted_for_natsu()

        world.scope.run(falls(NATSU))

        assert reached.chosen == [NATSU]

    def test_second_reaction_to_the_same_death_changes_nothing(self) -> None:
        """ナツが倒れた同じ確定で死ぬと、倒れたことへの反応で外し終わり、死んだことへの反応は何も確定しないので、受け口に届くまとまりは元の確定と最初の反応の 2 つだけ。"""
        world, reached = _world_where_aki_and_haru_voted_for_natsu()

        world.scope.run(falls_and_dies(NATSU))

        assert reached.batches == 2
