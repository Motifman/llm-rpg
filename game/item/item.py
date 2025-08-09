from dataclasses import dataclass
from abc import ABC, abstractmethod
import uuid
from game.enums import AppearanceSlot


@dataclass(frozen=True)
class Item:
    item_id: str
    name: str
    description: str

    def __str__(self):
        return f"{self.name} ({self.item_id}) - {self.description}"
    
    def __repr__(self):
        return f"Item(item_id={self.item_id}, name={self.name}, description={self.description})"
    
    def can_be_traded(self) -> bool:
        """アイテムが取引可能かどうかを判定"""
        # デフォルトでは取引可能
        return True


class StackableItem(Item, ABC):
    """スタック可能なアイテムの基底クラス"""
    
    def __init__(self, item_id: str, name: str, description: str, max_stack: int = 1):
        super().__init__(item_id, name, description)
        self.max_stack = max_stack
    
    def can_stack_with(self, other: 'StackableItem') -> bool:
        return (self.item_id == other.item_id and 
                self.max_stack == other.max_stack)
    
    def can_be_traded(self) -> bool:
        """アイテムが取引可能かどうかを判定"""
        # デフォルトでは取引可能
        return True


class UniqueItem(Item, ABC):
    """固有アイテムの基底クラス（耐久度などの状態を持つ）"""
    
    def __init__(self, item_id: str, name: str, description: str):
        super().__init__(item_id, name, description)
        self._unique_id = str(uuid.uuid4())
    
    def get_unique_id(self) -> str:
        """固有IDを取得"""
        return self._unique_id
    
    @abstractmethod
    def get_status_description(self) -> str:
        """アイテムの状態を表す文字列を取得"""
        pass
    
    def can_be_traded(self) -> bool:
        """アイテムが取引可能かどうかを判定"""
        # デフォルトでは取引可能
        return True
    
    def __str__(self):
        return f"{self.name} ({self.item_id}) - {self.description} [{self.get_status_description()}]"


@dataclass(frozen=True)
class AppearanceItem(Item):
    """戦闘性能に影響しない外見用アイテム。
    Playerの見た目スロットに装着されることを想定。
    """
    slot: AppearanceSlot
    appearance_text: str = ""

    def can_be_traded(self) -> bool:
        return True