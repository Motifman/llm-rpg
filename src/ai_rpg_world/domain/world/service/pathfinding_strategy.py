from abc import ABC, abstractmethod
from typing import List, Optional, Protocol
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability


class PathfindingMap(Protocol):
    """経路探索に必要なマップの情報を抽象化したプロトコル"""
    def is_passable(self, coordinate: Coordinate, capability: MovementCapability) -> bool:
        ...
    
    def get_movement_cost(self, coordinate: Coordinate, capability: MovementCapability) -> float:
        ...

    def is_visible(self, from_coord: Coordinate, to_coord: Coordinate) -> bool:
        """指定された座標間が視認可能（直線移動可能）か判定する"""
        ...

class PathfindingStrategy(ABC):
    """経路探索アルゴリズムの戦略インターフェース"""
    
    @abstractmethod
    def find_path(
        self,
        start: Coordinate,
        goal: Coordinate,
        map_data: PathfindingMap,
        capability: MovementCapability,
        max_iterations: int = 1000
    ) -> List[Coordinate]:
        """
        開始地点から目標地点までの経路を計算する。
        
        Args:
            start: 開始座標
            goal: 目標座標
            map_data: マップデータ（通行可能性とコストの取得に使用）
            capability: 移動能力
            max_iterations: 探索の最大試行回数
            
        Returns:
            座標のリスト。
            経路が見つからない場合は空リスト。
            探索制限に達した場合は、その時点での「最も目標に近い地点」までの部分経路を返すことがある。
        """
        pass
