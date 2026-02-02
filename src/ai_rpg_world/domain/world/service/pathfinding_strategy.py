from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, TYPE_CHECKING
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class PathfindingMap(Protocol):
    """経路探索に必要なマップの情報を抽象化したプロトコル"""
    def is_passable(self, coordinate: Coordinate, capability: MovementCapability, exclude_object_id: Optional["WorldObjectId"] = None) -> bool:
        ...
    
    def get_movement_cost(self, coordinate: Coordinate, capability: MovementCapability, exclude_object_id: Optional["WorldObjectId"] = None) -> float:
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
        max_iterations: int = 1000,
        allow_partial_path: bool = False,
        exclude_object_id: Optional["WorldObjectId"] = None
    ) -> List[Coordinate]:
        """
        開始地点から目標地点までの経路を計算する。
        
        Args:
            start: 開始座標
            goal: 目標座標
            map_data: マップデータ（通行可能性とコストの取得に使用）
            capability: 移動能力
            max_iterations: 探索の最大試行回数
            allow_partial_path: Trueの場合、ゴールに到達できなくても最善の地点までの経路を返す
            
        Returns:
            座標のリスト。
            経路が見つからない場合は空リスト。
        """
        pass
