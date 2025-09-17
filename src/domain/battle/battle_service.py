import random
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional, Callable
from itertools import chain
from src.domain.battle.battle_action import BattleAction
from src.domain.battle.battle_enum import ActionType
from src.domain.battle.battle_result import BattleActionResult, TurnStartResult, TurnEndResult, TargetStateChange, ActorStateChange, BattleActionMetadata
from src.domain.battle.battle_participant import BattleParticipant
from src.domain.battle.battle_enum import BuffType, StatusEffectType, ParticipantType, TargetSelectionMethod
from src.domain.battle.compatible_table import COMPATIBLE_TABLE
from src.domain.battle.battle_exception import InsufficientMpException, InsufficientHpException, SilencedException, BlindedException
from src.domain.battle.constant import CRITICAL_MULTIPLIER, WAKE_RATE, CONFUSION_DAMAGE_MULTIPLIER, POISON_DAMAGE_RATE, BURN_DAMAGE_AMOUNT, BLESSING_HEAL_AMOUNT
from src.domain.battle.combat_state import CombatState


class TargetResolver:
    """ターゲット解決サービス"""
    
    def resolve_targets(
        self, 
        actor: CombatState, 
        action: BattleAction, 
        specified_targets: Optional[List[CombatState]],
        all_participants: List[CombatState]
    ) -> List[CombatState]:
        """ターゲットを解決する"""
        
        method = action.target_selection_method
        
        if method == TargetSelectionMethod.SINGLE_TARGET:
            if not specified_targets or len(specified_targets) != 1:
                raise ValueError("単一ターゲットが必要です")  # TODO: カスタム例外を実装
            return specified_targets
            
        elif method == TargetSelectionMethod.ALL_ENEMIES:
            return self._get_enemies(actor, all_participants)
            
        elif method == TargetSelectionMethod.ALL_ALLIES:
            return self._get_allies(actor, all_participants)
            
        elif method == TargetSelectionMethod.RANDOM_ENEMY:
            enemies = self._get_enemies(actor, all_participants)
            return [random.choice(enemies)] if enemies else []
            
        elif method == TargetSelectionMethod.RANDOM_ALLY:
            allies = self._get_allies(actor, all_participants)
            return [random.choice(allies)] if allies else []
            
        elif method == TargetSelectionMethod.RANDOM_ALL:
            return [random.choice(all_participants)] if all_participants else []
            
        elif method == TargetSelectionMethod.SELF:
            return [actor]
            
        else:
            raise ValueError(f"未対応のターゲット選択方法: {method}")  # TODO: カスタム例外を実装
    
    def _get_enemies(self, actor: CombatState, all_participants: List[CombatState]) -> List[CombatState]:
        """敵を取得"""
        return [p for p in all_participants if p.participant_type != actor.participant_type]
    
    def _get_allies(self, actor: CombatState, all_participants: List[CombatState]) -> List[CombatState]:
        """味方を取得"""
        return [p for p in all_participants if p.participant_type == actor.participant_type]


class ActionValidator:
    """アクション実行の事前チェック"""
    
    def validate_action(self, combat_state: CombatState, action: BattleAction) -> None:
        """アクション実行可能かチェック"""
        if not self._can_execute_magic_action(combat_state, action):
            raise SilencedException(f"{combat_state.name}は沈黙状態で魔法が使えない")
        if not self._can_execute_physical_action(combat_state, action):
            raise BlindedException(f"{combat_state.name}は暗闇状態で物理攻撃ができない")
        if not self._can_consume_mp(combat_state, action):
            raise InsufficientMpException(f"{combat_state.name}はMPが不足している")
        if not self._can_consume_hp(combat_state, action):
            raise InsufficientHpException(f"{combat_state.name}はHPが不足している")
    
    def _can_execute_magic_action(self, combat_state: CombatState, action: BattleAction) -> bool:
        is_silence = combat_state.has_status_effect(StatusEffectType.SILENCE)
        action_is_magic = action.action_type == ActionType.MAGIC
        return not (is_silence and action_is_magic)
    
    def _can_execute_physical_action(self, combat_state: CombatState, action: BattleAction) -> bool:
        is_blinded = combat_state.has_status_effect(StatusEffectType.BLINDNESS)
        action_is_physical = action.action_type == ActionType.PHYSICAL
        return not (is_blinded and action_is_physical)
    
    def _can_consume_mp(self, combat_state: CombatState, action: BattleAction) -> bool:
        if action.mp_cost is not None and not combat_state.current_mp.can_consume(action.mp_cost):
            return False
        return True
    
    def _can_consume_hp(self, combat_state: CombatState, action: BattleAction) -> bool:
        if action.hp_cost is not None and not combat_state.current_hp.can_consume(action.hp_cost):
            return False
        return True


