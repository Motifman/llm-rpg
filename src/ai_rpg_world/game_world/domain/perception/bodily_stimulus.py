from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception.delivery_rank import DeliveryRank, Sense
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perceived_quality import Felt
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import StimulusDescription
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived, PerceptionOutcome
from ai_rpg_world.game_world.domain.perception.perception_senses import PerceptionSenses
from ai_rpg_world.game_world.domain.perception.salience import Notable, Salience
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts.location import NotAtSpot

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.people.text_with_unassigned_people import TextWithUnassignedPeople


@final
@dataclass(frozen=True)
class BodilyStimulus:
    person: PersonId
    text: TextAboutPeople
    salience: Salience
    at: WorldTick

    @classmethod
    def on_waking(cls, person: PersonId, waking: TextWithUnassignedPeople, at: WorldTick) -> BodilyStimulus:
        return cls(person=person, text=waking.about({}), salience=Notable(), at=at)

    @property
    def counts_toward_one_per_person(self) -> bool:
        return True

    @property
    def always_delivered(self) -> bool:
        return False

    def delivery_rank(self) -> DeliveryRank:
        return DeliveryRank.of(Sense.OWN_BODY, self.salience)

    def described(self) -> StimulusDescription:
        return StimulusDescription(
            sense=Sense.OWN_BODY,
            text=self.text.template.template,
            where=NotAtSpot(),
            addressed_to=frozenset({self.person}),
        )

    def perceived_in(self, perceiver: Perceiver, senses: PerceptionSenses) -> PerceptionOutcome:
        return self.perceived_by(perceiver, senses.view_for(perceiver.person))

    def perceived_by(self, perceiver: Perceiver, view: PeopleAsSeen) -> PerceptionOutcome:
        if not perceiver.feels_body_of(self.person):
            return NotPerceived(NotPerceivedReason.NOT_OWN_BODY)
        return Perceived(
            perceiver=perceiver.person,
            text=self.text.seen_by(view),
            quality=Felt(),
            happened_at=self.at,
            calls_attention=self.salience.stands_out(),
            addressed_to_perceiver=False,
        )
