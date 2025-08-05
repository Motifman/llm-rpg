from typing import List, Dict, Set, Optional, TYPE_CHECKING
from game.monster.monster import Monster
from game.player.player import Player
from game.player.inventory import Inventory
from game.object.interactable import InteractableObject
from game.enums import MonsterType

if TYPE_CHECKING:
    from game.action.action_strategy import ActionStrategy


class Spot:
    def __init__(self, spot_id: str, name: str, description: str):
        self.spot_id = spot_id
        self.name = name
        self.description = description
        self.inventory = Inventory()
        self.interactables: Dict[str, InteractableObject] = {}
        self.monsters: Dict[str, Monster] = {}
        self.hidden_monsters: Dict[str, Monster] = {}
        self._possible_actions: Dict[str, 'ActionStrategy'] = {}

    def add_interactable(self, interactable: InteractableObject):
        self.interactables[interactable.object_id] = interactable
    
    def remove_interactable(self, object_id: str):
        if object_id in self.interactables:
            del self.interactables[object_id]
    
    def get_interactable_by_id(self, object_id: str) -> Optional[InteractableObject]:
        return self.interactables.get(object_id)
    
    def get_all_interactables(self) -> List[InteractableObject]:
        return list(self.interactables.values())

    def get_unique_interactables_by_type(self) -> List[InteractableObject]:
        unique_interactable_types = []
        unique_interactables = []
        for interactable in self.interactables.values():
            interactable_type = type(interactable)
            if interactable_type not in unique_interactable_types:
                unique_interactable_types.append(interactable_type)
                unique_interactables.append(interactable)
        return unique_interactables

    def get_interactables_of_type(self, interactable_type: type) -> List[InteractableObject]:
        return [obj for obj in self.interactables.values() if isinstance(obj, interactable_type)]

    def add_monster(self, monster: Monster):
        monster.set_current_spot_id(self.spot_id)
        
        if monster.monster_type == MonsterType.HIDDEN:
            self.hidden_monsters[monster.monster_id] = monster
        else:
            self.monsters[monster.monster_id] = monster

    def remove_monster(self, monster_id: str):
        if monster_id in self.monsters:
            del self.monsters[monster_id]
        if monster_id in self.hidden_monsters:
            del self.hidden_monsters[monster_id]
    
    def get_visible_monsters(self) -> List[Monster]:
        return list(self.monsters.values())
    
    def get_all_monsters(self) -> List[Monster]:
        all_monsters = list(self.monsters.values())
        all_monsters.extend(self.hidden_monsters.values())
        return all_monsters
    
    def reveal_hidden_monster(self, monster_id: str) -> bool:
        if monster_id in self.hidden_monsters:
            monster = self.hidden_monsters[monster_id]
            del self.hidden_monsters[monster_id]
            self.monsters[monster_id] = monster
            return True
        return False
    
    def add_action(self, action: 'ActionStrategy'):
        self._possible_actions[action.get_name()] = action
    
    def get_possible_actions(self) -> Dict[str, 'ActionStrategy']:
        all_actions = self._possible_actions.copy()
        for obj in self.get_unique_interactables_by_type():
            all_actions.update(obj.get_possible_actions())
        return all_actions

    def get_exploration_summary(self) -> str:
        summary = f"周囲の状況:\n"
        if self.interactables:
            summary += f"インタラクト可能なオブジェクト:\n"
            for obj in self.interactables.values():
                summary += f"- {obj.get_description()}\n"
        if self.monsters:
            summary += f"モンスター:\n"
            for monster in self.monsters.values():
                summary += f"- {monster.get_description()}\n"
        return summary