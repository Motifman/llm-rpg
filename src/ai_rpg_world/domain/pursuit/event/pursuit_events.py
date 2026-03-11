from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class PursuitStartedEvent(BaseDomainEvent[WorldObjectId, str]):
    """追跡開始時のドメインイベント。"""

    actor_id: WorldObjectId
    target_id: WorldObjectId
    target_snapshot: PursuitTargetSnapshot
    last_known: PursuitLastKnownState


@dataclass(frozen=True)
class PursuitUpdatedEvent(BaseDomainEvent[WorldObjectId, str]):
    """追跡判断に意味のある変化があったことを表すイベント。"""

    actor_id: WorldObjectId
    target_id: WorldObjectId
    last_known: PursuitLastKnownState
    target_snapshot: Optional[PursuitTargetSnapshot] = None


@dataclass(frozen=True)
class PursuitFailedEvent(BaseDomainEvent[WorldObjectId, str]):
    """追跡が失敗で終了したことを表すイベント。"""

    actor_id: WorldObjectId
    target_id: WorldObjectId
    failure_reason: PursuitFailureReason
    last_known: PursuitLastKnownState
    target_snapshot: Optional[PursuitTargetSnapshot] = None


@dataclass(frozen=True)
class PursuitCancelledEvent(BaseDomainEvent[WorldObjectId, str]):
    """追跡が明示的に中断されたことを表すイベント。"""

    actor_id: WorldObjectId
    target_id: WorldObjectId
    last_known: PursuitLastKnownState
    target_snapshot: Optional[PursuitTargetSnapshot] = None
