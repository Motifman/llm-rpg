from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.manner import Openly, Stealthily
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.exception.perception_exception import TargetNotInvolvedException
from ai_rpg_world.game_world.domain.lighting.lighting import Lighting
from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesNothing, SeesShapes, SightQuality
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.no_target import NoTarget
from ai_rpg_world.game_world.domain.perception.not_noticed_later import NotNoticedLater
from ai_rpg_world.game_world.domain.perception.not_seen_in_dim import NotSeenInDim
from ai_rpg_world.game_world.domain.perception.not_seen_without_actor import NotSeenWithoutActor
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived, PerceptionOutcome
from ai_rpg_world.game_world.domain.perception.salience import Notable, Salience
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.value_object import PersonId, Probability, SpotId, WorldTick


@final
@dataclass(frozen=True)
class SightTexts:
    clear: TextAboutPeople
    dim: TextAboutPeople | NotSeenInDim
    unseen_actor: TextAboutPeople | NotSeenWithoutActor
    noticed_later: TextAboutPeople | NotNoticedLater


@final
@dataclass(frozen=True)
class SightTarget:
    person: PersonId
    texts: SightTexts


@final
@dataclass(frozen=True)
class SightStimulus:
    where: SpotId
    witness: SightTexts
    target: SightTarget | NoTarget
    seen_in_dark: bool
    manner: Openly | Stealthily
    actor_departed: bool
    involved: tuple[PersonId, ...]
    salience: Salience
    always_delivered: bool
    at: WorldTick

    def __post_init__(self) -> None:
        if isinstance(self.target, SightTarget) and self.target.person not in self.involved:
            raise TargetNotInvolvedException(
                f"target {self.target.person.value} is not among involved {[p.value for p in self.involved]}"
            )

    def perceived_by(
        self,
        perceiver: Perceiver,
        lighting: Lighting,
        view: PeopleAsSeen,
        random: RandomSource,
        stealth: StealthRule,
    ) -> PerceptionOutcome:
        if not perceiver.is_at(self.where):
            return NotPerceived()
        if isinstance(self.target, SightTarget) and self.target.person == perceiver.person:
            texts, chances = self.target.texts, stealth.notice_by_target
        else:
            texts, chances = self.witness, stealth.notice_by_bystander
        involved = perceiver.person in self.involved
        return perceiver.notices_surroundings(involved).outcome(
            when_aware=lambda: self._seen(perceiver, texts, lighting, view, random, chances, stealth, involved),
            on_waking=lambda: self._noticed_on_waking(texts, view),
        )

    def _seen(
        self,
        perceiver: Perceiver,
        texts: SightTexts,
        lighting: Lighting,
        view: PeopleAsSeen,
        random: RandomSource,
        chances: Mapping[SightQuality, Probability],
        stealth: StealthRule,
        involved: bool,
    ) -> PerceptionOutcome:
        sight = perceiver.sight_in(lighting)
        if isinstance(sight, SeesNothing):
            if not self.seen_in_dark:
                return NotPerceived()
            sight = SeesShapes()
        text = self._text_for(perceiver, texts, sight, view)
        if text is None:
            return NotPerceived()
        if self.manner == Stealthily() and not perceiver.notices_stealthy_act(
            chances[sight], stealth.attentive_bonus, random
        ):
            return NotPerceived()
        return Perceived.of(
            perceiver=perceiver.person,
            text=text,
            quality=sight,
            happened_at=self.at,
            worth_attention=involved or self.salience == Notable(),
        )

    def _text_for(
        self, perceiver: Perceiver, texts: SightTexts, sight: SeesClearly | SeesShapes, view: PeopleAsSeen
    ) -> TextWithAssignedPeople | None:
        if self.actor_departed and not perceiver.sees_departed_people():
            if isinstance(texts.unseen_actor, NotSeenWithoutActor):
                return None
            return texts.unseen_actor.seen_by(view) if sight == SeesClearly() else texts.unseen_actor.unidentified()
        if sight == SeesClearly():
            return texts.clear.seen_by(view)
        if isinstance(texts.dim, NotSeenInDim):
            return None
        return texts.dim.unidentified()

    def _noticed_on_waking(self, texts: SightTexts, view: PeopleAsSeen) -> MissedNotice | NotNoticedLater:
        if isinstance(texts.noticed_later, NotNoticedLater):
            return NotNoticedLater()
        return MissedNotice(text=texts.noticed_later.seen_by(view), happened_at=self.at)
