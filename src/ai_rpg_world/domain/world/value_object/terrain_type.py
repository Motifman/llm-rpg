from dataclasses import dataclass
from ai_rpg_world.domain.world.enum.world_enum import TerrainTypeEnum
from ai_rpg_world.domain.world.value_object.movement_cost import MovementCost


@dataclass(frozen=True)
class TerrainType:
    """地形の種類と基本移動コスト"""
    type: TerrainTypeEnum
    base_cost: MovementCost

    @classmethod
    def road(cls) -> "TerrainType":
        return cls(TerrainTypeEnum.ROAD, MovementCost(1.0))

    @classmethod
    def grass(cls) -> "TerrainType":
        return cls(TerrainTypeEnum.GRASS, MovementCost(1.2))

    @classmethod
    def bush(cls) -> "TerrainType":
        return cls(TerrainTypeEnum.BUSH, MovementCost(2.5))

    @classmethod
    def swamp(cls) -> "TerrainType":
        return cls(TerrainTypeEnum.SWAMP, MovementCost(5.0))

    @classmethod
    def water(cls) -> "TerrainType":
        return cls(TerrainTypeEnum.WATER, MovementCost(10.0))

    @classmethod
    def wall(cls) -> "TerrainType":
        return cls(TerrainTypeEnum.WALL, MovementCost.impassable())

    @property
    def is_walkable(self) -> bool:
        return self.base_cost.value != float('inf')
