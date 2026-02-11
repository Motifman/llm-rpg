from dataclasses import dataclass

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


@dataclass(frozen=True)
class HitBoxVelocity:
    """HitBoxの1ティックあたり移動量"""
    dx: int
    dy: int
    dz: int = 0

    @classmethod
    def zero(cls) -> "HitBoxVelocity":
        return cls(dx=0, dy=0, dz=0)

    @property
    def is_stationary(self) -> bool:
        return self.dx == 0 and self.dy == 0 and self.dz == 0

    def apply_to(self, coordinate: Coordinate) -> Coordinate:
        return Coordinate(
            coordinate.x + self.dx,
            coordinate.y + self.dy,
            coordinate.z + self.dz,
        )
