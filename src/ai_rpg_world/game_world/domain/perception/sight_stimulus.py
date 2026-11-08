from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.manner import Openly, Stealthily
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.exception.perception_exception import TargetNotInvolvedException
from ai_rpg_world.game_world.domain.lighting.lighting import Lighting
from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesShapes, SightQuality
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

    def without_actor(self) -> SightTexts | NotSeenWithoutActor:
        if isinstance(self.unseen_actor, NotSeenWithoutActor):
            return NotSeenWithoutActor()
        return SightTexts(
            clear=self.unseen_actor,
            dim=self.unseen_actor,
            unseen_actor=self.unseen_actor,
            noticed_later=self.noticed_later,
        )

    def noticed_on_waking(self, view: PeopleAsSeen, at: WorldTick) -> MissedNotice | NotNoticedLater:
        if isinstance(self.noticed_later, NotNoticedLater):
            return NotNoticedLater()
        return MissedNotice(text=self.noticed_later.seen_by(view), happened_at=at)


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
            on_waking=lambda: texts.noticed_on_waking(view, self.at),
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
        visible = texts if not self.actor_departed or perceiver.sees_departed_people() else texts.without_actor()
        if isinstance(visible, NotSeenWithoutActor):
            return NotPerceived()
        sighting = _Sighting(
            stimulus=self,
            perceiver=perceiver,
            texts=visible,
            view=view,
            random=random,
            chances=chances,
            attentive_bonus=stealth.attentive_bonus,
            worth_attention=involved or self.salience == Notable(),
        )
        return perceiver.sight_in(lighting).read(sighting)


@final
@dataclass(frozen=True)
class _Sighting:
    stimulus: SightStimulus
    perceiver: Perceiver
    texts: SightTexts
    view: PeopleAsSeen
    random: RandomSource
    chances: Mapping[SightQuality, Probability]
    attentive_bonus: Probability
    worth_attention: bool

    def when_clear(self) -> PerceptionOutcome:
        return self._seen_as(self.texts.clear.seen_by(self.view), SeesClearly())

    def when_shapes(self) -> PerceptionOutcome:
        if isinstance(self.texts.dim, NotSeenInDim):
            return NotPerceived()
        return self._seen_as(self.texts.dim.unidentified(), SeesShapes())

    def when_nothing(self) -> PerceptionOutcome:
        return self.when_shapes() if self.stimulus.seen_in_dark else NotPerceived()

    def _seen_as(self, text: TextWithAssignedPeople, sight: SeesClearly | SeesShapes) -> PerceptionOutcome:
        if self.stimulus.manner == Stealthily() and not self.perceiver.notices_stealthy_act(
            self.chances[sight], self.attentive_bonus, self.random
        ):
            return NotPerceived()
        return Perceived(
            perceiver=self.perceiver.person,
            text=text,
            quality=sight,
            happened_at=self.stimulus.at,
            calls_attention=self.worth_attention,
        )
