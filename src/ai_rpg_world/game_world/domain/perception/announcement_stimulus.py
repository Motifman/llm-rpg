from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception.delivery_rank import DeliveryRank, Sense
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perceived_quality import Told
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import StimulusDescription
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived, PerceptionOutcome
from ai_rpg_world.game_world.domain.perception.perception_senses import PerceptionSenses
from ai_rpg_world.game_world.domain.perception.salience import Salience
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts.location import NotAtSpot


@final
@dataclass(frozen=True)
class AnnouncementStimulus:
    audience: frozenset[PersonId]
    text: TextAboutPeople
    salience: Salience
    at: WorldTick
    reaches_who_left_the_world: bool = False
    kept_while_fainted: bool = True

    @property
    def counts_toward_one_per_person(self) -> bool:
        # 世界の知らせは見聞きしたことの言い換えではなく、別のことを伝えるので、1 人に 1 つの数に入れない。
        return False

    @property
    def always_delivered(self) -> bool:
        return False

    def delivery_rank(self) -> DeliveryRank:
        return DeliveryRank.of(Sense.ANNOUNCEMENT, self.salience)

    def described(self) -> StimulusDescription:
        return StimulusDescription(
            sense=Sense.ANNOUNCEMENT, text=self.text.template.template, where=NotAtSpot(), addressed_to=self.audience
        )

    def perceived_in(self, perceiver: Perceiver, senses: PerceptionSenses) -> PerceptionOutcome:
        return self.perceived_by(perceiver, senses.view_for(perceiver.person))

    def perceived_by(self, perceiver: Perceiver, view: PeopleAsSeen) -> PerceptionOutcome:
        if perceiver.person not in self.audience:
            return NotPerceived(NotPerceivedReason.NOT_ADDRESSED)
        if not perceiver.takes_announcement(self.reaches_who_left_the_world):
            return NotPerceived(NotPerceivedReason.LEFT_THE_WORLD)
        # 知らせは選ばれた本人に宛てたものなので、倒れていれば起きてから知る。
        # 時間帯は、目覚めたときに古い時間帯が届くといまの時刻と食い違うので、ためない (D2203)。
        return perceiver.notices_surroundings(involved=self.kept_while_fainted).outcome(
            when_aware=lambda: Perceived(
                perceiver=perceiver.person,
                text=self.text.seen_by(view),
                quality=Told(),
                happened_at=self.at,
                calls_attention=self.salience.stands_out(),
            ),
            on_waking=lambda: MissedNotice(text=self.text.seen_by(view), happened_at=self.at),
        )
