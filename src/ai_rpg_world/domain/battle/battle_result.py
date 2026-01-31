from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from ai_rpg_world.domain.battle.battle_enum import StatusEffectType, BuffType, ParticipantType
from ai_rpg_world.domain.battle.combat_state import CombatState


@dataclass(frozen=True)
class TurnStartResult:
    actor_id: int
    participant_type: ParticipantType
    can_act: bool
    messages: List[str] = field(default_factory=list)
    # 状態異常による自分へのダメージ
    damage: int = 0
    healing: int = 0
    # ターン開始時に期限切れになった状態異常・バフ
    status_effects_to_remove: List[StatusEffectType] = field(default_factory=list)
    buffs_to_remove: List[BuffType] = field(default_factory=list)
    
    def __post_init__(self):
        if self.damage < 0:
            raise ValueError("Damage must be non-negative")
        if self.healing < 0:
            raise ValueError("Healing must be non-negative")
    
    def apply_to_combat_state(self, combat_state: CombatState):
        if self.actor_id != combat_state.entity_id:
            raise ValueError("Actor ID does not match combat state")
        if self.participant_type != combat_state.participant_type:
            raise ValueError("Participant type does not match combat state")
        
        combat_state = combat_state.with_hp_damaged(self.damage)
        combat_state = combat_state.with_hp_healed(self.healing)
        for effect in self.status_effects_to_remove:
            combat_state = combat_state.without_status_effect(effect)
        for buff in self.buffs_to_remove:
            combat_state = combat_state.without_buff(buff)

        return combat_state


@dataclass(frozen=True)
class TurnEndResult:
    actor_id: int
    participant_type: ParticipantType
    messages: List[str] = field(default_factory=list)
    # 状態異常によるダメージ・回復
    damage: int = 0
    healing: int = 0
    # 期限切れになった状態異常・バフ
    status_effects_to_remove: List[StatusEffectType] = field(default_factory=list)
    buffs_to_remove: List[BuffType] = field(default_factory=list)
    
    def __post_init__(self):
        if self.damage < 0:
            raise ValueError("Damage must be non-negative")
        if self.healing < 0:
            raise ValueError("Healing must be non-negative")

    def apply_to_combat_state(self, combat_state: CombatState):
        if self.actor_id != combat_state.entity_id:
            raise ValueError("Actor ID does not match combat state")
        if self.participant_type != combat_state.participant_type:
            raise ValueError("Participant type does not match combat state")
        
        combat_state = combat_state.with_hp_damaged(self.damage)
        combat_state = combat_state.with_hp_healed(self.healing)
        for effect in self.status_effects_to_remove:
            combat_state = combat_state.without_status_effect(effect)
        for buff in self.buffs_to_remove:
            combat_state = combat_state.without_buff(buff)

        return combat_state

            
@dataclass(frozen=True)
class ActorStateChange:
    """アクション実行者の状態変更を表現"""
    actor_id: int
    participant_type: ParticipantType
    hp_change: int = 0  # 負の値はダメージ、正の値は回復
    mp_change: int = 0  # 負の値は消費、正の値は回復
    status_effects_to_add: List[Tuple[StatusEffectType, int]] = field(default_factory=list)  # (効果タイプ, 持続ターン数)
    status_effects_to_remove: List[StatusEffectType] = field(default_factory=list)
    buffs_to_add: List[Tuple[BuffType, float, int]] = field(default_factory=list)  # (バフタイプ, 倍率, 持続ターン数)
    buffs_to_remove: List[BuffType] = field(default_factory=list)
    is_defend: bool = False

    def __post_init__(self):
        pass
    
    def apply_to_combat_state(self, combat_state: CombatState):
        if self.actor_id != combat_state.entity_id:
            raise ValueError("Actor ID does not match combat state")
        if self.participant_type != combat_state.participant_type:
            raise ValueError("Participant type does not match combat state")

        # HP変更（負の値はダメージ、正の値は回復）
        if self.hp_change < 0:
            combat_state = combat_state.with_hp_damaged(abs(self.hp_change))
        elif self.hp_change > 0:
            combat_state = combat_state.with_hp_healed(self.hp_change)

        # MP変更（負の値は消費、正の値は回復）
        if self.mp_change < 0:
            combat_state = combat_state.with_mp_consumed(abs(self.mp_change))
        elif self.mp_change > 0:
            combat_state = combat_state.with_mp_healed(self.mp_change)

        for effect in self.status_effects_to_add:
            combat_state = combat_state.with_status_effect(effect[0], effect[1])
        for effect in self.status_effects_to_remove:
            combat_state = combat_state.without_status_effect(effect)
        for buff in self.buffs_to_add:
            combat_state = combat_state.with_buff(buff[0], buff[1], buff[2])
        for buff in self.buffs_to_remove:
            combat_state = combat_state.without_buff(buff)
        if self.is_defend:
            combat_state = combat_state.with_defend()
        else:
            combat_state = combat_state.without_defend()

        return combat_state


