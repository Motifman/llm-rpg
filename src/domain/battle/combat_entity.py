from abc import ABC
from typing import List
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.monster.monster_enum import Race
from src.domain.battle.battle_enum import StatusEffectType, Element
from src.domain.battle.status_effect_result import StatusEffectResult


class CombatEntity(ABC):
    """戦闘エンティティの基底クラス - PlayerとMonsterの共通機能"""
    
    def __init__(
        self,
        name: str,
        race: Race,
        element: Element,
        current_spot_id: int,
        base_status: BaseStatus,
        dynamic_status: DynamicStatus,
    ):
        self._name = name
        self._race = race
        self._element = element
        self._current_spot_id = current_spot_id
        self._base_status = base_status
        self._dynamic_status = dynamic_status
    
    # ===== 基本プロパティ =====
    @property
    def name(self) -> str:
        """名前を取得"""
        return self._name
    
    @property
    def race(self) -> Race:
        """種族を取得"""
        return self._race
    
    @property
    def element(self) -> Element:
        """属性を取得"""
        return self._element
    
    @property
    def current_spot_id(self) -> int:
        """現在のスポットIDを取得"""
        return self._current_spot_id
    
    # ===== ステータスプロパティ =====
    @property
    def attack(self) -> int:
        """攻撃力を取得（基本実装：ベース + 状態異常ボーナス）"""
        base = self._base_status.attack
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.ATTACK_UP)
        return base + effect_bonus
    
    @property
    def defense(self) -> int:
        """防御力を取得（基本実装：ベース + 状態異常ボーナス）"""
        base = self._base_status.defense
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.DEFENSE_UP)
        return base + effect_bonus
    
    @property
    def speed(self) -> int:
        """素早さを取得（基本実装：ベース + 状態異常ボーナス）"""
        base = self._base_status.speed
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.SPEED_UP)
        return base + effect_bonus
    
    @property
    def hp(self) -> int:
        """HPを取得"""
        return self._dynamic_status.hp
    
    @property
    def mp(self) -> int:
        """MPを取得"""
        return self._dynamic_status.mp
    
    @property
    def max_hp(self) -> int:
        """最大HPを取得"""
        return self._dynamic_status.max_hp
    
    @property
    def max_mp(self) -> int:
        """最大MPを取得"""
        return self._dynamic_status.max_mp
    
    # ===== 戦闘関連メソッド =====
    def take_damage(self, damage: int):
        """ダメージを受ける"""
        assert damage > 0, "damage must be greater than 0"
        damage = max(0, damage - self.defense)
        self._dynamic_status.take_damage(damage)
    
    def heal(self, amount: int):
        """回復"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.heal(amount)
    
    def recover_mp(self, amount: int):
        """MP回復"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.recover_mp(amount)
    
    def consume_mp(self, amount: int):
        """MPを消費"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.consume_mp(amount)
    
    def can_consume_mp(self, amount: int) -> bool:
        """MPが足りるかどうか"""
        return self._dynamic_status.can_consume_mp(amount)
    
    def heal_status_effect(self, status_effect_type: StatusEffectType):
        """特定の状態異常を回復"""
        self._dynamic_status.remove_status_effect_by_type(status_effect_type)
    
    def add_status_effect(self, status_effect_type: StatusEffectType, duration: int, value: int):
        """状態異常を追加"""
        self._dynamic_status.add_status_effect(status_effect_type, duration, value)
    
    def has_status_effect(self, status_effect_type: StatusEffectType) -> bool:
        """特定の状態異常を持っているかどうか"""
        return self._dynamic_status.has_status_effect_type(status_effect_type)
    
    def is_alive(self) -> bool:
        """生存しているかどうか"""
        return self._dynamic_status.is_alive()
    
    def is_defending(self) -> bool:
        """防御状態かどうか"""
        return self._dynamic_status.defending
    
    def defend(self):
        """防御状態にする"""
        self._dynamic_status.defend()
    
    def un_defend(self):
        """防御解除"""
        self._dynamic_status.un_defend()

    def process_status_effects_on_turn_start(self) -> List[StatusEffectResult]:
        """ターン開始時に実行し、該当する状態異常のメッセージを返す"""
        results: List[StatusEffectResult] = []
        if self.has_status_effect(StatusEffectType.PARALYSIS):
            results.append(StatusEffectResult(status_effect_type=StatusEffectType.PARALYSIS, message=f"{self.name}は麻痺で動けない！"))
        if self.has_status_effect(StatusEffectType.SLEEP):
            results.append(StatusEffectResult(status_effect_type=StatusEffectType.SLEEP, message=f"{self.name}は眠っていて行動できない…"))
        if self.has_status_effect(StatusEffectType.CONFUSION):
            damage = max(1, self.attack // 2)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectResult(status_effect_type=StatusEffectType.CONFUSION, message=f"{self.name}は混乱して自分を攻撃！ {damage}のダメージ", damage_dealt=damage))
        return results

    def process_status_effects_on_turn_end(self) -> List[StatusEffectResult]:
        """ターン終了時に実行し、該当する状態異常のメッセージを返す"""
        results: List[StatusEffectResult] = []
        if self.has_status_effect(StatusEffectType.POISON):
            damage = self._dynamic_status.get_effect_damage(StatusEffectType.POISON)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectResult(status_effect_type=StatusEffectType.POISON, message=f"{self.name}は毒により{damage}のダメージを受けた", damage_dealt=damage))
        if self.has_status_effect(StatusEffectType.BURN):
            damage = self._dynamic_status.get_effect_damage(StatusEffectType.BURN)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectResult(status_effect_type=StatusEffectType.BURN, message=f"{self.name}は火傷により{damage}のダメージを受けた", damage_dealt=damage))
        if self.has_status_effect(StatusEffectType.BLESSING):
            bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.BLESSING)
            if bonus > 0:
                self._dynamic_status.heal(bonus)
                results.append(StatusEffectResult(status_effect_type=StatusEffectType.BLESSING, message=f"{self.name}は加護により{bonus}回復した", healing_done=bonus))
        return results

    def progress_status_effects_on_turn_end(self) -> None:
        """ターン終了時に呼び出して、状態異常のターンを進める"""
        self._dynamic_status.decrease_status_effect_duration()
    
    def can_act(self) -> bool:
        """行動可能かどうか"""
        if self.has_status_effect(StatusEffectType.PARALYSIS):
            return False
        if self.has_status_effect(StatusEffectType.SLEEP):
            return False
        return self.is_alive() and not self.is_defending()
    
    def can_magic(self) -> bool:
        """魔法攻撃可能かどうか"""
        if self.has_status_effect(StatusEffectType.SILENCE):
            return False
        return self.is_alive() and not self.is_defending()
    
    # ===== スポット移動 =====
    def set_current_spot_id(self, spot_id: int):
        """現在のスポットIDを設定"""
        self._current_spot_id = spot_id
