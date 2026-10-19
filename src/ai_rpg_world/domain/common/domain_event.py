import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, Protocol, TypeVar

from ai_rpg_world.domain.common.value_object import WorldTick

# 集約IDの型変数
AggregateId = TypeVar('AggregateId')
AggregateType = TypeVar('AggregateType')
SelfEvent = TypeVar('SelfEvent', bound='BaseDomainEvent[Any, Any]')

class DomainEventProtocol(Protocol[AggregateId, AggregateType]):
    """ドメインイベントのプロトコル"""
    event_id: int
    occurred_at: datetime
    aggregate_id: AggregateId
    aggregate_type: str

    @classmethod
    def create(
        cls, aggregate_id: AggregateId, aggregate_type: str, **kwargs: Any
    ) -> 'DomainEventProtocol[AggregateId, AggregateType]':
        ...


@dataclass(frozen=True)
class BaseDomainEvent(Generic[AggregateId, AggregateType]):
    """ドメインイベントの基底クラス（新設計）"""
    event_id: int 
    occurred_at: datetime
    aggregate_id: AggregateId
    # 実際に入るのは集約のクラス名の文字列。型引数 AggregateType は
    # 「このイベントがどの集約のものか」を宣言側に残すための印で、
    # この属性の型ではない。
    aggregate_type: str
    occurred_tick: WorldTick | None = field(default=None, kw_only=True)

    @classmethod
    def create(
        cls: type[SelfEvent], aggregate_id: Any, aggregate_type: str, **kwargs: Any
    ) -> SelfEvent:
        # tz-aware UTC で発行 (Issue #311 後続: #300 の取りこぼし回帰修正)。
        # ドメインイベントは observation pipeline の occurred_at 比較で
        # aware と混ざるため、発生源を統一する。
        event_id = uuid.uuid4().int
        occurred_at = datetime.now(timezone.utc)
        return cls(event_id, occurred_at, aggregate_id, aggregate_type, **kwargs)


# 後方互換のため BaseDomainEvent[Any, Any] の型エイリアスを提供
DomainEvent = BaseDomainEvent[Any, Any]