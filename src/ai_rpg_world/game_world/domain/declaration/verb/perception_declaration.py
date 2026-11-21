from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import final

from ai_rpg_world.game_world.domain.action.manner import Manner
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import AnnouncementTo
from ai_rpg_world.game_world.domain.declaration.verb.noticed_on_waking import NoticedOnWaking
from ai_rpg_world.game_world.domain.declaration.verb.sight_texts_declaration import SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.exception.perception_exception import PerceptionTargetNotGivenException
from ai_rpg_world.game_world.domain.people import NameInText
from ai_rpg_world.game_world.domain.perception import (
    NoTarget,
    Salience,
    SightStimulus,
    SightTarget,
    SoundSource,
    Stimulus,
)
from ai_rpg_world.game_world.domain.perception.people_present import PeoplePresent
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
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
        self,
        where: SpotId,
        actor: Occupant,
        names: Mapping[str, NameInText],
        at: WorldTick,
        *,
        target: PersonId | NoTarget,
        manner: Manner,
        source: SoundSource,
        present: PeoplePresent,
    ) -> tuple[Stimulus, ...]:
        people = {"actor": actor.person} | ({"target": target} if isinstance(target, PersonId) else {})
        involved = tuple(people.values())
        sight_target = self._sight_target(where, target, people, names)
        sight = SightStimulus(
            where=where,
            witness=self.witness.about_named(people, names),
            target=sight_target,
            seen_in_dark=self.seen_in_dark,
            manner=manner,
            actor_departed=actor.is_departed(),
            involved=involved,
            salience=self.salience,
            always_delivered=False,
            at=at,
            present=present,
        )
        if isinstance(self.sound, Silent):
            return (sight,)
        return (sight, replace(self.sound.heard_at(where, people, names, source, self.salience, at), present=present))

    def failure_seen_at(
        self,
        where: SpotId,
        actor: Occupant,
        names: Mapping[str, NameInText],
        at: WorldTick,
        *,
        target: PersonId | NoTarget,
        manner: Manner,
    ) -> tuple[Stimulus, ...]:
        if isinstance(self.on_failure, NoFailureWitness):
            return ()
        people = {"actor": actor.person} | ({"target": target} if isinstance(target, PersonId) else {})
        # 失敗の文は見ていた人への文だけで、相手が見る文を持たない。相手にも見ていた人の文を届ける。
        return (
            SightStimulus(
                where=where,
                witness=self.on_failure.about_named(people, names),
                target=NoTarget(),
                seen_in_dark=self.seen_in_dark,
                manner=manner,
                actor_departed=actor.is_departed(),
                involved=tuple(people.values()),
                salience=self.salience,
                always_delivered=False,
                at=at,
            ),
        )

    def _sight_target(
        self,
        where: SpotId,
        target: PersonId | NoTarget,
        people: Mapping[str, PersonId],
        names: Mapping[str, NameInText],
    ) -> SightTarget | NoTarget:
        if isinstance(self.target, NoTarget):
            return NoTarget()
        if not isinstance(target, PersonId):
            raise PerceptionTargetNotGivenException(
                f"the perception tells a target, but none is given at {where.value}"
            )
        return self.target.target_of(target, people, names)

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
