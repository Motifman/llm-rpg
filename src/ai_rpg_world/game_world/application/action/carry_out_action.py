from __future__ import annotations

from typing import Protocol, TypeVar, final

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused, ActionReply
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_prerequisite_check import ActionPrerequisiteCheck
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal, PreconditionRefusal, WorldStateRefusal
from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.exception.action_exception import ActionRefusedException
from ai_rpg_world.game_world.domain.exception.game_world_exception import WorldRefusal
from ai_rpg_world.game_world.domain.value_object import Ticks

_Attempt = TypeVar("_Attempt", bound=ActionAttempt)
_StepsAttempt = TypeVar("_StepsAttempt", bound=ActionAttempt, contravariant=True)


class ActionSteps(Protocol[_StepsAttempt]):
    def unmet_precondition(self, attempt: _StepsAttempt, facts: WorldFacts) -> FailureReason | HiddenFailure | None: ...

    def change_world(self, attempt: _StepsAttempt, facts: WorldFacts, world: WorldAggregates) -> Ticks: ...


@final
class CarryOutAction:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._texts = design.refusal_texts
        self._joint_actions = design.joint_actions()
        self._check = ActionPrerequisiteCheck()

    def __call__(self, attempt: _Attempt, steps: ActionSteps[_Attempt]) -> ActionReply:
        aimed = attempt

        def carry_out(session: WorldSession) -> None:
            nonlocal aimed
            facts = session.facts()
            aimed = self._check.cleared(attempt, facts, self._texts)
            self._carry_out_aimed(aimed, steps, session, facts)

        try:
            self._scope.run(carry_out)
        except ActionRefusedException as refused:
            return self._note_refusal(refused.refusal)
        except WorldRefusal as exception:
            code = RefusalCode.of(exception)
            text = self._texts.world_state_text(code, aimed.actor)
            return self._note_refusal(ActionRefusal(attempt=aimed, reason=WorldStateRefusal(code), text=text))
        return ActionDone()

    def _carry_out_aimed(
        self, attempt: _Attempt, steps: ActionSteps[_Attempt], session: WorldSession, facts: WorldFacts
    ) -> None:
        failure = steps.unmet_precondition(attempt, facts)
        if failure is not None:
            text = self._texts.precondition_text(failure, attempt.actor)
            raise ActionRefusedException(ActionRefusal(attempt=attempt, reason=PreconditionRefusal(failure), text=text))
        now = facts.now()
        situation = ActorSituation.of(attempt, facts)
        world = session.aggregates()
        busy_for = steps.change_world(attempt, facts, world)
        world.vitals(attempt.actor).start_acting(attempt.exertion(), now + busy_for, facts.rules().fatigue)
        session.latest_actions().note(attempt, situation, now)
        session.scenario_progress().note_joint_action_part_done(attempt, self._joint_actions, now)

    def _note_refusal(self, refusal: ActionRefusal) -> ActionRefused:
        self._scope.run(lambda session: self._note_failed_attempt(refusal, session))
        return ActionRefused(refusal)

    def _note_failed_attempt(self, refusal: ActionRefusal, session: WorldSession) -> None:
        facts = session.facts()
        situation = ActorSituation.of(refusal.attempt, facts)
        session.latest_actions().note_failed_attempt(refusal, situation, facts.now())