@dataclass(frozen=True)
class ResourceConsumptionResult:
    mp_consumed: int
    hp_consumed: int
    messages: List[str]
    
    def __post_init__(self):
        if self.mp_consumed < 0:
            raise ValueError(f"Invalid mp_consumed: {self.mp_consumed}")
        if self.hp_consumed < 0:
            raise ValueError(f"Invalid hp_consumed: {self.hp_consumed}")


class ResourceConsumer:
    """リソース消費"""
    
    def consume_resource(self, combat_state: CombatState, action: BattleAction) -> ResourceConsumptionResult:
        """消費したリソースとメッセージを返す"""
        messages = []
        
        if action.mp_cost is not None and action.mp_cost > 0:
            messages.append(f"{combat_state.name}は{action.mp_cost}MPを消費した！")

        if action.hp_cost is not None and action.hp_cost > 0:
            messages.append(f"{combat_state.name}は{action.hp_cost}HPを消費した！")
        
        return ResourceConsumptionResult(mp_consumed=action.mp_cost or 0, hp_consumed=action.hp_cost or 0, messages=messages)


@dataclass(frozen=True)
class HitResolutionResult:
    missed: bool
    evaded_targets: List[Tuple[int, ParticipantType]]


class HitResolver:
    """命中/回避判定"""
    
    def _check_rate(self, rate: float) -> bool:
        """確率チェック"""
        return random.random() < rate
    
    def resolve_hits(self, combat_state: CombatState, defenders: List[CombatState], action: BattleAction) -> HitResolutionResult:
        """命中/回避判定"""
        messages = []
        if action.hit_rate is not None and not self._check_rate(action.hit_rate):
            messages.append(f"{combat_state.name}の攻撃が外れた！")
            return HitResolutionResult(missed=True, evaded_targets=[])
        
        # 回避率チェック
        evaded_targets = []
        for defender in defenders:
            if self._check_rate(defender.evasion_rate):
                evaded_targets.append((defender.entity_id, defender.participant_type))
        
        return HitResolutionResult(missed=False, evaded_targets=evaded_targets)


@dataclass(frozen=True)
class DamageCalculationResult:
    damage: int
    is_critical: bool
    compatibility_multiplier: float
    race_attack_multiplier: float
    
    def __post_init__(self):
        if self.damage < 0:
            raise ValueError(f"Invalid damage: {self.damage}")
        if self.compatibility_multiplier < 0:
            raise ValueError(f"Invalid compatibility_multiplier: {self.compatibility_multiplier}")
        if self.race_attack_multiplier < 0:
            raise ValueError(f"Invalid race_attack_multiplier: {self.race_attack_multiplier}")


class DamageCalculator:
    """ダメージ計算"""

    def _check_rate(self, rate: float) -> bool:
        """確率チェック"""
        return random.random() < rate
    
    def _calculate_compatible_multiplier(self, action: BattleAction, defender: CombatState) -> float:
        """相性倍率計算"""
        return COMPATIBLE_TABLE.get((action.element, defender.element), 1.0)
    
    def _calculate_race_attack_multiplier(self, action: BattleAction, defender: CombatState) -> float:
        """種族特攻倍率計算"""
        return action.race_attack_multiplier.get(defender.race, 1.0)
    
    def calculate_damage(self, attacker: CombatState, defender: CombatState, action: BattleAction) -> DamageCalculationResult:
        """ダメージを計算"""
        is_critical = self._check_rate(attacker.critical_rate)
        compatibility_multiplier = self._calculate_compatible_multiplier(action, defender)
        race_attack_multiplier = self._calculate_race_attack_multiplier(action, defender)
        
        # 基本ダメージ
        damage = attacker.calculate_current_attack() * action.damage_multiplier
        
        # 各種倍率適用
        damage *= compatibility_multiplier
        damage *= race_attack_multiplier
        
        if is_critical:
            damage *= CRITICAL_MULTIPLIER
        
        # 防御計算
        defense = defender.calculate_current_defense()
        damage = max(damage - defense, 0)
        
        return DamageCalculationResult(
            damage=int(damage),
            is_critical=is_critical,
            compatibility_multiplier=compatibility_multiplier,
            race_attack_multiplier=race_attack_multiplier
        )


