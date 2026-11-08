from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, final

from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.people import TextAboutPeople

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class NoText:
    pass


@final
@dataclass(frozen=True)
class FailureReason:
    failed_part: ConditionPath
    text: TextAboutPeople | NoText


@final
@dataclass(frozen=True)
class HiddenFailure:
    failed_part: ConditionPath


class Condition(Protocol):
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool: ...

    def requirements(self) -> Requirements: ...

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None: ...

    def explains_failure(self) -> bool: ...
