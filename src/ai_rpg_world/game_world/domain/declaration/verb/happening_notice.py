from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sight_texts_declaration import SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Salience
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class SightAt:
    spot: SpotDeclaration
    texts: SightTextsDeclaration
    salience: Salience

    def requirements(self) -> Requirements:
        return Requirements.nothing()

    def addressees(self, facts: WorldFacts, trigger: Trigger) -> frozenset[PersonId]:
        return frozenset()


@final
@dataclass(frozen=True)
class SoundFrom:
    spot: SpotDeclaration
    sound: SoundDeclaration
    salience: Salience

    def requirements(self) -> Requirements:
        return Requirements.nothing()

    def addressees(self, facts: WorldFacts, trigger: Trigger) -> frozenset[PersonId]:
        return frozenset()


@final
@dataclass(frozen=True)
class AnnouncementTo:
    audience: PeopleSelection
    text: TextWithUnassignedPeople
    salience: Salience

    def requirements(self) -> Requirements:
        return self.audience.requirements()

    def addressees(self, facts: WorldFacts, trigger: Trigger) -> frozenset[PersonId]:
        return self.audience.select(facts, trigger)


@final
@dataclass(frozen=True)
class NoNotice:
    def requirements(self) -> Requirements:
        return Requirements.nothing()

    def addressees(self, facts: WorldFacts, trigger: Trigger) -> frozenset[PersonId]:
        return frozenset()


HappeningNotice = SightAt | SoundFrom | AnnouncementTo
