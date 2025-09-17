from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, TYPE_CHECKING
from src.domain.battle.battle_enum import StatusEffectType, Element, BuffType, Race, ActionType, TargetSelectionMethod
from src.domain.battle.battle_result import BattleActionResult
from typing import List
from abc import abstractmethod, ABC
from src.domain.battle.battle_result import ActorStateChange, TargetStateChange, BattleActionMetadata

if TYPE_CHECKING:
    from src.domain.battle.battle_service import BattleLogicService
    from src.domain.battle.combat_state import CombatState




@dataclass(frozen=True)
class BattleAction(ABC):
    """戦闘行動の基底クラス"""
    action_id: int
    name: str
    description: str
    action_type: ActionType
    target_selection_method: TargetSelectionMethod
    mp_cost: Optional[int] = None
    hp_cost: Optional[int] = None
    
    def execute(self, actor: "CombatState", specified_targets: Optional[List["CombatState"]], context: "BattleLogicService", all_participants: List["CombatState"]) -> BattleActionResult:
        """実行のメイン処理"""
        # 1. ターゲット選択
        targets = context.target_resolver.resolve_targets(actor, self, specified_targets, all_participants)
        
        # 2. 事前チェック
        context.action_validator.validate_action(actor, self)
        
        # 3. リソース消費
        resource_result = context.resource_consumer.consume_resource(actor, self)
        
        # 4. アクション固有の処理
        result = self._execute_core(actor, targets, context, resource_result.messages)
        return result
    
    @abstractmethod
    def _execute_core(self, actor: "CombatState", targets: List["CombatState"],
                     context: "BattleLogicService", base_messages: List[str]) -> BattleActionResult:
        """アクション固有の実行ロジック（サブクラスで実装）"""
        pass


@dataclass(frozen=True)
class HealAction(BattleAction):
    """回復系のアクション"""
    heal_hp_amount: Optional[int] = None
    heal_mp_amount: Optional[int] = None
    
    recovered_status_effects: Optional[List[StatusEffectType]] = None
    recovered_debuffs: Optional[List[BuffType]] = None
    
    def __post_init__(self):
        if self.heal_hp_amount is None and self.heal_mp_amount is None:
            raise ValueError("At least one of heal_hp_amount or heal_mp_amount must be specified")
        if self.heal_hp_amount is not None and self.heal_hp_amount <= 0:
            raise ValueError("heal_hp_amount must be positive value")
        if self.heal_mp_amount is not None and self.heal_mp_amount <= 0:
            raise ValueError("heal_mp_amount must be positive value")
        if self.hp_cost is not None and self.hp_cost < 0:
            raise ValueError("hp_cost must be non-negative")
        if self.mp_cost is not None and self.mp_cost < 0:
            raise ValueError("mp_cost must be non-negative")
    
    def _execute_core(self, actor: "CombatState", targets: List["CombatState"], context: "BattleLogicService", base_messages: List[str]) -> BattleActionResult:
        healing_hp_amount = self.heal_hp_amount or 0
        healing_mp_amount = self.heal_mp_amount or 0

        actor_state_change = ActorStateChange(actor_id=actor.entity_id, participant_type=actor.participant_type, mp_change=-(self.mp_cost or 0), hp_change=-(self.hp_cost or 0))
        target_state_changes = [
            TargetStateChange(
                target_id=target.entity_id,
                participant_type=target.participant_type,
                hp_change=healing_hp_amount,
                mp_change=healing_mp_amount,
                status_effects_to_remove=self.recovered_status_effects,
                buffs_to_remove=self.recovered_debuffs,
            )
            for target in targets
        ]
        return BattleActionResult.create_success(
            messages=base_messages,
            actor_state_change=actor_state_change,
            target_state_changes=target_state_changes,
        )


@dataclass(frozen=True)
class StatusEffectInfo:
    """状態異常の情報"""
    effect_type: StatusEffectType
    apply_rate: float
    duration: int

    def __post_init__(self):
        if self.apply_rate < 0 or self.apply_rate > 1.0:
            raise ValueError(f"apply_rate must be between 0 and 1. apply_rate: {self.apply_rate}")
        if self.duration <= 0:
            raise ValueError(f"duration must be positive. duration: {self.duration}")


@dataclass(frozen=True)
class BuffInfo:
    """バフの情報"""
    buff_type: BuffType
    apply_rate: float
    multiplier: float
    duration: int

    def __post_init__(self):
        if self.apply_rate < 0 or self.apply_rate > 1.0:
            raise ValueError(f"apply_rate must be between 0 and 1. apply_rate: {self.apply_rate}")
        if self.multiplier <= 0:
            raise ValueError(f"multiplier must be positive. multiplier: {self.multiplier}")
        if self.duration <= 0:
            raise ValueError(f"duration must be positive. duration: {self.duration}")


