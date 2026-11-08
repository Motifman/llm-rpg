from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.domain.value_object import PassageId, PassageStateName, WorldId


@final
@dataclass(frozen=True, kw_only=True)
class PassageStateChangedEvent(DomainEvent):
    world_id: WorldId
    passage: PassageId
    before: PassageStateName
    after: PassageStateName


@final
@dataclass(frozen=True, kw_only=True)
class PassageRevealedEvent(DomainEvent):
    world_id: WorldId
    passage: PassageId


@final
@dataclass(frozen=True, kw_only=True)
class PassageRemovedEvent(DomainEvent):
    world_id: WorldId
    passage: PassageId


PassageStatesEvent = PassageStateChangedEvent | PassageRevealedEvent | PassageRemovedEvent
