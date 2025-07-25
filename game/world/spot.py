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
        self._possible_actions: List['ActionStrategy'] = []

    def add_interactable(self, interactable: InteractableObject):
        self.interactables[interactable.object_id] = interactable
    
    def remove_interactable(self, object_id: str):
        if object_id in self.interactables:
            del self.interactables[object_id]
    
    def get_interactable_by_id(self, object_id: str) -> Optional[InteractableObject]:
        return self.interactables.get(object_id)
    
    def get_all_interactables(self) -> List[InteractableObject]:
        return list(self.interactables.values())

    def add_monster(self, monster: Monster):
        monster.set_current_spot(self.spot_id)
        
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
        self._possible_actions.append(action)
    
    def get_possible_actions(self) -> List['ActionStrategy']:
        all_actions = list(self._possible_actions)
        for obj in self.interactables.values():
            all_actions.extend(obj.get_possible_actions())
        return all_actions