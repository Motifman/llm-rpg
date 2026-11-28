from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sight_texts_declaration import SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import PersonInNoticeTextException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    AnnouncementStimulus,
    Noise,
    NoTarget,
    Salience,
    SightStimulus,
    Stimulus,
)
from ai_rpg_world.game_world.domain.perception.people_present import PeopleWhoWereThere
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class NoticeReach:
    audience: frozenset[PersonId]
    present: PeopleWhoWereThere


@final
@dataclass(frozen=True)
class SightAt:
    spot: SpotDeclaration
    texts: SightTextsDeclaration
    salience: Salience

    def __post_init__(self) -> None:
        _refuse_people("sight_at", self.texts.placeholders())

    def requirements(self) -> Requirements:
        return Requirements.nothing()

    def stimuli(
        self, audience: frozenset[PersonId], present: PeopleWhoWereThere, at: WorldTick
    ) -> tuple[Stimulus, ...]:
        return (
            SightStimulus(
                where=self.spot.spot_id,
                witness=self.texts.about_named({}, {}),
                target=NoTarget(),
                seen_in_dark=False,
                manner=Openly(),
                actor_departed=False,
                involved=(),
                salience=self.salience,
                always_delivered=False,
                at=at,
                present=present,
            ),
        )

    def reach_before_the_effect(self, facts: WorldFacts, trigger: Trigger) -> NoticeReach:
        return NoticeReach(audience=frozenset(), present=PeopleWhoWereThere.before_the_effect(facts))


@final
@dataclass(frozen=True)
class SoundFrom:
    spot: SpotDeclaration
    sound: SoundDeclaration
    salience: Salience

    def __post_init__(self) -> None:
        _refuse_people("sound_from", self.sound.placeholders())

    def requirements(self) -> Requirements:
        return Requirements.nothing()

    def stimuli(
        self, audience: frozenset[PersonId], present: PeopleWhoWereThere, at: WorldTick
    ) -> tuple[Stimulus, ...]:
        heard = self.sound.heard_at(self.spot.spot_id, {}, {}, Noise(), self.salience, at)
        return (replace(heard, present=present),)

    def reach_before_the_effect(self, facts: WorldFacts, trigger: Trigger) -> NoticeReach:
        return NoticeReach(audience=frozenset(), present=PeopleWhoWereThere.before_the_effect(facts))


@final
@dataclass(frozen=True)
class AnnouncementTo:
    audience: PeopleSelection
    text: TextWithUnassignedPeople
    salience: Salience

    def __post_init__(self) -> None:
        _refuse_people("announcement_to", self.text.placeholders())

    def requirements(self) -> Requirements:
        return self.audience.requirements()

    def stimuli(
        self, audience: frozenset[PersonId], present: PeopleWhoWereThere, at: WorldTick
    ) -> tuple[Stimulus, ...]:
        return (AnnouncementStimulus(audience=audience, text=self.text.about({}), salience=self.salience, at=at),)

    def reach_before_the_effect(self, facts: WorldFacts, trigger: Trigger) -> NoticeReach:
        return NoticeReach(audience=self.audience.select(facts, trigger), present=PeopleWhoWereThere())


@final
@dataclass(frozen=True)
class NoNotice:
    def requirements(self) -> Requirements:
        return Requirements.nothing()

    def stimuli(
        self, audience: frozenset[PersonId], present: PeopleWhoWereThere, at: WorldTick
    ) -> tuple[Stimulus, ...]:
        return ()

    def reach_before_the_effect(self, facts: WorldFacts, trigger: Trigger) -> NoticeReach:
        return NoticeReach(audience=frozenset(), present=PeopleWhoWereThere())


HappeningNotice = SightAt | SoundFrom | AnnouncementTo


def _refuse_people(notice: str, placeholders: frozenset[str]) -> None:
    # 出来事には行った人がおらず、知らせの文に当てる人がいない。書けば発火のたびに文を作れない。
    if placeholders:
        raise PersonInNoticeTextException(f"the {notice} notice cannot name people, but names {sorted(placeholders)}")
