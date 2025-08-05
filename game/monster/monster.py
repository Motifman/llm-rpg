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
        
    def get_monster_id(self) -> str:
        return self.monster_id
    
    def get_name(self) -> str:
        return self.name
    
    def get_description(self) -> str:
        return self.description
    
    def get_monster_type(self) -> MonsterType:
        return self.monster_type
    
    def get_race(self) -> Race:
        return self.race
    
    def get_element(self) -> Element:
        return self.element
    
    def get_drop_reward(self) -> MonsterDropReward:
        return self.drop_reward
    
    def get_battle_actions(self) -> List[str]:
        return self.battle_actions
    
    def get_allowed_spots(self) -> Set[str]:
        return self.allowed_spots
    
    def get_status(self) -> Status:
        return self.status
    
    def get_current_spot_id(self) -> str:
        return self.current_spot_id
    
    def set_current_spot_id(self, spot_id: str):
        self.current_spot_id = spot_id
    
    def is_alive(self) -> bool:
        """生存しているかチェック"""
        return self.status.get_hp() > 0

    def get_attack(self) -> int:
        """攻撃力を取得"""
        return self.status.get_attack()
    
    def get_defense(self) -> int:
        """防御力を取得"""
        return self.status.get_defense()
    
    def get_speed(self) -> int:
        """素早さを取得"""
        return self.status.get_speed()

    def get_critical_rate(self) -> float:
        """クリティカル率を取得"""
        return self.status.get_critical_rate()
    
    def get_evasion_rate(self) -> float:
        """回避率を取得"""
        return self.status.get_evasion_rate()

    def get_hp(self) -> int:
        """現在のHPを取得"""
        return self.status.get_hp()
    
    def get_max_hp(self) -> int:
        """最大HPを取得"""
        return self.status.get_max_hp()

    def set_hp(self, hp: int):
        """HPを設定"""
        self.status.set_hp(hp)
    
    def set_max_hp(self, max_hp: int):
        """最大HPを設定"""
        self.status.set_max_hp(max_hp)
    
    def set_attack(self, attack: int):
        """攻撃力を設定"""
        self.status.set_attack(attack)
    
    def set_defense(self, defense: int):
        """防御力を設定"""
        self.status.set_defense(defense)
    
    def set_speed(self, speed: int):
        """素早さを設定"""
        self.status.set_speed(speed)

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
            return random.choice(["attack", "defend"])
        
        if self.status.get_hp() <= self.status.get_max_hp() // 2:
            return "defend"
        return "attack"
    
    def is_alive(self) -> bool:
        """生存しているかチェック"""
        return self.status.get_hp() > 0
    
    def can_act(self) -> bool:
        """行動可能かチェック"""
        return self.is_alive() and not self.status.has_status_effect_type(StatusEffectType.PARALYSIS) and not self.status.has_status_effect_type(StatusEffectType.SLEEP)
    
    def is_confused(self) -> bool:
        """混乱しているかチェック"""
        return self.status.has_status_effect_type(StatusEffectType.CONFUSION)
    
    def take_damage(self, damage: int):
        """ダメージを受ける"""
        self.status.add_hp(-damage)
    
    def set_defending(self, defending: bool):
        """防御状態を設定"""
        self.status.set_defending(defending)
    
    def is_defending(self) -> bool:
        """防御状態かどうか"""
        return self.status.is_defending()
    
    def process_status_effects(self):
        """状態異常を処理"""
        self.status.process_status_effects()
    
    def add_status_condition(self, status_effect_type: StatusEffectType, duration: int):
        """状態異常を追加"""
        effect = StatusEffect(status_effect_type, duration)
        self.status.add_status_effect(effect)
    
    def __str__(self):
        return f"Monster(id={self.monster_id}, name={self.name}, type={self.monster_type.value}, race={self.race.value}, element={self.element.value}, hp={self.status.get_hp()}/{self.status.get_max_hp()})"
    
    def __repr__(self):
        return self.__str__() 