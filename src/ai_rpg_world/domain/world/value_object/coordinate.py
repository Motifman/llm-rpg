from dataclasses import dataclass
from ai_rpg_world.domain.world.exception.map_exception import CoordinateValidationException


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

    def to_2d(self) -> tuple[int, int]:
        """(x, y) のタプルを返す"""
        return (self.x, self.y)
