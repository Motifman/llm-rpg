from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar, final

from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.people import TextAboutPeople

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.value_object import PersonId

_Read = TypeVar("_Read")


@final
@dataclass(frozen=True)
class NoText:
    def explains(self) -> bool:
        return False

    def placeholders_read_as(self, read: Callable[[str, str], _Read]) -> frozenset[_Read]:
        return frozenset()

    def about_each(self, person_of: Callable[[str, str], PersonId]) -> NoText:
        return NoText()


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
