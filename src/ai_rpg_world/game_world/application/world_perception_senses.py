from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.lighting import Lighting, LightingConditions
from ai_rpg_world.game_world.domain.people import PeopleSeenBy
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.perception import Perceiver
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound import HearingValues, Loudness, SoundNetwork, SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId
from ai_rpg_world.game_world.domain.whereabouts import PersonBody


@final
class WorldPerceptionSenses:
    def __init__(self, facts: WorldFacts) -> None:
        self._facts = facts
        self._lighting: dict[SpotId, Lighting] = {}
        self._reach: dict[tuple[SpotId, Loudness], SoundReach] = {}

    def lighting_at(self, spot: SpotId) -> Lighting:
        if spot not in self._lighting:
            self._lighting[spot] = self._lighting_conditions_at(self._facts.nouns().spot_of(spot)).lighting()
        return self._lighting[spot]

    def reach_of(self, origin: SpotId, loudness: Loudness) -> SoundReach:
        if (origin, loudness) not in self._reach:
            hearing = self.hearing()
            passages = self._facts.passages().sound_carrying(self._facts.nouns().all_passages())
            network = SoundNetwork.through(passages, hearing.loss_per_passage)
            self._reach[(origin, loudness)] = network.spread(
                origin, hearing.level_of(loudness), hearing.quietest_audible()
            )
        return self._reach[(origin, loudness)]

    def view_for(self, viewer: PersonId) -> PeopleAsSeen:
        return PeopleSeenBy(
            viewer=viewer,
            register=self._facts.people_register(),
            name_tags=self._facts.rules().name_tags,
            knows_at_start=frozenset(self._facts.nouns().character_of(viewer).knows_at_start),
        )

    def random(self) -> RandomSource:
        return self._facts.random()

    def stealth(self) -> StealthRule:
        return self._facts.rules().stealth

    def hearing(self) -> HearingValues:
        return self._facts.rules().hearing

    def _lighting_conditions_at(self, spot: SpotDeclaration) -> LightingConditions:
        atmosphere = self._facts.atmospheres().atmosphere_of(spot)
        return LightingConditions(
            declared=atmosphere.lighting,
            outdoor=atmosphere.outdoor,
            dark_time_of_day=self._is_dark_time_of_day(),
            weather_obscures=self._weather_obscures_sight(),
            light_source_present=self._light_source_held_at(spot),
        )

    def _weather_obscures_sight(self) -> bool:
        weather = self._facts.weather_declaration()
        return weather.is_declared() and weather.obscures_sight(self._facts.weather().current())

    def _is_dark_time_of_day(self) -> bool:
        day_night = self._facts.day_night()
        return day_night.is_declared() and day_night.phase_at(self._facts.clock().time_of_day(day_night)).dark

    def _light_source_held_at(self, spot: SpotDeclaration) -> bool:
        return any(
            self._facts.item(item).gives_light()
            for occupant in self._facts.whereabouts().occupants_at(spot)
            # 去った人には手が無く、持ち物は倒れた体のほうにある。
            if occupant == PersonBody(occupant.person)
            for item in self._facts.inventory(occupant.person).held_items()
        )


def perceivers_in_world(facts: WorldFacts) -> tuple[Perceiver, ...]:
    departed_persons_act = facts.rules().departed_persons_act
    perceivers: list[Perceiver] = []
    for person in facts.people():
        vitals = facts.vitals(person)
        location = facts.whereabouts().location_of(vitals.occupant_in_world(departed_persons_act))
        # 耳を澄ましているかを世界の状態に持たないので、誰も耳を澄ましていないものとして知覚する。
        perceiver = vitals.perceiver_at(location, departed_persons_act, attentive=False)
        if perceiver is not None:
            perceivers.append(perceiver)
    return tuple(perceivers)