@dataclass(frozen=True)
class AttackAction(BattleAction):
    """攻撃系のアクション"""
    damage_multiplier: float = 1.0
    element: Optional[Element] = None
    
    status_effect_infos: List[StatusEffectInfo] = field(default_factory=list)
    buff_infos: List[BuffInfo] = field(default_factory=list)
    
    race_attack_multiplier: Dict[Race, float] = field(default_factory=dict)

    hit_rate: Optional[float] = None
    
    def __post_init__(self):
        if self.hit_rate is not None and (self.hit_rate < 0 or self.hit_rate > 1.0):
            raise ValueError(f"hit_rate must be between 0 and 1. hit_rate: {self.hit_rate}")
        if self.mp_cost is not None and self.mp_cost < 0:
            raise ValueError(f"mp_cost must be non-negative. mp_cost: {self.mp_cost}")
        if self.hp_cost is not None and self.hp_cost < 0:
            raise ValueError(f"hp_cost must be non-negative. hp_cost: {self.hp_cost}")
        if self.damage_multiplier < 0:
            raise ValueError(f"damage_multiplier must be non-negative. damage_multiplier: {self.damage_multiplier}")

    def _execute_core(self, actor: "CombatState", targets: List["CombatState"], context: "BattleLogicService", base_messages: List[str]) -> BattleActionResult:
        hit_result = context.hit_resolver.resolve_hits(actor, targets, self)
        
        if hit_result.missed or len(hit_result.evaded_targets) == len(targets):
            return BattleActionResult.create_failure(
                messages=base_messages + ["攻撃が外れた！"],
                failure_reason="missed",
                actor_state_change=ActorStateChange(
                    actor_id=actor.entity_id,
                    participant_type=actor.participant_type,
                    mp_change=-(self.mp_cost or 0),
                    hp_change=-(self.hp_cost or 0)
                )
            )
        
        target_state_changes = []
        all_messages = base_messages.copy()
        damage_results = []

        for defender in targets:
            if (defender.entity_id, defender.participant_type) in hit_result.evaded_targets:
                all_messages.append(f"{defender.name}は攻撃を回避した！")
                target_state_changes.append(TargetStateChange(target_id=defender.entity_id, participant_type=defender.participant_type))
                continue

            # ダメージ計算
            damage_result = context.damage_calculator.calculate_damage(actor, defender, self)
            damage_results.append(damage_result)

            # 効果適用
            effect_result = context.effect_applier.apply_effects(defender, self)

            # 状態変更を作成
            target_state_changes.append(TargetStateChange(
                target_id=defender.entity_id,
                participant_type=defender.participant_type,
                hp_change=damage_result.damage,
                status_effects_to_add=effect_result.status_effects_to_add,
                buffs_to_add=effect_result.buffs_to_add,
            ))

            # メッセージ追加
            all_messages.extend(effect_result.messages)
            all_messages.append(f"{actor.name}は{defender.name}に{damage_result.damage}のダメージを与えた！{'クリティカル！' if damage_result.is_critical else ''}")

        return BattleActionResult.create_success(
            messages=all_messages,
            actor_state_change=ActorStateChange(
                actor_id=actor.entity_id,
                participant_type=actor.participant_type,
                mp_change=-(self.mp_cost or 0),
                hp_change=-(self.hp_cost or 0)
            ),
            target_state_changes=target_state_changes,
            metadata=BattleActionMetadata(
                critical_hits=[r.is_critical for r in damage_results],
                compatibility_multipliers=[r.compatibility_multiplier for r in damage_results],
                race_attack_multipliers=[r.race_attack_multiplier for r in damage_results]
            )
        )


