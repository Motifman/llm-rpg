from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Tuple
from src.domain.common.domain_event import DomainEvent
from src.domain.battle.battle_enum import BattleResultType, ParticipantType, StatusEffectType, BuffType, Element, Race, ActionType
from src.domain.monster.drop_reward import DropReward


@dataclass(frozen=True)
class BattleStartedEvent(DomainEvent):
    """戦闘開始イベント"""
    battle_id: int = 0
    spot_id: int = 0
    player_ids: List[int] = field(default_factory=list)
    monster_ids: List[int] = field(default_factory=list)
    max_players: int = 4
    max_turns: int = 30
    battle_config: Dict[str, Any] = field(default_factory=dict)  # 戦闘設定情報


@dataclass(frozen=True)
class PlayerJoinedBattleEvent(DomainEvent):
    """プレイヤー戦闘参加イベント"""
    battle_id: int = 0
    player_id: int = 0
    join_turn: int = 0
    player_stats: Dict[str, Any] = field(default_factory=dict)  # 参加時のプレイヤー統計


@dataclass(frozen=True)
class MonsterJoinedBattleEvent(DomainEvent):
    """モンスター戦闘参加イベント"""
    battle_id: int = 0
    monster_id: int = 0
    join_turn: int = 0
    monster_stats: Dict[str, Any] = field(default_factory=dict)  # 参加時のモンスター統計


@dataclass(frozen=True)
class PlayerLeftBattleEvent(DomainEvent):
    """プレイヤー戦闘離脱イベント"""
    battle_id: int = 0
    player_id: int = 0
    reason: str = ""  # "escape", "defeated", "disconnected"
    final_stats: Dict[str, Any] = field(default_factory=dict)  # 離脱時の最終統計
    contribution_score: int = 0  # 貢献度スコア


@dataclass(frozen=True)
class MonsterLeftBattleEvent(DomainEvent):
    """モンスター戦闘離脱イベント"""
    battle_id: int = 0
    monster_id: int = 0
    reason: str = ""  # "defeated", "disconnected"
    final_stats: Dict[str, Any] = field(default_factory=dict)  # 離脱時の最終統計


@dataclass(frozen=True)
class ParticipantInfo:
    """参加者の情報（UI表示用）"""
    entity_id: int
    participant_type: ParticipantType
    name: str
    race: Race
    element: Element
    current_hp: int
    max_hp: int
    current_mp: int
    max_mp: int
    attack: int
    defense: int
    speed: int
    is_defending: bool
    can_act: bool
    level: int = 1  # レベル情報を追加
    status_effects: Dict[StatusEffectType, int] = field(default_factory=dict)  # effect_type -> remaining_duration
    buffs: Dict[BuffType, Tuple[float, int]] = field(default_factory=dict)  # buff_type -> (multiplier, remaining_duration)
    available_action_ids: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class ActionInfo:
    """アクション情報（UI表示用）"""
    action_id: int
    name: str
    description: str
    action_type: ActionType
    element: Optional[Element] = None
    mp_cost: Optional[int] = None
    hp_cost: Optional[int] = None


@dataclass(frozen=True)
class TurnStartedEvent(DomainEvent):
    """ターン開始イベント"""
    battle_id: int = 0
    turn_number: int = 0
    round_number: int = 0
    actor_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    actor_info: Optional[ParticipantInfo] = None  # アクターの詳細情報
    all_participants: List[ParticipantInfo] = field(default_factory=list)  # 全参加者の現在状態
    turn_order: List[Tuple[ParticipantType, int]] = field(default_factory=list)  # 現在のターン順序
    can_act: bool = True
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StatusEffectApplication:
    """状態異常適用情報"""
    target_id: int
    target_participant_type: ParticipantType
    effect_type: StatusEffectType
    duration: int
    effect_value: Optional[int] = None  # 毒のダメージ量など


@dataclass(frozen=True)
class BuffApplication:
    """バフ適用情報"""
    target_id: int
    target_participant_type: ParticipantType
    buff_type: BuffType
    multiplier: float
    duration: int


@dataclass(frozen=True)
class TargetResult:
    """各ターゲットへの結果"""
    target_id: int
    target_participant_type: ParticipantType
    damage_dealt: int = 0
    healing_done: int = 0
    was_critical: bool = False
    compatibility_multiplier: float = 1.0
    was_evaded: bool = False
    was_blocked: bool = False
    hp_before: int = 0
    hp_after: int = 0
    mp_before: int = 0
    mp_after: int = 0


@dataclass(frozen=True)
class TurnExecutedEvent(DomainEvent):
    """ターン実行イベント"""
    battle_id: int = 0
    turn_number: int = 0
    round_number: int = 0
    actor_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    
    # アクション情報
    action_info: Optional[ActionInfo] = None
    
    # 結果情報
    target_results: List[TargetResult] = field(default_factory=list)
    hp_consumed: int = 0
    mp_consumed: int = 0
    
    # 効果適用
    applied_status_effects: List[StatusEffectApplication] = field(default_factory=list)
    applied_buffs: List[BuffApplication] = field(default_factory=list)
    
    # 状態変化後の全参加者情報
    all_participants_after: List[ParticipantInfo] = field(default_factory=list)
    
    # メッセージと結果
    messages: List[str] = field(default_factory=list)
    success: bool = True
    failure_reason: Optional[str] = None


