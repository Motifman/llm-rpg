from dataclasses import dataclass, field
from typing import List, Any, Dict, TYPE_CHECKING
from src.domain.spot.condition import Condition

if TYPE_CHECKING:
    from src.domain.player.player import Player


@dataclass(frozen=True)
class Road:
    road_id: int
    from_spot_id: int
    from_spot_name: str
    to_spot_id: int
    to_spot_name: str
    description: str
    conditions: List[Condition] = field(default_factory=list)
    
    def create_inverse_road(self, road_id: int, description: str, conditions: List[Condition] = None) -> "Road":
        if self.road_id == road_id:
            raise ValueError(f"Road {road_id} is the same as the original road")
        return Road(
            road_id=road_id,
            from_spot_id=self.to_spot_id,
            from_spot_name=self.to_spot_name,
            to_spot_id=self.from_spot_id,
            to_spot_name=self.from_spot_name,
            description=description,
            conditions=conditions
        )
    
    def is_available(self, player: 'Player') -> bool:
        if self.conditions is None:
            return True
        for condition in self.conditions:
            if not condition.check(player):
                return False
        return True

    def _check_availability_details(self, player: 'Player') -> Dict[str, Any]:
        """道路の利用可能性の詳細な結果を返す"""
        if self.conditions is None:
            return {
                "is_available": True,
                "failed_conditions": [],
                "all_condition_results": []
            }
        
        condition_results = []
        failed_conditions = []
        
        for condition in self.conditions:
            result = condition.check_with_details(player)
            condition_results.append(result)
            if not result.is_satisfied:
                failed_conditions.append(result)
        
        return {
            "is_available": len(failed_conditions) == 0,
            "failed_conditions": failed_conditions,
            "all_condition_results": condition_results
        }

    def get_availability_message(self, player: 'Player') -> str:
        """利用可能性に関する詳細なメッセージを生成"""
        details = self._check_availability_details(player)
        
        if details["is_available"]:
            return f"道路 '{self.description}' は利用可能です"
        
        failed_messages = [result.message for result in details["failed_conditions"]]
        return f"道路 '{self.description}' は利用できません。理由: {', '.join(failed_messages)}"