@dataclass(frozen=True)
class StatusEffectApplyAction(BattleAction):
    """状態異常付与系のアクション"""
    status_effect_rate: Dict[StatusEffectType, float] = field(default_factory=dict)
    status_effect_duration: Dict[StatusEffectType, int] = field(default_factory=dict)
    
    hit_rate: Optional[float] = None
    
    def __post_init__(self):
        if self.hit_rate is not None and (self.hit_rate < 0 or self.hit_rate > 1.0):
            raise ValueError(f"hit_rate must be between 0 and 1. hit_rate: {self.hit_rate}")
        for rate in self.status_effect_rate.values():
            if rate < 0 or rate > 1.0:
                raise ValueError(f"status_effect_rate must be between 0 and 1.0. status_effect_rate: {rate}")
        for duration in self.status_effect_duration.values():
            if duration <= 0:
                raise ValueError(f"status_effect_duration must be positive. status_effect_duration: {duration}")
        if self.mp_cost is not None and self.mp_cost < 0:
            raise ValueError(f"mp_cost must be non-negative. mp_cost: {self.mp_cost}")
        if self.hp_cost is not None and self.hp_cost < 0:
            raise ValueError(f"hp_cost must be non-negative. hp_cost: {self.hp_cost}")
    
    def _execute_core(self, actor: "CombatState", targets: List["CombatState"], context: "BattleLogicService", base_messages: List[str]) -> BattleActionResult:
        hit_result = context.hit_resolver.resolve_hits(actor, targets, self)
        
        if hit_result.missed or len(hit_result.evaded_targets) == len(targets):
            return BattleActionResult.create_failure(
                messages=base_messages + ["状態異常付与に失敗した！"],
                failure_reason="missed",
                actor_state_change=ActorStateChange(
                    actor_id=actor.entity_id,
                    participant_type=actor.participant_type,
                    mp_change=-(self.mp_cost or 0),
                    hp_change=-(self.hp_cost or 0)
                )
            )
        
        target_state_changes = []
        all_messages = base_messages.copy()

        for target in targets:
            if (target.entity_id, target.participant_type) in hit_result.evaded_targets:
                all_messages.append(f"{target.name}には当たらなかった...")
                target_state_changes.append(TargetStateChange(target_id=target.entity_id, participant_type=target.participant_type))
                continue

            # 状態異常付与
            effect_result = context.effect_applier.apply_effects(target, self)

            # 状態変更を作成
            target_state_changes.append(TargetStateChange(
                target_id=target.entity_id,
                participant_type=target.participant_type,
                status_effects_to_add=effect_result.status_effects_to_add,
            ))

            # メッセージ追加
            all_messages.extend(effect_result.messages)
            all_messages.append(f"{actor.name}は{target.name}に状態異常を付与した！")

        return BattleActionResult.create_success(
            messages=all_messages,
            actor_state_change=ActorStateChange(
                actor_id=actor.entity_id,
                participant_type=actor.participant_type,
                mp_change=-(self.mp_cost or 0),
                hp_change=-(self.hp_cost or 0)
            ),
            target_state_changes=target_state_changes,
        )


@dataclass(frozen=True)
class BuffApplyAction(BattleAction):
    """バフ付与系のアクション"""
    buff_rate: Dict[BuffType, float] = field(default_factory=dict)
    buff_duration: Dict[BuffType, int] = field(default_factory=dict)
    
    hit_rate: Optional[float] = None
    
    def __post_init__(self):
        if self.hit_rate is not None and (self.hit_rate < 0 or self.hit_rate > 1.0):
            raise ValueError(f"hit_rate must be between 0 and 1. hit_rate: {self.hit_rate}")
        for rate in self.buff_rate.values():
            if rate < 0 or rate > 1.0:
                raise ValueError(f"buff_rate must be between 0 and 1.0. buff_rate: {rate}")
        for duration in self.buff_duration.values():
            if duration <= 0:
                raise ValueError(f"buff_duration must be positive. buff_duration: {duration}")
        if self.mp_cost is not None and self.mp_cost < 0:
            raise ValueError(f"mp_cost must be non-negative. mp_cost: {self.mp_cost}")
        if self.hp_cost is not None and self.hp_cost < 0:
            raise ValueError(f"hp_cost must be non-negative. hp_cost: {self.hp_cost}")
    
    def _execute_core(self, actor: "CombatState", targets: List["CombatState"], context: "BattleLogicService", base_messages: List[str]) -> BattleActionResult:
        hit_result = context.hit_resolver.resolve_hits(actor, targets, self)
        
        if hit_result.missed or len(hit_result.evaded_targets) == len(targets):
            return BattleActionResult.create_failure(
                messages=base_messages + ["バフ付与に失敗した！"],
                failure_reason="missed",
                actor_state_change=ActorStateChange(
                    actor_id=actor.entity_id,
                    mp_change=-(self.mp_cost or 0),
                    hp_change=-(self.hp_cost or 0)
                )
            )
        
        target_state_changes = []
        all_messages = base_messages.copy()

        for target in targets:
            if (target.entity_id, target.participant_type) in hit_result.evaded_targets:
                all_messages.append(f"{target.name}には当たらなかった...")
                target_state_changes.append(TargetStateChange(target_id=target.entity_id, participant_type=target.participant_type))
                continue

            # バフ付与
            effect_result = context.effect_applier.apply_effects(target, self)

            # 状態変更を作成
            target_state_changes.append(TargetStateChange(
                target_id=target.entity_id,
                participant_type=target.participant_type,
                buffs_to_add=effect_result.buffs_to_add,
            ))

            # メッセージ追加
            all_messages.extend(effect_result.messages)
            all_messages.append(f"{actor.name}は{target.name}にバフを付与した！")

        return BattleActionResult.create_success(
            messages=all_messages,
            actor_state_change=ActorStateChange(
                actor_id=actor.entity_id,
                participant_type=actor.participant_type,
                mp_change=-(self.mp_cost or 0),
                hp_change=-(self.hp_cost or 0)
            ),
            target_state_changes=target_state_changes,
        )


