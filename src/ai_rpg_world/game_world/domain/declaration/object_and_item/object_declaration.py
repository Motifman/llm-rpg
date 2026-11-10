from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item._state_keys import require_own_distinct_keys
from ai_rpg_world.game_world.domain.declaration.object_and_item.state_kind import StateKind
from ai_rpg_world.game_world.domain.declaration.object_and_item.state_value import StateValue
from ai_rpg_world.game_world.domain.exception.object_and_item_declaration_exception import (
    StateKeyOfAnotherKindException,
    StateValueMismatchesKindException,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, ObjectId, SpotId, StateKeyId


@final
@dataclass(frozen=True)
class ObjectStateKeyDeclaration:
    object_id: ObjectId
    key: StateKeyId
    kind: StateKind
    initial: StateValue

    def __post_init__(self) -> None:
        if not self.kind.accepts(self.initial):
            raise StateValueMismatchesKindException(
                f"initial {self.initial!r} of {self._name()} does not fit {self.kind!r}"
            )

    def require_fits(self, value: StateValue) -> None:
        if not self.kind.accepts(value):
            raise StateValueMismatchesKindException(f"{value!r} does not fit {self.kind!r} of {self._name()}")

    def require_count(self) -> None:
        if not self.kind.holds_count():
            raise self._of_another_kind("a count")

    def require_stock(self) -> None:
        if not self.kind.holds_stock():
            raise self._of_another_kind("a stock")

    def require_written_text(self) -> None:
        if not self.kind.holds_written_text():
            raise self._of_another_kind("a written text")

    def _of_another_kind(self, needed: str) -> StateKeyOfAnotherKindException:
        return StateKeyOfAnotherKindException(f"{self._name()} is {self.kind!r}, not {needed}")

    def _name(self) -> str:
        return f"{self.object_id.value}.{self.key.value}"


@final
@dataclass(frozen=True)
class ObjectAppearance:
    seen_in_dark: bool
    hidden_until_revealed: bool


@final
@dataclass(frozen=True)
class ObjectDeclaration:
    object_id: ObjectId
    spot_id: SpotId
    name: DisplayName
    description: DescriptionText
    appearance: ObjectAppearance
    state_keys: tuple[ObjectStateKeyDeclaration, ...]

    def __post_init__(self) -> None:
        require_own_distinct_keys(
            self.object_id,
            [state_key.object_id for state_key in self.state_keys],
            [state_key.key for state_key in self.state_keys],
        )
