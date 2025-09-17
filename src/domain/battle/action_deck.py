from dataclasses import dataclass
from typing import List, Optional
from src.domain.battle.action_slot import ActionSlot
from src.domain.battle.skill_capacity import SkillCapacity


@dataclass(frozen=True)
class ActionDeck:
    """技のデッキを表現する値オブジェクト"""
    slots: List[ActionSlot]
    capacity: SkillCapacity
    
    def __post_init__(self):
        if len(self.slots) < 0:
            raise ValueError("slots cannot be negative length")
        
        # 重複チェック
        action_ids = [slot.action_id for slot in self.slots]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("Duplicate action_ids are not allowed in deck")
        
        # キャパシティチェック
        current_usage = self.current_capacity_usage()
        if current_usage > self.capacity.max_capacity:
            raise ValueError(f"Total cost exceeds max capacity. current: {current_usage}, max: {self.capacity.max_capacity}")
    
    def current_capacity_usage(self) -> int:
        """現在のキャパシティ使用量を計算"""
        return sum(slot.cost for slot in self.slots)
    
    def remaining_capacity(self) -> int:
        """残りキャパシティを計算"""
        return self.capacity.calculate_remaining(self.current_capacity_usage())
    
    def can_add_action(self, action_slot: ActionSlot) -> bool:
        """アクションを追加できるかどうか"""
        # 既に同じaction_idが存在するかチェック
        if any(slot.action_id == action_slot.action_id for slot in self.slots):
            return False
        
        # キャパシティチェック
        return self.capacity.can_accommodate(action_slot.cost, self.current_capacity_usage())
    
    def add_action(self, action_slot: ActionSlot) -> "ActionDeck":
        """アクションを追加した新しいデッキを返す"""
        if not self.can_add_action(action_slot):
            raise ValueError(f"Cannot add action. action_id: {action_slot.action_id}, cost: {action_slot.cost}")
        
        new_slots = self.slots + [action_slot]
        return ActionDeck(new_slots, self.capacity)
    
    def remove_action(self, action_id: int) -> "ActionDeck":
        """アクションを削除した新しいデッキを返す"""
        new_slots = [slot for slot in self.slots if slot.action_id != action_id]
        if len(new_slots) == len(self.slots):
            raise ValueError(f"Action not found in deck. action_id: {action_id}")
        
        return ActionDeck(new_slots, self.capacity)
    
    def update_action_slot(self, action_id: int, new_slot: ActionSlot) -> "ActionDeck":
        """指定されたアクションのスロットを更新した新しいデッキを返す"""
        if new_slot.action_id != action_id:
            raise ValueError("Cannot change action_id in update_action_slot")
        
        slot_index = None
        for i, slot in enumerate(self.slots):
            if slot.action_id == action_id:
                slot_index = i
                break
        
        if slot_index is None:
            raise ValueError(f"Action not found in deck. action_id: {action_id}")
        
        # キャパシティチェック（他のスロットのコストは変わらない前提）
        other_slots_cost = sum(slot.cost for i, slot in enumerate(self.slots) if i != slot_index)
        if other_slots_cost + new_slot.cost > self.capacity.max_capacity:
            raise ValueError(f"Updated slot would exceed capacity. new_cost: {new_slot.cost}")
        
        new_slots = self.slots.copy()
        new_slots[slot_index] = new_slot
        return ActionDeck(new_slots, self.capacity)
    
    def get_action_ids(self) -> List[int]:
        """デッキ内のアクションIDのリストを取得"""
        return [slot.action_id for slot in self.slots]
    
    def get_action_slot(self, action_id: int) -> Optional[ActionSlot]:
        """指定されたアクションのスロットを取得"""
        for slot in self.slots:
            if slot.action_id == action_id:
                return slot
        return None
    
    def has_action(self, action_id: int) -> bool:
        """指定されたアクションを持っているかどうか"""
        return any(slot.action_id == action_id for slot in self.slots)
    
    def is_empty(self) -> bool:
        """デッキが空かどうか"""
        return len(self.slots) == 0
    
    def is_full(self) -> bool:
        """キャパシティが満杯かどうか"""
        return self.capacity.is_full(self.current_capacity_usage())
    
    def slot_count(self) -> int:
        """スロット数を取得"""
        return len(self.slots)
