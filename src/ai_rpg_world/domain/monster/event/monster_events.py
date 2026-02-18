from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.enum.monster_enum import DeathCauseEnum

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate


@dataclass(frozen=True)
class MonsterCreatedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    template_id: int


@dataclass(frozen=True)
class MonsterSpawnedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    coordinate: dict
    spot_id: SpotId


@dataclass(frozen=True)
class MonsterDamagedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    damage: int
    current_hp: int
    attacker_id: Optional[WorldObjectId] = None


@dataclass(frozen=True)
class MonsterDiedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    respawn_tick: int
    exp: int
    gold: int
    loot_table_id: Optional[str] = None
    killer_player_id: Optional[PlayerId] = None
    killer_world_object_id: Optional[WorldObjectId] = None
    cause: Optional[DeathCauseEnum] = None
    spot_id: Optional[SpotId] = None


@dataclass(frozen=True)
class MonsterRespawnedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    coordinate: dict
    spot_id: SpotId


@dataclass(frozen=True)
class MonsterEvadedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    coordinate: dict
    current_hp: int


@dataclass(frozen=True)
class MonsterHealedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    amount: int
    current_hp: int


@dataclass(frozen=True)
class MonsterMpRecoveredEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    amount: int
    current_mp: int
