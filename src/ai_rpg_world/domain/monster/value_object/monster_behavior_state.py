"""
MonsterBehaviorState: モンスターの行動状態を表す不変の値オブジェクト。

MonsterAggregate が持つ行動関連の状態（state, target_id, last_known_position,
initial_position, patrol_index, search_timer, failure_count）をカプセル化する。
状態遷移結果の適用メソッドを提供する。
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterStatsValidationException,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.service.monster_behavior_state_machine import (
        AttackedTransitionResult,
        TransitionApplicationOutput,
    )


@dataclass(frozen=True)
class MonsterBehaviorState:
    """
    モンスターの行動状態を表す値オブジェクト。
    不変。変更時は新しいインスタンスを返す。
    """

    state: BehaviorStateEnum
    target_id: Optional[WorldObjectId]
    last_known_position: Optional[Coordinate]
    initial_position: Optional[Coordinate]
    patrol_index: int
    search_timer: int
    failure_count: int

    def __post_init__(self) -> None:
        if self.patrol_index < 0:
            raise MonsterStatsValidationException(
                f"patrol_index cannot be negative: {self.patrol_index}"
            )
        if self.search_timer < 0:
            raise MonsterStatsValidationException(
                f"search_timer cannot be negative: {self.search_timer}"
            )
        if self.failure_count < 0:
            raise MonsterStatsValidationException(
                f"failure_count cannot be negative: {self.failure_count}"
            )

    @classmethod
    def create_idle(
        cls,
        initial_position: Optional[Coordinate] = None,
    ) -> "MonsterBehaviorState":
        """IDLE 状態の初期値を作成する（スポーン/リスポーン時）。"""
        return cls(
            state=BehaviorStateEnum.IDLE,
            target_id=None,
            last_known_position=None,
            initial_position=initial_position,
            patrol_index=0,
            search_timer=0,
            failure_count=0,
        )

    @classmethod
    def from_parts(
        cls,
        state: BehaviorStateEnum,
        target_id: Optional[WorldObjectId],
        last_known_position: Optional[Coordinate],
        initial_position: Optional[Coordinate],
        patrol_index: int = 0,
        search_timer: int = 0,
        failure_count: int = 0,
    ) -> "MonsterBehaviorState":
        """個別フィールドから値を組み立てて構築する（永続化層・テスト用）。"""
        return cls(
            state=state,
            target_id=target_id,
            last_known_position=last_known_position,
            initial_position=initial_position,
            patrol_index=max(0, patrol_index),
            search_timer=max(0, search_timer),
            failure_count=max(0, failure_count),
        )

    def with_attacked(
        self,
        transition: "AttackedTransitionResult",
    ) -> "MonsterBehaviorState":
        """
        被弾時の遷移結果を適用した新しい状態を返す。
        no_transition の場合は self を返す。
        """
        if transition.no_transition:
            return self
        return MonsterBehaviorState(
            state=transition.new_state or self.state,
            target_id=transition.new_target_id,
            last_known_position=transition.new_last_known_position,
            initial_position=self.initial_position,
            patrol_index=self.patrol_index,
            search_timer=self.search_timer,
            failure_count=self.failure_count,
        )

    def with_transition(
        self,
        output: "TransitionApplicationOutput",
    ) -> "MonsterBehaviorState":
        """apply_behavior_transition の結果を適用した新しい状態を返す。"""
        return MonsterBehaviorState(
            state=output.final_state,
            target_id=output.final_target_id,
            last_known_position=output.final_last_known_position,
            initial_position=self.initial_position,
            patrol_index=self.patrol_index,
            search_timer=self.search_timer,
            failure_count=self.failure_count,
        )

    def with_territory_return(self) -> "MonsterBehaviorState":
        """テリトリ復帰（RETURN）に遷移した新しい状態を返す。"""
        return MonsterBehaviorState(
            state=BehaviorStateEnum.RETURN,
            target_id=None,
            last_known_position=None,
            initial_position=self.initial_position,
            patrol_index=self.patrol_index,
            search_timer=self.search_timer,
            failure_count=self.failure_count,
        )

    def with_spawn_reset(
        self,
        initial_position: Coordinate,
    ) -> "MonsterBehaviorState":
        """スポーン/リスポーン時のリセットを適用した新しい状態を返す。"""
        return MonsterBehaviorState.create_idle(initial_position=initial_position)

    def with_target_cleared(self) -> "MonsterBehaviorState":
        """target_id と last_known_position をクリアした新しい状態を返す（fail_pursuit 等）。"""
        return MonsterBehaviorState(
            state=self.state,
            target_id=None,
            last_known_position=None,
            initial_position=self.initial_position,
            patrol_index=self.patrol_index,
            search_timer=self.search_timer,
            failure_count=self.failure_count,
        )

    def advance_patrol_index(self, patrol_points_count: int) -> "MonsterBehaviorState":
        """パトロール点に到達したときにインデックスを進めた新しい状態を返す。"""
        if patrol_points_count <= 0:
            return self
        new_index = (self.patrol_index + 1) % patrol_points_count
        return MonsterBehaviorState(
            state=self.state,
            target_id=self.target_id,
            last_known_position=self.last_known_position,
            initial_position=self.initial_position,
            patrol_index=new_index,
            search_timer=self.search_timer,
            failure_count=self.failure_count,
        )
