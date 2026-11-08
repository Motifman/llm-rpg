from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item import ObjectStateKeyDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import ShownKeyHoldsNoWrittenTextException


@final
@dataclass(frozen=True)
class PeopleCountAt:
    spot: SpotDeclaration


@final
@dataclass(frozen=True)
class WrittenTextOf:
    key: ObjectStateKeyDeclaration

    def __post_init__(self) -> None:
        if not self.key.kind.holds_written_text():
            raise ShownKeyHoldsNoWrittenTextException(
                f"WrittenTextOf {self.key.object_id.value}.{self.key.key.value} points at a key that holds no written text"
            )


ShownToActor = PeopleCountAt | WrittenTextOf
