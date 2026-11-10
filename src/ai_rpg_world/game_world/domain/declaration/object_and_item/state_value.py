from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.object_and_item_declaration_exception import TextBodyBlankException
from ai_rpg_world.game_world.domain.value_object import Count, PersonId, WorldTick
from ai_rpg_world.game_world.domain.value_object._checks import require_declared_name


@final
@dataclass(frozen=True)
class ChoiceName:
    value: str

    def __post_init__(self) -> None:
        require_declared_name("ChoiceName", self.value)


@final
@dataclass(frozen=True)
class TextBody:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise TextBodyBlankException(f"TextBody must be non-blank text, got {self.value!r}")


@final
@dataclass(frozen=True)
class FlagValue:
    raised: bool


@final
@dataclass(frozen=True)
class CountValue:
    count: Count


@final
@dataclass(frozen=True)
class ChoiceValue:
    choice: ChoiceName


@final
@dataclass(frozen=True)
class StockValue:
    amount: Count


@final
@dataclass(frozen=True)
class WrittenText:
    body: TextBody
    author: PersonId
    written_at: WorldTick


@final
@dataclass(frozen=True)
class NothingWritten:
    pass


StateValue = FlagValue | CountValue | ChoiceValue | StockValue | WrittenText | NothingWritten
