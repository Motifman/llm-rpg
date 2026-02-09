from typing import List, Optional, Tuple
from collections import deque
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.aggregate.world_map_aggregate import WorldMapAggregate
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.value_object.area import PointArea, RectArea, CircleArea
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService


class GlobalPathfindingService:
    """スポット内およびスポット間を跨ぐ経路探索を行うドメインサービス"""

    def __init__(self, pathfinding_service: PathfindingService):
        self._pathfinding_service = pathfinding_service

    def calculate_global_path(
        self,
        current_spot_id: SpotId,
        current_coord: Coordinate,
        target_spot_id: SpotId,
        target_coord: Coordinate,
        physical_map: PhysicalMapAggregate,
        world_map: WorldMapAggregate,
        world_object_id: WorldObjectId,
        capability: MovementCapability
    ) -> Tuple[Coordinate, List[Coordinate]]:
        """
        目的地までの経路（現在のスポット内での暫定目的地とそのパス）を計算する。
        スポットを跨ぐ場合は、最適なゲートウェイを中継地点としてパスを生成する。
        
        Returns:
            Tuple[Coordinate, List[Coordinate]]: (暫定の目的地, その目的地までのパス)
        """
        if current_spot_id == target_spot_id:
            # 同じスポット内の移動
            path = self._pathfinding_service.calculate_path(
                start=current_coord,
                goal=target_coord,
                map_data=physical_map,
                capability=capability,
                exclude_object_id=world_object_id,
                smooth_path=False
            )
            return target_coord, path
        
        # 別スポットへの移動：最適なゲートウェイを探す
        # 1. 直接の接続があるか確認
        gateways = physical_map.get_all_gateways()
        target_gateway = next((g for g in gateways if g.target_spot_id == target_spot_id), None)
        
        if not target_gateway:
            # 2. 直接の接続がない場合、WorldMapから経路を探す（BFSを使用）
            next_spot_id = self._find_next_spot_in_world_path(current_spot_id, target_spot_id, world_map)
            if not next_spot_id:
                return None, []
            
            # 次のスポットへのゲートウェイを探す
            target_gateway = next((g for g in gateways if g.target_spot_id == next_spot_id), None)
            if not target_gateway:
                # 世界地図には接続があるが、物理マップにゲートウェイがない不整合
                return None, []
            
        # ゲートウェイの進入可能座標を取得
        gateway_coord = self._get_gateway_entry_coordinate(target_gateway)
        if not gateway_coord:
            return None, []

        path = self._pathfinding_service.calculate_path(
            start=current_coord,
            goal=gateway_coord,
            map_data=physical_map,
            capability=capability,
            exclude_object_id=world_object_id,
            smooth_path=False
        )
        return gateway_coord, path

    def _get_gateway_entry_coordinate(self, gateway: Gateway) -> Optional[Coordinate]:
        """ゲートウェイエリア内の代表的な進入座標を取得"""
        if isinstance(gateway.area, PointArea):
            return gateway.area.coordinate
        elif isinstance(gateway.area, RectArea):
            # 中心に近い座標を選択（簡易的にmin座標）
            return Coordinate(gateway.area.min_x, gateway.area.min_y, gateway.area.min_z)
        elif isinstance(gateway.area, CircleArea):
            return gateway.area.center
        return None

    def _find_next_spot_in_world_path(
        self, 
        start_id: SpotId, 
        goal_id: SpotId, 
        world_map: WorldMapAggregate
    ) -> Optional[SpotId]:
        """世界地図上で最短経路を探索し、次に向かうべき隣接スポットIDを返す"""
        if start_id == goal_id:
            return None

        queue = deque([(start_id, [])])
        visited = {start_id}

        while queue:
            current, path = queue.popleft()
            
            if current == goal_id:
                # 最初のステップを返す
                return path[0] if path else None

            for neighbor_id in world_map.get_connected_spots(current):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    new_path = path + [neighbor_id]
                    queue.append((neighbor_id, new_path))
        
        return None
