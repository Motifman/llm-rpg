from typing import Protocol, List

from src.domain.poi.poi import POI
from src.domain.poi.player_poi_state import PlayerPOIState


class POIRepository(Protocol):
    def find_by_id(self, poi_id: int) -> POI:
        ...
    
    def find_by_spot_id(self, spot_id: int) -> List[POI]:
        ...


class PlayerPOIStateRepository(Protocol):
    def find_by_player_id(self, player_id: str) -> PlayerPOIState:
        ...
    
    def save(self, player_poi_state: PlayerPOIState):
        ...