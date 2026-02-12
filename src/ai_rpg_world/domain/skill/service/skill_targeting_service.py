from typing import Optional
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class SkillTargetingDomainService:
    """
    スキルのターゲット選定や方向決定を担当するドメインサービス。
    """
    
    # ゲーム全体で共通のオートエイム射程（10マス）
    DEFAULT_AUTO_AIM_RANGE = 10

    def calculate_auto_aim_direction(
        self,
        physical_map: PhysicalMapAggregate,
        actor_id: WorldObjectId,
        vision_range: int = DEFAULT_AUTO_AIM_RANGE
    ) -> Optional[DirectionEnum]:
        """
        指定されたアクターから付近の敵を探し、最適な向きを計算する。
        """
        actor = physical_map.get_actor(actor_id)
        
        # 付近のターゲットを探す
        targets = physical_map.get_objects_in_range(actor.coordinate, vision_range)
        
        # 自分以外の敵（アクター）を抽出し、かつ視線が通るもののみを対象とする
        enemies = [
            t for t in targets 
            if t.is_actor and t.object_id != actor_id and physical_map.is_visible(actor.coordinate, t.coordinate)
        ]
        
        if not enemies:
            return None
            
        # 最も近い敵を選択
        nearest = min(enemies, key=lambda e: actor.coordinate.distance_to(e.coordinate))
        
        # 敵への方向を計算
        return self._calculate_general_direction(actor.coordinate, nearest.coordinate)

    def _calculate_general_direction(self, from_coord: Coordinate, to_coord: Coordinate) -> DirectionEnum:
        """
        2点間の座標から、大まかな4方向を計算する。
        """
        dx = to_coord.x - from_coord.x
        dy = to_coord.y - from_coord.y
        
        # 同じ座標の場合はデフォルト（南）
        if dx == 0 and dy == 0:
            return DirectionEnum.SOUTH

        if abs(dx) >= abs(dy):
            return DirectionEnum.EAST if dx > 0 else DirectionEnum.WEST
        else:
            return DirectionEnum.SOUTH if dy > 0 else DirectionEnum.NORTH
