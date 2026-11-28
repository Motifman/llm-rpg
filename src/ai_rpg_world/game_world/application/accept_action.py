from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar, final

from ai_rpg_world.game_world.application.action.action_reply import ActionRefused, ActionReply
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.settle_world_conditions import (
    SettleWorldConditions,
    SettleWorldConditionsCommand,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal, WorldStateRefusal
from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.settling_occasion import SettlingOccasion
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.world_progress_exception import WorldAlreadyEndedException


class ActionCommand(Protocol):
    @property
    def attempt(self) -> ActionAttempt: ...


_Command = TypeVar("_Command", bound=ActionCommand)


@final
@dataclass(frozen=True)
class AcceptActionCommand(Generic[_Command]):
    command: _Command
    carry_out: Callable[[_Command], ActionReply]


@final
class AcceptAction:
    def __init__(self, scope: CommandScope, design: WorldDesign, settle: SettleWorldConditions) -> None:
        self._scope = scope
        self._design = design
        self._texts = design.refusal_texts
        self._settle = settle

    def __call__(self, command: AcceptActionCommand[_Command]) -> ActionReply:
        attempt = command.command.attempt
        try:
            self._scope.run(lambda session: session.ending().admit_change())
        except WorldAlreadyEndedException as ended:
            # 終わったあとの世界は変えないので、CarryOutAction の断りと違い、断られた試みも記録しない
            code = RefusalCode.of(ended)
            text = self._texts.world_state_text(code, attempt.actor)
            refusal = ActionRefusal(attempt=attempt, reason=WorldStateRefusal(code), text=text)
            return self._scope.run(lambda session: self._refused(refusal, session))
        reply = command.carry_out(command.command)
        # 断られた行為も試みの記録で世界を変えているので、確定した行為と同じく落ち着かせる
        self._settle(SettleWorldConditionsCommand(SettlingOccasion.AFTER_COMMAND))
        return reply

    def _refused(self, refusal: ActionRefusal, session: WorldSession) -> ActionRefused:
        situation = ActorSituation.of(refusal.attempt, session.facts())
        return ActionRefused(refusal, refusal.outcome_for_actor(self._design, situation))
