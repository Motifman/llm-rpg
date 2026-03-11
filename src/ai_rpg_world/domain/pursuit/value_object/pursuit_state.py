from dataclasses import dataclass
from typing import Optional

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
class PursuitState:
    """静的移動とは独立した追跡状態。"""

    actor_id: WorldObjectId
    target_id: WorldObjectId
    target_snapshot: Optional[PursuitTargetSnapshot] = None
    last_known: Optional[PursuitLastKnownState] = None
    failure_reason: Optional[PursuitFailureReason] = None

    def __post_init__(self) -> None:
        if self.target_snapshot is None and self.last_known is None:
            raise ValueError("PursuitState requires target_snapshot or last_known state.")

        if self.target_snapshot is not None and self.target_snapshot.target_id != self.target_id:
            raise ValueError("target_snapshot target_id must match PursuitState target_id.")

        if self.last_known is not None and self.last_known.target_id != self.target_id:
            raise ValueError("last_known target_id must match PursuitState target_id.")

    @property
    def has_target_snapshot(self) -> bool:
        """現在の対象スナップショットを保持しているかを返す。"""
        return self.target_snapshot is not None

    @property
    def is_failed(self) -> bool:
        """失敗状態かどうかを返す。"""
        return self.failure_reason is not None
