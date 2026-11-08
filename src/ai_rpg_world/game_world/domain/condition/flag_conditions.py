from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.leaf_condition import LeafCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Count

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


def _waiting_for(flags: tuple[FlagDeclaration, ...]) -> Requirements:
    return replace(Requirements.nothing(), waits_for_flags=frozenset(flags))


@final
@dataclass(frozen=True)
class FlagIsRaisedCondition(LeafCondition):
    flag: FlagDeclaration
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.flags().is_raised(self.flag)

    def _requirements_besides_text(self) -> Requirements:
        return _waiting_for((self.flag,))


@final
@dataclass(frozen=True)
class FlagsRaisedAtLeastCondition(LeafCondition):
    flags: tuple[FlagDeclaration, ...]
    count: Count
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        world_flags = facts.flags()
        return Count(sum(1 for flag in self.flags if world_flags.is_raised(flag))) >= self.count

    def _requirements_besides_text(self) -> Requirements:
        return _waiting_for(self.flags)
