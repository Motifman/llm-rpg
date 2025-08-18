from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Tuple
from src.domain.common.domain_event import DomainEvent
from src.domain.battle.battle_enum import BattleResultType, ParticipantType, StatusEffectType, BuffType


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
class TurnStartedEvent(DomainEvent):
    """ターン開始イベント"""
    battle_id: int = 0
    turn_number: int = 0
    round_number: int = 0
    actor_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    actor_stats: Dict[str, Any] = field(default_factory=dict)  # アクターの現在統計
    can_act: bool = True
    status_effects: List[StatusEffectType] = field(default_factory=list)
    active_buffs: List[BuffType] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TurnExecutedEvent(DomainEvent):
    """ターン実行イベント"""
    battle_id: int = 0
    turn_number: int = 0
    round_number: int = 0
    actor_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    action_type: str = ""
    action_name: str = ""
    target_ids: List[int] = field(default_factory=list)
    target_participant_types: List[ParticipantType] = field(default_factory=list)
    damage_dealt: int = 0
    healing_done: int = 0
    hp_consumed: int = 0
    mp_consumed: int = 0
    critical_hits: List[bool] = field(default_factory=list)
    compatibility_multipliers: List[float] = field(default_factory=list)
    applied_status_effects: List[Tuple[int, StatusEffectType, int]] = field(default_factory=list)
    applied_buffs: List[Tuple[int, BuffType, float, int]] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    success: bool = True
    failure_reason: Optional[str] = None


@dataclass(frozen=True)
class TurnEndedEvent(DomainEvent):
    """ターン終了イベント"""
    battle_id: int = 0
    turn_number: int = 0
    round_number: int = 0
    actor_id: int = 0
    participant_type: ParticipantType = ParticipantType.PLAYER
    is_actor_defeated: bool = False
    damage_from_status_effects: int = 0
    healing_from_status_effects: int = 0
    expired_status_effects: List[StatusEffectType] = field(default_factory=list)
    expired_buffs: List[BuffType] = field(default_factory=list)
    final_actor_stats: Dict[str, Any] = field(default_factory=dict)
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoundStartedEvent(DomainEvent):
    """ラウンド開始イベント"""
    battle_id: int = 0
    round_number: int = 0
    turn_order: List[Tuple[int, ParticipantType]] = field(default_factory=list)  # (entity_id, participant_type)
    remaining_participants: Dict[ParticipantType, List[int]] = field(default_factory=dict)
    round_stats: Dict[str, Any] = field(default_factory=dict)  # ラウンド開始時の統計


@dataclass(frozen=True)
class RoundEndedEvent(DomainEvent):
    """ラウンド終了イベント"""
    battle_id: int = 0
    round_number: int = 0
    round_summary: Dict[str, Any] = field(default_factory=dict)  # ラウンドの要約統計
    next_round_turn_order: List[Tuple[int, ParticipantType]] = field(default_factory=list)


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
    total_rewards: Dict[str, int] = field(default_factory=dict)  # {"gold": 1000, "exp": 500}
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
    drop_reward: Dict[str, Any] = field(default_factory=dict)
    final_monster_stats: Dict[str, Any] = field(default_factory=dict)
    damage_dealt_by_defeater: int = 0


@dataclass(frozen=True)
class PlayerDefeatedEvent(DomainEvent):
    """プレイヤー撃破イベント"""
    battle_id: int = 0
    player_id: int = 0
    defeated_by_monster_id: int = 0
    defeat_turn: int = 0
    defeat_round: int = 0
    final_player_stats: Dict[str, Any] = field(default_factory=dict)
    damage_dealt_by_defeater: int = 0


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