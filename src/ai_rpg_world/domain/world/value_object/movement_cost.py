from dataclasses import dataclass
from ai_rpg_world.domain.world.exception.map_exception import MovementCostValidationException


@dataclass(frozen=True)
class MovementCost:
    """移動にかかる重み"""
    value: float

    def __post_init__(self):
        if self.value < 0:
            raise MovementCostValidationException(f"Movement cost cannot be negative: {self.value}")

    def __add__(self, other: "MovementCost") -> "MovementCost":
        return MovementCost(self.value + other.value)
    
    def __str__(self) -> str:
        return str(self.value)
    
    @classmethod
    def zero(cls) -> "MovementCost":
        return cls(0.0)
    
    @classmethod
    def normal(cls) -> "MovementCost":
        return cls(1.0)
    
    @classmethod
    def high(cls) -> "MovementCost":
        return cls(2.0)
    
    @classmethod
    def impassable(cls) -> "MovementCost":
        return cls(float('inf'))
