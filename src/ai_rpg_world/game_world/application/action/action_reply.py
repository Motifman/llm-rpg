from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind


@final
@dataclass(frozen=True)
class ActionDone:
    attempt: ActionAttempt

    def was_waiting(self) -> bool:
        return self.attempt.kind() is ActionKind.WAIT


@final
@dataclass(frozen=True)
class ActionRefused:
    refusal: ActionRefusal


ActionReply = ActionDone | ActionRefused
