from typing import Dict, List, Set, Tuple
from collections import defaultdict
from game.world.movement_graph import MovementGraph, MovementEdge
from game.action.action_strategy import ActionStrategy
from game.player.player import Player


class MovementCache:
    def __init__(self, movement_graph: MovementGraph):
        self.movement_graph = movement_graph
        self._movement_cache: Dict[str, List[ActionStrategy]] = {}
        self._connection_index: Dict[Tuple[str, str], List[MovementEdge]] = defaultdict(list)
        self._cache_valid = False
        self._build_indexes()
    
    def _build_indexes(self):
        self._connection_index.clear()
        
        for spot_id, edges in self.movement_graph.edges.items():
            for edge in edges:
                connection_key = (edge.from_spot_id, edge.to_spot_id)
                self._connection_index[connection_key].append(edge)
        
        self._cache_valid = True
    
    def invalidate_cache(self):
        self._movement_cache.clear()
        self._cache_valid = False
    
    def _check_movement_conditions(self, edge: MovementEdge, player: Player) -> bool:
        if not edge.conditions:
            return True
        
        if "required_key" in edge.conditions:
            if not player or not player.has_item(edge.conditions["required_key"]):
                return False
        
        if "required_level" in edge.conditions:
            if not player or player.get_level() < edge.conditions["required_level"]:
                return False
        
        return True
    
    def find_connections(self, from_spot_id: str, to_spot_id: str) -> List[MovementEdge]:
        connection_key = (from_spot_id, to_spot_id)
        return self._connection_index.get(connection_key, [])
    
    def get_connected_spots(self, spot_id: str) -> Set[str]:
        connected = set()
        if spot_id in self.movement_graph.edges:
            for edge in self.movement_graph.edges[spot_id]:
                connected.add(edge.to_spot_id)
        return connected
    
    def get_reverse_connections(self, spot_id: str) -> Set[str]:
        reverse_connected = set()
        
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
        success = self.movement_graph.add_connection(
            from_spot_id, to_spot_id, direction, description,
            is_bidirectional, conditions, is_dynamic
        )
        
        if success:
            self.invalidate_cache()
        
        return success
    
    def remove_connection(self, from_spot_id: str, to_spot_id: str, direction: str):
        self.movement_graph.remove_connection(from_spot_id, to_spot_id, direction)
        self.invalidate_cache()
    
    def get_movement_statistics(self) -> Dict[str, any]:
        total_spots = len(self.movement_graph.nodes)
        total_connections = sum(len(edges) for edges in self.movement_graph.edges.values())
        
        avg_connections = total_connections / total_spots if total_spots > 0 else 0
        
        max_connections = 0
        most_connected_spot = None
        for spot_id, edges in self.movement_graph.edges.items():
            if len(edges) > max_connections:
                max_connections = len(edges)
                most_connected_spot = spot_id
        
        isolated_count = 0
        for spot_id in self.movement_graph.nodes:
            has_outgoing = spot_id in self.movement_graph.edges and len(self.movement_graph.edges[spot_id]) > 0
            has_incoming = False
            
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
        if len(self._movement_cache) > max_cache_size:
            keys_to_remove = list(self._movement_cache.keys())[:len(self._movement_cache) - max_cache_size]
            for key in keys_to_remove:
                del self._movement_cache[key]
    
    def clear_cache(self):
        self._movement_cache.clear()
        self._cache_valid = False 