from typing import List
from game.world.spot import Spot
from game.world.movement_graph import MovementGraph
from game.world.movement_cache import MovementCache
from game.world.movement_validator import MovementValidator


class SpotManager:
    def __init__(self):
        self.movement_graph = MovementGraph()
        self.movement_cache = MovementCache(self.movement_graph)
        self.movement_validator = MovementValidator(self.movement_graph)

    def add_spot(self, spot: Spot):
        self.movement_graph.add_spot(spot)

    def get_spot(self, spot_id: str) -> Spot:
        try:
            return self.movement_graph.get_spot(spot_id)
        except KeyError:
            return None
    
    def get_all_spots(self) -> List[Spot]:
        return list(self.movement_graph.get_all_spots())
    
    def get_movement_graph(self) -> MovementGraph:
        return self.movement_graph
    
    def get_movement_cache(self) -> MovementCache:
        return self.movement_cache
    
    def get_movement_validator(self) -> MovementValidator:
        return self.movement_validator

    def get_destination_spot_ids(self, spot_id: str) -> List[str]:
        return self.movement_graph.get_destination_spot_ids(spot_id)