from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.domain.action.built_in_attempts import SpotSearchAttempt
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.value_object import Ticks


@final
@dataclass(frozen=True)
class SearchSpotCommand:
    attempt: SpotSearchAttempt


@final
class SearchSpot:
    def __init__(self, carry_out: CarryOutAction, design: WorldDesign) -> None:
        self._carry_out = carry_out
        self._design = design

    def __call__(self, command: SearchSpotCommand) -> ActionReply:
        return self._carry_out(command.attempt, self)

    def unmet_precondition(self, attempt: SpotSearchAttempt, facts: WorldFacts) -> FailureReason | HiddenFailure | None:
        return None

    def change_world(self, attempt: SpotSearchAttempt, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        return attempt.search(self._design, facts, world)
