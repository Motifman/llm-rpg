from __future__ import annotations

from typing import TYPE_CHECKING

from ai_rpg_world.game_world.domain.value_object.readiness_to_act import (
    FreeToAct,
    InTheMiddleOfAction,
    ReadinessToAct,
    UnableToAct,
)

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.value_object import PersonId


def readiness_to_act(person: PersonId, facts: WorldFacts) -> ReadinessToAct:
    vitals = facts.vitals(person)
    # 死者が動ける世界でも、死者にはターンを回さない
    if not vitals.can_act() or person not in facts.outcomes().undecided_people():
        return UnableToAct()
    if vitals.is_busy(facts.now()):
        return InTheMiddleOfAction()
    return FreeToAct()
