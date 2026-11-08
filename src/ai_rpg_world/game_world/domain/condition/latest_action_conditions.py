from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.leaf_condition import LeafCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Anyone, Subject
from ai_rpg_world.game_world.domain.condition.world_time_conditions import declared_world_stage
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, Ticks, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class SinceStart:
    def baseline(self, facts: WorldFacts) -> WorldTick:
        return WorldTick(0)


@final
@dataclass(frozen=True)
class SinceWorldStageEntered:
    def baseline(self, facts: WorldFacts) -> WorldTick:
        return declared_world_stage(facts).entered_at()


@final
@dataclass(frozen=True)
class TicksSinceLastActionAtLeastCondition(LeafCondition):
    who: Subject | Anyone
    action: ActionKind | InteractionId
    ticks: Ticks
    since: SinceStart | SinceWorldStageEntered
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        last_done = facts.latest_actions().last_done_at(self.who.person_in(trigger), self.action)
        return last_done.later_of(self.since.baseline(facts)).has_passed(self.ticks, facts.now())

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()
