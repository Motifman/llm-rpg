from typing import Optional
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.movement_cost import MovementCost


class Tile:
    """物理マップ上のタイル"""
    def __init__(
        self,
        coordinate: Coordinate,
        terrain_type: TerrainType,
        is_walkable_override: bool = None
    ):
        self._coordinate = coordinate
        self._terrain_type = terrain_type
        # 地形タイプによる通行可能性を基本とするが、個別に上書き可能にする（例：一時的な障害物）
        self._is_walkable_override = is_walkable_override

    @property
    def coordinate(self) -> Coordinate:
        return self._coordinate

    @property
    def terrain_type(self) -> TerrainType:
        return self._terrain_type

    @property
    def is_walkable(self) -> bool:
        if self._is_walkable_override is not None:
            return self._is_walkable_override
        return self._terrain_type.is_walkable

    @property
    def movement_cost(self) -> MovementCost:
        return self._terrain_type.base_cost

    def override_walkable(self, is_walkable: bool):
        """通行可能性を上書きする"""
        self._is_walkable_override = is_walkable

    def reset_walkable(self):
        """通行可能性の上書きを解除する"""
        self._is_walkable_override = None

    def change_terrain(self, new_terrain_type: TerrainType):
        """地形を変更する"""
        self._terrain_type = new_terrain_type
