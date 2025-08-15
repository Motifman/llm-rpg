from typing import Dict, TYPE_CHECKING, Optional
from domain.player.enum import StatusEffectType
from domain.player.status_effect import StatusEffect


class DynamicStatus:
    """動的なステータスの管理クラス"""
    
    def __init__(
        self,
        hp: int,
        mp: int,
        max_hp: int,
        max_mp: int,
        exp: int = 0,
        level: int = 1,
        gold: int = 0,
        status_effects: Optional[Dict[StatusEffectType, StatusEffect]] = None,
        defending: bool = False,
    ):
        assert hp > 0, "hp must be greater than 0"
        assert mp > 0, "mp must be greater than 0"
        assert max_hp > 0, "max_hp must be greater than 0"
        assert max_mp > 0, "max_mp must be greater than 0"
        assert exp >= 0, "exp must be greater than or equal to 0"
        assert level >= 1, "level must be greater than or equal to 1"
        assert gold >= 0, "gold must be greater than or equal to 0"

        self._hp = hp
        self._mp = mp
        self._max_hp = max_hp
        self._max_mp = max_mp
        self._exp = exp
        self._level = level
        self._gold = gold
        self._status_effects = {} if status_effects is None else dict(status_effects)
        self._defending = defending
    
    @property
    def hp(self) -> int:
        """HPを取得"""
        return self._hp
    
    @property
    def mp(self) -> int:
        """MPを取得"""
        return self._mp
    
    @property
    def max_hp(self) -> int:
        """最大HPを取得"""
        return self._max_hp
    
    @property
    def max_mp(self) -> int:
        """最大MPを取得"""
        return self._max_mp
    
    @property
    def exp(self) -> int:
        """経験値を取得"""
        return self._exp
    
    @property
    def level(self) -> int:
        """レベルを取得"""
        return self._level
    
    @property
    def status_effects(self) -> Dict[StatusEffectType, StatusEffect]:
        """状態異常を取得"""
        return self._status_effects
    
    @property
    def gold(self) -> int:
        """所持金を取得"""
        return self._gold
    
    @property
    def defending(self) -> bool:
        """防御状態かどうか"""
        return self._defending

    # == ビジネスロジックの実装 ==
    def take_damage(self, damage: int):
        """ダメージを受ける"""
        self._hp = max(0, self._hp - damage)
    
    def heal(self, amount: int):
        """回復"""
        self._hp = min(self._hp + amount, self._max_hp)

    def is_alive(self) -> bool:
        """生存しているかどうか"""
        return self._hp > 0
    
    def receive_gold(self, amount: int):
        """所持金を追加"""
        self._gold = max(0, self._gold + amount)
    
    def pay_gold(self, amount: int):
        """所持金を支払う"""
        self._gold = max(0, self._gold - amount)
    
    def can_pay_gold(self, amount: int) -> bool:
        """所持金が足りるかどうか"""
        return self._gold >= amount
    
    def receive_exp(self, amount: int):
        """経験値を追加"""
        self._exp = max(0, self._exp + amount)
    
    def pay_exp(self, amount: int):
        """経験値を支払う"""
        self._exp = max(0, self._exp - amount)
    
    def can_pay_exp(self, amount: int) -> bool:
        """経験値が足りるかどうか"""
        return self._exp >= amount
    
    def level_up(self):
        """レベルアップ"""
        pass
    
    def defend(self):
        """防御"""
        self._defending = True
    
    def un_defend(self):
        """防御解除"""
        self._defending = False

    def add_status_effect(self, status_effect_type: StatusEffectType, duration: int, value: int):
        """状態異常を追加"""
        self._status_effects[status_effect_type] = StatusEffect(status_effect_type, duration, value)
    
    def remove_status_effect_by_type(self, status_effect_type: StatusEffectType):
        """状態異常を削除"""
        self._status_effects.pop(status_effect_type, None)
    
    def has_status_effect_type(self, status_effect_type: StatusEffectType) -> bool:
        """特定の状態異常が存在するかどうか"""
        return status_effect_type in self._status_effects
    
    def get_effect_bonus(self, status_effect_type: StatusEffectType) -> int:
        """状態異常によるボーナスを取得"""
        status_effect = self._status_effects.get(status_effect_type)
        return status_effect.value if status_effect else 0
    
    def get_effect_damage(self, status_effect_type: StatusEffectType) -> int:
        """状態異常によるダメージを取得"""
        return self.get_effect_bonus(status_effect_type)
    
    def decrease_status_effect_duration(self):
        """状態異常の残りターン数を減らす"""
        to_remove: list[StatusEffectType] = []
        for effect in self._status_effects.values():
            effect.duration -= 1
            if effect.duration <= 0:
                to_remove.append(effect.effect)
        for effect_type in to_remove:
            self.remove_status_effect_by_type(effect_type)