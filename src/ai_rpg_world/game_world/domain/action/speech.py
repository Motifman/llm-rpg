from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.action_attempt import CopresenceRequirement, WithPerson
from ai_rpg_world.game_world.domain.action.offered_action import LISTENER, REACH, OfferedStep
from ai_rpg_world.game_world.domain.exception.action_exception import (
    ArgumentsNotChosenException,
    BlankSpeechContentException,
)
from ai_rpg_world.game_world.domain.perception import NoTarget, NotWhispered, Voice
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording

_WHISPER = OfferedStep(REACH, DisplayName("ささやく"))
_ORDINARY_VOICE = OfferedStep(REACH, DisplayName("ふつうの声で話す"))
_SHOUT = OfferedStep(REACH, DisplayName("叫ぶ"))


@final
@dataclass(frozen=True)
class Whisper:
    to: PersonId

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithPerson(self.to),)

    def listener(self) -> PersonId | NoTarget:
        return self.to

    def voice(self) -> Voice:
        return Voice(whispered_to=self.to)

    def offered_steps(self, wording: ChoiceWording) -> tuple[OfferedStep, ...]:
        return (_WHISPER, OfferedStep(LISTENER, wording.person(self.to)))


@final
@dataclass(frozen=True)
class OrdinaryVoice:
    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return ()

    def listener(self) -> PersonId | NoTarget:
        return NoTarget()

    def voice(self) -> Voice:
        return Voice(whispered_to=NotWhispered())

    def offered_steps(self, wording: ChoiceWording) -> tuple[OfferedStep, ...]:
        return (_ORDINARY_VOICE,)


@final
@dataclass(frozen=True)
class Shout:
    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return ()

    def listener(self) -> PersonId | NoTarget:
        return NoTarget()

    def voice(self) -> Voice:
        return Voice(whispered_to=NotWhispered())

    def offered_steps(self, wording: ChoiceWording) -> tuple[OfferedStep, ...]:
        return (_SHOUT,)


SpeechReach = Whisper | OrdinaryVoice | Shout


@final
@dataclass(frozen=True)
class SpeechContentNotChosen:
    def chosen_by(self, speaker: PersonId) -> SpeechContent:
        raise ArgumentsNotChosenException(f"{speaker.value} has not chosen what to say")


@final
@dataclass(frozen=True)
class SpeechContent:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise BlankSpeechContentException(f"SpeechContent must be non-blank, got {self.text!r}")

    def chosen_by(self, speaker: PersonId) -> SpeechContent:
        return self
