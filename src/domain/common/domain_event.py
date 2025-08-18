from abc import ABC
from datetime import datetime
from dataclasses import dataclass
import uuid


@dataclass(frozen=True)
class DomainEvent(ABC):
    """ドメインイベントの基底クラス"""
    event_id: int
    occurred_at: datetime
    aggregate_id: str
    aggregate_type: str
    event_version: int = 1
    
    @classmethod
    def create(cls, aggregate_id: str, aggregate_type: str, **kwargs):
        return cls(
            event_id=int(uuid.uuid4()),
            occurred_at=datetime.now(),
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            **kwargs
        )
