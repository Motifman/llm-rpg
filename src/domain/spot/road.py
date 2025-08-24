from typing import TYPE_CHECKING, Optional
from src.domain.spot.condition import ConditionChecker
from src.domain.common.aggregate_root import AggregateRoot

if TYPE_CHECKING:
    from src.domain.player.player import Player


class Road(AggregateRoot):
    def __init__(
        self,
        road_id: int,
        from_spot_id: int,
        to_spot_id: int,
        description: str,
        conditions: Optional[ConditionChecker] = None,
    ):
        super().__init__()
        self._road_id = road_id
        self._from_spot_id = from_spot_id
        self._to_spot_id = to_spot_id
        self._description = description
        self._conditions = conditions
    
    @property
    def road_id(self) -> int:
        return self._road_id
    
    @property
    def from_spot_id(self) -> int:
        return self._from_spot_id
    
    @property
    def to_spot_id(self) -> int:
        return self._to_spot_id
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def conditions(self) -> Optional[ConditionChecker]:
        return self._conditions
    
    def create_inverse_road(self, road_id: int, description: str, conditions: Optional[ConditionChecker] = None) -> "Road":
        if self.road_id == road_id:
            raise ValueError(f"Road {road_id} is the same as the original road")
        return Road(
            road_id=road_id,
            from_spot_id=self.to_spot_id,
            to_spot_id=self.from_spot_id,
            description=description,
            conditions=conditions
        )
    
    def check_player_conditions(self, player: 'Player'):
        if self.conditions is not None:
            self.conditions.check(player)