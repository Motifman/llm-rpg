from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.people import TextAboutPeople


@final
@dataclass(frozen=True)
class Doable:
    pass


@final
@dataclass(frozen=True)
class NotNow:
    reason: TextAboutPeople


@final
@dataclass(frozen=True)
class AvailableAction:
    attempt: ActionAttempt
    standing: Doable | NotNow


@final
@dataclass(frozen=True)
class AvailableActions:
    actions: tuple[AvailableAction, ...]
