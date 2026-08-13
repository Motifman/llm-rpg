"""用途を跨いで同じ意味を持つ、型付きのシナリオ述語。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
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


@dataclass(frozen=True)
class ItemSpecOwnedPredicate:
    """解決済みの所持品種集合に指定品目が含まれることを要求する。"""

    item_spec_id: ItemSpecId

    def __post_init__(self) -> None:
        if not isinstance(self.item_spec_id, ItemSpecId):
            raise ScenarioPredicateValidationException(
                "ItemSpecOwnedPredicate.item_spec_id must be an ItemSpecId"
            )


@dataclass(frozen=True)
class ItemSpecCountAtLeastPredicate:
    """指定品目の解決済み個数が正の閾値以上であることを要求する。"""

    item_spec_id: ItemSpecId
    required_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.item_spec_id, ItemSpecId):
            raise ScenarioPredicateValidationException(
                "ItemSpecCountAtLeastPredicate.item_spec_id must be an ItemSpecId"
            )
        if (
            isinstance(self.required_count, bool)
            or not isinstance(self.required_count, int)
            or self.required_count <= 0
        ):
            raise ScenarioPredicateValidationException(
                "ItemSpecCountAtLeastPredicate.required_count must be positive"
            )


@dataclass(frozen=True)
class StateValuesMatchPredicate:
    """現在stateが要求された全キー・値を含むことを要求する。"""

    required_values: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.required_values, Mapping) or any(
            not isinstance(key, str) for key in self.required_values
        ):
            raise ScenarioPredicateValidationException(
                "StateValuesMatchPredicate.required_values must map str keys"
            )
        object.__setattr__(
            self,
            "required_values",
            MappingProxyType(deepcopy(dict(self.required_values))),
        )


@dataclass(frozen=True)
class StateIntAtLeastPredicate:
    """stateの指定キーを整数として読み、閾値以上であることを要求する。"""

    state_key: str
    threshold: int

    def __post_init__(self) -> None:
        if not isinstance(self.state_key, str) or not self.state_key:
            raise ScenarioPredicateValidationException(
                "StateIntAtLeastPredicate.state_key must be a non-empty str"
            )
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, int):
            raise ScenarioPredicateValidationException(
                "StateIntAtLeastPredicate.threshold must be an int"
            )


@dataclass(frozen=True)
class WeatherTypeIsPredicate:
    """現在天候が指定した列挙値と一致することを要求する。"""

    required_weather_type: WeatherTypeEnum

    def __post_init__(self) -> None:
        if not isinstance(self.required_weather_type, WeatherTypeEnum):
            raise ScenarioPredicateValidationException(
                "WeatherTypeIsPredicate.required_weather_type must be a "
                "WeatherTypeEnum"
            )


ScenarioPredicate = (
    FlagSetPredicate
    | TickAtLeastPredicate
    | EntityAtSpotPredicate
    | EntityCountAtSpotAtLeastPredicate
    | ItemSpecOwnedPredicate
    | ItemSpecCountAtLeastPredicate
    | StateValuesMatchPredicate
    | StateIntAtLeastPredicate
    | WeatherTypeIsPredicate
)


__all__ = [
    "EntityAtSpotPredicate",
    "EntityCountAtSpotAtLeastPredicate",
    "FlagSetPredicate",
    "ItemSpecCountAtLeastPredicate",
    "ItemSpecOwnedPredicate",
    "ScenarioPredicate",
    "StateIntAtLeastPredicate",
    "StateValuesMatchPredicate",
    "TickAtLeastPredicate",
    "WeatherTypeIsPredicate",
]
