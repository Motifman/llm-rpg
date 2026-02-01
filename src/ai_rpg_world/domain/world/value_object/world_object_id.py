from dataclasses import dataclass
from ai_rpg_world.domain.world.exception.map_exception import WorldObjectIdValidationException


@dataclass(frozen=True)
class WorldObjectId:
    """ワールドオブジェクトの一意識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise WorldObjectIdValidationException(f"WorldObject ID must be positive: {self.value}")

    def __str__(self) -> str:
        return str(self.value)
