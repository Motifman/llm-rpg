from dataclasses import dataclass
from ai_rpg_world.domain.world.exception.map_exception import CoordinateValidationException


@dataclass(frozen=True)
class Coordinate:
    """物理マップ上の (x, y) 座標"""
    x: int
    y: int

    def __post_init__(self):
        # 座標は0以上であることを期待（仕様に応じて変更可能）
        if self.x < 0 or self.y < 0:
            raise CoordinateValidationException(f"Coordinates must be non-negative: ({self.x}, {self.y})")

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"
    
    def distance_to(self, other: "Coordinate") -> int:
        """マンハッタン距離を計算"""
        return abs(self.x - other.x) + abs(self.y - other.y)
