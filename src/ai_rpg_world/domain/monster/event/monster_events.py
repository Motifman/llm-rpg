from dataclasses import dataclass
from typing import TYPE_CHECKING
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate


@dataclass(frozen=True)
class MonsterCreatedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    template_id: int


@dataclass(frozen=True)
class MonsterSpawnedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    coordinate: dict


@dataclass(frozen=True)
class MonsterDamagedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    damage: int
    current_hp: int


@dataclass(frozen=True)
class MonsterDiedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    respawn_tick: int
    exp: int
    gold: int
    loot_table_id: str


@dataclass(frozen=True)
class MonsterRespawnedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    coordinate: dict


@dataclass(frozen=True)
class MonsterEvadedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    pass


@dataclass(frozen=True)
class MonsterHealedEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    amount: int
    current_hp: int


@dataclass(frozen=True)
class MonsterMpRecoveredEvent(BaseDomainEvent[MonsterId, "MonsterAggregate"]):
    amount: int
    current_mp: int
