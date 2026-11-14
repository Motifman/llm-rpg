from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from typing import TypeVar

from ai_rpg_world.game_world.domain.value_object import FlagId, WorldId, WorldTick
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    StoredMementoUnreadableException,
)

_Item = TypeVar("_Item")


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


def distinct_items(raw: object, read_item: Callable[[object], _Item]) -> frozenset[_Item]:
    if not isinstance(raw, list):
        raise StoredMementoUnreadableException(f"expected a list, got {raw!r}")
    items = [read_item(item) for item in raw]
    distinct = frozenset(items)
    if len(distinct) != len(items):
        raise StoredMementoUnreadableException(f"{len(items) - len(distinct)} items are listed more than once")
    return distinct


def world_id_from_json(raw: object) -> WorldId:
    return WorldId(json_str(raw))


def world_tick_from_json(raw: object) -> WorldTick:
    return WorldTick(json_int(raw))


def flag_id_from_json(raw: object) -> FlagId:
    return FlagId(json_str(raw))
