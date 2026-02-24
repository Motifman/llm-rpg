from dataclasses import dataclass
from typing import Optional, List

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


@dataclass(frozen=True)
class PlayerDownedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤー戦闘不能イベント。死因は様々なため killer_player_id は Optional。"""
    killer_player_id: Optional[PlayerId] = None


@dataclass(frozen=True)
class PlayerEvadedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤー回避イベント"""
    current_hp: int


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


@dataclass(frozen=True)
class PlayerLocationChangedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤー位置変更イベント"""
    old_spot_id: Optional[SpotId]
    old_coordinate: Optional[Coordinate]
    new_spot_id: SpotId
    new_coordinate: Coordinate
