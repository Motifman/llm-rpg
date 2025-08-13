from typing import List, Dict, Set, Optional, Tuple
from .movement_graph import MovementGraph, MovementEdge
from .spot import Spot


class MovementValidator:
    """移動の妥当性を検証するクラス"""
    
    def __init__(self, movement_graph: MovementGraph):
        self.movement_graph = movement_graph
    
    def validate_movement(self, from_spot_id: str, to_spot_id: str, 
                         direction: str, agent=None) -> Tuple[bool, List[str]]:
        """移動の妥当性を検証"""
        errors = []
        
        # 基本的な存在チェック
        if not self._check_spot_exists(from_spot_id):
            errors.append(f"移動元Spot {from_spot_id} が存在しません")
        
        if not self._check_spot_exists(to_spot_id):
            errors.append(f"移動先Spot {to_spot_id} が存在しません")
        
        # 接続の存在チェック（移動実行時のみ）
        if agent is not None:  # 移動実行時の場合のみチェック
            if not self._check_connection_exists(from_spot_id, to_spot_id, direction):
                errors.append(f"移動先 {to_spot_id} への {direction} 方向の接続が存在しません")
        
        # 条件チェック
        condition_errors = self._check_movement_conditions(from_spot_id, to_spot_id, direction, agent)
        errors.extend(condition_errors)
        
        # 循環参照チェック（移動実行時のみ）- 実際の移動では循環チェックは不要
        # 移動実行時は既存の接続を使用するため、循環は問題にならない
        # if agent is not None:
        #     if self._would_create_cycle(from_spot_id, to_spot_id):
        #         errors.append(f"移動により循環参照が作成されます: {from_spot_id} -> {to_spot_id}")
        
        return len(errors) == 0, errors
    
    def validate_graph(self) -> List[str]:
        """グラフ全体の妥当性を検証"""
        errors = []
        
        # 孤立したノードのチェック
        isolated_spots = self._find_isolated_spots()
        if isolated_spots:
            errors.append(f"孤立したSpotが存在します: {isolated_spots}")
        
        # 循環参照のチェック
        cycles = self._detect_cycles()
        if cycles:
            errors.append(f"循環参照が検出されました: {cycles}")
        
        # 無効な接続のチェック
        invalid_connections = self._find_invalid_connections()
        if invalid_connections:
            errors.append(f"無効な接続が存在します: {invalid_connections}")
        
        # 到達可能性のチェック
        unreachable_spots = self._find_unreachable_spots()
        if unreachable_spots:
            errors.append(f"到達不可能なSpotが存在します: {unreachable_spots}")
        
        return errors
    
    def _check_spot_exists(self, spot_id: str) -> bool:
        """Spotが存在するかチェック"""
        return spot_id in self.movement_graph.nodes
    
    def _check_connection_exists(self, from_spot_id: str, to_spot_id: str, direction: str) -> bool:
        """接続が存在するかチェック"""
        if from_spot_id not in self.movement_graph.edges:
            return False
        
        for edge in self.movement_graph.edges[from_spot_id]:
            if edge.to_spot_id == to_spot_id and edge.direction == direction:
                return True
        return False
    
    def _check_movement_conditions(self, from_spot_id: str, to_spot_id: str, 
                                 direction: str, agent) -> List[str]:
        """移動条件をチェック"""
        errors = []
        
        if from_spot_id not in self.movement_graph.edges:
            return ["移動元Spotが存在しません"]
        
        for edge in self.movement_graph.edges[from_spot_id]:
            if edge.to_spot_id == to_spot_id and edge.direction == direction:
                # 鍵が必要な場合
                if "required_key" in edge.conditions:
                    if not agent or not agent.has_item(edge.conditions["required_key"]):
                        errors.append(f"鍵 '{edge.conditions['required_key']}' が必要です")
                
                # レベル制限
                if "required_level" in edge.conditions:
                    if not agent or agent.get_level() < edge.conditions["required_level"]:
                        errors.append(f"レベル {edge.conditions['required_level']} が必要です")
                
                # 時間制限
                if "time_restriction" in edge.conditions:
                    time_restriction = edge.conditions["time_restriction"]
                    if not self._check_time_restriction(time_restriction):
                        errors.append(f"時間制限により移動できません: {time_restriction}")
                
                break
        
        return errors
    
    def _check_time_restriction(self, time_restriction: Dict) -> bool:
        """時間制限をチェック"""
        # 簡易実装：実際の時間システムと連携する必要がある
        import datetime
        current_hour = datetime.datetime.now().hour
        
        if "allowed_hours" in time_restriction:
            allowed_hours = time_restriction["allowed_hours"]
            if current_hour not in allowed_hours:
                return False
        
        return True
    
    def _would_create_cycle(self, from_spot_id: str, to_spot_id: str) -> bool:
        """移動により循環が作成されるかチェック"""
        # 一時的に接続を追加して循環をチェック
        temp_edge = MovementEdge(
            from_spot_id=from_spot_id,
            to_spot_id=to_spot_id,
            direction="temp",
            description="temp"
        )
        
        # 循環検出ロジック（簡易版）
        visited = set()
        rec_stack = set()
        
        def has_cycle_dfs(spot_id: str) -> bool:
            visited.add(spot_id)
            rec_stack.add(spot_id)
            
            for edge in self.movement_graph.edges.get(spot_id, []):
                if edge.to_spot_id not in visited:
                    if has_cycle_dfs(edge.to_spot_id):
                        return True
                elif edge.to_spot_id in rec_stack:
                    return True
            
            rec_stack.remove(spot_id)
            return False
        
        # 一時的な接続を追加
        if from_spot_id not in self.movement_graph.edges:
            self.movement_graph.edges[from_spot_id] = []
        self.movement_graph.edges[from_spot_id].append(temp_edge)
        
        # 循環チェック
        has_cycle = has_cycle_dfs(from_spot_id)
        
        # 一時的な接続を削除
        self.movement_graph.edges[from_spot_id].remove(temp_edge)
        
        return has_cycle
    
    def _find_isolated_spots(self) -> List[str]:
        """孤立したSpotを検出"""
        isolated = []
        
        for spot_id in self.movement_graph.nodes:
            has_outgoing = spot_id in self.movement_graph.edges and len(self.movement_graph.edges[spot_id]) > 0
            has_incoming = False
            
            # 他のSpotからこのSpotへの接続があるかチェック
            for other_spot_id, edges in self.movement_graph.edges.items():
                if other_spot_id != spot_id:
                    for edge in edges:
                        if edge.to_spot_id == spot_id:
                            has_incoming = True
                            break
                if has_incoming:
                    break
            
            if not has_outgoing and not has_incoming:
                isolated.append(spot_id)
        
        return isolated
    
    def _detect_cycles(self) -> List[List[str]]:
        """循環参照を検出"""
        return self.movement_graph._detect_cycles()
    
    def _find_invalid_connections(self) -> List[Tuple[str, str]]:
        """無効な接続を検出"""
        invalid = []
        
        for spot_id, edges in self.movement_graph.edges.items():
            for edge in edges:
                if edge.to_spot_id not in self.movement_graph.nodes:
                    invalid.append((spot_id, edge.to_spot_id))
        
        return invalid
    
    def _find_unreachable_spots(self) -> List[str]:
        """到達不可能なSpotを検出"""
        # 開始点として最初のSpotを使用
        if not self.movement_graph.nodes:
            return []
        
        start_spot_id = next(iter(self.movement_graph.nodes))
        reachable = self.movement_graph.get_reachable_spots(start_spot_id)
        
        unreachable = []
        for spot_id in self.movement_graph.nodes:
            if spot_id not in reachable:
                unreachable.append(spot_id)
        
        return unreachable
    
    def suggest_shortest_path(self, from_spot_id: str, to_spot_id: str) -> Optional[List[str]]:
        """最短経路を提案"""
        return self.movement_graph.get_shortest_path(from_spot_id, to_spot_id)
    
    def get_alternative_routes(self, from_spot_id: str, to_spot_id: str, 
                             max_routes: int = 3) -> List[List[str]]:
        """代替経路を取得"""
        # 簡易実装：BFSで複数の経路を探索
        if from_spot_id not in self.movement_graph.nodes or to_spot_id not in self.movement_graph.nodes:
            return []
        
        routes = []
        queue = [(from_spot_id, [from_spot_id])]
        visited = {from_spot_id}
        
        while queue and len(routes) < max_routes:
            current_spot_id, path = queue.pop(0)
            
            if current_spot_id == to_spot_id:
                routes.append(path)
                continue
            
            for edge in self.movement_graph.edges.get(current_spot_id, []):
                if edge.to_spot_id not in visited:
                    visited.add(edge.to_spot_id)
                    queue.append((edge.to_spot_id, path + [edge.to_spot_id]))
        
        return routes 