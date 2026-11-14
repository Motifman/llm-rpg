from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import AnnouncementTo
from ai_rpg_world.game_world.domain.declaration.verb.noticed_on_waking import NoticedOnWaking
from ai_rpg_world.game_world.domain.declaration.verb.sight_texts_declaration import SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.exception.perception_exception import PerceptionTargetNotGivenException
from ai_rpg_world.game_world.domain.perception import NoTarget, Salience, SightStimulus, Stimulus
from ai_rpg_world.game_world.domain.value_object import DisplayName, SpotId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import Occupant


@final
@dataclass(frozen=True)
class Silent:
    pass


@final
@dataclass(frozen=True)
class NoFailureWitness:
    pass


@final
@dataclass(frozen=True)
class PerceptionDeclaration:
    witness: SightTextsDeclaration
    target: SightTextsDeclaration | NoticedOnWaking | NoTarget
    sound: SoundDeclaration | Silent
    seen_in_dark: bool
    announcement: AnnouncementTo | NoAnnouncement
    on_failure: SightTextsDeclaration | NoFailureWitness
    salience: Salience

    def seen_at(
        self, where: SpotId, actor: Occupant, names: Mapping[str, DisplayName], at: WorldTick
    ) -> tuple[Stimulus, ...]:
        if not isinstance(self.target, NoTarget):
            raise PerceptionTargetNotGivenException(
                f"the perception tells a target, but none is given at {where.value}"
            )
        people = {"actor": actor.person}
        sight = SightStimulus(
            where=where,
            witness=self.witness.about_named(people, names),
            target=NoTarget(),
            seen_in_dark=self.seen_in_dark,
            manner=Openly(),
            actor_departed=actor.is_departed(),
            involved=(actor.person,),
            salience=self.salience,
            always_delivered=False,
            at=at,
        )
        if isinstance(self.sound, Silent):
            return (sight,)
        return (sight, self.sound.noise_at(where, people, names, self.salience, at))

    def requirements(self) -> Requirements:
        if isinstance(self.announcement, NoAnnouncement):
            return Requirements.nothing()
        return self.announcement.requirements()

    def placeholders(self) -> frozenset[str]:
        names = set(self.witness.placeholders())
        for part in (self.target, self.sound, self.on_failure):
            if isinstance(part, (SightTextsDeclaration, SoundDeclaration, NoticedOnWaking)):
                names |= part.placeholders()
        if isinstance(self.announcement, AnnouncementTo):
            names |= self.announcement.text.placeholders()
        return frozenset(names)