class MessageGenerator:
    """メッセージ生成"""
    
    def generate_messages(self, action: BattleAction, results: List[DamageCalculationResult]) -> List[str]:
        """戦闘メッセージを生成"""
        messages = []
        for result in results:
            crit_msg = "クリティカル！" if result.is_critical else ""
            messages.append(f"ダメージ{result.damage}を与えた！{crit_msg}")
        return messages


@dataclass(frozen=True)
class EffectApplicationResult:
    status_effects_to_add: List[Tuple[StatusEffectType, int]]
    buffs_to_add: List[Tuple[BuffType, float, int]]
    messages: List[str]


class EffectApplier:
    """効果適用"""

    def _check_rate(self, rate: float) -> bool:
        """確率チェック"""
        return random.random() < rate

    def apply_effects(self, defender: CombatState, action: BattleAction) -> EffectApplicationResult:
        """状態異常とバフを適用"""
        messages = []
        status_effects_to_add = []
        buffs_to_add = []
        
        # 状態異常適用
        if action.status_effect_infos:
            for effect_info in action.status_effect_infos:
                if self._check_rate(effect_info.apply_rate):
                    duration = effect_info.duration
                    status_effects_to_add.append((effect_info.effect_type, duration))
                    messages.append(f"{defender.name}は「{effect_info.effect_type.value}」の状態異常を受けた！")
        
        # バフ適用
        if action.buff_infos:
            for buff_info in action.buff_infos:
                duration = buff_info.duration
                buffs_to_add.append((buff_info.buff_type, buff_info.multiplier, duration))
                messages.append(f"{defender.name}は「{buff_info.buff_type.value}」のバフを受けた！")
        
        return EffectApplicationResult(
            status_effects_to_add=status_effects_to_add,
            buffs_to_add=buffs_to_add,
            messages=messages
        )


