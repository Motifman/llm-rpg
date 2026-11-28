from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId


class TurnSkipReason(Enum):
    WAITING = "waiting"
    WAITING_AFTER_CHOICES_KEPT_FAILING = "waiting_after_choices_kept_failing"
    IN_THE_MIDDLE_OF_ACTION_AND_NOT_ADDRESSED = "in_the_middle_of_action_and_not_addressed"
    UNABLE_TO_ACT = "unable_to_act"


@final
@dataclass(frozen=True)
class SkippedTurn:
    person: PersonId
    reason: TurnSkipReason
