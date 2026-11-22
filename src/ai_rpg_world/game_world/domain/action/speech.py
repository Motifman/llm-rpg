from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.action_attempt import CopresenceRequirement, WithPerson
from ai_rpg_world.game_world.domain.action.offered_action import CONTENT, LISTENER, REACH, OfferedStep
from ai_rpg_world.game_world.domain.exception.action_exception import (
    ArgumentsNotChosenException,
    BlankSpeechContentException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
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
    def written_as(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> SpeechContent:
        written = values.get(CONTENT.name)
        if not isinstance(written, TextArgumentValue):
            raise ArgumentsNotChosenException("the content of the speech was not written")
        return SpeechContent(written.text)

    def chosen_by(self, speaker: PersonId) -> SpeechContent:
        raise ArgumentsNotChosenException(f"{speaker.value} has not chosen what to say")


@final
@dataclass(frozen=True)
class SpeechContent:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise BlankSpeechContentException(f"SpeechContent must be non-blank, got {self.text!r}")

    def written_as(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> SpeechContent:
        return self

    def chosen_by(self, speaker: PersonId) -> SpeechContent:
        return self
