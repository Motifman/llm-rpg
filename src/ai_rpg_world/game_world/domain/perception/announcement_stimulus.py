from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perceived_quality import Told
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived, PerceptionOutcome
from ai_rpg_world.game_world.domain.perception.salience import Notable, Salience
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class AnnouncementStimulus:
    audience: frozenset[PersonId]
    text: TextAboutPeople
    salience: Salience
    at: WorldTick

    def perceived_by(self, perceiver: Perceiver, view: PeopleAsSeen) -> PerceptionOutcome:
        if perceiver.person not in self.audience:
            return NotPerceived()
        # 知らせは選ばれた本人に宛てたものなので、倒れていれば起きてから知る。
        return perceiver.notices_surroundings(involved=True).outcome(
            when_aware=lambda: Perceived(
                perceiver=perceiver.person,
                text=self.text.seen_by(view),
                quality=Told(),
                happened_at=self.at,
                calls_attention=self.salience.stands_out(),
            ),
            on_waking=lambda: MissedNotice(text=self.text.seen_by(view), happened_at=self.at),
        )
