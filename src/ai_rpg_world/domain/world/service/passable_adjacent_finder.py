"""PassableAdjacentFinder: オブジェクト座標に隣接する通行可能セルを探索するドメインサービス。

リポジトリに依存せず、aggregate から渡された物理マップのみで判定を行う。
"""


from typing import ClassVar

from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    CoordinateValidationException,
    TileNotFoundException,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class PassableAdjacentFinder:
    """
    オブジェクト座標に隣接する通行可能セルを1つ返すドメインサービス。
    リポジトリ非依存。
    """

    PLANAR_DIRECTIONS: ClassVar[list[DirectionEnum]] = [
        DirectionEnum.NORTH,
        DirectionEnum.NORTHEAST,
        DirectionEnum.EAST,
        DirectionEnum.SOUTHEAST,
        DirectionEnum.SOUTH,
        DirectionEnum.SOUTHWEST,
        DirectionEnum.WEST,
        DirectionEnum.NORTHWEST,
    ]

    @classmethod
    def find_one(
        cls,
        physical_map: PhysicalMapAggregate,
        object_coord: Coordinate,
        capability: MovementCapability,
        exclude_object_id: WorldObjectId | None = None,
    ) -> Coordinate | None:
        """
        オブジェクト座標に隣接する通行可能セルを1つ返す。
        見つからなければ None。

        Args:
            physical_map: 物理マップ（is_passable が利用可能な aggregate）
            object_coord: 対象オブジェクトの座標
            capability: 移動能力
            exclude_object_id: 通行判定から除外するオブジェクトID（対象オブジェクト自体など）

        Returns:
            通行可能な隣接座標。見つからなければ None。
        """
        for direction in cls.PLANAR_DIRECTIONS:
            try:
                adj = object_coord.neighbor(direction)
                if physical_map.is_passable(
                    adj, capability, exclude_object_id=exclude_object_id
                ):
                    return adj
            except (TileNotFoundException, CoordinateValidationException):
                continue
        return None