class EffectProcessor:
    """状態異常の効果計算"""
    def process_sleep_on_turn_start(self, combat_state: CombatState) -> TurnStartResult:
        """眠りの処理"""
        can_act = True
        messages = []
        status_effects_to_remove = []

        if combat_state.has_status_effect(StatusEffectType.SLEEP):
            if random.random() < WAKE_RATE:
                messages.append(f"{combat_state.name}は眠りから覚めた！")
                status_effects_to_remove.append(StatusEffectType.SLEEP)
            else:
                messages.append(f"{combat_state.name}は眠っているようだ...")
                can_act = False

        return TurnStartResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            can_act=can_act,
            messages=messages,
            status_effects_to_remove=status_effects_to_remove,
        )

    def process_paralysis_on_turn_start(self, combat_state: CombatState) -> TurnStartResult:
        """麻痺の処理"""
        can_act = True
        messages = []
        status_effects_to_remove = []

        if combat_state.has_status_effect(StatusEffectType.PARALYSIS):
            messages.append(f"{combat_state.name}は体が麻痺して動けないようだ...")
            can_act = False

        return TurnStartResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            can_act=can_act,
            messages=messages,
            status_effects_to_remove=status_effects_to_remove,
        )

    def process_confusion_on_turn_start(self, combat_state: CombatState) -> TurnStartResult:
        """混乱の処理"""
        can_act = True
        messages = []
        damage = 0

        if combat_state.has_status_effect(StatusEffectType.CONFUSION):
            damage = int(combat_state.attack * CONFUSION_DAMAGE_MULTIPLIER)
            messages.append(f"{combat_state.name}は混乱により自分に{damage}のダメージを与えた！")
            can_act = False

        return TurnStartResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            can_act=can_act,
            messages=messages,
            damage=damage,
        )

    def process_curse_on_turn_start(self, combat_state: CombatState) -> TurnStartResult:
        """呪いの処理"""
        can_act = True
        messages = []
        
        if combat_state.has_status_effect(StatusEffectType.CURSE):
            duration = combat_state.get_status_effect_remaining_duration(StatusEffectType.CURSE)
            messages.append(f"{combat_state.name}は呪いに体を蝕まれている... 残り{duration}ターン...")

        return TurnStartResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            can_act=can_act,
            messages=messages,
        )

    def process_poison_on_turn_end(self, combat_state: CombatState) -> TurnEndResult:
        """毒の処理"""
        messages = []
        damage = 0

        if combat_state.has_status_effect(StatusEffectType.POISON):
            damage = int(combat_state.current_hp.value * POISON_DAMAGE_RATE)
            messages.append(f"{combat_state.name}は毒により{damage}のダメージを受けた！")

        return TurnEndResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            messages=messages,
            damage=damage,
        )

    def process_burn_on_turn_end(self, combat_state: CombatState) -> TurnEndResult:
        """やけどの処理"""
        messages = []
        damage = 0

        if combat_state.has_status_effect(StatusEffectType.BURN):
            damage = BURN_DAMAGE_AMOUNT
            messages.append(f"{combat_state.name}はやけどにより{damage}のダメージを受けた！")

        return TurnEndResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            messages=messages,
            damage=damage,
        )

    def process_blessing_on_turn_end(self, combat_state: CombatState) -> TurnEndResult:
        """加護の処理"""
        messages = []
        healing = 0

        if combat_state.has_status_effect(StatusEffectType.BLESSING):
            healing = BLESSING_HEAL_AMOUNT
            messages.append(f"{combat_state.name}は加護によりHPが{healing}回復した！")

        return TurnEndResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            messages=messages,
            healing=healing,
        )

    def process_curse_on_turn_end(self, combat_state: CombatState) -> TurnEndResult:
        """呪いの処理"""
        messages = []
        damage = 0

        if combat_state.has_status_effect(StatusEffectType.CURSE) and combat_state.get_status_effect_remaining_duration(StatusEffectType.CURSE) == 1:
            damage = combat_state.current_hp.value
            messages.append(f"{combat_state.name}は呪いに体を蝕まれて死んでしまった...")

        return TurnEndResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            messages=messages,
            damage=damage,
        )


class BattleLogicService:
    """戦闘ロジックサービス"""
    
    def __init__(self):
        self.action_validator = ActionValidator()
        self.resource_consumer = ResourceConsumer()
        self.hit_resolver = HitResolver()
        self.damage_calculator = DamageCalculator()
        self.effect_applier = EffectApplier()
        self.message_generator = MessageGenerator()
        self.effect_processor = EffectProcessor()
        self.target_resolver = TargetResolver()
    
    def process_on_turn_start(self, combat_state: CombatState) -> TurnStartResult:
        """ターン開始時の処理"""
        results = [
            self.effect_processor.process_sleep_on_turn_start(combat_state),
            self.effect_processor.process_paralysis_on_turn_start(combat_state),
            self.effect_processor.process_confusion_on_turn_start(combat_state),
            self.effect_processor.process_curse_on_turn_start(combat_state),
        ]

        return TurnStartResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            can_act=all(result.can_act for result in results),
            messages=list(chain.from_iterable(result.messages for result in results)),
            damage=sum(result.damage for result in results),
            status_effects_to_remove=list(chain.from_iterable(result.status_effects_to_remove for result in results)),
            buffs_to_remove=list(chain.from_iterable(result.buffs_to_remove for result in results)),
        )
    
    def process_on_turn_end(self, combat_state: CombatState) -> TurnEndResult:
        """ターン終了時の処理"""
        results = [
            self.effect_processor.process_poison_on_turn_end(combat_state),
            self.effect_processor.process_burn_on_turn_end(combat_state),
            self.effect_processor.process_blessing_on_turn_end(combat_state),
            self.effect_processor.process_curse_on_turn_end(combat_state),
        ]
        return TurnEndResult(
            actor_id=combat_state.entity_id,
            participant_type=combat_state.participant_type,
            messages=list(chain.from_iterable(result.messages for result in results)),
            damage=sum(result.damage for result in results),
            healing=sum(result.healing for result in results),
            status_effects_to_remove=list(chain.from_iterable(result.status_effects_to_remove for result in results)),
            buffs_to_remove=list(chain.from_iterable(result.buffs_to_remove for result in results)),
        )



