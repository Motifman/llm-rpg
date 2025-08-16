from dataclasses import dataclass, field
from typing import List, Any, Dict
from src.domain.player.player import Player
from src.domain.spot.road_enum import ConditionType


@dataclass(frozen=True)
class ConditionCheckResult:
    condition: "Condition"
    is_satisfied: bool
    message: str = ""


@dataclass(frozen=True)
class Condition:
    condition_type: ConditionType
    value: Any
    
    def __post_init__(self):
        if self.condition_type == ConditionType.HAS_GOLD:
            if self.value < 0:
                raise ValueError(f"Value must be greater than or equal to 0: {self.value}")
        elif self.condition_type == ConditionType.HAS_ITEM:
            if self.value < 0:
                raise ValueError(f"Value must be greater than or equal to 0: {self.value}")
        elif self.condition_type == ConditionType.HAS_ROLE:
            if self.value is None:
                raise ValueError(f"Value must be not None: {self.value}")
        elif self.condition_type == ConditionType.MIN_LEVEL:
            if self.value < 0:
                raise ValueError(f"Value must be greater than or equal to 0: {self.value}")
        else:
            raise ValueError(f"Invalid condition type: {self.condition_type}")
    
    def check(self, player: Player) -> bool:
        if self.condition_type == ConditionType.MIN_LEVEL:
            return player.level_is_above(self.value)
        elif self.condition_type == ConditionType.HAS_ITEM:
            return player.has_stackable_item(self.value)
        elif self.condition_type == ConditionType.HAS_GOLD:
            return player.can_pay_gold(self.value)
        elif self.condition_type == ConditionType.HAS_ROLE:
            return player.role == self.value
        else:
            raise ValueError(f"Invalid condition type: {self.condition_type}")

    def check_with_details(self, player: Player) -> ConditionCheckResult:
        """条件チェックの詳細な結果を返す"""
        if self.condition_type == ConditionType.MIN_LEVEL:
            current_level = player.level
            is_satisfied = player.level_is_above(self.value)
            message = f"レベル {self.value} 以上が必要 (現在: {current_level})"
            return ConditionCheckResult(
                condition=self,
                is_satisfied=is_satisfied,
                current_value=current_level,
                required_value=self.value,
                message=message
            )
        elif self.condition_type == ConditionType.HAS_ITEM:
            has_item = player.has_stackable_item(self.value)
            message = f"アイテム '{self.value}' が必要"
            return ConditionCheckResult(
                condition=self,
                is_satisfied=has_item,
                required_value=self.value,
                message=message
            )
        elif self.condition_type == ConditionType.HAS_GOLD:
            current_gold = player.gold  # playerにgoldプロパティがあると仮定
            can_pay = player.can_pay_gold(self.value)
            message = f"ゴールド {self.value} 以上が必要 (現在: {current_gold})"
            return ConditionCheckResult(
                condition=self,
                is_satisfied=can_pay,
                current_value=current_gold,
                required_value=self.value,
                message=message
            )
        elif self.condition_type == ConditionType.HAS_ROLE:
            current_role = player.role
            has_role = player.role == self.value
            message = f"ロール '{self.value}' が必要 (現在: {current_role})"
            return ConditionCheckResult(
                condition=self,
                is_satisfied=has_role,
                current_value=current_role,
                required_value=self.value,
                message=message
            )
        else:
            raise ValueError(f"Invalid condition type: {self.condition_type}")


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
    
    def is_available(self, player: Player) -> bool:
        if self.conditions is None:
            return True
        for condition in self.conditions:
            if not condition.check(player):
                return False
        return True

    def _check_availability_details(self, player: Player) -> Dict[str, Any]:
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

    def get_availability_message(self, player: Player) -> str:
        """利用可能性に関する詳細なメッセージを生成"""
        details = self._check_availability_details(player)
        
        if details["is_available"]:
            return f"道路 '{self.description}' は利用可能です"
        
        failed_messages = [result.message for result in details["failed_conditions"]]
        return f"道路 '{self.description}' は利用できません。理由: {', '.join(failed_messages)}"