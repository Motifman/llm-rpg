import random
from typing import List, Optional, Set, Dict
from dataclasses import dataclass, field
from game.item.item import Item
from game.player.player import Player
from game.enums import MonsterType, Race, Element, StatusEffectType
from game.player.status import Status, StatusEffect


@dataclass
class MonsterDropReward:
    items: List[Item] = field(default_factory=list)
    money: int = 0
    experience: int = 0
    information: List[str] = field(default_factory=list)


class Monster:
    def __init__(
        self,
        monster_id: str,
        name: str,
        description: str,
        monster_type: MonsterType,
        race: Optional[Race] = None,
        element: Optional[Element] = None,
        allowed_spots: Optional[Set[str]] = None,
        drop_reward: Optional[MonsterDropReward] = None
    ):
        self.monster_id = monster_id
        self.name = name
        self.description = description
        self.monster_type = monster_type
        self.race = race if race else Race.MONSTER
        self.element = element if element else Element.PHYSICAL
        self.drop_reward = drop_reward or MonsterDropReward()
        self.battle_actions = ["attack", "defend"]
        self.allowed_spots = allowed_spots or set()
        
        self.status = Status()
        self.status.set_mp(0)
        self.current_spot_id = None

    def can_move_to_spot(self, spot_id: str) -> bool:
        if not self.allowed_spots:
            return True
        return spot_id in self.allowed_spots

    def get_current_spot_id(self) -> str:
        return self.current_spot_id
    
    def set_current_spot_id(self, spot_id: str):
        if self.can_move_to_spot(spot_id):
            self.current_spot_id = spot_id
        else:
            raise ValueError(f"モンスター {self.name} はスポット {spot_id} に移動できません")
        
    def get_status_summary(self) -> str:
        return self.status.get_status_summary()
    
    def is_battle_forced(self) -> bool:
        return self.monster_type == MonsterType.AGGRESSIVE
    
    def requires_exploration_to_find(self) -> bool:
        return self.monster_type == MonsterType.HIDDEN
    
    def is_passive(self) -> bool:
        return self.monster_type == MonsterType.PASSIVE
    
    def get_battle_action(self) -> str:
        if not self.can_act():
            return "unable_to_act"
        
        if self.is_confused():
            return random.choice(["attack", "defend", "confusion"])
        
        if self.status.get_hp() <= self.status.get_max_hp() // 2:
            return "defend"
        return "attack"
    
    def __str__(self):
        return f"Monster(id={self.monster_id}, name={self.name}, type={self.monster_type.value}, race={self.race.value}, element={self.element.value}, hp={self.status.get_hp()}/{self.status.get_max_hp()})"
    
    def __repr__(self):
        return self.__str__() 