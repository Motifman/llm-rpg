from typing import Protocol
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class VisibilityMap(Protocol):
    """視線判定に必要なマップ情報のインターフェース"""
    def is_sight_blocked(self, coordinate: Coordinate) -> bool:
        """指定された座標が視線を遮るか判定する"""
        ...


class MapGeometryService:
    """マップ上の幾何学的な計算を行うドメインサービス"""

    @staticmethod
    def is_visible(from_coord: Coordinate, to_coord: Coordinate, map_data: VisibilityMap) -> bool:
        """
        指定された座標間が互いに視認可能か判定する。
        3D Bresenham's Line Algorithm を使用して実装。
        """
        if from_coord == to_coord:
            return True

        x1, y1, z1 = from_coord.x, from_coord.y, from_coord.z
        x2, y2, z2 = to_coord.x, to_coord.y, to_coord.z

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        dz = abs(z2 - z1)

        xs = 1 if x2 > x1 else -1
        ys = 1 if y2 > y1 else -1
        zs = 1 if z2 > z1 else -1

        # 最大の変化量を基準にする
        if dx >= dy and dx >= dz:
            # x軸メイン
            p1 = 2 * dy - dx
            p2 = 2 * dz - dx
            while x1 != x2:
                x1 += xs
                if p1 >= 0:
                    y1 += ys
                    p1 -= 2 * dx
                if p2 >= 0:
                    z1 += zs
                    p2 -= 2 * dx
                p1 += 2 * dy
                p2 += 2 * dz
                if (x1, y1, z1) == (x2, y2, z2):
                    break
                if map_data.is_sight_blocked(Coordinate(x1, y1, z1)):
                    return False
        elif dy >= dx and dy >= dz:
            # y軸メイン
            p1 = 2 * dx - dy
            p2 = 2 * dz - dy
            while y1 != y2:
                y1 += ys
                if p1 >= 0:
                    x1 += xs
                    p1 -= 2 * dy
                if p2 >= 0:
                    z1 += zs
                    p2 -= 2 * dy
                p1 += 2 * dx
                p2 += 2 * dz
                if (x1, y1, z1) == (x2, y2, z2):
                    break
                if map_data.is_sight_blocked(Coordinate(x1, y1, z1)):
                    return False
        else:
            # z軸メイン
            p1 = 2 * dx - dz
            p2 = 2 * dy - dz
            while z1 != z2:
                z1 += zs
                if p1 >= 0:
                    x1 += xs
                    p1 -= 2 * dz
                if p2 >= 0:
                    y1 += ys
                    p2 -= 2 * dz
                p1 += 2 * dx
                p2 += 2 * dy
                if (x1, y1, z1) == (x2, y2, z2):
                    break
                if map_data.is_sight_blocked(Coordinate(x1, y1, z1)):
                    return False

        return True
