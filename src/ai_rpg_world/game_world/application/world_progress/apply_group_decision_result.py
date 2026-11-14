from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import GroupDecisionResult, GroupDecisionUnresolved
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import GroupDecisionId, PersonId


@final
@dataclass(frozen=True)
class ApplyGroupDecisionReachedCommand:
    decision: GroupDecisionId
    chosen: PersonId


@final
class ApplyGroupDecisionReached:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design

    def __call__(self, command: ApplyGroupDecisionReachedCommand) -> None:
        rules = self._design.group_decision_rules(command.decision)
        trigger = GroupDecisionResult(rules.decision, chosen=command.chosen)

        def work(session: WorldSession) -> None:
            rules.when_decided.apply(session.facts(), session.aggregates(), trigger)

        self._scope.run(work)


@final
@dataclass(frozen=True)
class ApplyGroupDecisionUnresolvedCommand:
    decision: GroupDecisionId


@final
class ApplyGroupDecisionUnresolved:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design

    def __call__(self, command: ApplyGroupDecisionUnresolvedCommand) -> None:
        rules = self._design.group_decision_rules(command.decision)
        trigger = GroupDecisionUnresolved(rules.decision)

        def work(session: WorldSession) -> None:
            rules.when_undecided.apply(session.facts(), session.aggregates(), trigger)

        self._scope.run(work)
