from dataclasses import dataclass
from typing import List
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.exception.map_exception import CoordinateValidationException
from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxValidationException


@dataclass(frozen=True)
class RelativeCoordinate:
    """グリッド上の相対座標"""
    dx: int
    dy: int
    dz: int = 0


@dataclass(frozen=True)
class HitBoxShape:
    """
    HitBoxの形状（グリッド上の相対座標リスト）。
    原点を基準とした相対位置の集合。
    """
    relative_coordinates: List[RelativeCoordinate]

    def __post_init__(self):
        if not self.relative_coordinates:
            raise HitBoxValidationException("HitBox shape must contain at least one coordinate")

    @classmethod
    def single_cell(cls) -> "HitBoxShape":
        """単一マス（原点のみ）"""
        return cls([RelativeCoordinate(0, 0, 0)])

    @classmethod
    def cross(cls) -> "HitBoxShape":
        """十字（原点＋上下左右）"""
        return cls([
            RelativeCoordinate(0, 0, 0),
            RelativeCoordinate(0, 1, 0),
            RelativeCoordinate(0, -1, 0),
            RelativeCoordinate(1, 0, 0),
            RelativeCoordinate(-1, 0, 0)
        ])

    def to_absolute(self, origin: Coordinate) -> List[Coordinate]:
        """指定された原点に基づいた絶対座標リストを返す。マップ外の座標は除外される可能性がある（呼び出し側で判定）"""
        abs_coords = []
        for rel in self.relative_coordinates:
            try:
                abs_coords.append(Coordinate(origin.x + rel.dx, origin.y + rel.dy, origin.z + rel.dz))
            except CoordinateValidationException:
                # 負の座標など、Coordinateのバリデーションに失敗した場合はスキップ（マップ外判定）
                pass
        return abs_coords
