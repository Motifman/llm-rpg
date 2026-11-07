from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item.state_value import (
    ChoiceName,
    ChoiceValue,
    CountValue,
    FlagValue,
    NothingWritten,
    StateValue,
    StockValue,
)
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import (
    ChoiceDuplicatedException,
    NoChoicesDeclaredException,
    StockCapacityBelowOneException,
    StockRefillIntervalBelowOneException,
)
from ai_rpg_world.game_world.domain.value_object import Count, Ticks


@final
@dataclass(frozen=True)
class FlagStateKind:
    def accepts(self, value: StateValue) -> bool:
        return isinstance(value, FlagValue)

    def accepts_initial(self, value: StateValue) -> bool:
        return self.accepts(value)


@final
@dataclass(frozen=True)
class CountStateKind:
    def accepts(self, value: StateValue) -> bool:
        return isinstance(value, CountValue)

    def accepts_initial(self, value: StateValue) -> bool:
        return self.accepts(value)


@final
@dataclass(frozen=True)
class ChoiceStateKind:
    choices: tuple[ChoiceName, ...]

    def __post_init__(self) -> None:
        if not self.choices:
            raise NoChoicesDeclaredException("ChoiceStateKind needs at least one choice")
        if len(set(self.choices)) != len(self.choices):
            raise ChoiceDuplicatedException(f"ChoiceStateKind choices must not repeat, got {self.choices!r}")

    def accepts(self, value: StateValue) -> bool:
        return isinstance(value, ChoiceValue) and value.choice in self.choices

    def accepts_initial(self, value: StateValue) -> bool:
        return self.accepts(value)


@final
@dataclass(frozen=True)
class NoRefill:
    pass


@final
@dataclass(frozen=True)
class StockStateKind:
    capacity: Count
    refills_every: Ticks | NoRefill

    def __post_init__(self) -> None:
        if self.capacity < Count(1):
            raise StockCapacityBelowOneException(f"StockStateKind capacity must be >= 1, got {self.capacity.value}")
        if isinstance(self.refills_every, Ticks) and self.refills_every < Ticks(1):
            raise StockRefillIntervalBelowOneException(
                f"StockStateKind refills_every must be >= 1 tick, got {self.refills_every.value}"
            )

    def accepts_initial(self, value: StateValue) -> bool:
        return isinstance(value, StockValue) and value.amount <= self.capacity


@final
@dataclass(frozen=True)
class WrittenTextStateKind:
    def accepts_initial(self, value: StateValue) -> bool:
        return isinstance(value, NothingWritten)


ItemStateKind = FlagStateKind | CountStateKind | ChoiceStateKind
StateKind = ItemStateKind | StockStateKind | WrittenTextStateKind
