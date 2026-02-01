from dataclasses import dataclass, field
from typing import Set, FrozenSet
from ai_rpg_world.domain.world.enum.world_enum import TerrainTypeEnum, MovementCapabilityEnum
from ai_rpg_world.domain.world.value_object.movement_cost import MovementCost
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability


@dataclass(frozen=True)
class TerrainType:
    """地形の種類と基本移動コスト、通行に必要な能力、不透明度"""
    type: TerrainTypeEnum
    base_cost: MovementCost
    required_capabilities: FrozenSet[MovementCapabilityEnum] = field(default_factory=lambda: frozenset({MovementCapabilityEnum.WALK}))
    is_opaque: bool = False

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
        return cls(TerrainTypeEnum.WATER, MovementCost(10.0), frozenset({MovementCapabilityEnum.SWIM, MovementCapabilityEnum.FLY}))

    @classmethod
    def wall(cls) -> "TerrainType":
        return cls(TerrainTypeEnum.WALL, MovementCost.impassable(), frozenset({MovementCapabilityEnum.GHOST_WALK, MovementCapabilityEnum.FLY}), is_opaque=True)

    @classmethod
    def glass_wall(cls) -> "TerrainType":
        """通行不可だが視線は通る地形"""
        return cls(TerrainTypeEnum.WALL, MovementCost.impassable(), frozenset({MovementCapabilityEnum.GHOST_WALK, MovementCapabilityEnum.FLY}), is_opaque=False)

    @property
    def is_walkable(self) -> bool:
        # 基本的な歩行能力で通行可能か
        return MovementCapabilityEnum.WALK in self.required_capabilities and self.base_cost.value != float('inf')

    def can_pass(self, actor_capability: MovementCapability) -> bool:
        """アクターの能力でこの地形を通行可能か判定する"""
        # いずれかの必要能力を持っていれば通行可能
        return any(cap in actor_capability.capabilities for cap in self.required_capabilities)

    def calculate_cost(self, actor_capability: MovementCapability) -> MovementCost:
        """アクターの能力に応じた移動コストを計算する"""
        if not self.can_pass(actor_capability):
            return MovementCost.impassable()
        
        # 基本コストをアクターの速度倍率で割る（速度が2倍ならコストは1/2）
        if actor_capability.speed_modifier <= 0:
            return MovementCost.impassable()
            
        return MovementCost(self.base_cost.value / actor_capability.speed_modifier)
