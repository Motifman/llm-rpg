from dataclasses import dataclass, field
from typing import Set, Dict, FrozenSet
from ai_rpg_world.domain.world.enum.world_enum import MovementCapabilityEnum


@dataclass(frozen=True)
class MovementCapability:
    """アクターの移動能力と速度倍率を管理する値オブジェクト"""
    capabilities: FrozenSet[MovementCapabilityEnum] = field(default_factory=lambda: frozenset({MovementCapabilityEnum.WALK}))
    speed_modifier: float = 1.0

    def __post_init__(self):
        if self.speed_modifier < 0:
            object.__setattr__(self, 'speed_modifier', 0.0)

    def has_capability(self, capability: MovementCapabilityEnum) -> bool:
        return capability in self.capabilities

    def with_capability(self, capability: MovementCapabilityEnum) -> "MovementCapability":
        new_capabilities = set(self.capabilities)
        new_capabilities.add(capability)
        return MovementCapability(frozenset(new_capabilities), self.speed_modifier)

    def without_capability(self, capability: MovementCapabilityEnum) -> "MovementCapability":
        new_capabilities = set(self.capabilities)
        new_capabilities.discard(capability)
        return MovementCapability(frozenset(new_capabilities), self.speed_modifier)

    def with_speed_modifier(self, modifier: float) -> "MovementCapability":
        return MovementCapability(self.capabilities, modifier)

    @classmethod
    def normal_walk(cls) -> "MovementCapability":
        return cls(frozenset({MovementCapabilityEnum.WALK}), 1.0)

    @classmethod
    def ghost(cls) -> "MovementCapability":
        return cls(frozenset({MovementCapabilityEnum.WALK, MovementCapabilityEnum.GHOST_WALK}), 1.0)
