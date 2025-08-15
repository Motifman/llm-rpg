from dataclasses import dataclass, field
from typing import Set


@dataclass
class Spot:
    spot_id: int
    name: str
    description: str
    current_player_ids: Set[int] = field(default_factory=set)

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
    
    def get_spot_summary(self) -> str:
        return f"{self.name} ({self.spot_id}) {self.description}"