"""
PlayerPursuitState: プレイヤーの追跡状態を表す Optional[PursuitState] のラッパー。

PlayerStatusAggregate が持つ追跡状態を値オブジェクトとしてカプセル化する。
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
class PlayerPursuitState:
    """
    プレイヤーの追跡状態を表す値オブジェクト。
    PursuitState をラップし、Optional（追跡なし）も表現する。
    """

    pursuit: Optional[PursuitState] = None

    @classmethod
    def empty(cls) -> "PlayerPursuitState":
        """初期状態（追跡なし）を作成する。"""
        return cls(pursuit=None)

    @classmethod
    def from_parts(cls, pursuit: Optional[PursuitState] = None) -> "PlayerPursuitState":
        """個別フィールドから構築する（永続化層・テスト用）。"""
        return cls(pursuit=pursuit)

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

    def cleared(self) -> "PlayerPursuitState":
        """追跡を解除した新しい状態を返す。"""
        return PlayerPursuitState(pursuit=None)

    def with_started(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        target_snapshot: PursuitTargetSnapshot,
        last_known: PursuitLastKnownState,
    ) -> "PlayerPursuitState":
        """
        追跡を開始した新しい状態を返す。
        """
        new_pursuit = PursuitState(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=target_snapshot,
            last_known=last_known,
        )
        return PlayerPursuitState(pursuit=new_pursuit)

    def with_updated(
        self,
        target_snapshot: Optional[PursuitTargetSnapshot],
        last_known: PursuitLastKnownState,
    ) -> "PlayerPursuitState":
        """
        追跡対象を更新した新しい状態を返す。
        追跡中でない場合は ValueError を送出する。
        target_snapshot が None のときは現在の target_snapshot を保持する。
        変更がなければ self を返す（同一インスタンス）。
        """
        if self.pursuit is None:
            raise ValueError("Cannot update pursuit when no active pursuit exists.")
        next_snapshot = (
            target_snapshot if target_snapshot is not None else self.pursuit.target_snapshot
        )
        next_pursuit = PursuitState(
            actor_id=self.pursuit.actor_id,
            target_id=self.pursuit.target_id,
            target_snapshot=next_snapshot,
            last_known=last_known,
        )
        if next_pursuit == self.pursuit:
            return self
        return PlayerPursuitState(pursuit=next_pursuit)
