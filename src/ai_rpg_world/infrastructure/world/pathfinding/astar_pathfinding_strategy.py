import heapq
import math
from typing import List, Dict, Set, Optional, Tuple
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.service.pathfinding_strategy import PathfindingStrategy, PathfindingMap
from ai_rpg_world.domain.world.exception.map_exception import CoordinateValidationException


class AStarPathfindingStrategy(PathfindingStrategy):
    """A*アルゴリズムによる経路探索の実装"""

    def find_path(
        self,
        start: Coordinate,
        goal: Coordinate,
        map_data: PathfindingMap,
        capability: MovementCapability,
        max_iterations: int = 1000
    ) -> List[Coordinate]:
        """
        A*アルゴリズムを使用して最短経路を探索する。
        """
        # (f_score, unique_counter, coordinate)
        counter = 0
        open_set: List[Tuple[float, int, Coordinate]] = []
        heapq.heappush(open_set, (0.0, counter, start))
        
        came_from: Dict[Coordinate, Coordinate] = {}
        g_score: Dict[Coordinate, float] = {start: 0.0}
        f_score: Dict[Coordinate, float] = {start: self._heuristic(start, goal)}
        closed_set: Set[Coordinate] = set()

        # 探索制限に達した場合のために、最もゴールに近いノードを記録しておく
        best_node = start
        min_h = f_score[start]

        iterations = 0
        while open_set and iterations < max_iterations:
            iterations += 1
            current_f, _, current = heapq.heappop(open_set)
            
            if current == goal:
                return self._reconstruct_path(came_from, current)
            
            if current in closed_set:
                continue
            
            closed_set.add(current)
            
            # 最小のHスコアを持つノードを更新
            h = self._heuristic(current, goal)
            if h < min_h:
                min_h = h
                best_node = current
            
            # 隣接ノードの探索（上下左右斜め、高さ±1まで考慮）
            for neighbor, move_cost_multiplier in self._get_neighbors_with_costs(current):
                if not map_data.is_passable(neighbor, capability):
                    continue
                
                # 移動コストの取得
                base_cost = map_data.get_movement_cost(neighbor, capability)
                if base_cost == float('inf'):
                    continue
                
                # 斜め移動の場合はコストを調整（1.41倍など）
                actual_move_cost = base_cost * move_cost_multiplier
                tentative_g_score = g_score[current] + actual_move_cost
                
                if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_val = tentative_g_score + self._heuristic(neighbor, goal)
                    f_score[neighbor] = f_val
                    counter += 1
                    heapq.heappush(open_set, (f_val, counter, neighbor))
        
        # ゴールに到達できず、ループを抜けた場合
        if iterations >= max_iterations and best_node != start:
            # 探索制限に達した場合は、そこまでの最善の経路を返す
            return self._reconstruct_path(came_from, best_node)
                    
        return []

    def _heuristic(self, a: Coordinate, b: Coordinate) -> float:
        """ヒューリスティック関数（3D距離）"""
        # 斜め移動を許可する場合、マンハッタン距離よりもユークリッド距離やチェビシェフ距離の方が適している場合がある
        # ここでは3Dの直線距離（ユークリッド距離）を使用
        return math.sqrt(
            (a.x - b.x) ** 2 + 
            (a.y - b.y) ** 2 + 
            (a.z - b.z) ** 2
        )

    def _get_neighbors_with_costs(self, coord: Coordinate) -> List[Tuple[Coordinate, float]]:
        """隣接する座標とその移動コスト倍率を取得する（2D 8方向 + Z軸上下2方向）"""
        neighbors_with_costs = []
        
        # XY平面の8方向
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                
                # 移動コスト倍率（直線なら1.0、斜めなら√2 ≒ 1.414）
                multiplier = 1.0 if (dx == 0 or dy == 0) else 1.4142135623730951
                
                try:
                    nx, ny, nz = coord.x + dx, coord.y + dy, coord.z
                    if nx >= 0 and ny >= 0:
                        neighbors_with_costs.append((Coordinate(nx, ny, nz), multiplier))
                except CoordinateValidationException:
                    continue
        
        # Z軸の上下（斜めなしの単純移動として扱う）
        for dz in [-1, 1]:
            try:
                nx, ny, nz = coord.x, coord.y, coord.z + dz
                # 高低差移動のコスト倍率は1.0とする（地形コスト側で調整される想定）
                neighbors_with_costs.append((Coordinate(nx, ny, nz), 1.0))
            except CoordinateValidationException:
                continue
                
        return neighbors_with_costs

    def _reconstruct_path(self, came_from: Dict[Coordinate, Coordinate], current: Coordinate) -> List[Coordinate]:
        """記録された親ノードを辿って経路を復元する"""
        total_path = [current]
        while current in came_from:
            current = came_from[current]
            total_path.append(current)
        return total_path[::-1]
