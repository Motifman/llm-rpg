from __future__ import annotations

from typing import Protocol

from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.lighting.lighting import Lighting
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound.hearing_values import HearingValues
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.sound.sound_network import SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId


class PerceptionSenses(Protocol):
    def lighting_at(self, spot: SpotId) -> Lighting: ...

    def reach_of(self, origin: SpotId, loudness: Loudness) -> SoundReach: ...

    def view_for(self, viewer: PersonId) -> PeopleAsSeen: ...

    def random(self) -> RandomSource: ...

    def stealth(self) -> StealthRule: ...

    def hearing(self) -> HearingValues: ...
