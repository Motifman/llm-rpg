from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import WorldStageChanged
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import WorldStageId, WorldTick


@final
@dataclass(frozen=True)
class ApplyWorldStageChangeCommand:
    before: WorldStageId
    after: WorldStageId
    at: WorldTick


@final
class ApplyWorldStageChange:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design

    def __call__(self, command: ApplyWorldStageChangeCommand) -> None:
        trigger = WorldStageChanged(before=command.before, after=command.after, at=command.at)

        def work(session: WorldSession) -> None:
            facts, world = session.facts(), session.aggregates()
            self._design.world_stage_effects(command.before).when_left.apply(facts, world, trigger)
            self._design.world_stage_effects(command.after).when_entered.apply(facts, world, trigger)

        self._scope.run(work)
