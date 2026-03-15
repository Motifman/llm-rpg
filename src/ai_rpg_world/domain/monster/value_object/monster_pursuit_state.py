"""
MonsterPursuitState: モンスターの追跡状態を表す Optional[PursuitState] のラッパー。

MonsterAggregate が持つ追跡状態を値オブジェクトとしてカプセル化する。
共有 pursuit 語彙（PursuitState）を内部に保持し、不変の操作メソッドを提供する。
"""

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class MonsterPursuitState:
    """
    モンスターの追跡状態を表す値オブジェクト。
    PursuitState をラップし、Optional（追跡なし）も表現する。
    """

    pursuit: Optional[PursuitState] = None

    @property
    def has_active_pursuit(self) -> bool:
        """追跡中かどうか。"""
        return self.pursuit is not None

    @property
    def target_id(self) -> Optional[WorldObjectId]:
        """追跡対象の WorldObjectId。追跡なしなら None。"""
        if self.pursuit is None:
            return None
        return self.pursuit.target_id

    @property
    def target_snapshot(self) -> Optional[PursuitTargetSnapshot]:
        """追跡対象の現在スナップショット。追跡なしなら None。"""
        if self.pursuit is None:
            return None
        return self.pursuit.target_snapshot

    @property
    def last_known(self) -> Optional[PursuitLastKnownState]:
        """追跡対象の最後の既知状態。追跡なしなら None。"""
        if self.pursuit is None:
            return None
        return self.pursuit.last_known

    def cleared(self) -> "MonsterPursuitState":
        """追跡を解除した新しい状態を返す。"""
        return MonsterPursuitState(pursuit=None)

    def with_sync(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        target_snapshot: PursuitTargetSnapshot,
        last_known: PursuitLastKnownState,
    ) -> "MonsterPursuitState":
        """
        追跡対象を同期した新しい状態を返す。
        現在の target_snapshot と last_known を渡す。
        """
        new_pursuit = PursuitState(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=target_snapshot,
            last_known=last_known,
        )
        return MonsterPursuitState(pursuit=new_pursuit)

    def with_preserve_last_known(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        last_known: PursuitLastKnownState,
        target_snapshot: PursuitTargetSnapshot,
    ) -> "MonsterPursuitState":
        """
        最後の既知状態を更新し、target_snapshot は既存を保持（または渡されたものを使用）する。
        追跡喪失時など、target_snapshot がなく last_known のみ更新するケースで使用。
        """
        snapshot_to_use = target_snapshot
        if self.pursuit is not None and self.pursuit.target_snapshot is not None:
            snapshot_to_use = self.pursuit.target_snapshot
        new_pursuit = PursuitState(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=snapshot_to_use,
            last_known=last_known,
        )
        return MonsterPursuitState(pursuit=new_pursuit)
