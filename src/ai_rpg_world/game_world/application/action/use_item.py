from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.domain.action.built_in_attempts import ItemUseAttempt
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.value_object import Ticks


@final
@dataclass(frozen=True)
class UseItemCommand:
    attempt: ItemUseAttempt


@final
class UseItem:
    def __init__(self, carry_out: CarryOutAction, design: WorldDesign) -> None:
        self._carry_out = carry_out
        self._design = design

    def __call__(self, command: UseItemCommand) -> ActionReply:
        return self._carry_out(command.attempt, self)

    def unmet_precondition(self, attempt: ItemUseAttempt, facts: WorldFacts) -> FailureReason | HiddenFailure | None:
        return None

    def change_world(self, attempt: ItemUseAttempt, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        return attempt.take_effect(self._design, facts, world)
