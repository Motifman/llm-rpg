from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Protocol, TypeVar, Generic, Any, Optional
import uuid

from ai_rpg_world.domain.common.value_object import WorldTick

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
    occurred_tick: Optional[WorldTick] = field(default=None, kw_only=True)

    @classmethod
    def create(cls, aggregate_id: AggregateId, aggregate_type: AggregateType, **kwargs: Any) -> 'BaseDomainEvent[AggregateId, AggregateType]':
        # tz-aware UTC で発行 (Issue #311 後続: #300 の取りこぼし回帰修正)。
        # ドメインイベントは observation pipeline / chunk_coordinator の
        # occurred_at 比較で aware と混ざるため、発生源を統一する。
        event_id = uuid.uuid4().int
        occurred_at = datetime.now(timezone.utc)
        return cls(event_id, occurred_at, aggregate_id, aggregate_type, **kwargs)


# 後方互換のため BaseDomainEvent[Any, Any] の型エイリアスを提供
DomainEvent = BaseDomainEvent[Any, Any]