from dataclasses import dataclass

from src.domain.common.domain_event import BaseDomainEvent
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.value_object.base_stats import BaseStats


@dataclass(frozen=True)
class PlayerDownedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤー戦闘不能イベント"""


@dataclass(frozen=True)
class PlayerRevivedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤー復帰イベント"""
    hp_recovered: int
    total_hp: int


@dataclass(frozen=True)
class PlayerLevelUpEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤーレベルアップイベント"""
    old_level: int
    new_level: int
    stat_growth: BaseStats


@dataclass(frozen=True)
class PlayerHpHealedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """HP回復イベント"""
    healed_amount: int
    total_hp: int


@dataclass(frozen=True)
class PlayerMpConsumedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """MP消費イベント"""
    consumed_amount: int
    remaining_mp: int


@dataclass(frozen=True)
class PlayerMpHealedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """MP回復イベント"""
    healed_amount: int
    total_mp: int


@dataclass(frozen=True)
class PlayerStaminaConsumedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """スタミナ消費イベント"""
    consumed_amount: int
    remaining_stamina: int


@dataclass(frozen=True)
class PlayerStaminaHealedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """スタミナ回復イベント"""
    healed_amount: int
    total_stamina: int


@dataclass(frozen=True)
class PlayerGoldEarnedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤーゴールド獲得イベント"""
    earned_amount: int
    total_gold: int


@dataclass(frozen=True)
class PlayerGoldPaidEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤーゴールド支払いイベント"""
    paid_amount: int
    total_gold: int
