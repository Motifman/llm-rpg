from dataclasses import dataclass
from typing import Any
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
    
    def check(self, player: 'Player') -> bool:
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

    def check_with_details(self, player: 'Player') -> ConditionCheckResult:
        """条件チェックの詳細な結果を返す"""
        if self.condition_type == ConditionType.MIN_LEVEL:
            current_level = player.level
            is_satisfied = player.level_is_above(self.value)
            message = f"レベル {self.value} 以上が必要 (現在: {current_level})"
            return ConditionCheckResult(
                condition=self,
                is_satisfied=is_satisfied,
                message=message
            )
        elif self.condition_type == ConditionType.HAS_ITEM:
            has_item = player.has_stackable_item(self.value)
            message = f"アイテム '{self.value}' が必要"
            return ConditionCheckResult(
                condition=self,
                is_satisfied=has_item,
                message=message
            )
        elif self.condition_type == ConditionType.HAS_GOLD:
            current_gold = player.gold
            can_pay = player.can_pay_gold(self.value)
            message = f"ゴールド {self.value} 以上が必要 (現在: {current_gold})"
            return ConditionCheckResult(
                condition=self,
                is_satisfied=can_pay,
                message=message
            )
        elif self.condition_type == ConditionType.HAS_ROLE:
            current_role = player.role
            has_role = player.role == self.value
            message = f"ロール '{self.value}' が必要 (現在: {current_role})"
            return ConditionCheckResult(
                condition=self,
                is_satisfied=has_role,
                message=message
            )
        else:
            raise ValueError(f"Invalid condition type: {self.condition_type}")
