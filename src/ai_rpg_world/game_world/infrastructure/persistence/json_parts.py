from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeVar, cast, final

from ai_rpg_world.game_world.domain.value_object import FlagId, PersonId, WorldId, WorldTick
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    MementoNotStorableException,
    StoredMementoUnreadableException,
)

_Item = TypeVar("_Item")
_Union = TypeVar("_Union")
_Enum = TypeVar("_Enum", bound=Enum)


def exact_fields(raw: object, keys: Collection[str]) -> Mapping[str, object]:
    if not isinstance(raw, dict):
        raise StoredMementoUnreadableException(f"expected an object, got {raw!r}")
    unknown = sorted(repr(key) for key in raw.keys() - set(keys))
    missing = sorted(set(keys) - raw.keys())
    if unknown or missing:
        raise StoredMementoUnreadableException(f"unknown keys {unknown}, missing keys {missing}")
    return raw


def json_str(raw: object) -> str:
    if not isinstance(raw, str):
        raise StoredMementoUnreadableException(f"expected a string, got {raw!r}")
    return raw


def json_int(raw: object) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise StoredMementoUnreadableException(f"expected an integer, got {raw!r}")
    return raw


def json_bool(raw: object) -> bool:
    if not isinstance(raw, bool):
        raise StoredMementoUnreadableException(f"expected true or false, got {raw!r}")
    return raw


def _json_list(raw: object) -> list[object]:
    if not isinstance(raw, list):
        raise StoredMementoUnreadableException(f"expected a list, got {raw!r}")
    return raw


def ordered_items(raw: object, read_item: Callable[[object], _Item]) -> tuple[_Item, ...]:
    return tuple(read_item(item) for item in _json_list(raw))


def distinct_items(raw: object, read_item: Callable[[object], _Item]) -> frozenset[_Item]:
    items = [read_item(item) for item in _json_list(raw)]
    distinct = frozenset(items)
    if len(distinct) != len(items):
        raise StoredMementoUnreadableException(f"{len(items) - len(distinct)} items are listed more than once")
    return distinct


def enum_to_json(value: Enum) -> str:
    return value.name


def enum_from_json(raw: object, enum_type: type[_Enum]) -> _Enum:
    name = json_str(raw)
    member = enum_type.__members__.get(name)
    if member is None or member.name != name:
        raise StoredMementoUnreadableException(f"{name!r} is not a member name of {enum_type.__name__}")
    return member


@final
@dataclass(frozen=True)
class JsonUnionMember(Generic[_Item]):
    tag: str
    member_type: type[_Item]
    to_json: Callable[[_Item], object]
    from_json: Callable[[object], _Item]

    @classmethod
    def fieldless(cls, tag: str, value: _Item) -> JsonUnionMember[_Item]:
        def read(raw: object) -> _Item:
            exact_fields(raw, ())
            return value

        return cls(tag, type(value), lambda _: {}, read)


@final
class JsonUnion(Generic[_Union]):
    def __init__(self, *members: JsonUnionMember[Any]) -> None:
        self._by_tag: dict[str, JsonUnionMember[Any]] = {}
        self._by_type: dict[type, JsonUnionMember[Any]] = {}
        for member in members:
            if member.tag in self._by_tag or member.member_type in self._by_type:
                raise ValueError(f"{member.tag} ({member.member_type.__name__}) is listed twice")
            self._by_tag[member.tag] = member
            self._by_type[member.member_type] = member

    def to_json(self, value: _Union) -> object:
        member = self._by_type.get(type(value))
        if member is None:
            raise MementoNotStorableException(f"{type(value).__name__} is not one of {sorted(self._by_tag)}")
        return {member.tag: member.to_json(value)}

    def from_json(self, raw: object) -> _Union:
        if not isinstance(raw, dict) or len(raw) != 1:
            raise StoredMementoUnreadableException(
                f"expected an object with one of {sorted(self._by_tag)}, got {raw!r}"
            )
        [(tag, value)] = raw.items()
        member = self._by_tag.get(tag)
        if member is None:
            raise StoredMementoUnreadableException(f"unknown tag {tag!r}, expected one of {sorted(self._by_tag)}")
        return cast(_Union, member.from_json(value))


def world_id_from_json(raw: object) -> WorldId:
    return WorldId(json_str(raw))


def world_tick_from_json(raw: object) -> WorldTick:
    return WorldTick(json_int(raw))


def flag_id_from_json(raw: object) -> FlagId:
    return FlagId(json_str(raw))


def person_id_from_json(raw: object) -> PersonId:
    return PersonId(json_str(raw))
