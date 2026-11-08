from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.action_attempt import CopresenceRequirement, WithPerson
from ai_rpg_world.game_world.domain.exception.action_exception import BlankSpeechContentException
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class Whisper:
    to: PersonId

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithPerson(self.to),)


@final
@dataclass(frozen=True)
class OrdinaryVoice:
    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return ()


@final
@dataclass(frozen=True)
class Shout:
    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return ()


SpeechReach = Whisper | OrdinaryVoice | Shout


@final
@dataclass(frozen=True)
class SpeechContent:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise BlankSpeechContentException(f"SpeechContent must be non-blank, got {self.text!r}")
