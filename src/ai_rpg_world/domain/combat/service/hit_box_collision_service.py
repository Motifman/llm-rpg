from typing import Tuple, Any
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class HitBoxCollisionDomainService:
    """HitBoxとマップ・オブジェクト間の衝突判定を調停するドメインサービス"""

    def resolve_collisions(
        self,
        physical_map: PhysicalMapAggregate,
        hit_box: HitBoxAggregate,
        max_collision_checks: int,
    ) -> Tuple[int, bool]:
        """
        HitBoxの被覆座標に対して、障害物→オブジェクトの順で衝突判定を行う。
        
        Returns:
            Tuple[int, bool]: (使用した判定回数, ガードがトリガーされたか)
        """
        collision_checks = 0

        if max_collision_checks <= 0:
            return 0, True

        for coord in hit_box.get_all_covered_coordinates():
            if not hit_box.is_active:
                return collision_checks, False

            if collision_checks >= max_collision_checks:
                return collision_checks, True

            collision_checks += 1
            if self._is_obstacle_coordinate(physical_map, hit_box, coord):
                hit_box.record_obstacle_collision(coord)
                if not hit_box.is_active:
                    return collision_checks, False
                # PASS_THROUGH時は座標走査を継続

            # オブジェクトとの衝突判定
            for obj in physical_map.get_objects_in_range(coord, 0):
                if not hit_box.is_active:
                    return collision_checks, False

                if collision_checks >= max_collision_checks:
                    return collision_checks, True

                collision_checks += 1
                hit_box.record_hit(obj.object_id)

        return collision_checks, False

    def _is_obstacle_coordinate(
        self,
        physical_map: PhysicalMapAggregate,
        hit_box: HitBoxAggregate,
        coordinate: Coordinate
    ) -> bool:
        """指定座標が（地形的に）障害物かどうかを判定する。"""
        try:
            tile = physical_map.get_tile(coordinate)
            return not tile.terrain_type.can_pass(hit_box.movement_capability)
        except Exception:
            # タイルが見つからない（マップ外）場合は障害物とみなす
            return True
