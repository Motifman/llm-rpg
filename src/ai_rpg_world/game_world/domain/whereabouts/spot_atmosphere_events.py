from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.domain.declaration.spot import SpotAtmosphere
from ai_rpg_world.game_world.domain.value_object import SpotId, WorldId


@final
@dataclass(frozen=True, kw_only=True)
class SpotAtmosphereChangedEvent(DomainEvent):
    world_id: WorldId
    spot: SpotId
    before: SpotAtmosphere
    after: SpotAtmosphere
