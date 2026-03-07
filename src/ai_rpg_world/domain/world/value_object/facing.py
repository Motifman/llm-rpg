from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Facing:
    """ワールド上の向きを表す値オブジェクト。"""

    direction: "DirectionEnum"

    def to_direction(self) -> "DirectionEnum":
        return self.direction

    def to_2d_vector(self) -> tuple[int, int] | None:
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum

        vectors = {
            DirectionEnum.NORTH: (0, -1),
            DirectionEnum.NORTHEAST: (1, -1),
            DirectionEnum.EAST: (1, 0),
            DirectionEnum.SOUTHEAST: (1, 1),
            DirectionEnum.SOUTH: (0, 1),
            DirectionEnum.SOUTHWEST: (-1, 1),
            DirectionEnum.WEST: (-1, 0),
            DirectionEnum.NORTHWEST: (-1, -1),
        }
        return vectors.get(self.direction)

    def to_delta(self, step: int = 1) -> tuple[int, int, int]:
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum

        if self.direction == DirectionEnum.UP:
            return (0, 0, step)
        if self.direction == DirectionEnum.DOWN:
            return (0, 0, -step)
        vec = self.to_2d_vector()
        if vec is None:
            return (0, 0, 0)
        return (vec[0] * step, vec[1] * step, 0)

    def rotation_from_south_degrees(self) -> float:
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum

        angles = {
            DirectionEnum.SOUTH: 0.0,
            DirectionEnum.SOUTHEAST: -45.0,
            DirectionEnum.EAST: -90.0,
            DirectionEnum.NORTHEAST: -135.0,
            DirectionEnum.NORTH: 180.0,
            DirectionEnum.NORTHWEST: 135.0,
            DirectionEnum.WEST: 90.0,
            DirectionEnum.SOUTHWEST: 45.0,
        }
        return angles.get(self.direction, 0.0)

    @classmethod
    def from_direction(cls, direction: "DirectionEnum") -> "Facing":
        return cls(direction)

    @classmethod
    def from_delta(cls, dx: int, dy: int, dz: int = 0) -> "Facing":
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum

        if dz > 0:
            return cls(DirectionEnum.UP)
        if dz < 0:
            return cls(DirectionEnum.DOWN)
        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)
        mapping = {
            (0, -1): DirectionEnum.NORTH,
            (1, -1): DirectionEnum.NORTHEAST,
            (1, 0): DirectionEnum.EAST,
            (1, 1): DirectionEnum.SOUTHEAST,
            (0, 1): DirectionEnum.SOUTH,
            (-1, 1): DirectionEnum.SOUTHWEST,
            (-1, 0): DirectionEnum.WEST,
            (-1, -1): DirectionEnum.NORTHWEST,
        }
        return cls(mapping[(step_x, step_y)])
