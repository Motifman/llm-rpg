import uuid
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from src.domain.common.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class PlayerSpokeEvent(DomainEvent):
    sender_id: int
    content: str
    recipient_id: Optional[int] = None
    
    @classmethod
    def create(cls, sender_id: int, content: str, recipient_id: Optional[int] = None):
        return cls(
            event_id=int(uuid.uuid4()),
            occurred_at=datetime.now(),
            aggregate_id=sender_id,
            aggregate_type="Player",
            sender_id=sender_id,
            content=content,
            recipient_id=recipient_id
        )