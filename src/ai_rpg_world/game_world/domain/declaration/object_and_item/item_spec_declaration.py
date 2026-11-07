from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item._state_keys import require_own_distinct_keys
from ai_rpg_world.game_world.domain.declaration.object_and_item.state_kind import (
    ChoiceStateKind,
    CountStateKind,
    FlagStateKind,
    ItemStateKind,
)
from ai_rpg_world.game_world.domain.declaration.object_and_item.state_value import StateValue
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import (
    ItemStateKindNotAllowedException,
    LightKeyNotDeclaredException,
    StateValueMismatchesKindException,
)
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    HandsNeeded,
    ItemSpecId,
    StateKeyId,
)


@final
@dataclass(frozen=True)
class ItemStateKeyDeclaration:
    item_spec_id: ItemSpecId
    key: StateKeyId
    kind: ItemStateKind
    initial: StateValue

    def __post_init__(self) -> None:
        if not isinstance(self.kind, (FlagStateKind, CountStateKind, ChoiceStateKind)):
            raise ItemStateKindNotAllowedException(
                f"{self.item_spec_id.value}.{self.key.value} cannot be {self.kind!r} on an item"
            )
        if not self.kind.accepts_initial(self.initial):
            raise StateValueMismatchesKindException(
                f"initial {self.initial!r} of {self.item_spec_id.value}.{self.key.value} does not fit {self.kind!r}"
            )


@final
@dataclass(frozen=True)
class LitWhen:
    key: StateKeyId
    value: StateValue


@final
@dataclass(frozen=True)
class NotALightSource:
    pass


@final
@dataclass(frozen=True)
class ItemSpecDeclaration:
    item_spec_id: ItemSpecId
    name: DisplayName
    description: DescriptionText
    state_keys: tuple[ItemStateKeyDeclaration, ...]
    lights_up: LitWhen | NotALightSource
    hands_needed: HandsNeeded = field(default=HandsNeeded(1))

    def __post_init__(self) -> None:
        require_own_distinct_keys(
            self.item_spec_id,
            [state_key.item_spec_id for state_key in self.state_keys],
            [state_key.key for state_key in self.state_keys],
        )
        if isinstance(self.lights_up, LitWhen):
            self._require_light_key(self.lights_up)

    def _require_light_key(self, lit_when: LitWhen) -> None:
        state_key = next((state_key for state_key in self.state_keys if state_key.key == lit_when.key), None)
        if state_key is None:
            raise LightKeyNotDeclaredException(
                f"{self.item_spec_id.value} lights up by {lit_when.key.value}, which it does not declare"
            )
        if not state_key.kind.accepts(lit_when.value):
            raise StateValueMismatchesKindException(
                f"{self.item_spec_id.value} lights up at {lit_when.value!r}, which does not fit {state_key.kind!r}"
            )
