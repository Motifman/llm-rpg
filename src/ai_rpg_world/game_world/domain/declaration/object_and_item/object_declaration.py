from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item._state_keys import require_own_distinct_keys
from ai_rpg_world.game_world.domain.declaration.object_and_item.state_kind import StateKind
from ai_rpg_world.game_world.domain.declaration.object_and_item.state_value import StateValue
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import StateValueMismatchesKindException
from ai_rpg_world.game_world.domain.value_object import ObjectId, SpotId, StateKeyId


@final
@dataclass(frozen=True)
class ObjectStateKeyDeclaration:
    object_id: ObjectId
    key: StateKeyId
    kind: StateKind
    initial: StateValue

    def __post_init__(self) -> None:
        if not self.kind.accepts_initial(self.initial):
            raise StateValueMismatchesKindException(
                f"initial {self.initial!r} of {self.object_id.value}.{self.key.value} does not fit {self.kind!r}"
            )


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
    name: str
    description: str
    appearance: ObjectAppearance
    state_keys: tuple[ObjectStateKeyDeclaration, ...]

    def __post_init__(self) -> None:
        require_own_distinct_keys(
            self.object_id,
            [state_key.object_id for state_key in self.state_keys],
            [state_key.key for state_key in self.state_keys],
        )
