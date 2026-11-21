from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perceiver_in_world import perceiver_in_world
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.whereabouts.location import Location

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class WhoeverIsThere:
    def position(self, perceiver: Perceiver) -> Perceiver:
        return perceiver


@final
@dataclass(frozen=True)
class PeopleWhoWereThere:
    places: Mapping[PersonId, Location] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "places", MappingProxyType(dict(self.places)))

    @classmethod
    def before_the_effect(cls, facts: WorldFacts) -> PeopleWhoWereThere:
        places: dict[PersonId, Location] = {}
        for person in facts.people():
            place = perceiver_in_world(facts, person, attentive=False).perceives_from()
            if place is not None:
                places[person] = place
        return cls(places)

    def position(self, perceiver: Perceiver) -> Perceiver:
        # 効果の前に居場所の無かった人 (もう死んでいた人、もう外れていた人) は、いまのままにする (D2207)
        place = self.places.get(perceiver.person)
        return perceiver if place is None else perceiver.placed_at(place)


PeoplePresent = WhoeverIsThere | PeopleWhoWereThere
