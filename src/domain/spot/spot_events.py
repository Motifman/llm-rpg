from src.domain.common.domain_event import DomainEvent
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class PlayerEnteredSpotEvent(DomainEvent):
    player_id: int
    spot_id: int


@dataclass(frozen=True, kw_only=True)
class PlayerExitedSpotEvent(DomainEvent):
    player_id: int
    spot_id: int