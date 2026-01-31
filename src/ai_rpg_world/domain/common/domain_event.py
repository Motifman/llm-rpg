from abc import ABC
from datetime import datetime
from dataclasses import dataclass
from typing import Protocol, TypeVar, Generic, Any
import uuid

# 既存のDomainEvent（変更なし）
@dataclass(frozen=True)
class DomainEvent(ABC):
    """ドメインイベントの基底クラス"""
    event_id: int
    occurred_at: datetime
    aggregate_id: int
    aggregate_type: str
    event_version: int = 1

    @classmethod
    def create(cls, aggregate_id: int, aggregate_type: str, **kwargs):
        return cls(
            event_id=int(uuid.uuid4()),
            occurred_at=datetime.now(),
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            **kwargs
        )

# 集約IDの型変数
AggregateId = TypeVar('AggregateId')
AggregateType = TypeVar('AggregateType')

class DomainEventProtocol(Protocol[AggregateId, AggregateType]):
    """ドメインイベントのプロトコル"""
    event_id: str
    occurred_at: datetime
    aggregate_id: AggregateId
    aggregate_type: AggregateType

    @classmethod
    def create(cls, aggregate_id: AggregateId, aggregate_type: AggregateType, **kwargs: Any) -> 'DomainEventProtocol[AggregateId, AggregateType]':
        ...


@dataclass(frozen=True)
class BaseDomainEvent(Generic[AggregateId, AggregateType]):
    """ドメインイベントの基底クラス（新設計）"""
    event_id: int 
    occurred_at: datetime
    aggregate_id: AggregateId
    aggregate_type: AggregateType

    @classmethod
    def create(cls, aggregate_id: AggregateId, aggregate_type: AggregateType, **kwargs: Any) -> 'BaseDomainEvent[AggregateId, AggregateType]':
        event_id = int(uuid.uuid4())
        occurred_at = datetime.now()
        return cls(event_id, occurred_at, aggregate_id, aggregate_type, **kwargs)