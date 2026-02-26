from abc import ABC, abstractmethod
from dataclasses import dataclass
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class Area(ABC):
    """範囲を定義する基底クラス"""

    @abstractmethod
    def contains(self, coordinate: Coordinate) -> bool:
        """指定された座標が範囲内にあるか判定する"""
        pass

    @abstractmethod
    def get_reference_coordinate(self) -> Coordinate:
        """経路探索などの目標として使う代表座標を返す（範囲内の1点）"""
        pass


@dataclass(frozen=True)
class PointArea(Area):
    """単一の点（タイル）を表す範囲"""
    coordinate: Coordinate

    def contains(self, coordinate: Coordinate) -> bool:
        return self.coordinate == coordinate

    def get_reference_coordinate(self) -> Coordinate:
        return self.coordinate


@dataclass(frozen=True)
class RectArea(Area):
    """矩形（直方体）の範囲"""
    min_x: int
    max_x: int
    min_y: int
    max_y: int
    min_z: int
    max_z: int

    @classmethod
    def from_coordinates(cls, min_coord: Coordinate, max_coord: Coordinate) -> "RectArea":
        """2つの座標から矩形範囲を作成する"""
        return cls(
            min_x=min(min_coord.x, max_coord.x),
            max_x=max(min_coord.x, max_coord.x),
            min_y=min(min_coord.y, max_coord.y),
            max_y=max(min_coord.y, max_coord.y),
            min_z=min(min_coord.z, max_coord.z),
            max_z=max(min_coord.z, max_coord.z)
        )

    def contains(self, coordinate: Coordinate) -> bool:
        return (
            self.min_x <= coordinate.x <= self.max_x and
            self.min_y <= coordinate.y <= self.max_y and
            self.min_z <= coordinate.z <= self.max_z
        )

    def get_reference_coordinate(self) -> Coordinate:
        """矩形の中心に近い座標を返す（整数）"""
        return Coordinate(
            (self.min_x + self.max_x) // 2,
            (self.min_y + self.max_y) // 2,
            (self.min_z + self.max_z) // 2,
        )


@dataclass(frozen=True)
class CircleArea(Area):
    """円形（球体）の範囲（距離ベース）"""
    center: Coordinate
    radius: int

    def contains(self, coordinate: Coordinate) -> bool:
        # Coordinate.distance_to (マンハッタン距離) を使用
        return self.center.distance_to(coordinate) <= self.radius

    def get_reference_coordinate(self) -> Coordinate:
        return self.center
