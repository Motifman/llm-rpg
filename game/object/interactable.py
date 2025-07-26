from typing import List, Dict, Set, Optional, TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from game.action.action_strategy import ActionStrategy


class InteractableObject(ABC):
    def __init__(self, object_id: str, description: str):
        self.object_id = object_id
        self.description = description
        self._possible_actions: Dict[str, 'ActionStrategy'] = {}

    def get_possible_actions(self) -> Dict[str, 'ActionStrategy']:
        return self._possible_actions

    def get_object_id(self) -> str:
        return self.object_id
    
    def get_description(self) -> str:
        return self.description
    
    def __str__(self):
        return f"InteractableObject(id='{self.object_id}')"
    
    def __repr__(self):
        return f"InteractableObject(id='{self.object_id}')"