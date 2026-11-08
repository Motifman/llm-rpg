from __future__ import annotations

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.action.common_rule_refusal import (
    ActorCannotAct,
    Busy,
    CommonRuleRefusal,
    NotAllowedInThisStage,
    TooTired,
)
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, Occupant, PersonBody


class ActionPrerequisiteCheck:
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
