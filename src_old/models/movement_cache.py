from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
from .movement_graph import MovementGraph, MovementEdge
from .action import Movement


class MovementCache:
    """移動情報のキャッシュとインデックス管理"""
    
    def __init__(self, movement_graph: MovementGraph):
        self.movement_graph = movement_graph
        self._movement_cache: Dict[str, List[Movement]] = {}
        self._connection_index: Dict[Tuple[str, str], List[MovementEdge]] = defaultdict(list)
        self._direction_index: Dict[str, List[MovementEdge]] = defaultdict(list)
        self._cache_valid = False
        
        # キャッシュを初期化
        self._build_indexes()
    
    def _build_indexes(self):
        """インデックスを構築"""
        self._connection_index.clear()
        self._direction_index.clear()
        
        for spot_id, edges in self.movement_graph.edges.items():
            for edge in edges:
                # 接続インデックス
                connection_key = (edge.from_spot_id, edge.to_spot_id)
                self._connection_index[connection_key].append(edge)
                
                # 方向インデックス
                direction_key = f"{edge.from_spot_id}_{edge.direction}"
                self._direction_index[direction_key].append(edge)
        
        self._cache_valid = True
    
    def invalidate_cache(self):
        """キャッシュを無効化"""
        self._movement_cache.clear()
        self._cache_valid = False
    
    def get_available_movements(self, spot_id: str, agent=None, use_cache: bool = True) -> List[Movement]:
        """キャッシュを使用して移動可能先を取得"""
        cache_key = f"{spot_id}_{agent.agent_id if agent else 'no_agent'}"
        
        if use_cache and cache_key in self._movement_cache:
            return self._movement_cache[cache_key]
        
        # キャッシュが無効な場合はインデックスを再構築
        if not self._cache_valid:
            self._build_indexes()
        
        movements = []
        if spot_id in self.movement_graph.edges:
            for edge in self.movement_graph.edges[spot_id]:
                # 条件チェック
                if self._check_movement_conditions(edge, agent):
                    movement = Movement(
                        description=edge.description,
                        direction=edge.direction,
                        target_spot_id=edge.to_spot_id
                    )
                    movements.append(movement)
        
        # キャッシュに保存
        if use_cache:
            self._movement_cache[cache_key] = movements
        
        return movements
    
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
    
    def find_connections(self, from_spot_id: str, to_spot_id: str) -> List[MovementEdge]:
        """特定の接続を高速検索"""
        connection_key = (from_spot_id, to_spot_id)
        return self._connection_index.get(connection_key, [])
    
    def find_by_direction(self, spot_id: str, direction: str) -> List[MovementEdge]:
        """方向による高速検索"""
        direction_key = f"{spot_id}_{direction}"
        return self._direction_index.get(direction_key, [])
    
    def has_connection(self, from_spot_id: str, to_spot_id: str, direction: str) -> bool:
        """接続の存在を高速チェック"""
        direction_key = f"{from_spot_id}_{direction}"
        for edge in self._direction_index.get(direction_key, []):
            if edge.to_spot_id == to_spot_id:
                return True
        return False
    
    def get_connected_spots(self, spot_id: str) -> Set[str]:
        """接続されているSpotを高速取得"""
        connected = set()
        if spot_id in self.movement_graph.edges:
            for edge in self.movement_graph.edges[spot_id]:
                connected.add(edge.to_spot_id)
        return connected
    
    def get_reverse_connections(self, spot_id: str) -> Set[str]:
        """逆方向の接続を高速取得"""
        reverse_connected = set()
        
        # 他のSpotからこのSpotへの接続を検索
        for other_spot_id, edges in self.movement_graph.edges.items():
            if other_spot_id != spot_id:
                for edge in edges:
                    if edge.to_spot_id == spot_id:
                        reverse_connected.add(other_spot_id)
        
        return reverse_connected
    
    def add_connection(self, from_spot_id: str, to_spot_id: str, 
                      direction: str, description: str, 
                      is_bidirectional: bool = True, 
                      conditions: Dict[str, any] = None,
                      is_dynamic: bool = False):
        """接続を追加（キャッシュも更新）"""
        success = self.movement_graph.add_connection(
            from_spot_id, to_spot_id, direction, description,
            is_bidirectional, conditions, is_dynamic
        )
        
        if success:
            self.invalidate_cache()
        
        return success
    
    def remove_connection(self, from_spot_id: str, to_spot_id: str, direction: str):
        """接続を削除（キャッシュも更新）"""
        self.movement_graph.remove_connection(from_spot_id, to_spot_id, direction)
        self.invalidate_cache()
    
    def get_movement_statistics(self) -> Dict[str, any]:
        """移動統計情報を取得"""
        total_spots = len(self.movement_graph.nodes)
        total_connections = sum(len(edges) for edges in self.movement_graph.edges.values())
        
        # 平均接続数
        avg_connections = total_connections / total_spots if total_spots > 0 else 0
        
        # 最も接続が多いSpot
        max_connections = 0
        most_connected_spot = None
        for spot_id, edges in self.movement_graph.edges.items():
            if len(edges) > max_connections:
                max_connections = len(edges)
                most_connected_spot = spot_id
        
        # 孤立したSpot数
        isolated_count = 0
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
                isolated_count += 1
        
        return {
            "total_spots": total_spots,
            "total_connections": total_connections,
            "average_connections_per_spot": avg_connections,
            "most_connected_spot": most_connected_spot,
            "max_connections": max_connections,
            "isolated_spots_count": isolated_count,
            "cache_size": len(self._movement_cache),
            "cache_valid": self._cache_valid
        }
    
    def optimize_cache(self, max_cache_size: int = 1000):
        """キャッシュを最適化"""
        if len(self._movement_cache) > max_cache_size:
            # LRU方式でキャッシュを削減
            # 簡易実装：古いエントリを削除
            keys_to_remove = list(self._movement_cache.keys())[:len(self._movement_cache) - max_cache_size]
            for key in keys_to_remove:
                del self._movement_cache[key]
    
    def clear_cache(self):
        """キャッシュをクリア"""
        self._movement_cache.clear()
        self._cache_valid = False 