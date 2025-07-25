from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from .spot import Spot
from .action import Movement


@dataclass
class MovementEdge:
    """移動エッジの情報"""
    from_spot_id: str
    to_spot_id: str
    direction: str
    description: str
    is_bidirectional: bool = True
    conditions: Dict[str, any] = None  # 移動条件（鍵が必要など）
    is_dynamic: bool = False  # 動的に追加された移動かどうか


class MovementGraph:
    """移動グラフを管理するクラス"""
    
    def __init__(self):
        self.nodes: Dict[str, Spot] = {}
        self.edges: Dict[str, List[MovementEdge]] = {}  # spot_id -> [MovementEdge]
    
    def add_spot(self, spot: Spot):
        """Spotをグラフに追加"""
        self.nodes[spot.spot_id] = spot
        if spot.spot_id not in self.edges:
            self.edges[spot.spot_id] = []
    
    def add_connection(self, from_spot_id: str, to_spot_id: str, 
                      direction: str, description: str, 
                      is_bidirectional: bool = True, 
                      conditions: Dict[str, any] = None,
                      is_dynamic: bool = False):
        """移動接続を追加"""
        
        # 存在チェック
        if from_spot_id not in self.nodes:
            raise ValueError(f"Spot {from_spot_id} が存在しません")
        if to_spot_id not in self.nodes:
            raise ValueError(f"Spot {to_spot_id} が存在しません")
        
        # 重複チェック
        if self._has_connection(from_spot_id, to_spot_id, direction):
            return False
        
        # エッジを作成
        edge = MovementEdge(
            from_spot_id=from_spot_id,
            to_spot_id=to_spot_id,
            direction=direction,
            description=description,
            is_bidirectional=is_bidirectional,
            conditions=conditions or {},
            is_dynamic=is_dynamic
        )
        
        # 順方向のエッジを追加
        self.edges[from_spot_id].append(edge)
        
        # 逆方向のエッジを追加（双方向の場合）
        if is_bidirectional:
            reverse_direction = self._get_reverse_direction(direction)
            # 逆方向の重複チェック
            if not self._has_connection(to_spot_id, from_spot_id, reverse_direction):
                reverse_edge = MovementEdge(
                    from_spot_id=to_spot_id,
                    to_spot_id=from_spot_id,
                    direction=reverse_direction,
                    description=f"{description}から戻る",
                    is_bidirectional=True,
                    conditions=conditions or {},
                    is_dynamic=is_dynamic
                )
                self.edges[to_spot_id].append(reverse_edge)
        
        return True
    
    def remove_connection(self, from_spot_id: str, to_spot_id: str, direction: str):
        """移動接続を削除"""
        # 順方向のエッジを削除
        self.edges[from_spot_id] = [
            edge for edge in self.edges[from_spot_id]
            if not (edge.to_spot_id == to_spot_id and edge.direction == direction)
        ]
        
        # 逆方向のエッジも削除
        reverse_direction = self._get_reverse_direction(direction)
        self.edges[to_spot_id] = [
            edge for edge in self.edges[to_spot_id]
            if not (edge.to_spot_id == from_spot_id and edge.direction == reverse_direction)
        ]
    
    def get_available_movements(self, spot_id: str, agent=None) -> List[Movement]:
        """指定されたSpotから利用可能な移動を取得"""
        if spot_id not in self.edges:
            return []
        
        movements = []
        for edge in self.edges[spot_id]:
            # 条件チェック
            if self._check_movement_conditions(edge, agent):
                movement = Movement(
                    description=edge.description,
                    direction=edge.direction,
                    target_spot_id=edge.to_spot_id
                )
                movements.append(movement)
        
        return movements
    
    def _has_connection(self, from_spot_id: str, to_spot_id: str, direction: str) -> bool:
        """指定された接続が存在するかチェック"""
        if from_spot_id not in self.edges:
            return False
        
        for edge in self.edges[from_spot_id]:
            if edge.to_spot_id == to_spot_id and edge.direction == direction:
                return True
        return False
    
    def _get_reverse_direction(self, direction: str) -> str:
        """逆方向を取得"""
        direction_map = {
            "北": "南", "南": "北", "東": "西", "西": "東",
            "上": "下", "下": "上", "外に出る": "中に入る", "中に入る": "外に出る"
        }
        return direction_map.get(direction, f"{direction}から戻る")
    
    def _check_movement_conditions(self, edge: MovementEdge, agent) -> bool:
        """移動条件をチェック"""
        if not edge.conditions:
            return True
        
        # 鍵が必要な場合
        if "required_key" in edge.conditions:
            if not agent or not agent.has_item(edge.conditions["required_key"]):
                return False
        
        # レベル制限
        if "required_level" in edge.conditions:
            if not agent or agent.get_level() < edge.conditions["required_level"]:
                return False
        
        return True
    
    def validate_graph(self) -> List[str]:
        """グラフの妥当性を検証"""
        errors = []
        
        # 孤立したノードのチェック
        for spot_id in self.nodes:
            if not self.edges.get(spot_id):
                errors.append(f"Spot {spot_id} は孤立しています")
        
        # 循環参照のチェック
        cycles = self._detect_cycles()
        if cycles:
            errors.append(f"循環参照が検出されました: {cycles}")
        
        # 無効な接続のチェック
        for spot_id, edges in self.edges.items():
            for edge in edges:
                if edge.to_spot_id not in self.nodes:
                    errors.append(f"無効な接続: {spot_id} -> {edge.to_spot_id}")
        
        return errors
    
    def _detect_cycles(self) -> List[List[str]]:
        """循環参照を検出（改善版）"""
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(spot_id: str, path: List[str]):
            visited.add(spot_id)
            rec_stack.add(spot_id)
            path.append(spot_id)
            
            for edge in self.edges.get(spot_id, []):
                if edge.to_spot_id not in visited:
                    dfs(edge.to_spot_id, path.copy())
                elif edge.to_spot_id in rec_stack:
                    # 循環を発見
                    cycle_start = path.index(edge.to_spot_id)
                    cycle = path[cycle_start:] + [edge.to_spot_id]
                    
                    # 問題のある循環のみを報告
                    if self._is_problematic_cycle(cycle):
                        cycles.append(cycle)
            
            rec_stack.remove(spot_id)
        
        for spot_id in self.nodes:
            if spot_id not in visited:
                dfs(spot_id, [])
        
        return cycles
    
    def _is_problematic_cycle(self, cycle: List[str]) -> bool:
        """問題のある循環かどうかを判定"""
        # 短い循環（2-3個のSpot）は正常
        if len(cycle) <= 4:
            return False
        
        # 同じSpotが複数回現れる循環は問題
        if len(cycle) != len(set(cycle)):
            return True
        
        # 長すぎる循環は問題
        if len(cycle) > 6:
            return True
        
        # 特定のパターンの循環は問題
        # 例：A→B→A のような単純な往復
        if len(cycle) == 3 and cycle[0] == cycle[2]:
            return True
        
        # 例：A→B→C→B→A のような複雑な往復
        if len(cycle) == 5 and cycle[0] == cycle[4] and cycle[1] == cycle[3]:
            return True
        
        return False
    
    def get_shortest_path(self, from_spot_id: str, to_spot_id: str) -> Optional[List[str]]:
        """最短経路を取得（BFS）"""
        if from_spot_id not in self.nodes or to_spot_id not in self.nodes:
            return None
        
        queue = [(from_spot_id, [from_spot_id])]
        visited = {from_spot_id}
        
        while queue:
            current_spot_id, path = queue.pop(0)
            
            if current_spot_id == to_spot_id:
                return path
            
            for edge in self.edges.get(current_spot_id, []):
                if edge.to_spot_id not in visited:
                    visited.add(edge.to_spot_id)
                    queue.append((edge.to_spot_id, path + [edge.to_spot_id]))
        
        return None
    
    def get_reachable_spots(self, from_spot_id: str) -> Set[str]:
        """到達可能なSpotを取得"""
        if from_spot_id not in self.nodes:
            return set()
        
        reachable = {from_spot_id}
        queue = [from_spot_id]
        
        while queue:
            current_spot_id = queue.pop(0)
            
            for edge in self.edges.get(current_spot_id, []):
                if edge.to_spot_id not in reachable:
                    reachable.add(edge.to_spot_id)
                    queue.append(edge.to_spot_id)
        
        return reachable 