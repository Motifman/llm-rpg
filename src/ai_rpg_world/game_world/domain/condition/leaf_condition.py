from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure, NoText
from ai_rpg_world.game_world.domain.condition.failure_texts import own_failure, placeholder_requirements
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


class LeafCondition(ABC):
    failure_text: TextWithUnassignedPeople | NoText

    @abstractmethod
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool: ...

    @abstractmethod
    def _requirements_besides_text(self) -> Requirements: ...

    def requirements(self) -> Requirements:
        return self._requirements_besides_text().combined_with(placeholder_requirements(self.failure_text))

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        if self.holds(facts, trigger):
            return None
        return own_failure(self.failure_text, trigger)
