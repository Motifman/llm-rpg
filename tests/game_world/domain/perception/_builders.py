from __future__ import annotations

from collections.abc import Mapping

from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonHandle, PersonRef, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception.perceiver import DepartedPerceiver, LivingPerceiver
from ai_rpg_world.game_world.domain.person.life_state import Alive, Down, Starvation
from ai_rpg_world.game_world.domain.value_object import DescriptionText, PersonId, SpotId, Ticks, WorldTick
from ai_rpg_world.game_world.domain.whereabouts.location import AtSpot, OpenArea, TravelInProgress
from ai_rpg_world.game_world.domain.whereabouts.route import Route
from tests.game_world.domain.whereabouts._builders import path

ALICE = PersonId("alice")
BOB = PersonId("bob")
CAROL = PersonId("carol")
SQUARE = SpotId("square")
HALL = SpotId("hall")


def ref(handle: int) -> PersonRef:
    return PersonRef(
        handle=PersonHandle(handle), appearance=DescriptionText(f"人{handle}"), visible_name=NoVisibleName()
    )


class PeopleByHandle:
    def __init__(self, refs: Mapping[PersonId, PersonRef]) -> None:
        self._refs = dict(refs)

    def ref_of(self, person: PersonId) -> PersonRef:
        return self._refs[person]


VIEW = PeopleByHandle({ALICE: ref(1), BOB: ref(2), CAROL: ref(3)})


def about(template: str, **people: PersonId) -> TextAboutPeople:
    return TextWithUnassignedPeople(template).about(people)


def at(spot: SpotId) -> AtSpot:
    return AtSpot(spot=spot, section=OpenArea())


def awake(person: PersonId, spot: SpotId = SQUARE, *, attentive: bool = False) -> LivingPerceiver:
    return LivingPerceiver(person=person, life=Alive(), location=at(spot), attentive=attentive)


def fallen(person: PersonId, spot: SpotId = SQUARE) -> LivingPerceiver:
    return LivingPerceiver(
        person=person, life=Down(fell_at=WorldTick(0), cause=Starvation()), location=at(spot), attentive=False
    )


def departed(person: PersonId, spot: SpotId = SQUARE) -> DepartedPerceiver:
    return DepartedPerceiver(person=person, location=at(spot))


CELLAR = SpotId("cellar")


def travelling(person: PersonId, *, attentive: bool = False) -> LivingPerceiver:
    """広場から広間を経て地下室へ向かう途中で、いまは広間と地下室のあいだの区間を歩いている。"""
    route = Route(start=SQUARE, passages=(path("square_hall", "square", "hall"), path("hall_cellar", "hall", "cellar")))
    return LivingPerceiver(
        person=person,
        life=Alive(),
        location=TravelInProgress(route=route, passage_index=1, ticks_left_on_passage=Ticks(1), departed_from=SQUARE),
        attentive=attentive,
    )


def setting_out(person: PersonId) -> LivingPerceiver:
    route = Route(start=SQUARE, passages=(path("square_hall", "square", "hall"),))
    return LivingPerceiver(
        person=person,
        life=Alive(),
        location=TravelInProgress(route=route, passage_index=0, ticks_left_on_passage=Ticks(1), departed_from=SQUARE),
        attentive=False,
    )
