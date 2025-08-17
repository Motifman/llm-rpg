from dataclasses import dataclass, field
from typing import Set, List, Optional
from src.domain.spot.road import Road


class Spot:
    def __init__(
        self,
        spot_id: int,
        name: str,
        description: str,
        area_id: Optional[int] = None,
        current_player_ids: Optional[Set[int]] = None,
        roads: Optional[List[Road]] = None
    ):
        self._spot_id = spot_id
        self._name = name
        self._description = description
        self._area_id = area_id
        self._current_player_ids: Set[int] = current_player_ids or set()
        self._roads: List[Road] = roads or []
    
    @property
    def spot_id(self) -> int:
        return self._spot_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    # ===== プレイヤー管理 =====
    def add_player(self, player_id: int):
        self._current_player_ids.add(player_id)

    def remove_player(self, player_id: int):
        self._current_player_ids.discard(player_id)
    
    def get_current_player_ids(self) -> Set[int]:
        return self._current_player_ids
    
    def get_current_player_count(self) -> int:
        return len(self._current_player_ids)
    
    def is_player_in_spot(self, player_id: int) -> bool:
        return player_id in self._current_player_ids
    
    # ===== スポット間の繋がりを管理 =====
    def add_road(self, road: Road):
        if road.from_spot_id != self.spot_id:
            raise ValueError(f"Road {road.road_id} is not connected to spot {self.spot_id}")
        self._roads.append(road)
    
    def remove_road(self, road: Road):
        if road not in self._roads:
            raise ValueError(f"Road {road.road_id} is not connected to spot {self.spot_id}")
        self._roads.remove(road)
    
    def get_all_roads(self) -> List[Road]:
        return self._roads

    def get_connected_spot_ids(self) -> Set[int]:
        return {road.to_spot_id for road in self._roads}
    
    def get_connected_spot_names(self) -> Set[str]:
        return {road.to_spot_name for road in self._roads}
    
    def is_connected_to(self, spot: "Spot") -> bool:
        return spot.spot_id in self.get_connected_spot_ids()
    
    def get_spot_summary(self) -> str:
        return f"{self._name} ({self._spot_id}) {self._description}"

    def get_spot_summary_with_area(self, area_name: Optional[str] = None) -> str:
        """エリア名を含むスポット概要を取得"""
        if area_name is None:
            return self.get_spot_summary()
        return f"{self._name} ({self._spot_id}) {self._description} (area:{area_name})"