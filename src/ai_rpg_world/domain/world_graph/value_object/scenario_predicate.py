"""用途を跨いで同じ意味を持つ、型付きのシナリオ述語。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioPredicateValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


@dataclass(frozen=True)
class FlagSetPredicate:
    """名前が完全一致する世界フラグが立っていることを要求する。"""

    flag_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.flag_name, str) or not self.flag_name.strip():
            raise ScenarioPredicateValidationException(
                "FlagSetPredicate.flag_name must be a non-empty str"
            )


@dataclass(frozen=True)
class TickAtLeastPredicate:
    """現在tickが指定した整数閾値以上であることを要求する。"""

    threshold: int

    def __post_init__(self) -> None:
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, int):
            raise ScenarioPredicateValidationException(
                "TickAtLeastPredicate.threshold must be an int"
            )


@dataclass(frozen=True)
class EntityAtSpotPredicate:
    """明示した1 entityが指定spotに配置されていることを要求する。"""

    entity_id: EntityId
    spot_id: SpotId

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, EntityId) or not isinstance(
            self.spot_id, SpotId
        ):
            raise ScenarioPredicateValidationException(
                "EntityAtSpotPredicate requires EntityId and SpotId"
            )


@dataclass(frozen=True)
class EntityCountAtSpotAtLeastPredicate:
    """指定spotの通常entity在席数が正の閾値以上であることを要求する。"""

    spot_id: SpotId
    required_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.spot_id, SpotId):
            raise ScenarioPredicateValidationException(
                "EntityCountAtSpotAtLeastPredicate.spot_id must be a SpotId"
            )
        if (
            isinstance(self.required_count, bool)
            or not isinstance(self.required_count, int)
            or self.required_count <= 0
        ):
            raise ScenarioPredicateValidationException(
                "EntityCountAtSpotAtLeastPredicate.required_count must be positive"
            )


ScenarioPredicate = (
    FlagSetPredicate
    | TickAtLeastPredicate
    | EntityAtSpotPredicate
    | EntityCountAtSpotAtLeastPredicate
)


__all__ = [
    "EntityAtSpotPredicate",
    "EntityCountAtSpotAtLeastPredicate",
    "FlagSetPredicate",
    "ScenarioPredicate",
    "TickAtLeastPredicate",
]
