from dataclasses import dataclass
from typing import Dict, List, Optional
from game.enums import StatusEffectType, EquipmentSlot
from game.player.player import Player
from game.item.equipment_item import Weapon, Armor


@dataclass
class BattleStats:
    """戦闘前の確定ステータスを表すクラス"""
    
    # 基本ステータス
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    
    # 戦闘ステータス（装備ボーナス含む）
    attack: int
    defense: int
    speed: int
    critical_rate: float
    evasion_rate: float
    
    # 装備情報
    equipped_weapon: Optional[Weapon]
    equipped_armors: List[Armor]
    
    # 状態異常
    status_effects: Dict[StatusEffectType, 'StatusEffect']
    
    @classmethod
    def from_player(cls, player: Player) -> 'BattleStats':
        """プレイヤーから戦闘ステータスを生成"""
        return cls(
            hp=player.get_hp(),
            max_hp=player.status.get_max_hp(),
            mp=player.get_mp(),
            max_mp=player.status.get_max_mp(),
            attack=player.get_attack(),
            defense=player.get_defense(),
            speed=player.get_speed(),
            critical_rate=player.get_critical_rate(),
            evasion_rate=player.get_evasion_rate(),
            equipped_weapon=player.get_equipped_weapon(),
            equipped_armors=player.get_equipped_armors(),
            status_effects=player.status.get_status_effects()
        )
    
    def get_total_defense_bonus(self) -> int:
        """装備による防御力ボーナス合計"""
        return sum(armor.get_defense_bonus() for armor in self.equipped_armors)
    
    def get_total_speed_bonus(self) -> int:
        """装備による素早さボーナス合計"""
        return sum(armor.get_speed_bonus() for armor in self.equipped_armors)
    
    def get_total_evasion_bonus(self) -> float:
        """装備による回避率ボーナス合計"""
        return sum(armor.get_evasion_bonus() for armor in self.equipped_armors)
    
    def get_total_status_resistance(self, status_type: StatusEffectType) -> float:
        """装備による状態異常耐性合計"""
        return sum(armor.get_status_resistance(status_type) for armor in self.equipped_armors)
    
    def get_working_armors(self) -> List[Armor]:
        """破損していない防具のみを取得"""
        return [armor for armor in self.equipped_armors if not armor.is_broken()]
    
    def has_status_effect(self, status_type: StatusEffectType) -> bool:
        """特定の状態異常を持っているか"""
        return status_type in self.status_effects
    
    def get_status_effect(self, status_type: StatusEffectType) -> Optional['StatusEffect']:
        """特定の状態異常を取得"""
        return self.status_effects.get(status_type)
    
    def is_alive(self) -> bool:
        """生存しているか"""
        return self.hp > 0
    
    def can_act(self) -> bool:
        """行動可能か"""
        if (self.has_status_effect(StatusEffectType.PARALYSIS) or 
            self.has_status_effect(StatusEffectType.SLEEP)):
            return False
        return self.is_alive()
    
    def get_summary(self) -> str:
        """ステータスの要約を取得"""
        return (f"HP: {self.hp}/{self.max_hp}, "
                f"MP: {self.mp}/{self.max_mp}, "
                f"攻撃: {self.attack}, 防御: {self.defense}, 素早さ: {self.speed}, "
                f"クリティカル: {self.critical_rate:.1%}, 回避: {self.evasion_rate:.1%}")


class BattleStatsCalculator:
    """戦闘前の確定ステータスを計算するクラス"""
    
    @staticmethod
    def calculate_battle_stats(player: Player) -> BattleStats:
        """プレイヤーの戦闘前確定ステータスを計算"""
        return BattleStats.from_player(player)
    
    @staticmethod
    def calculate_party_stats(players: List[Player]) -> List[BattleStats]:
        """パーティ全体の戦闘前確定ステータスを計算"""
        return [BattleStats.from_player(player) for player in players]
    
    @staticmethod
    def get_equipment_bonuses(player: Player) -> Dict[str, int]:
        """装備によるボーナス一覧を取得"""
        equipment = player.equipment
        return {
            'attack_bonus': equipment.get_total_attack_bonus(),
            'defense_bonus': equipment.get_total_defense_bonus(),
            'speed_bonus': equipment.get_total_speed_bonus(),
            'critical_rate': equipment.get_total_critical_rate(),
            'evasion_rate': equipment.get_total_evasion_rate()
        }
    
    @staticmethod
    def get_status_effect_bonuses(player: Player) -> Dict[str, int]:
        """状態異常によるボーナス一覧を取得"""
        status = player.status
        return {
            'attack_bonus': status.get_attack_bonus(),
            'defense_bonus': status.get_defense_bonus(),
            'speed_bonus': status.get_speed_bonus()
        } 