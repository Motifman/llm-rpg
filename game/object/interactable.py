from typing import List, Dict, Set, Optional, TYPE_CHECKING
from abc import ABC, abstractmethod

# 型ヒントの遅延インポート
if TYPE_CHECKING:
    from game.action.action_strategy import ActionStrategy


class InteractableObject(ABC):
    def __init__(self, object_id: str, name: str, description: str):
        self.object_id = object_id
        self.name = name
        self.description = description
        self._possible_actions: List['ActionStrategy'] = []
        print(f"DEBUG: インタラクティブオブジェクト {self.name} (ID: {self.object_id}) が作成されました。")

    def get_possible_actions(self) -> List['ActionStrategy']:
        return self._possible_actions

    def get_object_id(self) -> str:
        return self.object_id
    
    def get_name(self) -> str:
        return self.name
    
    def __str__(self):
        return f"InteractiveObject(id='{self.object_id}', name='{self.name}')"
    
    def __repr__(self):
        return f"InteractiveObject(id='{self.object_id}', name='{self.name}')"