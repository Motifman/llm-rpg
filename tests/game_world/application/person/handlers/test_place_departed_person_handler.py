from __future__ import annotations

from ai_rpg_world.game_world.application.person.handlers.place_departed_person_handler import (
    PlaceDepartedPersonHandler,
)
from ai_rpg_world.game_world.application.person.place_departed_person import PlaceDepartedPerson
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.person import PersonDiedEvent
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, DepartedPerson, OpenArea, PersonBody, Whereabouts
from tests.game_world.application.world_for_handler_tests import WORLD, WiredWorld, falls_and_dies, healthy, rules
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

NATSU = PersonId("natsu")
CAVE = spot("cave")


def _world(*, departed_persons_act: bool) -> WiredWorld:
    design = compose_world(
        nouns(spots=[CAVE], characters=[character("natsu", "cave")]),
        world_rules=rules(departed_persons_act=departed_persons_act),
    )
    whereabouts = Whereabouts.start(WORLD)
    whereabouts.place(PersonBody(NATSU), CAVE)
    world = WiredWorld(design, whereabouts, healthy(NATSU))
    world.distributor.register_handler(PersonDiedEvent, PlaceDepartedPersonHandler(PlaceDepartedPerson(world.scope)))
    return world


def _occupants_in_cave(session: WorldSession) -> frozenset[object]:
    return frozenset(session.aggregates().whereabouts().occupants_at(CAVE))


class TestPlaceDepartedPersonHandler:
    """人が死んだことへの反応で、去った人の動く世界でだけ、体のある場所に去った人を置く挙動を保証する。"""

    def test_departed_person_is_placed_beside_the_body_where_departed_people_act(self) -> None:
        """去った人の動く世界でナツが洞窟で死ぬと、ナツの体は洞窟に残り、去ったナツが洞窟の区画の外に置かれる。"""
        world = _world(departed_persons_act=True)

        world.scope.run(falls_and_dies(NATSU))

        assert world.read(_occupants_in_cave) == {PersonBody(NATSU), DepartedPerson(NATSU)}
        assert world.read(lambda session: session.aggregates().whereabouts().location_of(DepartedPerson(NATSU))) == (
            AtSpot(spot=SpotId("cave"), section=OpenArea())
        )

    def test_nobody_is_placed_where_departed_people_do_not_act(self) -> None:
        """去った人の動かない世界でナツが洞窟で死ぬと、洞窟にはナツの体だけが残る。"""
        world = _world(departed_persons_act=False)

        world.scope.run(falls_and_dies(NATSU))

        assert world.read(_occupants_in_cave) == {PersonBody(NATSU)}
