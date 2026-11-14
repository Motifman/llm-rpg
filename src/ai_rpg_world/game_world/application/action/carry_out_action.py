from __future__ import annotations

from typing import Protocol, TypeVar, final

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused, ActionReply
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_prerequisite_check import ActionPrerequisiteCheck
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal, PreconditionRefusal, WorldStateRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.exception.game_world_exception import WorldRefusal
from ai_rpg_world.game_world.domain.value_object import Ticks

_Attempt = TypeVar("_Attempt", bound=ActionAttempt)
_StepsAttempt = TypeVar("_StepsAttempt", bound=ActionAttempt, contravariant=True)


class ActionSteps(Protocol[_StepsAttempt]):
    def unmet_precondition(self, attempt: _StepsAttempt, facts: WorldFacts) -> FailureReason | HiddenFailure | None: ...

    def change_world(self, attempt: _StepsAttempt, facts: WorldFacts, world: WorldAggregates) -> Ticks: ...


class _Refused(Exception):
    def __init__(self, refusal: ActionRefusal) -> None:
        super().__init__(type(refusal.reason).__name__)
        self.refusal = refusal


@final
class CarryOutAction:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._texts = design.refusal_texts
        self._check = ActionPrerequisiteCheck()

    def __call__(self, attempt: _Attempt, steps: ActionSteps[_Attempt]) -> ActionReply:
        try:
            self._scope.run(lambda session: self._carry_out(attempt, steps, session))
        except _Refused as refused:
            return self._note_refusal(refused.refusal)
        except WorldRefusal as exception:
            code = RefusalCode.of(exception)
            text = self._texts.world_state_text(code, attempt.actor)
            return self._note_refusal(ActionRefusal(attempt=attempt, reason=WorldStateRefusal(code), text=text))
        return ActionDone()

    def _carry_out(self, attempt: _Attempt, steps: ActionSteps[_Attempt], session: WorldSession) -> None:
        facts = session.facts()
        refusal = self._check.refusal(attempt, facts, self._texts)
        if refusal is not None:
            raise _Refused(refusal)
        failure = steps.unmet_precondition(attempt, facts)
        if failure is not None:
            text = self._texts.precondition_text(failure, attempt.actor)
            raise _Refused(ActionRefusal(attempt=attempt, reason=PreconditionRefusal(failure), text=text))
        now = facts.now()
        world = session.aggregates()
        busy_for = steps.change_world(attempt, facts, world)
        world.vitals(attempt.actor).start_acting(attempt.exertion(), now + busy_for, facts.rules().fatigue)
        session.latest_actions().note(attempt, now)

    def _note_refusal(self, refusal: ActionRefusal) -> ActionRefused:
        self._scope.run(lambda session: session.latest_actions().note_failed_attempt(refusal, session.facts().now()))
        return ActionRefused(refusal)
