from typing import List, Dict, Optional, Tuple
from game.world.movement_graph import MovementGraph, MovementEdge
from game.player.player import Player


class MovementValidator:
    def __init__(self, movement_graph: MovementGraph):
        self.movement_graph = movement_graph
    
    def validate_movement(self, from_spot_id: str, to_spot_id: str, player: Player) -> Tuple[bool, List[str]]:
        errors = []
        
        if not self._check_spot_exists(from_spot_id):
            errors.append(f"移動元Spot {from_spot_id} が存在しません")
        
        if not self._check_spot_exists(to_spot_id):
            errors.append(f"移動先Spot {to_spot_id} が存在しません")
        
        if player is not None:
            if not self._check_connection_exists(from_spot_id, to_spot_id):
                errors.append(f"移動先 {to_spot_id} への接続が存在しません")
        
        condition_errors = self._check_movement_conditions(from_spot_id, to_spot_id, player)
        errors.extend(condition_errors)
        
        return len(errors) == 0, errors
    
    def validate_graph(self) -> List[str]:
        errors = []
        
        isolated_spots = self._find_isolated_spots()
        if isolated_spots:
            errors.append(f"孤立したSpotが存在します: {isolated_spots}")
        
        cycles = self._detect_cycles()
        if cycles:
            errors.append(f"循環参照が検出されました: {cycles}")
        
        invalid_connections = self._find_invalid_connections()
        if invalid_connections:
            errors.append(f"無効な接続が存在します: {invalid_connections}")
        
        unreachable_spots = self._find_unreachable_spots()
        if unreachable_spots:
            errors.append(f"到達不可能なSpotが存在します: {unreachable_spots}")
        
        return errors
    
    def _check_spot_exists(self, spot_id: str) -> bool:
        return spot_id in self.movement_graph.nodes
    
    def _check_connection_exists(self, from_spot_id: str, to_spot_id: str) -> bool:
        if from_spot_id not in self.movement_graph.edges:
            return False
        
        for edge in self.movement_graph.edges[from_spot_id]:
            if edge.to_spot_id == to_spot_id:
                return True
        return False
    
    def _check_movement_conditions(self, from_spot_id: str, to_spot_id: str, 
                                 player: Player) -> List[str]:
        errors = []
        
        if from_spot_id not in self.movement_graph.edges:
            return ["移動元Spotが存在しません"]
        
        for edge in self.movement_graph.edges[from_spot_id]:
            if edge.to_spot_id == to_spot_id:
                if "required_key" in edge.conditions:
                    if not player or not player.has_item(edge.conditions["required_key"]):
                        errors.append(f"鍵 '{edge.conditions['required_key']}' が必要です")
                
                if "required_level" in edge.conditions:
                    if not player or player.get_level() < edge.conditions["required_level"]:
                        errors.append(f"レベル {edge.conditions['required_level']} が必要です")
                
                if "time_restriction" in edge.conditions:
                    time_restriction = edge.conditions["time_restriction"]
                    if not self._check_time_restriction(time_restriction):
                        errors.append(f"時間制限により移動できません: {time_restriction}")
                
                break
        
        return errors
    
    def _check_time_restriction(self, time_restriction: Dict) -> bool:
        import datetime
        current_hour = datetime.datetime.now().hour
        
        if "allowed_hours" in time_restriction:
            allowed_hours = time_restriction["allowed_hours"]
            if current_hour not in allowed_hours:
                return False
        
        return True
    
    def _would_create_cycle(self, from_spot_id: str, to_spot_id: str) -> bool:
        temp_edge = MovementEdge(
            from_spot_id=from_spot_id,
            to_spot_id=to_spot_id,
            direction="temp",
            description="temp"
        )
        
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
        
        if from_spot_id not in self.movement_graph.edges:
            self.movement_graph.edges[from_spot_id] = []
        self.movement_graph.edges[from_spot_id].append(temp_edge)
        
        has_cycle = has_cycle_dfs(from_spot_id)
        
        self.movement_graph.edges[from_spot_id].remove(temp_edge)
        
        return has_cycle
    
    def _find_isolated_spots(self) -> List[str]:
        isolated = []
        
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
                isolated.append(spot_id)
        
        return isolated
    
    def _detect_cycles(self) -> List[List[str]]:
        return self.movement_graph._detect_cycles()
    
    def _find_invalid_connections(self) -> List[Tuple[str, str]]:
        invalid = []
        
        for spot_id, edges in self.movement_graph.edges.items():
            for edge in edges:
                if edge.to_spot_id not in self.movement_graph.nodes:
                    invalid.append((spot_id, edge.to_spot_id))
        
        return invalid
    
    def _find_unreachable_spots(self) -> List[str]:
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
        return self.movement_graph.get_shortest_path(from_spot_id, to_spot_id)
    
    def get_alternative_routes(self, from_spot_id: str, to_spot_id: str, 
                             max_routes: int = 3) -> List[List[str]]:
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