# # TODO: 副作用がない形で元の実装を修正
# # 責務の分散
# class _BattleLogicService:
#     """戦闘ロジックを調整"""

#     def _check_rate(self, rate: float) -> bool:
#         """確率チェック"""
#         return random.random() < rate

#     def _calculate_damage(
#         self,
#         attacker: BattleParticipant,
#         defender: BattleParticipant,
#         action: BattleAction,
#         is_critical: bool,
#         compatibility_multiplier: float,
#         race_attack_multiplier: float,
#     ) -> int:
#         """ダメージ計算"""
#         damage = attacker.calculate_base_damage(action)
        
#         # 相性チェック
#         damage *= compatibility_multiplier

#         # 種族特攻チェック
#         damage *= race_attack_multiplier
        
#         # クリティカルダメージチェック
#         if is_critical:
#             damage *= CRITICAL_MULTIPLIER
#             damage = int(damage)

#         # ディフェンスチェック
#         defence = defender.calculate_defense()

#         # ダメージ軽減
#         damage = max(damage - defence, 0)

#         return damage

#     def _calculate_contribution_score(
#         self,
#         damage_dealt: int,
#         healing_done: int,
#         critical_hits: int,
#         status_effects_applied: int,
#         buffs_applied: int,
#     ) -> int:
#         """貢献度スコアを計算"""
#         base_score = damage_dealt + (healing_done * 2)  # 回復は2倍の価値
#         critical_bonus = critical_hits * 10  # クリティカル1回につき10点
#         status_bonus = status_effects_applied * 5  # 状態異常1つにつき5点
#         buff_bonus = buffs_applied * 3  # バフ1つにつき3点
        
#         return base_score + critical_bonus + status_bonus + buff_bonus
    
#     def execute_attack(self, attacker: BattleParticipant, defenders: List[BattleParticipant], action: BattleAction) -> BattleActionResult:
#         messages = []
#         hp_consumed = action.hp_cost or 0
#         mp_consumed = action.mp_cost or 0

#         # ======= 事前チェック可能な例外ケース =======
#         if not attacker.can_magic_action(action):
#             raise SilencedException(f"{attacker.entity.name}はMPが不足しているため魔法を使用できない")
#         if not attacker.can_consume_mp(action):
#             raise InsufficientMpException(f"{attacker.entity.name}はMPが不足しているため魔法を使用できない")
#         if not attacker.can_consume_hp(action):
#             raise InsufficientHpException(f"{attacker.entity.name}はHPが不足しているため魔法を使用できない")
        
#         # ======= リソース消費 =======
#         if mp_consumed > 0:
#             messages.append(f"{attacker.entity.name}は{mp_consumed}MPを消費した！")
#         if hp_consumed > 0:
#             messages.append(f"{attacker.entity.name}は{hp_consumed}HPを消費した！")
#         actor_state_change = ActorStateChange(actor_id=attacker.entity_id, mp_change=-mp_consumed, hp_change=-hp_consumed)

#         # ======= 命中率チェック =======
#         if action.hit_rate is not None and not self._check_rate(action.hit_rate):
#             messages.append(f"{attacker.entity.name}の攻撃が外れた！")
#             return BattleActionResult.create_failure(
#                 messages=messages,
#                 failure_reason="missed",
#                 actor_state_change=actor_state_change,
#             )
        
#         # ======= 回避率チェック =======
#         evaded_defenders = []
#         for defender in defenders:
#             if self._check_rate(defender.entity.evasion_rate):
#                 evaded_defenders.append(defender)
#                 messages.append(f"{defender.entity.name}は攻撃を回避した！")
        