class DefendAction(BattleAction):
    """防御アクション"""
    def _execute_core(self, actor: "CombatState", targets: List["CombatState"], context: "BattleLogicService", base_messages: List[str]) -> BattleActionResult:
        messages = base_messages.copy()
        messages.append(f"{actor.name}は防御の構えを取った！")
        return BattleActionResult.create_success(
            messages=messages,
            actor_state_change=ActorStateChange(actor_id=actor.entity_id, participant_type=actor.participant_type, is_defend=True),
        )


# @dataclass(frozen=True)
# class BattleAction:
#     """戦闘行動"""
#     action_id: int
#     name: str
#     description: str
#     action_type: ActionType
    
#     # ダメージ系
#     damage_multiplier: float = 1.0
#     element: Optional[Element] = None
    
#     # 回復系
#     heal_hp_amount: Optional[int] = None
#     heal_mp_amount: Optional[int] = None
    
#     # 状態異常
#     status_effect_rate: Dict[StatusEffectType, float] = field(default_factory=dict)
#     status_effect_duration: Dict[StatusEffectType, int] = field(default_factory=dict)
    
#     # バフ、デバフ
#     buff_multiplier: Dict[BuffType, float] = field(default_factory=dict)
#     buff_duration: Dict[BuffType, int] = field(default_factory=dict)
    
#     # 種族特攻
#     race_attack_multiplier: Dict[Race, float] = field(default_factory=dict)
    
#     # コスト
#     hp_cost: Optional[int] = None
#     mp_cost: Optional[int] = None
    
#     # その他
#     hit_rate: Optional[float] = None
    
#     def __post_init__(self):
#         """バリデーション"""
#         if self.hit_rate is not None and (self.hit_rate < 0 or self.hit_rate > 1.0):
#             raise ValueError(f"hit_rate must be between 0 and 1. hit_rate: {self.hit_rate}")
#         if self.mp_cost is not None and self.mp_cost < 0:
#             raise ValueError(f"mp_cost must be non-negative. mp_cost: {self.mp_cost}")
#         if self.hp_cost is not None and self.hp_cost < 0:
#             raise ValueError(f"hp_cost must be non-negative. hp_cost: {self.hp_cost}")
#         if self.damage_multiplier < 0:
#             raise ValueError(f"damage_multiplier must be non-negative. damage_multiplier: {self.damage_multiplier}")
#         for rate in self.status_effect_rate.values():
#             if rate < 0 or rate > 1.0:
#                 raise ValueError(f"status_effect_rate must be between 0 and 1.0. status_effect_rate: {rate}")
#         for multiplier in self.race_attack_multiplier.values():
#             if multiplier < 0:
#                 raise ValueError(f"race_attack_multiplier must be non-negative. race_attack_multiplier: {multiplier}")
#         for multiplier in self.buff_multiplier.values():
#             if multiplier < 0:
#                 raise ValueError(f"buff_multiplier must be non-negative. buff_multiplier: {multiplier}")
                
#     @classmethod
#     def create_heal_action(cls, action_id: int, name: str, description: str, action_type: ActionType, heal_hp_amount: int, heal_mp_amount: int, hp_cost: int, mp_cost: int) -> "BattleAction":
#         return BattleAction(
#             action_id=action_id,
#             name=name,
#             description=description,
#             action_type=action_type,
#             heal_hp_amount=heal_hp_amount,
#             heal_mp_amount=heal_mp_amount,
#             hp_cost=hp_cost,
#             mp_cost=mp_cost,
#         )

#     @classmethod
#     def create_attack_action(
#         cls,
#         action_id: int,
#         name: str,
#         description: str,
#         action_type: ActionType,
#         damage_multiplier: float,
#         element: Element,
#         hp_cost: int,
#         mp_cost: int,
#         status_effect_rate: Dict[StatusEffectType, float],
#         status_effect_duration: Dict[StatusEffectType, int],
#         buff_multiplier: Dict[BuffType, float],
#         buff_duration: Dict[BuffType, int],
#         race_attack_multiplier: Dict[Race, float],
#     ) -> "BattleAction":
#         return BattleAction(
#             action_id=action_id,
#             name=name,
#             description=description,
#             action_type=action_type,
#             damage_multiplier=damage_multiplier,
#             element=element,
#             status_effect_rate=status_effect_rate,
#             status_effect_duration=status_effect_duration,
#             buff_multiplier=buff_multiplier,
#             buff_duration=buff_duration,
#             race_attack_multiplier=race_attack_multiplier,
#             hp_cost=hp_cost,
#             mp_cost=mp_cost,
#         )