@dataclass(frozen=True)
class StatusEffectTrigger:
    """状態異常発動情報"""
    target_id: int
    target_participant_type: ParticipantType
    effect_type: StatusEffectType
    damage_or_healing: int  # 正の値は回復、負の値はダメージ
    remaining_duration: int


@dataclass(frozen=True)
class TurnEndedEvent(DomainEvent):
    """ターン終了イベント"""
    battle_id: int = 0
    turn_number: int = 0
    round_number: int = 0
    actor_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    
    # 状態異常・バフの処理結果
    status_effect_triggers: List[StatusEffectTrigger] = field(default_factory=list)
    expired_status_effects: List[Tuple[int, ParticipantType, StatusEffectType]] = field(default_factory=list)
    expired_buffs: List[Tuple[int, ParticipantType, BuffType]] = field(default_factory=list)
    
    # アクター状態
    is_actor_defeated: bool = False
    actor_info_after: Optional[ParticipantInfo] = None
    
    # 全参加者の最新状態
    all_participants_after: List[ParticipantInfo] = field(default_factory=list)
    
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoundStartedEvent(DomainEvent):
    """ラウンド開始イベント"""
    battle_id: int = 0
    round_number: int = 0
    turn_order: List[Tuple[ParticipantType, int]] = field(default_factory=list)  # (participant_type, entity_id)
    all_participants: List[ParticipantInfo] = field(default_factory=list)  # ラウンド開始時の全参加者状態
    remaining_players: List[int] = field(default_factory=list)
    remaining_monsters: List[int] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoundSummary:
    """ラウンド要約情報"""
    total_damage_dealt: Dict[int, int] = field(default_factory=dict)  # entity_id -> total_damage
    total_healing_done: Dict[int, int] = field(default_factory=dict)  # entity_id -> total_healing
    actions_taken: Dict[int, int] = field(default_factory=dict)  # entity_id -> action_count
    critical_hits: Dict[int, int] = field(default_factory=dict)  # entity_id -> critical_count


@dataclass(frozen=True)
class RoundEndedEvent(DomainEvent):
    """ラウンド終了イベント"""
    battle_id: int = 0
    round_number: int = 0
    round_summary: RoundSummary = field(default_factory=RoundSummary)
    all_participants_at_end: List[ParticipantInfo] = field(default_factory=list)
    next_round_turn_order: List[Tuple[ParticipantType, int]] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BattleEndedEvent(DomainEvent):
    """戦闘終了イベント"""
    battle_id: int = 0
    spot_id: int = 0
    result_type: BattleResultType = BattleResultType.DRAW
    winner_ids: List[int] = field(default_factory=list)
    participant_ids: List[int] = field(default_factory=list)
    total_turns: int = 0
    total_rounds: int = 0
    total_rewards: DropReward = field(default_factory=DropReward)  # {"gold": 1000, "exp": 500}  # DropRewardにする
    battle_statistics: Dict[str, Any] = field(default_factory=dict)  # 戦闘全体の統計
    contribution_scores: Dict[int, int] = field(default_factory=dict)  # player_id -> contribution_score


@dataclass(frozen=True)
class MonsterDefeatedEvent(DomainEvent):
    """モンスター撃破イベント"""
    battle_id: int = 0
    monster_id: int = 0
    monster_type_id: int = 0
    defeated_by_player_id: int = 0
    defeat_turn: int = 0
    defeat_round: int = 0
    drop_reward: DropReward = field(default_factory=DropReward)
    final_monster_info: Optional[ParticipantInfo] = None
    damage_dealt_by_defeater: int = 0
    total_damage_taken: int = 0
    defeat_action_info: Optional[ActionInfo] = None  # 撃破に使用されたアクション
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerDefeatedEvent(DomainEvent):
    """プレイヤー撃破イベント"""
    battle_id: int = 0
    player_id: int = 0
    defeated_by_monster_id: int = 0
    defeat_turn: int = 0
    defeat_round: int = 0
    final_player_info: Optional[ParticipantInfo] = None
    damage_dealt_by_defeater: int = 0
    total_damage_taken: int = 0
    defeat_action_info: Optional[ActionInfo] = None  # 撃破に使用されたアクション
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StatusEffectAppliedEvent(DomainEvent):
    """状態異常適用イベント"""
    battle_id: int = 0
    target_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    status_effect_type: StatusEffectType = StatusEffectType.POISON
    duration: int = 0
    applied_turn: int = 0
    applied_round: int = 0
    applied_by_id: int = 0
    applied_by_type: ParticipantType = ParticipantType.PLAYER


@dataclass(frozen=True)
class StatusEffectExpiredEvent(DomainEvent):
    """状態異常期限切れイベント"""
    battle_id: int = 0
    target_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    status_effect_type: StatusEffectType = StatusEffectType.POISON
    expired_turn: int = 0
    expired_round: int = 0


@dataclass(frozen=True)
class BuffAppliedEvent(DomainEvent):
    """バフ適用イベント"""
    battle_id: int = 0
    target_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    buff_type: BuffType = BuffType.ATTACK
    multiplier: float = 1.0
    duration: int = 0
    applied_turn: int = 0
    applied_round: int = 0
    applied_by_id: int = 0
    applied_by_type: ParticipantType = ParticipantType.PLAYER


@dataclass(frozen=True)
class BuffExpiredEvent(DomainEvent):
    """バフ期限切れイベント"""
    battle_id: int = 0
    target_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    buff_type: BuffType = BuffType.ATTACK
    expired_turn: int = 0
    expired_round: int = 0