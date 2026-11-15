from __future__ import annotations

from typing import Protocol, TypeVar, final

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal, PreconditionRefusal
from ai_rpg_world.game_world.domain.action.available_actions import AvailableAction, Doable, NotNow
from ai_rpg_world.game_world.domain.action.built_in_attempts import GroupDecisionBallotAttempt
from ai_rpg_world.game_world.domain.action.common_rule_refusal import (
    ActorCannotAct,
    Busy,
    CommonRuleRefusal,
    NoOneFoundInTheDark,
    NotAllowedInThisStage,
    TooTired,
)
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.exception.action_exception import ActionRefusedException
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, Occupant, PersonBody

_Attempt = TypeVar("_Attempt", bound=ActionAttempt)
_CheckedAttempt = TypeVar("_CheckedAttempt", bound=ActionAttempt, contravariant=True)


class ActionPrecondition(Protocol[_CheckedAttempt]):
    def unmet_precondition(
        self, attempt: _CheckedAttempt, facts: WorldFacts
    ) -> FailureReason | HiddenFailure | None: ...


@final
class CommonRulesOnly:
    def unmet_precondition(self, attempt: ActionAttempt, facts: WorldFacts) -> FailureReason | HiddenFailure | None:
        return None


class ActionPrerequisiteCheck:
    def cleared(
        self,
        attempt: _Attempt,
        precondition: ActionPrecondition[_Attempt],
        facts: WorldFacts,
        refusal_texts: RefusalTexts,
    ) -> _Attempt:
        refusal = self.refusal(attempt, facts, refusal_texts)
        if refusal is not None:
            raise ActionRefusedException(refusal)
        aimed = attempt.aimed_in(facts)
        if isinstance(aimed, NoOneFoundInTheDark):
            raise ActionRefusedException(
                ActionRefusal(attempt=attempt, reason=aimed, text=refusal_texts.common_rule_text(aimed, attempt.actor))
            )
        failure = precondition.unmet_precondition(aimed, facts)
        if failure is not None:
            text = refusal_texts.precondition_text(failure, aimed.actor)
            raise ActionRefusedException(ActionRefusal(attempt=aimed, reason=PreconditionRefusal(failure), text=text))
        return aimed

    def available(
        self,
        attempt: _Attempt,
        precondition: ActionPrecondition[_Attempt],
        facts: WorldFacts,
        refusal_texts: RefusalTexts,
    ) -> AvailableAction:
        refusal = self.refusal(attempt, facts, refusal_texts)
        if refusal is not None:
            return AvailableAction(attempt=attempt, standing=NotNow(refusal.text))
        failure = precondition.unmet_precondition(attempt, facts)
        # 伏せた理由まで「できない」に分けると、一覧の出る / 出ないの差から伏せた所属が漏れる。
        if isinstance(failure, FailureReason):
            return AvailableAction(
                attempt=attempt, standing=NotNow(refusal_texts.precondition_text(failure, attempt.actor))
            )
        return AvailableAction(attempt=attempt, standing=Doable())

    def available_ballot(
        self, attempt: GroupDecisionBallotAttempt, facts: WorldFacts, refusal_texts: RefusalTexts
    ) -> AvailableAction:
        refusal = self.refusal(attempt, facts, refusal_texts)
        if refusal is not None:
            return AvailableAction(attempt=attempt, standing=NotNow(refusal.text))
        # 前提だけで分けると投票済みの票が「できる」に出て、試すと集約に断られる。
        turned_down = attempt.refusal_by_decision(facts)
        if turned_down is not None:
            text = refusal_texts.world_state_text(RefusalCode.of(turned_down), attempt.actor)
            return AvailableAction(attempt=attempt, standing=NotNow(text))
        return AvailableAction(attempt=attempt, standing=Doable())

    def refusal(self, attempt: ActionAttempt, facts: WorldFacts, refusal_texts: RefusalTexts) -> ActionRefusal | None:
        reason = self._broken_rule(attempt, facts)
        if reason is None:
            return None
        return ActionRefusal(attempt=attempt, reason=reason, text=refusal_texts.common_rule_text(reason, attempt.actor))

    def _broken_rule(self, attempt: ActionAttempt, facts: WorldFacts) -> CommonRuleRefusal | None:
        actor = _acting_occupant(attempt, facts)
        if actor is None:
            return ActorCannotAct()
        if not _is_allowed_in_current_stage(attempt, facts):
            return NotAllowedInThisStage()
        vitals = facts.vitals(attempt.actor)
        if vitals.is_busy(facts.now()) and not attempt.can_start_while_busy():
            return Busy()
        if attempt.exertion().is_too_tiring_for(vitals, facts.rules().fatigue):
            return TooTired()
        for requirement in attempt.copresence_requirements():
            refusal = requirement.refusal_for(actor, facts)
            if refusal is not None:
                return refusal
        return None


def _acting_occupant(attempt: ActionAttempt, facts: WorldFacts) -> Occupant | None:
    vitals = facts.vitals(attempt.actor)
    if vitals.can_act() and attempt.actor in facts.outcomes().undecided_people():
        return PersonBody(attempt.actor)
    occupant = vitals.occupant_in_world(facts.rules().departed_persons_act)
    if occupant == DepartedPerson(attempt.actor) and attempt.actor_requirement().admits_departed():
        return occupant
    return None


def _is_allowed_in_current_stage(attempt: ActionAttempt, facts: WorldFacts) -> bool:
    return attempt.is_allowed_in(facts.world_stage().declaration_in(facts.nouns()))
