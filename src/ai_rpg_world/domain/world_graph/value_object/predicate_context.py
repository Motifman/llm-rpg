"""共通シナリオ述語へ渡す、用途から独立した評価文脈。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, FrozenSet, Mapping, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PredicateContextValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


@dataclass(frozen=True)
class WorldFlagPredicateContext:
    """世界フラグ判定に必要な集合。Noneは未配線、空集合は正当な世界状態。"""

    world_flags: Optional[FrozenSet[str]]

    def __post_init__(self) -> None:
        if self.world_flags is not None and (
            not isinstance(self.world_flags, frozenset)
            or any(
                not isinstance(flag_name, str) or not flag_name
                for flag_name in self.world_flags
            )
        ):
            raise PredicateContextValidationException(
                "world_flags must be a frozenset of non-empty str or None"
            )


@dataclass(frozen=True)
class TickPredicateContext:
    """tick判定に必要な現在値。Noneは評価入力の未配線を表す。"""

    current_tick: Optional[WorldTick]

    def __post_init__(self) -> None:
        if self.current_tick is not None and not isinstance(
            self.current_tick, WorldTick
        ):
            raise PredicateContextValidationException(
                "current_tick must be a WorldTick or None"
            )


@dataclass(frozen=True)
class EntityPlacementPredicateContext:
    """通常entityの配置snapshot。Noneは未配線、空mappingは正当な世界状態。"""

    entity_locations: Optional[Mapping[EntityId, SpotId]]

    def __post_init__(self) -> None:
        locations = self.entity_locations
        if locations is None:
            return
        if not isinstance(locations, Mapping) or any(
            not isinstance(entity_id, EntityId) or not isinstance(spot_id, SpotId)
            for entity_id, spot_id in locations.items()
        ):
            raise PredicateContextValidationException(
                "entity_locations must map EntityId to SpotId or be None"
            )
        object.__setattr__(self, "entity_locations", MappingProxyType(dict(locations)))


@dataclass(frozen=True)
class OwnedItemSpecsPredicateContext:
    """解決済み所持品種の集合。Noneは未配線、空集合は正当な未所持。"""

    owned_item_spec_ids: Optional[FrozenSet[ItemSpecId]]

    def __post_init__(self) -> None:
        item_spec_ids = self.owned_item_spec_ids
        if item_spec_ids is not None and (
            not isinstance(item_spec_ids, frozenset)
            or any(not isinstance(item_spec_id, ItemSpecId) for item_spec_id in item_spec_ids)
        ):
            raise PredicateContextValidationException(
                "owned_item_spec_ids must be a frozenset of ItemSpecId or None"
            )


@dataclass(frozen=True)
class ItemSpecCountsPredicateContext:
    """解決済み品目別個数。Noneは未配線、空mappingは正当な未所持。"""

    item_spec_counts: Optional[Mapping[ItemSpecId, int]]

    def __post_init__(self) -> None:
        counts = self.item_spec_counts
        if counts is None:
            return
        if not isinstance(counts, Mapping) or any(
            not isinstance(item_spec_id, ItemSpecId)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for item_spec_id, count in counts.items()
        ):
            raise PredicateContextValidationException(
                "item_spec_counts must map ItemSpecId to non-negative int or be None"
            )
        object.__setattr__(self, "item_spec_counts", MappingProxyType(dict(counts)))


@dataclass(frozen=True)
class StateValuesPredicateContext:
    """評価対象stateのsnapshot。Noneは未配線、空mappingは正当な状態。"""

    state_values: Optional[Mapping[str, Any]]

    def __post_init__(self) -> None:
        values = self.state_values
        if values is None:
            return
        if not isinstance(values, Mapping) or any(
            not isinstance(key, str) for key in values
        ):
            raise PredicateContextValidationException(
                "state_values must map str keys or be None"
            )
        object.__setattr__(
            self,
            "state_values",
            MappingProxyType(deepcopy(dict(values))),
        )


@dataclass(frozen=True)
class WeatherTypePredicateContext:
    """天候判定の現在値。Noneは評価入力の未配線を表す。"""

    current_weather_type: Optional[WeatherTypeEnum]

    def __post_init__(self) -> None:
        if self.current_weather_type is not None and not isinstance(
            self.current_weather_type, WeatherTypeEnum
        ):
            raise PredicateContextValidationException(
                "current_weather_type must be a WeatherTypeEnum or None"
            )


PredicateContext = (
    WorldFlagPredicateContext
    | TickPredicateContext
    | EntityPlacementPredicateContext
    | OwnedItemSpecsPredicateContext
    | ItemSpecCountsPredicateContext
    | StateValuesPredicateContext
    | WeatherTypePredicateContext
)


__all__ = [
    "EntityPlacementPredicateContext",
    "ItemSpecCountsPredicateContext",
    "OwnedItemSpecsPredicateContext",
    "PredicateContext",
    "StateValuesPredicateContext",
    "TickPredicateContext",
    "WorldFlagPredicateContext",
    "WeatherTypePredicateContext",
]
