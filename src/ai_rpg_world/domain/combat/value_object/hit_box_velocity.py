from dataclasses import dataclass
from typing import ClassVar

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


@dataclass(frozen=True)
class HitBoxVelocity:
    """HitBoxの1ティックあたり移動量"""
    dx: float
    dy: float
    dz: float = 0.0

    EPSILON: ClassVar[float] = 1e-9

    @classmethod
    def zero(cls) -> "HitBoxVelocity":
        return cls(dx=0.0, dy=0.0, dz=0.0)

    @property
    def is_stationary(self) -> bool:
        return (
            abs(self.dx) < self.EPSILON
            and abs(self.dy) < self.EPSILON
            and abs(self.dz) < self.EPSILON
        )

    def apply_to(self, coordinate: Coordinate, step_ratio: float = 1.0) -> Coordinate:
        return Coordinate(
            int(coordinate.x + (self.dx * step_ratio)),
            int(coordinate.y + (self.dy * step_ratio)),
            int(coordinate.z + (self.dz * step_ratio)),
        )

    def apply_to_precise(self, x: float, y: float, z: float, step_ratio: float = 1.0) -> tuple[float, float, float]:
        return (
            x + (self.dx * step_ratio),
            y + (self.dy * step_ratio),
            z + (self.dz * step_ratio),
        )
