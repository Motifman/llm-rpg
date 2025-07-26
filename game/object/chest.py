from typing import List, Optional
from game.object.interactable import InteractableObject
from game.action.actions.interactable_action import OpenChestStrategy
from game.item.item import Item


class Chest(InteractableObject):
    def __init__(self, chest_id: str, display_name: str, contents: List[Item] = None, is_locked: bool = False, required_item_id: Optional[str] = None):
        super().__init__(chest_id, f"{display_name}（宝箱）")
        self.chest_id = chest_id
        self.display_name = display_name
        self.contents = contents if contents is not None else []
        self.is_locked = is_locked
        self.is_opened = False
        self.required_item_id = required_item_id
        
        self._possible_actions[OpenChestStrategy().get_name()] = OpenChestStrategy() 
        
    def unlock(self) -> bool:
        if self.is_locked:
            self.is_locked = False
            return True
        return False

    def open(self) -> List[Item]:
        if not self.is_opened and not self.is_locked:
            self.is_opened = True
            items = self.contents.copy()
            self.contents.clear()
            return items
        return []
    
    def set_contents(self, contents: List[Item]):
        self.contents = contents
        self.is_opened = False

    def get_remaining_contents(self) -> List[Item]:
        return self.contents if not self.is_opened else []
    
    def get_chest_id(self) -> str:
        return self.chest_id
    
    def get_display_name(self) -> str:
        return self.display_name
        
    def __str__(self):
        return f"Chest(id='{self.chest_id}', name='{self.display_name}', contents={self.contents}, opened={self.is_opened}, locked={self.is_locked})"