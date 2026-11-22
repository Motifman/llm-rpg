from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.domain.action.built_in_attempts import WaitAttempt
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.value_object import Ticks


@final
@dataclass(frozen=True)
class WaitCommand:
    attempt: WaitAttempt


@final
class Wait:
    def __init__(self, carry_out: CarryOutAction) -> None:
        self._carry_out = carry_out

    def __call__(self, command: WaitCommand) -> ActionReply:
        return self._carry_out(command.attempt, self)

    def unmet_precondition(self, attempt: WaitAttempt, facts: WorldFacts) -> FailureReason | HiddenFailure | None:
        return None

    def change_world(self, attempt: WaitAttempt, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        return attempt.take_effect()
