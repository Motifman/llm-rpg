from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.trigger import EachPersonOf
from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class PeopleSelection:
    where: Condition

    def select(self, facts: WorldFacts, trigger: Trigger) -> frozenset[PersonId]:
        return frozenset(person for person in facts.people() if self.where.holds(facts, EachPersonOf(trigger, person)))

    def requirements(self) -> Requirements:
        return self.where.requirements().without_subject(SubjectKind.EACH_PERSON)
