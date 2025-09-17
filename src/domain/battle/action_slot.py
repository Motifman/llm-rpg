from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSlot:
    """技スロットを表現する値オブジェクト"""
    action_id: int
    level: int = 1
    cost: int = 1
    
    def __post_init__(self):
        if self.action_id <= 0:
            raise ValueError(f"action_id must be positive. action_id: {self.action_id}")
        if self.level <= 0:
            raise ValueError(f"level must be positive. level: {self.level}")
        if self.cost <= 0:
            raise ValueError(f"cost must be positive. cost: {self.cost}")
    
    def with_level(self, level: int) -> "ActionSlot":
        """レベルを変更した新しいActionSlotを返す"""
        return ActionSlot(self.action_id, level, self.cost)
    
    def with_cost(self, cost: int) -> "ActionSlot":
        """コストを変更した新しいActionSlotを返す"""
        return ActionSlot(self.action_id, self.level, cost)
