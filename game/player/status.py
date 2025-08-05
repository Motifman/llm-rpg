from typing import Dict, TYPE_CHECKING
from dataclasses import dataclass
from game.enums import StatusEffectType

if TYPE_CHECKING:
    from game.item.item_effect import ItemEffect


@dataclass
class StatusEffect:
    """状態異常"""
    effect: StatusEffectType
    duration: int 
    value: int = 0
    
    def __str__(self):
        return f"{self.effect.value}({self.duration}ターン)" 


class Status:
    def __init__(self):
        self.hp = 100
        self.mp = 100
        self.attack = 10
        self.defense = 10
        self.speed = 10
        self.critical_rate = 0.0
        self.evasion_rate = 0.0
        self.experience_points = 0
        self.level = 1
        self.money = 0
        self.status_effects: Dict[StatusEffectType, StatusEffect] = {}
        self.defending = False

        self.max_hp = 100
        self.max_mp = 100
    
    def get_hp(self) -> int:
        """HPを取得"""
        return self.hp
    
    def get_max_hp(self) -> int:
        """HPの最大値を取得"""
        return self.max_hp
    
    def set_max_hp(self, max_hp: int):
        """HPの最大値を設定"""
        self.max_hp = max(0, max_hp)
        self.hp = min(self.hp, self.max_hp)

    def set_hp(self, hp: int):
        """HPを設定"""
        self.hp = max(0, min(hp, self.max_hp))
    
    def add_hp(self, hp: int):
        """HPを追加"""
        self.hp = max(0, min(self.hp + hp, self.max_hp))

    def get_mp(self) -> int:
        """MPを取得"""
        return self.mp
    
    def get_max_mp(self) -> int:
        """MPの最大値を取得"""
        return self.max_mp
    
    def set_max_mp(self, max_mp: int):
        """MPの最大値を設定"""
        self.max_mp = max(0, max_mp)
        self.mp = min(self.mp, self.max_mp)
    
    def set_mp(self, mp: int):
        """MPを設定"""
        self.mp = max(0, min(mp, self.max_mp))
    
    def add_mp(self, mp: int):
        """MPを追加"""
        self.mp = max(0, min(self.mp + mp, self.max_mp))
    
    def get_base_attack(self) -> int:
        """基本攻撃力を取得（装備ボーナスなし）"""
        return self.attack
    
    def get_attack(self) -> int:
        """攻撃力を取得（基本値のみ）"""
        return self.attack
    
    def set_attack(self, attack: int):
        """攻撃力を設定"""
        self.attack = max(0, attack)
    
    def add_attack(self, attack: int):
        """攻撃力を追加"""
        if attack < 0:
            attack = 0
        self.attack += attack
    
    def get_base_defense(self) -> int:
        """基本防御力を取得（装備ボーナスなし）"""
        return self.defense
    
    def get_defense(self) -> int:
        """防御力を取得（基本値のみ）"""
        return self.defense
    
    def set_defense(self, defense: int):
        """防御力を設定"""
        self.defense = max(0, defense)
    
    def add_defense(self, defense: int):
        """防御力を追加"""
        self.defense = max(0, self.defense + defense)
    
    def get_base_speed(self) -> int:
        """基本素早さを取得（装備ボーナスなし）"""
        return self.speed
    
    def get_speed(self) -> int:
        """素早さを取得（基本値のみ）"""
        return self.speed
    
    def set_speed(self, speed: int):
        """素早さを設定"""
        self.speed = max(0, speed)
    
    def add_speed(self, speed: int):
        """素早さを追加"""
        self.speed = max(0, self.speed + speed)
    
    def get_critical_rate(self) -> float:
        """クリティカル率を取得"""
        return self.critical_rate
    
    def set_critical_rate(self, critical_rate: float):
        """クリティカル率を設定"""
        self.critical_rate = max(0, critical_rate)
    
    def add_critical_rate(self, critical_rate: float):
        """クリティカル率を追加"""
        self.critical_rate = max(0, self.critical_rate + critical_rate)
    
    def get_evasion_rate(self) -> float:
        """回避率を取得"""
        return self.evasion_rate
    
    def set_evasion_rate(self, evasion_rate: float):
        """回避率を設定"""
        self.evasion_rate = max(0, evasion_rate)
    
    def add_evasion_rate(self, evasion_rate: float):
        """回避率を追加"""
        self.evasion_rate = max(0, self.evasion_rate + evasion_rate)
    
    def get_experience_points(self) -> int:
        """経験値を取得"""
        return self.experience_points
    
    def set_experience_points(self, experience_points: int):
        """経験値を設定"""
        self.experience_points = max(0, experience_points)
    
    def add_experience_points(self, experience_points: int):
        """経験値を追加"""
        self.experience_points = max(0, self.experience_points + experience_points)
        self._check_level_up()
    
    def get_level(self) -> int:
        """レベルを取得"""
        return self.level
    
    def set_level(self, level: int):
        """レベルを設定"""
        self.level = max(1, level)
    
    def _check_level_up(self):
        """レベルアップのチェック"""
        # 簡単なレベルアップ計算（経験値100ごとにレベルアップ）
        new_level = (self.experience_points // 100) + 1
        if new_level > self.level:
            self.level = new_level
            # レベルアップ時のステータス上昇
            self.max_hp += 10
            self.max_mp += 5
            self.attack += 2
            self.defense += 1
            self.speed += 1
            # HPとMPを最大値まで回復
            self.hp = self.max_hp
            self.mp = self.max_mp
    
    def get_money(self) -> int:
        """所持金を取得"""
        return self.money
    
    def set_money(self, money: int):
        """所持金を設定"""
        self.money = max(0, money)
    
    def add_money(self, money: int):
        """所持金を追加"""
        self.money = max(0, self.money + money)
        
    def set_defending(self, defending: bool):
        """防御状態を設定"""
        self.defending = defending
    
    def is_defending(self) -> bool:
        """防御状態かどうか"""
        return self.defending
    
    def get_status_effects(self) -> Dict[StatusEffectType, StatusEffect]:
        """状態異常を取得"""
        return self.status_effects
    
    def set_status_effects(self, status_effects: Dict[StatusEffectType, StatusEffect]):
        """状態異常を設定"""
        self.status_effects = status_effects
    
    def add_status_effect(self, status_effect: StatusEffect):
        """状態異常を追加"""
        self.status_effects[status_effect.effect] = status_effect
    
    def remove_status_effect(self, status_effect: StatusEffect):
        """状態異常を削除"""
        self.status_effects.pop(status_effect.effect, None)
    
    def remove_status_effect_by_type(self, effect_type: StatusEffectType):
        """状態異常を削除"""
        self.status_effects.pop(effect_type, None)
    
    def has_status_effect(self, status_effect: StatusEffect) -> bool:
        """状態異常が存在するかどうか"""
        return status_effect.effect in self.status_effects
    
    def has_status_effect_type(self, effect_type: StatusEffectType) -> bool:
        """特定の状態異常が存在するかどうか"""
        return effect_type in self.status_effects
    
    def get_status_effect(self, effect_type: StatusEffectType) -> StatusEffect:
        """状態異常を取得"""
        return self.status_effects.get(effect_type)
    
    def update_status_effect_duration(self, effect_type: StatusEffectType, new_duration: int):
        """状態異常の残りターン数を更新"""
        if effect_type in self.status_effects:
            self.status_effects[effect_type].duration = new_duration
    
    def _decrease_all_status_effect_durations(self):
        """状態異常の残りターン数を減らす"""
        expired_effects = []
        for effect_type, effect in self.status_effects.items():
            effect.duration -= 1
            if effect.duration <= 0:
                expired_effects.append(effect_type)
        
        for effect_type in expired_effects:
            self.status_effects.pop(effect_type)
    
    def process_status_effects(self):
        """状態異常を処理"""
        self._decrease_all_status_effect_durations()
        
        # 状態異常による効果を適用
        for effect_type, effect in self.status_effects.items():
            if effect_type == StatusEffectType.POISON:
                self.add_hp(-effect.value)
            elif effect_type == StatusEffectType.BURN:
                self.add_hp(-effect.value)
        self._decrease_all_status_effect_durations()

    def get_status_effect_bonus(self, effect_type: StatusEffectType) -> int:
        """状態異常によるボーナスを取得"""
        status_effect = self.status_effects.get(effect_type)
        return status_effect.value if status_effect else 0

    def is_alive(self) -> bool:
        """生存しているかどうか"""
        return self.hp > 0
    
    def get_status_summary(self) -> str:
        """ステータスの要約を取得"""
        return (f"HP: {self.hp}/{self.max_hp}, "
                f"MP: {self.mp}/{self.max_mp}, "
                f"基本攻撃: {self.attack}, 基本防御: {self.defense}, 基本素早さ: {self.speed}, "
                f"所持金: {self.money}, 経験値: {self.experience_points}, "
                f"クリティカル: {self.get_critical_rate():.1%}, 回避: {self.get_evasion_rate():.1%}")

    def apply_item_effect(self, effect: 'ItemEffect'):
        """アイテム効果を適用"""
        self.add_hp(effect.hp_change)
        self.add_mp(effect.mp_change)
        self.add_money(effect.money_change)
        self.add_experience_points(effect.experience_change)
        for status_effect in effect.temporary_effects:
            self.add_status_effect(status_effect)

    def can_act(self) -> bool:
        """行動可能かどうか"""
        if (self.has_status_effect_type(StatusEffectType.PARALYSIS) or 
            self.has_status_effect_type(StatusEffectType.SLEEP)):
            return False
        return self.is_alive()
    
    def is_confused(self) -> bool:
        """混乱しているかどうか"""
        return self.has_status_effect_type(StatusEffectType.CONFUSION)
    
    def is_silenced(self) -> bool:
        """シーンしているかどうか"""
        return self.has_status_effect_type(StatusEffectType.SILENCE)