@dataclass(frozen=True)
class TargetStateChange:
    """ターゲットの状態変更を表現"""
    target_id: int
    participant_type: ParticipantType
    hp_change: int = 0  # 負の値はダメージ、正の値は回復
    mp_change: int = 0  # 負の値は消費、正の値は回復
    status_effects_to_add: List[Tuple[StatusEffectType, int]] = field(default_factory=list)
    status_effects_to_remove: List[StatusEffectType] = field(default_factory=list)
    buffs_to_add: List[Tuple[BuffType, float, int]] = field(default_factory=list)
    buffs_to_remove: List[BuffType] = field(default_factory=list)
    was_evaded: bool = False

    def __post_init__(self):
        pass
    
    def apply_to_combat_state(self, combat_state: CombatState):
        if self.target_id != combat_state.entity_id:
            raise ValueError("Target ID does not match combat state")
        if self.participant_type != combat_state.participant_type:
            raise ValueError("Participant type does not match combat state")

        # HP変更（負の値はダメージ、正の値は回復）
        if self.hp_change < 0:
            combat_state = combat_state.with_hp_damaged(abs(self.hp_change))
        elif self.hp_change > 0:
            combat_state = combat_state.with_hp_healed(self.hp_change)

        # MP変更（負の値は消費、正の値は回復）
        if self.mp_change < 0:
            combat_state = combat_state.with_mp_consumed(abs(self.mp_change))
        elif self.mp_change > 0:
            combat_state = combat_state.with_mp_healed(self.mp_change)

        for effect in self.status_effects_to_add:
            combat_state = combat_state.with_status_effect(effect[0], effect[1])
        for effect in self.status_effects_to_remove:
            combat_state = combat_state.without_status_effect(effect)
        for buff in self.buffs_to_add:
            combat_state = combat_state.with_buff(buff[0], buff[1], buff[2])
        for buff in self.buffs_to_remove:
            combat_state = combat_state.without_buff(buff)

        return combat_state


@dataclass(frozen=True)
class BattleActionMetadata:
    """アクションの補助情報（表示用、ログ用）"""
    critical_hits: List[bool] = field(default_factory=list)
    compatibility_multipliers: List[float] = field(default_factory=list)
    race_attack_multipliers: List[float] = field(default_factory=list)
    
    def __post_init__(self):
        if len(self.critical_hits) != len(self.compatibility_multipliers) or len(self.critical_hits) != len(self.race_attack_multipliers):
            raise ValueError("critical_hits, compatibility_multipliers, race_attack_multipliersの長さが一致していません")


@dataclass(frozen=True)
class BattleActionResult:
    success: bool
    messages: List[str] = field(default_factory=list)
    
    # 実行者の状態変更
    actor_state_change: ActorStateChange = field(default_factory=ActorStateChange)
    
    # ターゲットの状態変更
    target_state_changes: List[TargetStateChange] = field(default_factory=list)
    
    # 補助情報
    metadata: BattleActionMetadata = field(default_factory=BattleActionMetadata)
    
    # 失敗時の詳細
    failure_reason: Optional[str] = None

    @property
    def total_damage_dealt(self) -> int:
        """与えたダメージの合計"""
        return sum(abs(change.hp_change) for change in self.target_state_changes if change.hp_change < 0)
    
    @property
    def total_healing_dealt(self) -> int:
        """与えた回復の合計"""
        return sum(change.hp_change for change in self.target_state_changes if change.hp_change > 0)
    
    @classmethod
    def create_success(
        cls,
        messages: List[str],
        actor_state_change: ActorStateChange = None,
        target_state_changes: List[TargetStateChange] = None,
        metadata: BattleActionMetadata = None,
    ) -> "BattleActionResult":
        """成功時のBattleActionResultを作成"""
        return cls(
            success=True,
            messages=messages,
            actor_state_change=actor_state_change or ActorStateChange(actor_id=0, participant_type=ParticipantType.PLAYER),
            target_state_changes=target_state_changes or [],
            metadata=metadata or BattleActionMetadata(),
            failure_reason=None,
        )
    
    @classmethod
    def create_failure(
        cls,
        messages: List[str],
        failure_reason: str,
        actor_state_change: ActorStateChange = None,
    ) -> "BattleActionResult":
        """失敗時のBattleActionResultを作成"""
        return cls(
            success=False,
            messages=messages,
            actor_state_change=actor_state_change or ActorStateChange(actor_id=0, participant_type=ParticipantType.PLAYER),
            target_state_changes=[],
            metadata=BattleActionMetadata(),
            failure_reason=failure_reason,
        )