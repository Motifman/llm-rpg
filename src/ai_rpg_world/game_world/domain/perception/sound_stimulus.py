from __future__ import annotations

from collections.abc import Callable
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
        hearing = _Hearing(stimulus=self, perceiver=perceiver, view=view)
        return self.source.heard_by(perceiver, self.origin, self.loudness, reach, values).read(hearing)


@final
@dataclass(frozen=True)
class _Hearing:
    stimulus: SoundStimulus
    perceiver: Perceiver
    view: PeopleAsSeen

    def when_clear(self) -> PerceptionOutcome:
        return self._reached(
            lambda: self.stimulus.source.clear_text(self.stimulus.clear, self.view), HearsClearly(), stands_out=True
        )

    def when_muffled(self) -> PerceptionOutcome:
        return self._reached(self.stimulus.muffled.unidentified, HearsMuffled(), stands_out=True)

    def when_faint(self) -> PerceptionOutcome:
        return self._reached(self.stimulus.muffled.unidentified, HearsFaintly(), stands_out=False)

    def when_nothing(self) -> PerceptionOutcome:
        return NotPerceived()

    def _reached(
        self,
        text: Callable[[], TextWithAssignedPeople],
        quality: HearsClearly | HearsMuffled | HearsFaintly,
        stands_out: bool,
    ) -> PerceptionOutcome:
        stimulus, perceiver = self.stimulus, self.perceiver
        involved = perceiver.person in stimulus.involved
        return perceiver.notices_surroundings(involved).outcome(
            when_aware=lambda: Perceived(
                perceiver=perceiver.person,
                text=text(),
                quality=quality,
                happened_at=stimulus.at,
                # かすかに聞こえただけのものは、関わっていても目立っても、考え直す目安にしない。
                calls_attention=stands_out and (involved or stimulus.salience == Notable()),
            ),
            on_waking=lambda: MissedNotice.from_text(stimulus.noticed_later, self.view, stimulus.at),
        )
