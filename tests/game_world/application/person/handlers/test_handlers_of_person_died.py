from __future__ import annotations

from collections.abc import Callable

import pytest

from ai_rpg_world.game_world.application.person.decide_death_outcome import DecideDeathOutcome
from ai_rpg_world.game_world.application.person.handlers.decide_death_outcome_handler import (
    DecideDeathOutcomeHandler,
)
from ai_rpg_world.game_world.application.person.handlers.place_departed_person_handler import (
    PlaceDepartedPersonHandler,
)
from ai_rpg_world.game_world.application.person.place_departed_person import PlaceDepartedPerson
from ai_rpg_world.game_world.application.world_progress.handlers.withdraw_from_group_decision_handler import (
    WithdrawFromGroupDecisionHandler,
)
from ai_rpg_world.game_world.application.world_progress.withdraw_from_group_decisions import (
    WithdrawFromGroupDecisions,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.person import Died, PersonDiedEvent, PersonFellEvent, PersonOutcomes
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, PersonBody, Whereabouts
from ai_rpg_world.game_world.domain.world_progress import GroupDecision, VoteFor
from tests.game_world.application.world_for_handler_tests import WORLD, WiredWorld, falls_and_dies, healthy, rules
from tests.game_world.support.verb_declarations_for_tests import everyone_votes_on
from tests.game_world.support.world_design_for_tests import character, compose_world, group_decision, nouns, spot

AKI = PersonId("aki")
HARU = PersonId("haru")
NATSU = PersonId("natsu")
EVERYONE = (AKI, HARU, NATSU)
SQUARE = spot("square")
EXILE = group_decision("exile")


def _world_with_handlers_in(order: str) -> WiredWorld:
    design = compose_world(
        nouns(
            spots=[SQUARE],
            characters=[character(person.value, "square") for person in EVERYONE],
            group_decisions=[EXILE],
        ),
        group_decision_rules=[everyone_votes_on(EXILE)],
        world_rules=rules(departed_persons_act=True),
    )
    whereabouts = Whereabouts.start(WORLD)
    for person in EVERYONE:
        whereabouts.place(PersonBody(person), SQUARE)
    exile = GroupDecision.not_started(EXILE)
    exile.start(frozenset(EVERYONE), frozenset(EVERYONE))
    exile.cast(AKI, VoteFor(NATSU))
    exile.cast(HARU, VoteFor(NATSU))
    world = WiredWorld(
        design, whereabouts, exile, PersonOutcomes.start(WORLD, EVERYONE), *(healthy(person) for person in EVERYONE)
    )
    withdraw = WithdrawFromGroupDecisionHandler(WithdrawFromGroupDecisions(world.scope))
    distributor = world.distributor
    registrations: list[Callable[[], None]] = [
        lambda: distributor.register_handler(
            PersonDiedEvent, DecideDeathOutcomeHandler(DecideDeathOutcome(world.scope))
        ),
        lambda: distributor.register_handler(
            PersonDiedEvent, PlaceDepartedPersonHandler(PlaceDepartedPerson(world.scope))
        ),
        lambda: distributor.register_handler(PersonDiedEvent, withdraw),
    ]
    for register in registrations if order == "declared" else reversed(registrations):
        register()
    world.distributor.register_handler(PersonFellEvent, withdraw)
    return world


def _state_after_natsu_died(session: WorldSession) -> tuple[object, ...]:
    world = session.aggregates()
    exile = world.group_decision(EXILE).memento()
    return (
        world.outcomes().outcome_of(NATSU),
        frozenset(world.whereabouts().occupants_at(SQUARE)),
        (exile.open, exile.ballots, exile.choices),
    )


class TestHandlersOfPersonDied:
    """人が死んだことに反応する 3 つのハンドラが、互いの登録の順に頼らないことを保証する。"""

    @pytest.mark.parametrize("order", ["declared", "reversed"])
    def test_every_reaction_to_a_death_applies_whatever_the_order(self, order: str) -> None:
        """アキとハルがナツに入れたあと、去った人の動く世界でナツが倒れて死ぬと、どの順に登録しても、結末は Died、広場にはナツの体と去ったナツがいて、2 人の票は戻り、ナツは選ばれる人から外れる。"""
        world = _world_with_handlers_in(order)

        world.scope.run(falls_and_dies(NATSU))

        assert world.distributor.refused_handlers == {}
        assert world.read(_state_after_natsu_died) == (
            Died(),
            frozenset({*(PersonBody(person) for person in EVERYONE), DepartedPerson(NATSU)}),
            (True, frozenset(), frozenset({AKI, HARU})),
        )
