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
from ai_rpg_world.game_world.domain.sound.sound_level import SoundLevel
from ai_rpg_world.game_world.domain.sound.sound_network import NotReached, SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, Probability, SpotId
from ai_rpg_world.game_world.domain.whereabouts.location import AtSpot, Location, TravelInProgress


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
        return _is_at(self.location, spot)

    def sight_in(self, lighting: Lighting) -> SightQuality:
        return lighting.sight()

    def sees_departed_people(self) -> bool:
        return False

    def notices_stealthy_act(self, chance: Probability, attentive_bonus: Probability, random: RandomSource) -> bool:
        if self.attentive:
            chance = chance + attentive_bonus
        return random.next_fraction() < chance.value

    def hears(self, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues) -> HearingQuality:
        return values.quality(_level_reaching(self.location, origin, loudness, reach, values), self.attentive)


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
        return _is_at(self.location, spot)

    def sight_in(self, lighting: Lighting) -> SightQuality:
        return SeesClearly()

    def sees_departed_people(self) -> bool:
        return True

    def notices_stealthy_act(self, chance: Probability, attentive_bonus: Probability, random: RandomSource) -> bool:
        return True

    def hears(self, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues) -> HearingQuality:
        if isinstance(_level_reaching(self.location, origin, loudness, reach, values), NotReached):
            return HearsNothing()
        return HearsClearly()


Perceiver = LivingPerceiver | DepartedPerceiver


def _is_at(location: Location, spot: SpotId) -> bool:
    return isinstance(location, AtSpot) and location.spot == spot


_HEARD_WHILE_TRAVELLING = frozenset({Loudness.LOUD, Loudness.VERY_LOUD})


def _level_reaching(
    location: Location, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues
) -> SoundLevel | NotReached:
    if isinstance(location, AtSpot):
        return reach.level_at(location.spot)
    if loudness not in _HEARD_WHILE_TRAVELLING or origin not in _ends_of_current_passage(location):
        return NotReached()
    # 通路の上はどの場所でもないので、端の場所から 1 つ隣にいるものとして聞く。
    return values.level_of(loudness).weakened_by(values.loss_per_passage)


def _ends_of_current_passage(travel: TravelInProgress) -> tuple[SpotId, SpotId]:
    index = travel.passage_index
    start = travel.route.start if index == 0 else travel.route.end_of_passage(index - 1)
    return (start, travel.route.end_of_passage(index))
