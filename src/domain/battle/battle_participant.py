from dataclasses import dataclass, field
from typing import Dict, List
from src.domain.battle.combat_entity import CombatEntity
from src.domain.battle.battle_enum import StatusEffectType, BuffType, ParticipantType
from src.domain.player.player import Player
from src.domain.monster.monster import Monster


@dataclass
class BattleParticipant:
    """戦闘参加者（戦闘中のみ存在）"""
    entity: CombatEntity  # Player or Monster
    entity_id: int  # PlayerまたはMonsterのID
    status_effects_remaining_duration: Dict[StatusEffectType, int] = field(default_factory=dict)
    buffs_remaining_duration: Dict[BuffType, int] = field(default_factory=dict)
    buffs_multiplier: Dict[BuffType, float] = field(default_factory=dict)
    
    @classmethod
    def create(cls, entity: CombatEntity, entity_id: int) -> "BattleParticipant":
        return cls(entity=entity, entity_id=entity_id)

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
    
    def get_buff_multiplier(self, buff_type: BuffType) -> float:
        """バフの倍率を取得"""
        return self.buffs_multiplier.get(buff_type, 1.0)

    def process_status_effects_on_turn_start(self):
        """状態異常を処理"""
        for effect_type, duration in self.status_effects_remaining_duration.items():
            if duration > 0:
                self.status_effects_remaining_duration[effect_type] -= 1
            elif duration < 0:
                raise ValueError(f"Duration must be greater than 0: {duration}")
    
    def process_status_effects_on_turn_end(self):
        """状態異常を処理"""
        to_remove = []
        for effect_type, duration in self.status_effects_remaining_duration.items():
            if duration == 0:
                to_remove.append(effect_type)
            elif duration < 0:
                raise ValueError(f"Duration must be greater than 0: {duration}")
        
        for effect_type in to_remove:
            self.status_effects_remaining_duration.pop(effect_type)
    
    def recover_status_effects(self, effect_type: StatusEffectType):
        """特定の状態異常を回復"""
        if effect_type in self.status_effects_remaining_duration:
            self.status_effects_remaining_duration.pop(effect_type)

    def process_buffs_on_turn_start(self):
        """バフを処理"""
        for buff_type, duration in self.buffs_remaining_duration.items():
            if duration > 0:
                self.buffs_remaining_duration[buff_type] -= 1
            elif duration < 0:
                raise ValueError(f"Duration must be greater than 0: {duration}")
    
    def process_buffs_on_turn_end(self):
        """バフを処理"""
        to_remove = []
        for buff_type, duration in self.buffs_remaining_duration.items():
            if duration == 0:
                to_remove.append(buff_type)
            elif duration < 0:
                raise ValueError(f"Duration must be greater than 0: {duration}")
        
        for buff_type in to_remove:
            self.buffs_remaining_duration.pop(buff_type)
            self.buffs_multiplier.pop(buff_type)