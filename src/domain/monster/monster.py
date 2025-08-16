
from typing import List
from src.domain.monster.monster_enum import Race
from src.domain.monster.drop_reward import DropReward
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.battle.battle_enum import StatusEffectType, Element
from src.domain.battle.battle_action import BattleAction
from src.domain.battle.status_effect_result import StatusEffectResult


class Monster:
    def __init__(
        self,
        monster_instance_id: int,
        monster_type_id: int,
        name: str,
        description: str,
        race: Race,
        element: Element,
        current_spot_id: int,
        base_status: BaseStatus,
        dynamic_status: DynamicStatus,
        available_actions: List[BattleAction],
        drop_reward: DropReward
    ):
        self._monster_instance_id = monster_instance_id
        self._monster_type_id = monster_type_id
        self._name = name
        self._description = description
        self._race = race
        self._element = element
        self._current_spot_id = current_spot_id
        self._base_status = base_status
        self._dynamic_status = dynamic_status
        self._available_actions = available_actions
        self._drop_reward = drop_reward
    
    @property
    def monster_instance_id(self) -> int:
        return self._monster_instance_id
    
    @property
    def monster_type_id(self) -> int:
        return self._monster_type_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def race(self) -> Race:
        return self._race
    
    @property
    def element(self) -> Element:
        return self._element
    
    @property
    def current_spot_id(self) -> int:
        return self._current_spot_id

    @property
    def attack(self) -> int:
        base = self._base_status.attack
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.ATTACK_UP)
        return base + effect_bonus
    
    @property
    def defense(self) -> int:
        base = self._base_status.defense
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.DEFENSE_UP)
        return base + effect_bonus
    
    @property
    def speed(self) -> int:
        base = self._base_status.speed
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.SPEED_UP)
        return base + effect_bonus

    @property
    def hp(self) -> int:
        return self._dynamic_status.hp
    
    @property
    def mp(self) -> int:
        return self._dynamic_status.mp

    @property
    def max_hp(self) -> int:
        return self._dynamic_status.max_hp
    
    @property
    def max_mp(self) -> int:
        return self._dynamic_status.max_mp

    # ===== ビジネスロジックの実装 =====
    # ===== 戦闘関連 =====
    def take_damage(self, damage: int):
        damage = max(0, damage - self.defense)
        self._dynamic_status.take_damage(damage)
    
    def heal(self, amount: int):
        self._dynamic_status.heal(amount)
    
    def heal_status_effect(self, status_effect_type: StatusEffectType):
        self._dynamic_status.remove_status_effect_by_type(status_effect_type)
    
    def add_status_effect(self, status_effect_type: StatusEffectType, duration: int, value: int):
        self._dynamic_status.add_status_effect(status_effect_type, duration, value)
    
    def has_status_effect(self, status_effect_type: StatusEffectType) -> bool:
        return self._dynamic_status.has_status_effect_type(status_effect_type)
    
    def is_alive(self) -> bool:
        return self._dynamic_status.is_alive()
    
    def is_defending(self) -> bool:
        return self._dynamic_status.defending
    
    def defend(self):
        self._dynamic_status.defend()
    
    def un_defend(self):
        self._dynamic_status.un_defend()

    def process_status_effects_on_turn_start(self) -> List[StatusEffectResult]:
        """ターン開始時に実行し、該当する状態異常のメッセージを返す"""
        results: List[StatusEffectResult] = []
        if self.has_status_effect(StatusEffectType.PARALYSIS):
            results.append(StatusEffectResult(StatusEffectType.PARALYSIS, f"{self.name}は麻痺で動けない！"))
        if self.has_status_effect(StatusEffectType.SLEEP):
            results.append(StatusEffectResult(StatusEffectType.SLEEP, f"{self.name}は眠っていて行動できない…"))
        if self.has_status_effect(StatusEffectType.CONFUSION):
            damage = max(1, self.attack // 2)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectResult(StatusEffectType.CONFUSION, f"{self.name}は混乱して自分を攻撃！ {damage}のダメージ"), damage_dealt=damage)
        return results

    def process_status_effects_on_turn_end(self) -> List[StatusEffectResult]:
        """ターン終了時に実行し、該当する状態異常のメッセージを返す"""
        results: List[StatusEffectResult] = []
        if self.has_status_effect(StatusEffectType.POISON):
            damage = self._dynamic_status.get_effect_damage(StatusEffectType.POISON)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectResult(StatusEffectType.POISON, f"{self.name}は毒により{damage}のダメージを受けた"), damage_dealt=damage)
        if self.has_status_effect(StatusEffectType.BURN):
            damage = self._dynamic_status.get_effect_damage(StatusEffectType.BURN)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectResult(StatusEffectType.BURN, f"{self.name}は火傷により{damage}のダメージを受けた"), damage_dealt=damage)
        if self.has_status_effect(StatusEffectType.BLESSING):
            bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.BLESSING)
            if bonus > 0:
                self._dynamic_status.heal(bonus)
                results.append(StatusEffectResult(StatusEffectType.BLESSING, f"{self.name}は加護により{bonus}回復した"), healing_done=bonus)
        return results

    def progress_status_effects_on_turn_end(self) -> None:
        """ターン終了時に呼び出して、状態異常のターンを進める"""
        self._dynamic_status.decrease_status_effect_duration()
    
    def can_act(self) -> bool:
        if self.has_status_effect(StatusEffectType.PARALYSIS):
            return False
        if self.has_status_effect(StatusEffectType.SLEEP):
            return False
        return self.is_alive() and not self.is_defending()
    
    def can_magic(self) -> bool:
        if self.has_status_effect(StatusEffectType.SILENCE):
            return False
        return self.is_alive() and not self.is_defending()
    
    def get_drop_reward(self) -> DropReward:
        return self._drop_reward
    
    def get_available_actions(self) -> List[BattleAction]:
        return self._available_actions
    
    # ===== ステータス表示 =====
    def get_full_status_display(self) -> str:
        lines = [f"=== {self.name} ==="]
        lines.append(f"HP: {self.hp}/{self.max_hp}")
        lines.append(f"MP: {self.mp}/{self.max_mp}")
        lines.append("")
        lines.append("=== ステータス ===")
        lines.append(f"攻撃力: {self.attack} (ベース:{self._base_status.attack} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.ATTACK_UP)})")
        lines.append(f"防御力: {self.defense} (ベース:{self._base_status.defense} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.DEFENSE_UP)})")
        lines.append(f"素早さ: {self.speed} (ベース:{self._base_status.speed} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.SPEED_UP)})")
        lines.append("")
        
        return "\n".join(lines)