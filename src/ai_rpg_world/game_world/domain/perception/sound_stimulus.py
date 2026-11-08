from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_noticed_later import NotNoticedLater
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived, PerceptionOutcome
from ai_rpg_world.game_world.domain.perception.salience import Notable, Salience
from ai_rpg_world.game_world.domain.sound.hearing_quality import (
    HearingQuality,
    HearsClearly,
    HearsFaintly,
    HearsMuffled,
    HearsNothing,
)
from ai_rpg_world.game_world.domain.sound.hearing_values import HearingValues
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.sound.sound_network import SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick


@final
@dataclass(frozen=True)
class NotWhispered:
    pass


@final
@dataclass(frozen=True)
class Voice:
    whispered_to: PersonId | NotWhispered

    def heard_by(
        self, perceiver: Perceiver, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues
    ) -> HearingQuality:
        if isinstance(self.whispered_to, NotWhispered):
            return perceiver.hears(origin, loudness, reach, values)
        if not perceiver.is_at(origin):
            return HearsNothing()
        return HearsClearly() if perceiver.person == self.whispered_to else HearsFaintly()

    def clear_text(self, clear: TextAboutPeople, view: PeopleAsSeen) -> TextWithAssignedPeople:
        return clear.seen_by(view)


@final
@dataclass(frozen=True)
class Noise:
    def heard_by(
        self, perceiver: Perceiver, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues
    ) -> HearingQuality:
        return perceiver.hears(origin, loudness, reach, values)

    def clear_text(self, clear: TextAboutPeople, view: PeopleAsSeen) -> TextWithAssignedPeople:
        return clear.unidentified()


SoundSource = Voice | Noise


@final
@dataclass(frozen=True)
class SoundStimulus:
    origin: SpotId
    loudness: Loudness
    clear: TextAboutPeople
    muffled: TextAboutPeople
    noticed_later: TextAboutPeople | NotNoticedLater
    source: SoundSource
    involved: tuple[PersonId, ...]
    salience: Salience
    at: WorldTick

    def perceived_by(
        self, perceiver: Perceiver, reach: SoundReach, values: HearingValues, view: PeopleAsSeen
    ) -> PerceptionOutcome:
        quality = self.source.heard_by(perceiver, self.origin, self.loudness, reach, values)
        if isinstance(quality, HearsNothing):
            return NotPerceived()
        heard = quality
        involved = perceiver.person in self.involved
        return perceiver.notices_surroundings(involved).outcome(
            when_aware=lambda: self._heard(perceiver, heard, view, involved),
            on_waking=lambda: self._noticed_on_waking(view),
        )

    def _heard(
        self,
        perceiver: Perceiver,
        quality: HearsClearly | HearsMuffled | HearsFaintly,
        view: PeopleAsSeen,
        involved: bool,
    ) -> PerceptionOutcome:
        text = self.source.clear_text(self.clear, view) if quality == HearsClearly() else self.muffled.unidentified()
        return Perceived.of(
            perceiver=perceiver.person,
            text=text,
            quality=quality,
            happened_at=self.at,
            worth_attention=involved or self.salience == Notable(),
        )

    def _noticed_on_waking(self, view: PeopleAsSeen) -> MissedNotice | NotNoticedLater:
        if isinstance(self.noticed_later, NotNoticedLater):
            return NotNoticedLater()
        return MissedNotice(text=self.noticed_later.seen_by(view), happened_at=self.at)
