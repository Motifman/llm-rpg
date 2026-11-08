from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.leaf_condition import LeafCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Ticks
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.world_records import NeverFired

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class HappeningHasFiredCondition(LeafCondition):
    happening: HappeningId
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.scenario_progress().last_fired_at(self.happening) != NeverFired()

    def _requirements_besides_text(self) -> Requirements:
        return replace(Requirements.nothing(), reads_happenings=frozenset({self.happening}))


@final
@dataclass(frozen=True)
class TicksSinceHappeningAtLeastCondition(LeafCondition):
    happening: HappeningId
    ticks: Ticks
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.scenario_progress().last_fired_at(self.happening).has_passed(self.ticks, facts.now())

    def _requirements_besides_text(self) -> Requirements:
        return replace(Requirements.nothing(), reads_happenings=frozenset({self.happening}))
