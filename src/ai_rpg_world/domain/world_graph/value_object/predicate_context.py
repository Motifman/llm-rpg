"""共通シナリオ述語へ渡す、用途から独立した評価文脈。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import FrozenSet, Mapping, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
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


PredicateContext = (
    WorldFlagPredicateContext | TickPredicateContext | EntityPlacementPredicateContext
)


__all__ = [
    "EntityPlacementPredicateContext",
    "PredicateContext",
    "TickPredicateContext",
    "WorldFlagPredicateContext",
]
