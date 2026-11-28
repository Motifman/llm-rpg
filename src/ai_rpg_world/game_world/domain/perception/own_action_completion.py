from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception.delivery_rank import DeliveryRank, Sense
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perceived_quality import Completed
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import StimulusDescription
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived, PerceptionOutcome
from ai_rpg_world.game_world.domain.perception.perception_senses import PerceptionSenses
from ai_rpg_world.game_world.domain.perception.salience import Notable
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts.location import NotAtSpot


@final
@dataclass(frozen=True)
class OwnActionCompletion:
    person: PersonId
    summary: TextAboutPeople
    text: TextAboutPeople
    tool: str
    at: WorldTick

    @property
    def counts_toward_one_per_person(self) -> bool:
        # 自分の行動の続きは見聞きしたことの言い換えではないので、同じときに届く知らせを押しのけない
        return False

    @property
    def always_delivered(self) -> bool:
        return False

    def delivery_rank(self) -> DeliveryRank:
        return DeliveryRank.of(Sense.OWN_BODY, Notable())

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
        if perceiver.person != self.person:
            return NotPerceived(NotPerceivedReason.NOT_ADDRESSED)
        return Perceived(
            perceiver=perceiver.person,
            text=self.text.seen_by(view),
            quality=Completed(summary=self.summary.seen_by(view), tool=self.tool),
            happened_at=self.at,
            calls_attention=False,
            addressed_to_perceiver=False,
        )
