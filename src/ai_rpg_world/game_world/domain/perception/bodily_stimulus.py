from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception.perceived_quality import Felt
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived, PerceptionOutcome
from ai_rpg_world.game_world.domain.perception.salience import Notable, Salience
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class BodilyStimulus:
    person: PersonId
    text: TextAboutPeople
    salience: Salience
    at: WorldTick

    def perceived_by(self, perceiver: Perceiver, view: PeopleAsSeen) -> PerceptionOutcome:
        if not perceiver.feels_body_of(self.person):
            return NotPerceived()
        return Perceived(
            perceiver=perceiver.person,
            text=self.text.seen_by(view),
            quality=Felt(),
            happened_at=self.at,
            calls_attention=self.salience == Notable(),
        )
