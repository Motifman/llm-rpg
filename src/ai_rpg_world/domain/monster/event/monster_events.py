from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum, DeathCauseEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate


@dataclass(frozen=True)
class MonsterCreatedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    template_id: int


@dataclass(frozen=True)
class MonsterSpawnedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    spot_id: SpotId


@dataclass(frozen=True)
class MonsterDamagedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    damage: int
    current_hp: int
    attacker_id: WorldObjectId | None = None


@dataclass(frozen=True)
class MonsterDiedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    respawn_tick: int
    exp: int
    gold: int
    template_id: int | None = None
    loot_table_id: LootTableId | None = None
    killer_player_id: PlayerId | None = None
    killer_world_object_id: WorldObjectId | None = None
    cause: DeathCauseEnum | None = None
    spot_id: SpotId | None = None


@dataclass(frozen=True)
class MonsterRespawnedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    spot_id: SpotId


@dataclass(frozen=True)
class MonsterHealedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    amount: int
    current_hp: int


@dataclass(frozen=True)
class MonsterMpRecoveredEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    amount: int
    current_mp: int


@dataclass(frozen=True)
class TargetSpottedEvent(BaseDomainEvent[WorldObjectId, str]):
    """ターゲットを視認したイベント"""

    actor_id: WorldObjectId
    target_id: WorldObjectId
    coordinate: Coordinate


@dataclass(frozen=True)
class TargetLostEvent(BaseDomainEvent[WorldObjectId, str]):
    """ターゲットを見失ったイベント"""

    actor_id: WorldObjectId
    target_id: WorldObjectId
    last_known_coordinate: Coordinate


@dataclass(frozen=True)
class BehaviorStuckEvent(BaseDomainEvent[WorldObjectId, str]):
    """行動がスタック（移動失敗の連続）したイベント"""

    actor_id: WorldObjectId
    state: BehaviorStateEnum
    coordinate: Coordinate