#         # ======= 全員が回避した場合は攻撃失敗 =======
#         if len(evaded_defenders) == len(defenders):
#             return BattleActionResult.create_failure(
#                 messages=messages,
#                 failure_reason="evaded",
#                 actor_state_change=actor_state_change,
#             )
        
#         # ダメージ,状態異常,バフの計算
#         critical_hits = []
#         compatibility_multipliers = []
#         race_attack_multipliers = []
#         target_state_changes: List[TargetStateChange] = []

#         for defender in defenders:
#             # 回避したdefenderはスキップ
#             if defender in evaded_defenders:
#                 target_state_changes.append(TargetStateChange(target_id=defender.entity_id))
#                 continue
            
#             is_critical = self._check_rate(attacker.entity.critical_rate)
#             critical_hits.append(is_critical)
#             compatibility_multiplier = self._calculate_compatible_multiplier(action, defender)
#             compatibility_multipliers.append(compatibility_multiplier)
#             race_attack_multiplier = self._calculate_race_attack_multiplier(action, defender)
#             race_attack_multipliers.append(race_attack_multiplier)

#             damage = self._calculate_damage(attacker, defender, action, is_critical, compatibility_multiplier, race_attack_multiplier)
            
#             status_effects_to_add = []
#             if action.status_effect_rate:
#                 for status_effect_type, rate in action.status_effect_rate.items():
#                     if self._check_rate(rate):
#                         duration = action.status_effect_duration[status_effect_type]
#                         status_effects_to_add.append((status_effect_type, duration))
#                         messages.append(f"{defender.entity.name}は「{status_effect_type.value}」の状態異常を受けた！")

#             buffs_to_add = []
#             if action.buff_multiplier:
#                 for buff_type, multiplier in action.buff_multiplier.items():
#                     duration = action.buff_duration[buff_type]
#                     buffs_to_add.append((buff_type, multiplier, duration))
#                     messages.append(f"{defender.entity.name}は「{buff_type.value}」のバフを受けた！")
            
#             target_state_changes.append(TargetStateChange(
#                 target_id=defender.entity_id,
#                 hp_change=damage,
#                 mp_change=0,
#                 status_effects_to_add=status_effects_to_add,
#                 buffs_to_add=buffs_to_add,
#             ))
            
#             crit_msg = "クリティカル！" if is_critical else ""
#             messages.append(f"{attacker.entity.name}は{defender.entity.name}に{damage}のダメージを与えた！{crit_msg}")

#         metadata = BattleActionMetadata(
#             critical_hits=critical_hits,
#             compatibility_multipliers=compatibility_multipliers,
#             race_attack_multipliers=race_attack_multipliers,
#         )

#         return BattleActionResult.create_success(
#             messages=messages,
#             actor_state_change=actor_state_change,
#             target_state_changes=target_state_changes,
#             metadata=metadata,
#         )

#     def execute_heal(self, healer: BattleParticipant, targets: List[BattleParticipant], action: BattleAction) -> BattleActionResult:
#         """回復を実行"""
#         messages = []
#         # MPチェック
#         if not healer.can_consume_mp(action):
#             raise InsufficientMpException(f"{healer.entity.name}はMPが不足しているため魔法を使用できない")

#         # HP, MP消費
#         mp_consumed = action.mp_cost or 0
#         hp_consumed = action.hp_cost or 0
#         if mp_consumed > 0:
#             messages.append(f"{healer.entity.name}は{mp_consumed}MPを消費した！")
#         if hp_consumed > 0:
#             messages.append(f"{healer.entity.name}は{hp_consumed}HPを消費した！")

#         # 回復
#         heal_hp_amount = action.heal_hp_amount or 0
#         heal_mp_amount = action.heal_mp_amount or 0
#         target_state_changes: List[TargetStateChange] = []

#         for target in targets:
#             target_state_changes.append(TargetStateChange(target_id=target.entity_id, hp_change=heal_hp_amount, mp_change=heal_mp_amount))

#         actor_state_change = ActorStateChange(actor_id=healer.entity_id, mp_change=-mp_consumed, hp_change=-hp_consumed)

#         return BattleActionResult.create_success(
#             messages=messages,
#             actor_state_change=actor_state_change,
#             target_state_changes=target_state_changes,
#         )