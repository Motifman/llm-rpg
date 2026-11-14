from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    CountStateKind,
    CountValue,
    NoRefill,
    NothingWritten,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StateValue,
    StockStateKind,
    StockValue,
    TextBody,
    WrittenText,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    MementoDoesNotMatchDesignException,
    require_distinct_memento_keys,
)
from ai_rpg_world.game_world.domain.exception.object_and_item_declaration_exception import (
    StateValueMismatchesKindException,
)
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    NeverHiddenObjectUnrevealedException,
    NotEnoughStockException,
    OperationNotForStateKindException,
    StateKeyNotOwnedException,
    StateValueOfAnotherKindException,
)
from ai_rpg_world.game_world.domain.value_object import Count, ObjectId, PersonId, StateKeyId, Ticks, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True, kw_only=True)
class ObjectStateChangedEvent(DomainEvent):
    object_id: ObjectId
    key: StateKeyId
    before: StateValue
    after: StateValue


@final
@dataclass(frozen=True, kw_only=True)
class TextWrittenEvent(DomainEvent):
    object_id: ObjectId
    key: StateKeyId
    before: WrittenText | NothingWritten
    after: WrittenText


@final
@dataclass(frozen=True, kw_only=True)
class ObjectRevealedEvent(DomainEvent):
    object_id: ObjectId


ObjectStateEvent = ObjectStateChangedEvent | TextWrittenEvent | ObjectRevealedEvent

_Kind = TypeVar("_Kind")


@final
@dataclass(frozen=True)
class _StockLevel:
    amount: Count
    counted_from: WorldTick

    def refilled(self, kind: StockStateKind, now: WorldTick) -> _StockLevel:
        if isinstance(kind.refills_every, NoRefill):
            return self
        interval = kind.refills_every.value
        refills = now.ticks_since(self.counted_from).value // interval
        amount = min(kind.capacity, self.amount + Count(refills))
        if amount == kind.capacity:
            return _StockLevel(amount, now)
        # 取ったときに数え始めを now に寄せると、次の補充までの端数が消えて補充が遅れる。
        return _StockLevel(amount, self.counted_from + Ticks(refills * interval))


@final
@dataclass(frozen=True)
class ObjectStateKeyValue:
    key: StateKeyId
    value: StateValue


@final
@dataclass(frozen=True)
class ObjectStockLevel:
    key: StateKeyId
    amount: Count
    counted_from: WorldTick


@final
@dataclass(frozen=True)
class ObjectStateMemento:
    object_id: ObjectId
    values: frozenset[ObjectStateKeyValue]
    stock_levels: frozenset[ObjectStockLevel]
    revealed: bool


