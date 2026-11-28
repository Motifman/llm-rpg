from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.lighting import Lighting, LightingConditions
from ai_rpg_world.game_world.domain.people import PeopleSeenBy
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.perception import Perceiver
from ai_rpg_world.game_world.domain.perception.perceiver_in_world import perceiver_in_world
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound import HearingValues, Loudness, SoundNetwork, SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId


@final
class WorldPerceptionSenses:
    def __init__(self, facts: WorldFacts) -> None:
        self._facts = facts
        self._lighting: dict[SpotId, Lighting] = {}
        self._reach: dict[tuple[SpotId, Loudness], SoundReach] = {}

    def lighting_at(self, spot: SpotId) -> Lighting:
        if spot not in self._lighting:
            self._lighting[spot] = LightingConditions.at(self._facts.nouns().spot_of(spot), self._facts).lighting()
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
        return PeopleSeenBy.in_world(viewer, self._facts)

    def random(self) -> RandomSource:
        return self._facts.random()

    def stealth(self) -> StealthRule:
        return self._facts.rules().stealth

    def hearing(self) -> HearingValues:
        return self._facts.rules().hearing


def perceivers_in_world(facts: WorldFacts) -> tuple[Perceiver, ...]:
    return tuple(perceiver_of(facts, person) for person in facts.people())


def perceiver_of(facts: WorldFacts, person: PersonId) -> Perceiver:
    # 耳を澄ましているかを世界の状態に持たないので、誰も耳を澄ましていないものとして知覚する。
    return perceiver_in_world(facts, person, attentive=False)
