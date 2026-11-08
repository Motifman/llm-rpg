from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar, final

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
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import StateValueMismatchesKindException
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    NotEnoughStockException,
    OperationNotForStateKindException,
    StateKeyNotOwnedException,
)
from ai_rpg_world.game_world.domain.objects_and_items._occurrence import occurrence
from ai_rpg_world.game_world.domain.value_object import Count, ObjectId, PersonId, StateKeyId, Ticks, WorldTick


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


class ObjectState(AggregateRoot[ObjectStateEvent]):
    def __init__(self, declaration: ObjectDeclaration, now: WorldTick) -> None:
        super().__init__()
        self._declaration = declaration
        self._values: dict[StateKeyId, StateValue] = {}
        self._stocks: dict[StateKeyId, _StockLevel] = {}
        for state_key in declaration.state_keys:
            self._store(state_key, state_key.initial, now)
        self._revealed = not declaration.appearance.hidden_until_revealed

    @classmethod
    def open(cls, declaration: ObjectDeclaration, now: WorldTick) -> ObjectState:
        return cls(declaration, now)

    @property
    def object_id(self) -> ObjectId:
        return self._declaration.object_id

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
        kind = self._require_kind(key, StockStateKind)
        level = self._stocks[key.key].refilled(kind, now)
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
            TextWrittenEvent(**occurrence(), object_id=self.object_id, key=key.key, before=before, after=written)
        )

    def reveal(self) -> None:
        if self._revealed:
            return
        self._revealed = True
        self.add_event(ObjectRevealedEvent(**occurrence(), object_id=self.object_id))

    def value_of(self, key: ObjectStateKeyDeclaration, now: WorldTick) -> StateValue:
        self._require_owned(key)
        if isinstance(key.kind, StockStateKind):
            return StockValue(self._stocks[key.key].refilled(key.kind, now).amount)
        return self._values[key.key]

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

    def _change_count(self, key: ObjectStateKeyDeclaration, before: Count, after: Count) -> None:
        if after == before:
            return
        self._values[key.key] = CountValue(after)
        self._record_change(key, CountValue(before), CountValue(after))

    def _record_change(self, key: ObjectStateKeyDeclaration, before: StateValue, after: StateValue) -> None:
        self.add_event(
            ObjectStateChangedEvent(**occurrence(), object_id=self.object_id, key=key.key, before=before, after=after)
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
