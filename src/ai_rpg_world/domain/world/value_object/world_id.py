from dataclasses import dataclass
from ai_rpg_world.domain.world.exception.map_exception import WorldIdValidationException


@dataclass(frozen=True)
class WorldId:
    """世界の一意識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise WorldIdValidationException(f"World ID must be positive: {self.value}")

    def __str__(self) -> str:
        return str(self.value)
