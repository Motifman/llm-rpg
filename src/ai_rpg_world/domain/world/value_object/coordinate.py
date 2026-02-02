import math
from dataclasses import dataclass
from typing import TYPE_CHECKING
from ai_rpg_world.domain.world.exception.map_exception import CoordinateValidationException

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum


@dataclass(frozen=True)
class Coordinate:
    """物理マップ上の (x, y, z) 座標"""
    x: int
    y: int
    z: int = 0

    def __post_init__(self):
        # x, y 座標は0以上であることを期待（仕様に応じて変更可能）
        # z は階層を表すため、地下を考慮して負の値も許容する設計とする
        if self.x < 0 or self.y < 0:
            raise CoordinateValidationException(f"x and y coordinates must be non-negative: ({self.x}, {self.y}, {self.z})")

    def __str__(self) -> str:
        return f"({self.x}, {self.y}, {self.z})"
    
    def distance_to(self, other: "Coordinate") -> int:
        """マンハッタン距離を計算（zの差も考慮）"""
        return abs(self.x - other.x) + abs(self.y - other.y) + abs(self.z - other.z)

    def euclidean_distance_to(self, other: "Coordinate") -> float:
        """直線距離（ユークリッド距離）を計算"""
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2 + (self.z - other.z)**2)

    def neighbor(self, direction: "DirectionEnum") -> "Coordinate":
        """指定された方向の隣接座標を返す"""
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        
        if direction == DirectionEnum.NORTH:
            return Coordinate(self.x, self.y - 1, self.z)
        elif direction == DirectionEnum.SOUTH:
            return Coordinate(self.x, self.y + 1, self.z)
        elif direction == DirectionEnum.EAST:
            return Coordinate(self.x + 1, self.y, self.z)
        elif direction == DirectionEnum.WEST:
            return Coordinate(self.x - 1, self.y, self.z)
        elif direction == DirectionEnum.UP:
            return Coordinate(self.x, self.y, self.z + 1)
        elif direction == DirectionEnum.DOWN:
            return Coordinate(self.x, self.y, self.z - 1)
        return self

    def direction_to(self, other: "Coordinate") -> "DirectionEnum":
        """別の座標への方向を取得する（隣接している前提）"""
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        from ai_rpg_world.domain.world.exception.map_exception import SameCoordinateDirectionException
        
        dx = other.x - self.x
        dy = other.y - self.y
        dz = other.z - self.z

        if dz > 0: return DirectionEnum.UP
        if dz < 0: return DirectionEnum.DOWN
        if dx > 0: return DirectionEnum.EAST
        if dx < 0: return DirectionEnum.WEST
        if dy > 0: return DirectionEnum.SOUTH
        if dy < 0: return DirectionEnum.NORTH
        
        raise SameCoordinateDirectionException(f"Cannot determine direction for the same coordinate: {self}")

    def to_2d(self) -> tuple[int, int]:
        """(x, y) のタプルを返す"""
        return (self.x, self.y)