class ObjectState(AggregateRoot[ObjectStateEvent]):
    def __init__(
        self,
        declaration: ObjectDeclaration,
        *,
        values: frozenset[ObjectStateKeyValue],
        stock_levels: frozenset[ObjectStockLevel],
        revealed: bool,
    ) -> None:
        super().__init__()
        self._values = {key_value.key: key_value.value for key_value in values}
        self._stocks = {level.key: _StockLevel(level.amount, level.counted_from) for level in stock_levels}
        repeated_key = f"{declaration.object_id.value} has a state key more than once"
        require_distinct_memento_keys([key_value.key for key_value in values], repeated_key)
        require_distinct_memento_keys([level.key for level in stock_levels], repeated_key)
        _require_matches(declaration, self._values, self._stocks)
        if not revealed and not declaration.appearance.hidden_until_revealed:
            raise NeverHiddenObjectUnrevealedException(f"{declaration.object_id.value} is never hidden")
        self._declaration = declaration
        self._revealed = revealed

    @classmethod
    def from_declaration(cls, declaration: ObjectDeclaration, now: WorldTick) -> ObjectState:
        values = frozenset(
            ObjectStateKeyValue(state_key.key, state_key.initial)
            for state_key in declaration.state_keys
            if not isinstance(state_key.initial, StockValue)
        )
        stock_levels = frozenset(
            ObjectStockLevel(state_key.key, state_key.initial.amount, now)
            for state_key in declaration.state_keys
            if isinstance(state_key.initial, StockValue)
        )
        return cls(
            declaration,
            values=values,
            stock_levels=stock_levels,
            revealed=not declaration.appearance.hidden_until_revealed,
        )

    @classmethod
    def from_memento(cls, memento: ObjectStateMemento, design: WorldDesign) -> ObjectState:
        return cls(
            design.nouns.object_of(memento.object_id),
            values=memento.values,
            stock_levels=memento.stock_levels,
            revealed=memento.revealed,
        )

    @property
    def object_id(self) -> ObjectId:
        return self._declaration.object_id

    def memento(self) -> ObjectStateMemento:
        return ObjectStateMemento(
            object_id=self.object_id,
            values=frozenset(ObjectStateKeyValue(key, value) for key, value in self._values.items()),
            stock_levels=frozenset(
                ObjectStockLevel(key, level.amount, level.counted_from) for key, level in self._stocks.items()
            ),
            revealed=self._revealed,
        )

    def set(self, key: ObjectStateKeyDeclaration, value: StateValue, now: WorldTick) -> None:
        before = self.value_of(key, now)
        if not key.kind.accepts(value):
            raise StateValueMismatchesKindException(
                f"{value!r} does not fit {key.kind!r} of {self.object_id.value}.{key.key.value}"
            )
        if value == before:
            return
        self._store(key, value, now)
        self._record_change(key, before, value)

    def add_to_count(self, key: ObjectStateKeyDeclaration, amount: Count) -> None:
        before = self._count_of(key)
        self._change_count(key, before, before + amount)

    def subtract_from_count(self, key: ObjectStateKeyDeclaration, amount: Count) -> None:
        before = self._count_of(key)
        self._change_count(key, before, before - amount)

    def take_from_stock(self, key: ObjectStateKeyDeclaration, amount: Count, now: WorldTick) -> None:
        level = self._stock_level(key, now)
        if amount > level.amount:
            raise NotEnoughStockException(
                f"{self.object_id.value}.{key.key.value} has {level.amount.value}, cannot take {amount.value}"
            )
        if amount == Count(0):
            return
        self._stocks[key.key] = _StockLevel(level.amount - amount, level.counted_from)
        self._record_change(key, StockValue(level.amount), StockValue(level.amount - amount))

    def write_text(self, key: ObjectStateKeyDeclaration, body: TextBody, author: PersonId, now: WorldTick) -> None:
        self._require_kind(key, WrittenTextStateKind)
        before = self._values[key.key]
        assert isinstance(before, (WrittenText, NothingWritten))
        written = WrittenText(body=body, author=author, written_at=now)
        if written == before:
            return
        self._values[key.key] = written
        self.add_event(
            TextWrittenEvent(**new_event_stamp(), object_id=self.object_id, key=key.key, before=before, after=written)
        )

    def reveal(self) -> None:
        if self._revealed:
            return
        self._revealed = True
        self.add_event(ObjectRevealedEvent(**new_event_stamp(), object_id=self.object_id))

    def value_of(self, key: ObjectStateKeyDeclaration, now: WorldTick) -> StateValue:
        self._require_owned(key)
        if key.kind.holds_stock():
            return StockValue(self._stock_level(key, now).amount)
        return self._values[key.key]

    def count_of(self, key: ObjectStateKeyDeclaration, now: WorldTick) -> Count:
        value = self.value_of(key, now)
        if not key.kind.holds_count():
            raise StateValueOfAnotherKindException(
                f"{key.object_id.value}.{key.key.value} holds {value!r}, not a count"
            )
        return self._count_of(key)

    def stock_of(self, key: ObjectStateKeyDeclaration, now: WorldTick) -> Count:
        value = self.value_of(key, now)
        if not key.kind.holds_stock():
            raise StateValueOfAnotherKindException(
                f"{key.object_id.value}.{key.key.value} holds {value!r}, not a stock"
            )
        return self._stock_level(key, now).amount

    def is_revealed(self) -> bool:
        return self._revealed

    def _store(self, key: ObjectStateKeyDeclaration, value: StateValue, now: WorldTick) -> None:
        if isinstance(value, StockValue):
            self._stocks[key.key] = _StockLevel(value.amount, now)
        else:
            self._values[key.key] = value

    def _count_of(self, key: ObjectStateKeyDeclaration) -> Count:
        self._require_kind(key, CountStateKind)
        value = self._values[key.key]
        assert isinstance(value, CountValue)
        return value.count

    def _stock_level(self, key: ObjectStateKeyDeclaration, now: WorldTick) -> _StockLevel:
        kind = self._require_kind(key, StockStateKind)
        return self._stocks[key.key].refilled(kind, now)

    def _change_count(self, key: ObjectStateKeyDeclaration, before: Count, after: Count) -> None:
        if after == before:
            return
        self._values[key.key] = CountValue(after)
        self._record_change(key, CountValue(before), CountValue(after))

    def _record_change(self, key: ObjectStateKeyDeclaration, before: StateValue, after: StateValue) -> None:
        self.add_event(
            ObjectStateChangedEvent(
                **new_event_stamp(), object_id=self.object_id, key=key.key, before=before, after=after
            )
        )

    def _require_owned(self, key: ObjectStateKeyDeclaration) -> None:
        if key not in self._declaration.state_keys:
            raise StateKeyNotOwnedException(
                f"{self.object_id.value} does not have {key.object_id.value}.{key.key.value}"
            )

    def _require_kind(self, key: ObjectStateKeyDeclaration, kind_type: type[_Kind]) -> _Kind:
        self._require_owned(key)
        if not isinstance(key.kind, kind_type):
            raise OperationNotForStateKindException(
                f"{self.object_id.value}.{key.key.value} is {key.kind!r}, not {kind_type.__name__}"
            )
        return key.kind


def _require_matches(
    declaration: ObjectDeclaration, values: dict[StateKeyId, StateValue], stocks: dict[StateKeyId, _StockLevel]
) -> None:
    declared_stocks = {key.key for key in declaration.state_keys if key.kind.holds_stock()}
    declared_values = {key.key for key in declaration.state_keys} - declared_stocks
    if declared_values != values.keys() or declared_stocks != stocks.keys():
        raise MementoDoesNotMatchDesignException(
            f"{declaration.object_id.value} has values {sorted(key.value for key in values)} "
            f"and stocks {sorted(key.value for key in stocks)}, which its declaration does not have"
        )
    for state_key in declaration.state_keys:
        value = StockValue(stocks[state_key.key].amount) if state_key.key in stocks else values[state_key.key]
        if not state_key.kind.can_hold(value):
            raise StateValueMismatchesKindException(
                f"{value!r} of {declaration.object_id.value} does not fit {state_key.kind!r} of {state_key.key.value}"
            )
