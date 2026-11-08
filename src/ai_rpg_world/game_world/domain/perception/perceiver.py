from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.exception.perception_exception import DeadPersonCannotPerceiveAsLivingException
from ai_rpg_world.game_world.domain.lighting.lighting import Lighting
from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SightQuality
from ai_rpg_world.game_world.domain.perception.surroundings_awareness import (
    Aware,
    AwareOnWaking,
    SurroundingsAwareness,
    Unaware,
)
from ai_rpg_world.game_world.domain.person.life_state import Alive, Down
from ai_rpg_world.game_world.domain.sound.hearing_quality import HearingQuality, HearsClearly, HearsNothing
from ai_rpg_world.game_world.domain.sound.hearing_values import HearingValues
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.sound.sound_network import NotReached, SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, Probability, SpotId
from ai_rpg_world.game_world.domain.whereabouts.location import Location


@final
@dataclass(frozen=True)
class LivingPerceiver:
    person: PersonId
    life: Alive | Down
    location: Location
    attentive: bool

    def __post_init__(self) -> None:
        if not isinstance(self.life, (Alive, Down)):
            raise DeadPersonCannotPerceiveAsLivingException(
                f"{self.person.value} is not alive or down, got {self.life!r}"
            )

    def notices_surroundings(self, involved: bool) -> SurroundingsAwareness:
        if isinstance(self.life, Alive):
            return Aware()
        return AwareOnWaking() if involved else Unaware()

    def feels_body_of(self, person: PersonId) -> bool:
        return self.person == person

    def is_at(self, spot: SpotId) -> bool:
        return self.location.is_at(spot)

    def sight_in(self, lighting: Lighting) -> SightQuality:
        return lighting.sight()

    def sees_departed_people(self) -> bool:
        return False

    def notices_stealthy_act(self, chance: Probability, attentive_bonus: Probability, random: RandomSource) -> bool:
        if self.attentive:
            chance = chance + attentive_bonus
        return random.next_fraction() < chance.value

    def hears(self, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues) -> HearingQuality:
        return values.quality(self.location.sound_level_from(origin, loudness, reach, values), self.attentive)


@final
@dataclass(frozen=True)
class DepartedPerceiver:
    person: PersonId
    location: Location

    def notices_surroundings(self, involved: bool) -> SurroundingsAwareness:
        return Aware()

    def feels_body_of(self, person: PersonId) -> bool:
        return False

    def is_at(self, spot: SpotId) -> bool:
        return self.location.is_at(spot)

    def sight_in(self, lighting: Lighting) -> SightQuality:
        return SeesClearly()

    def sees_departed_people(self) -> bool:
        return True

    def notices_stealthy_act(self, chance: Probability, attentive_bonus: Probability, random: RandomSource) -> bool:
        return True

    def hears(self, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues) -> HearingQuality:
        if isinstance(self.location.sound_level_from(origin, loudness, reach, values), NotReached):
            return HearsNothing()
        return HearsClearly()


Perceiver = LivingPerceiver | DepartedPerceiver
