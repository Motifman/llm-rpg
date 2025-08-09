from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from game.world.spot import Spot
from game.player.player import Player


@dataclass
class MovementEdge:
    from_spot_id: str
    to_spot_id: str
    description: str
    is_bidirectional: bool = True
    conditions: Dict[str, any] = None
    is_dynamic: bool = False


class MovementGraph:
    def __init__(self):
        self.nodes: Dict[str, Spot] = {}
        self.edges: Dict[str, List[MovementEdge]] = {}
    
    def get_spot(self, spot_id: str) -> Spot:
        return self.nodes[spot_id]
    
    def get_all_spots(self) -> List[Spot]:
        return list(self.nodes.values())
    
    def add_spot(self, spot: Spot):
        self.nodes[spot.spot_id] = spot
        if spot.spot_id not in self.edges:
            self.edges[spot.spot_id] = []
    
    def get_destination_spot_ids(self, spot_id: str) -> List[str]:
        return [edge.to_spot_id for edge in self.edges[spot_id]]
    
    def add_connection(
        self,
        from_spot_id: str,
        to_spot_id: str,
        description: str,
        is_bidirectional: bool = True,
        conditions: Dict[str, any] = None,
        is_dynamic: bool = False,
    ):
        if from_spot_id not in self.nodes:
            raise ValueError(f"Spot {from_spot_id} does not exist")
        if to_spot_id not in self.nodes:
            raise ValueError(f"Spot {to_spot_id} does not exist")
        
        if self._has_connection(from_spot_id, to_spot_id):
            return False

        edge = MovementEdge(
            from_spot_id=from_spot_id,
            to_spot_id=to_spot_id,
            description=description,
            is_bidirectional=is_bidirectional,
            conditions=conditions or {},
            is_dynamic=is_dynamic
        )
        
        self.edges[from_spot_id].append(edge)
        
        if is_bidirectional:
            if not self._has_connection(to_spot_id, from_spot_id):
                reverse_edge = MovementEdge(
                    from_spot_id=to_spot_id,
                    to_spot_id=from_spot_id,
                    description=f"{description}から戻る",
                    is_bidirectional=True,
                    conditions=conditions or {},
                    is_dynamic=is_dynamic
                )
                self.edges[to_spot_id].append(reverse_edge)
        
        return True
    
    def remove_connection(self, from_spot_id: str, to_spot_id: str):
        self.edges[from_spot_id] = [
            edge for edge in self.edges[from_spot_id]
            if not (edge.to_spot_id == to_spot_id)
        ]
        
        self.edges[to_spot_id] = [
            edge for edge in self.edges[to_spot_id]
            if not (edge.to_spot_id == from_spot_id)
        ]
    
    def _has_connection(self, from_spot_id: str, to_spot_id: str) -> bool:
        if from_spot_id not in self.edges:
            return False
        
        for edge in self.edges[from_spot_id]:
            if edge.to_spot_id == to_spot_id:
                return True
        return False
    
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
    
    def validate_graph(self) -> List[str]:
        errors = []
        
        for spot_id in self.nodes:
            if not self.edges.get(spot_id):
                errors.append(f"Spot {spot_id} は孤立しています")
        
        for spot_id, edges in self.edges.items():
            for edge in edges:
                if edge.to_spot_id not in self.nodes:
                    errors.append(f"無効な接続: {spot_id} -> {edge.to_spot_id}")
        
        return errors
    
    def get_shortest_path(self, from_spot_id: str, to_spot_id: str) -> Optional[List[str]]:
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