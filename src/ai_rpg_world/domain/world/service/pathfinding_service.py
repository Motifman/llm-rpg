from typing import List, Optional
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.service.pathfinding_strategy import PathfindingStrategy, PathfindingMap
from ai_rpg_world.domain.world.exception.map_exception import PathNotFoundException, InvalidPathRequestException


class PathfindingService:
    """経路探索を調整するドメインサービス"""
    
    def __init__(self, strategy: PathfindingStrategy):
        self._strategy = strategy

    def calculate_path(
        self,
        start: Coordinate,
        goal: Coordinate,
        map_data: PathfindingMap,
        capability: MovementCapability,
        ignore_errors: bool = False,
        max_iterations: int = 1000,
        allow_partial_path: bool = False,
        smooth_path: bool = True
    ) -> List[Coordinate]:
        """
        開始地点から目標地点までの経路を算出する。
        
        Args:
            start: 開始座標
            goal: 目標座標
            map_data: マップデータ
            capability: 移動能力
            ignore_errors: Trueの場合、経路が見つからなくても例外を投げず空リストを返す
            max_iterations: 探索の最大試行回数
            allow_partial_path: Trueの場合、目標に到達できなくてもそこまでの最善の経路を返す
            smooth_path: Trueの場合、視線が通る箇所を直線化して経路を単純化する
            
        Returns:
            座標のリスト（開始地点を含む）
            
        Raises:
            InvalidPathRequestException: 開始地点または目標地点が通行不能な場合
            PathNotFoundException: 経路が見つからない場合（ignore_errors=Falseの場合）
        """
        # バリデーション
        if not map_data.is_passable(start, capability):
            raise InvalidPathRequestException(f"Start point {start} is not passable with given capability")
        
        if not map_data.is_passable(goal, capability) and not allow_partial_path:
            raise InvalidPathRequestException(f"Goal point {goal} is not passable with given capability")

        if start == goal:
            return [start]

        path = self._strategy.find_path(
            start, 
            goal, 
            map_data, 
            capability, 
            max_iterations=max_iterations, 
            allow_partial_path=allow_partial_path
        )
        
        if not path:
            if ignore_errors:
                return []
            raise PathNotFoundException(f"No path found from {start} to {goal}")
        
        # ゴールに到達していないかチェック
        if path[-1] != goal and not allow_partial_path:
            if ignore_errors:
                return []
            raise PathNotFoundException(f"Complete path not found from {start} to {goal} (reached {path[-1]})")

        # 経路の単純化
        if smooth_path and len(path) > 2:
            path = self._smooth_path(path, map_data)
            
        return path

    def _smooth_path(self, path: List[Coordinate], map_data: PathfindingMap) -> List[Coordinate]:
        """視線が通る箇所を繋いで経路を単純化する"""
        if len(path) <= 2:
            return path
            
        smoothed = [path[0]]
        current_idx = 0
        
        while current_idx < len(path) - 1:
            # 遠くの地点から順に視線が通るかチェック
            next_idx = len(path) - 1
            while next_idx > current_idx + 1:
                if map_data.is_visible(path[current_idx], path[next_idx]):
                    break
                next_idx -= 1
            
            smoothed.append(path[next_idx])
            current_idx = next_idx
            
        return smoothed
