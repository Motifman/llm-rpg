from __future__ import annotations

from ai_rpg_world.game_world.application.person.decide_death_outcome import DecideDeathOutcome
from ai_rpg_world.game_world.application.person.handlers.decide_death_outcome_handler import (
    DecideDeathOutcomeHandler,
)
from ai_rpg_world.game_world.domain.person import Died, PersonDiedEvent, PersonOutcomes, Undecided
from ai_rpg_world.game_world.domain.value_object import PersonId
from tests.game_world.application.world_for_handler_tests import WORLD, WiredWorld, falls, falls_and_dies, healthy
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

NATSU = PersonId("natsu")


def _world() -> WiredWorld:
    design = compose_world(nouns(spots=[spot("cave")], characters=[character("natsu", "cave")]))
    world = WiredWorld(design, PersonOutcomes.start(WORLD, (NATSU,)), healthy(NATSU))
    world.distributor.register_handler(PersonDiedEvent, DecideDeathOutcomeHandler(DecideDeathOutcome(world.scope)))
    return world


class TestDecideDeathOutcomeHandler:
    """人が死んだことへの反応で、その人の結末を決める挙動を保証する。"""

    def test_person_who_died_gets_died_outcome(self) -> None:
        """ナツが倒れて同じ確定で死ぬと、ナツの結末は Died になる。"""
        world = _world()

        world.scope.run(falls_and_dies(NATSU))

        assert world.read(lambda session: session.facts().outcomes().outcome_of(NATSU)) == Died()

    def test_person_who_only_fell_stays_undecided(self) -> None:
        """ナツが倒れただけで死んでいないとき、ナツの結末は決まらない。"""
        world = _world()

        world.scope.run(falls(NATSU))

        assert world.read(lambda session: session.facts().outcomes().outcome_of(NATSU)) == Undecided()
