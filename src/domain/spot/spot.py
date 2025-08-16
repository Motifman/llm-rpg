from dataclasses import dataclass, field
from typing import Set, List
from src.domain.spot.road import Road
from src.domain.spot.area import Area


@dataclass
class Spot:
    spot_id: int
    name: str
    description: str
    current_player_ids: Set[int] = field(default_factory=set)
    roads: List[Road] = field(default_factory=list)
    area: Area = None
    
    # ===== プレイヤー管理 =====
    def add_player(self, player_id: int):
        self.current_player_ids.add(player_id)

    def remove_player(self, player_id: int):
        self.current_player_ids.discard(player_id)
    
    def get_current_player_ids(self) -> Set[int]:
        return self.current_player_ids
    
    def get_current_player_count(self) -> int:
        return len(self.current_player_ids)
    
    def is_player_in_spot(self, player_id: int) -> bool:
        return player_id in self.current_player_ids
    
    # ===== スポット間の繋がりを管理 =====
    def add_road(self, road: Road):
        if road.from_spot_id != self.spot_id:
            raise ValueError(f"Road {road.road_id} is not connected to spot {self.spot_id}")
        self.roads.append(road)
    
    def remove_road(self, road: Road):
        if road not in self.roads:
            raise ValueError(f"Road {road.road_id} is not connected to spot {self.spot_id}")
        self.roads.remove(road)
    
    def get_all_roads(self) -> List[Road]:
        return self.roads

    def get_connected_spot_ids(self) -> Set[int]:
        return {road.to_spot_id for road in self.roads}
    
    def get_connected_spot_names(self) -> Set[str]:
        return {road.to_spot_name for road in self.roads}
    
    def is_connected_to(self, spot: "Spot") -> bool:
        return spot.spot_id in self.get_connected_spot_ids()
    
    def get_spot_summary(self) -> str:
        return f"{self.name} ({self.spot_id}) {self.description}"

    def get_spot_summary_with_area(self) -> str:
        if self.area is None:
            return self.get_spot_summary()
        return f"{self.name} ({self.spot_id}) {self.description} (area:{self.area.name})"