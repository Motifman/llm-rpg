from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.leaf_condition import LeafCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import ItemSubject
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemStateKeyDeclaration, StateValue
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Ticks

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class ItemAgeAtLeastCondition(LeafCondition):
    item: ItemSubject
    ticks: Ticks
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.item(self.item.item_in(trigger)).age(facts.now()) >= self.ticks

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class ItemValueIsCondition(LeafCondition):
    item: ItemSubject
    key: ItemStateKeyDeclaration
    value: StateValue
    failure_text: TextWithUnassignedPeople | NoText

    def __post_init__(self) -> None:
        self.key.require_fits(self.value)

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.item(self.item.item_in(trigger)).value_of(self.key) == self.value

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()
