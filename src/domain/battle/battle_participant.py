import random
from dataclasses import dataclass, field
from typing import Dict, List, Any
from src.domain.battle.combat_entity import CombatEntity
from src.domain.battle.battle_enum import StatusEffectType, BuffType, ParticipantType, ActionType
from src.domain.battle.battle_action import BattleAction
from src.domain.battle.constant import (
    WAKE_RATE, CONFUSION_DAMAGE_MULTIPLIER, POISON_DAMAGE_RATE, BURN_DAMAGE_AMOUNT, BLESSING_HEAL_AMOUNT, IF_DEFENDER_DEFENDING_MULTIPLIER,
)
from src.domain.battle.battle_result import TurnStartResult, TurnEndResult


@dataclass
class BattleParticipant:
    """戦闘参加者（戦闘中のみ存在）"""
    entity: CombatEntity  # Player or Monster
    entity_id: int  # PlayerまたはMonsterのID
    participant_type: ParticipantType
    status_effects_remaining_duration: Dict[StatusEffectType, int] = field(default_factory=dict)
    buffs_remaining_duration: Dict[BuffType, int] = field(default_factory=dict)
    buffs_multiplier: Dict[BuffType, float] = field(default_factory=dict)
    
    def __post_init__(self):
        base_status = self.entity.calculate_status()
        self.attack = base_status.attack
        self.defense = base_status.defense
        self.speed = base_status.speed
        self.critical_rate = base_status.critical_rate
        self.evasion_rate = base_status.evasion_rate
    
    @classmethod
    def create(cls, entity: CombatEntity, entity_id: int, participant_type: ParticipantType) -> "BattleParticipant":
        return cls(entity=entity, entity_id=entity_id, participant_type=participant_type)

    def add_status_effect(self, effect_type: StatusEffectType, duration: int):
        """状態異常を追加"""
        if duration <= 0:
            raise ValueError(f"Duration must be greater than 0: {duration}")
        self.status_effects_remaining_duration[effect_type] = duration
    
    def add_buff(self, buff_type: BuffType, duration: int, multiplier: float):
        """バフを追加"""
        if duration <= 0:
            raise ValueError(f"Duration must be greater than 0: {duration}")
        if multiplier <= 0:
            raise ValueError(f"Multiplier must be greater than 0: {multiplier}")
        self.buffs_remaining_duration[buff_type] = duration
        self.buffs_multiplier[buff_type] = multiplier
    
    def get_status_effects(self) -> List[StatusEffectType]:
        """状態異常を取得"""
        return list(self.status_effects_remaining_duration.keys())
    
    def has_status_effect(self, effect_type: StatusEffectType) -> bool:
        """状態異常があるかどうか"""
        return effect_type in self.status_effects_remaining_duration
    
    def get_status_effect_remaining_duration(self, effect_type: StatusEffectType) -> int:
        """状態異常の残りターン数を取得"""
        return self.status_effects_remaining_duration.get(effect_type, 0)
    
    def _get_buff_multiplier(self, buff_type: BuffType) -> float:
        """バフの倍率を取得"""
        return self.buffs_multiplier.get(buff_type, 1.0)

    def recover_status_effects(self, effect_type: StatusEffectType):
        """特定の状態異常を回復"""
        if effect_type in self.status_effects_remaining_duration:
            self.status_effects_remaining_duration.pop(effect_type)

    def _process_status_effects_on_turn_start(self) -> TurnStartResult:
        """ターン開始時に状態異常を処理"""
        to_remove = []
        for effect_type, duration in self.status_effects_remaining_duration.items():
            if duration == 0:
                to_remove.append(effect_type)
            elif duration < 0:
                raise ValueError(f"Duration must be greater than 0: {duration}")
        
        for effect_type in to_remove:
            self.status_effects_remaining_duration.pop(effect_type)
        return TurnStartResult(
            can_act=True,
            expired_status_effects=to_remove,
        )

    def _process_buffs_on_turn_start(self) -> TurnStartResult:
        """ターン開始時にバフを処理"""
        to_remove = []
        for buff_type, duration in self.buffs_remaining_duration.items():
            if duration == 0:
                to_remove.append(buff_type)
            elif duration < 0:
                raise ValueError(f"Duration must be greater than 0: {duration}")
        
        for buff_type in to_remove:
            self.buffs_remaining_duration.pop(buff_type)
            self.buffs_multiplier.pop(buff_type)
        return TurnStartResult(
            can_act=True,
            expired_buffs=to_remove,
        )
    
    def _process_sleep(self) -> TurnStartResult:
        """眠りの処理"""
        can_act = True
        messages = []
        expired_status_effects = []

        if self.has_status_effect(StatusEffectType.SLEEP):
            if random.random() < WAKE_RATE:
                self.recover_status_effects(StatusEffectType.SLEEP)
                messages.append(f"{self.entity.name}は眠りから覚めた！")
                expired_status_effects.append(StatusEffectType.SLEEP)
            else:
                messages.append(f"{self.entity.name}は眠っているようだ...")
                can_act = False

        return TurnStartResult(
            can_act=can_act,
            messages=messages,
            expired_status_effects=expired_status_effects,
        )
    
    def _process_paralysis(self) -> TurnStartResult:
        """麻痺の処理"""
        can_act = True
        messages = []
        expired_status_effects = []

        if self.has_status_effect(StatusEffectType.PARALYSIS):
            messages.append(f"{self.entity.name}は体が麻痺して動けないようだ...")
            can_act = False
            expired_status_effects.append(StatusEffectType.PARALYSIS)

        return TurnStartResult(
            can_act=can_act,
            messages=messages,
            expired_status_effects=expired_status_effects,
        )
    
    def _process_confusion(self) -> TurnStartResult:
        """混乱の処理"""
        can_act = True
        messages = []
        damage = 0

        if self.has_status_effect(StatusEffectType.CONFUSION):
            damage = int(self.attack * CONFUSION_DAMAGE_MULTIPLIER)
            messages.append(f"{self.entity.name}は混乱により自分に{damage}のダメージを与えた！")
            can_act = False

        return TurnStartResult(
            can_act=can_act,
            messages=messages,
            damage=damage,
        )
    
    def _process_curse_on_turn_start(self) -> TurnStartResult:
        """呪いの処理"""
        can_act = True
        messages = []
        damage = 0

        if self.has_status_effect(StatusEffectType.CURSE) and self.get_status_effect_remaining_duration(StatusEffectType.CURSE) == 0:
            damage = self.entity.hp
            messages.append(f"{self.entity.name}は呪いに体を蝕まれて死んでしまった...")

        return TurnStartResult(
            can_act=can_act,
            messages=messages,
            damage=damage,
        )
    
    def process_on_turn_start(self) -> TurnStartResult:
        """ターン開始時の処理"""
        results = [
            self._process_sleep(),
            self._process_paralysis(),
            self._process_confusion(),
            self._process_curse_on_turn_start(),
            self._process_status_effects_on_turn_start(),
            self._process_buffs_on_turn_start(),
        ]
        
        can_act = all(result.can_act for result in results)
        messages = [result.messages for result in results]
        damage = sum(result.damage for result in results)
        expired_status_effects = set(result.expired_status_effects for result in results)
        expired_buffs = set(result.expired_buffs for result in results)
        
        return TurnStartResult(
            can_act=can_act,
            messages=messages,
            damage=damage,
            expired_status_effects=expired_status_effects,
            expired_buffs=expired_buffs,
        )
            
    def _process_buffs_on_turn_end(self):
        """ターン終了時にバフを処理"""
        for buff_type, duration in self.buffs_remaining_duration.items():
            if duration > 0:
                self.buffs_remaining_duration[buff_type] -= 1
            elif duration < 0:
                raise ValueError(f"Duration must be greater than 0: {duration}")

    def _process_status_effects_on_turn_end(self):
        """ターン終了時に状態異常を処理"""
        for effect_type, duration in self.status_effects_remaining_duration.items():
            if duration > 0:
                self.status_effects_remaining_duration[effect_type] -= 1
            elif duration < 0:
                raise ValueError(f"Duration must be greater than 0: {duration}")
    
    def _process_poison(self) -> TurnEndResult:
        """毒の処理"""
        messages = []
        damage = 0
        is_participant_defeated = False

        if self.has_status_effect(StatusEffectType.POISON):
            damage = int(self.entity.hp * POISON_DAMAGE_RATE)
            messages.append(f"{self.entity.name}は毒により{damage}のダメージを受けた！")
            is_participant_defeated = not self.entity.is_alive()

        return TurnEndResult(
            messages=messages,
            damage=damage,
            is_participant_defeated=is_participant_defeated,
        )

    def _process_burn(self) -> TurnEndResult:
        """やけどの処理"""
        messages = []
        damage = 0
        is_participant_defeated = False

        if self.has_status_effect(StatusEffectType.BURN):
            damage = BURN_DAMAGE_AMOUNT
            messages.append(f"{self.entity.name}はやけどにより{damage}のダメージを受けた！")
            is_participant_defeated = not self.entity.is_alive()

        return TurnEndResult(
            messages=messages,
            damage=damage,
            is_participant_defeated=is_participant_defeated,
        )

    def _process_blessing(self) -> TurnEndResult:
        """加護の処理"""
        messages = []
        healing = 0

        if self.has_status_effect(StatusEffectType.BLESSING):
            healing = BLESSING_HEAL_AMOUNT
            self.entity.heal(healing)
            messages.append(f"{self.entity.name}は加護によりHPが{healing}回復した！")

        return TurnEndResult(
            messages=messages,
            healing=healing,
        )
    
    def _process_curse_on_turn_end(self) -> TurnEndResult:
        """呪いの処理"""
        messages = []
        
        if self.has_status_effect(StatusEffectType.CURSE):
            duration = self.get_status_effect_remaining_duration(StatusEffectType.CURSE)
            messages.append(f"{self.entity.name}は呪いに体を蝕まれている... 残り{duration}ターン...")

        return TurnEndResult(
            messages=messages,
        )
    
    def process_on_turn_end(self) -> TurnEndResult:
        """ターン終了時の処理"""
        self._process_status_effects_on_turn_end()
        self._process_buffs_on_turn_end()
        
        results = [
            self._process_poison(),
            self._process_burn(),
            self._process_blessing(),
            self._process_curse_on_turn_end(),
        ]
        
        messages = [result.messages for result in results]
        damage = sum(result.damage for result in results)
        healing = sum(result.healing for result in results)
        expired_status_effects = set(result.expired_status_effects for result in results)
        expired_buffs = set(result.expired_buffs for result in results)

        return TurnEndResult(
            messages=messages,
            damage=damage,
            healing=healing,
            expired_status_effects=expired_status_effects,
            expired_buffs=expired_buffs,
        )
    
    def can_magic_action(self, action: BattleAction) -> bool:
        """行動を実行できるかどうか"""
        if self.has_status_effect(StatusEffectType.SILENCE) and action.action_type == ActionType.MAGIC:
            return False
        return True
    
    def can_consume_mp(self, action: BattleAction) -> bool:
        """MPが足りるかどうか"""
        if action.mp_cost is not None and not self.entity.can_consume_mp(action.mp_cost):
            return False
        return True
    
    def can_consume_hp(self, action: BattleAction) -> bool:
        """HPが足りるかどうか"""
        if action.hp_cost is not None and not self.entity.can_consume_hp(action.hp_cost):
            return False
        return True
    
    def can_execute_action(self, action: BattleAction) -> bool:
        """行動を実行できるかどうか"""
        if action.action_type == ActionType.MAGIC:
            return self.can_magic_action(action)
        return self.can_consume_mp(action) and self.can_consume_hp(action)

    def get_available_actions(self) -> List[BattleAction]:
        """実行可能な行動を取得"""
        return [action for action in self.entity.actions if self.can_execute_action(action)]

    def calculate_base_damage(self, action: BattleAction) -> int:
        """ダメージ計算"""
        # 基本ダメージ計算
        damage = self.attack
        damage *= action.damage_multiplier
        
        # バフチェック
        multiplier = self._get_buff_multiplier(BuffType.ATTACK)
        damage *= multiplier

        return int(damage)

    def calculate_defense(self) -> int:
        """防御力計算"""
        defense = self.defense
        if self.entity.is_defending():
            defense *= IF_DEFENDER_DEFENDING_MULTIPLIER
        
        # バフチェック
        multiplier = self._get_buff_multiplier(BuffType.DEFENSE)
        defense *= multiplier

        return int(defense)

    def get_entity_stats(self) -> Dict[str, Any]:
        """エンティティの統計情報を取得"""
        return {
            "entity_id": self.entity.entity_id,
            "name": self.entity.name,
            "hp": self.entity.hp,
            "max_hp": self.entity.max_hp,
            "mp": self.entity.mp,
            "max_mp": self.entity.max_mp,
            "attack": self.attack,
            "defense": self.defense,
            "speed": self.speed,
            "level": self.entity.level,
        }