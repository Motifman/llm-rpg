from ai_rpg_world.domain.common.domain_event import DomainEvent
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class PlayerMovedEvent(DomainEvent):
    player_id: int
    from_spot_id: int
    to_spot_id: int