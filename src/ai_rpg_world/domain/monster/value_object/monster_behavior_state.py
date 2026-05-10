"""
MonsterBehaviorState: モンスターの行動状態を表す不変の値オブジェクト。

MonsterAggregate が持つ行動関連の状態（state, target_id, last_known_position,
initial_position, patrol_index, search_timer, failure_count）をカプセル化する。
状態遷移結果の適用メソッドを提供する。
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
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
    from ai_rpg_world.domain.monster.value_object.attacker_ref import AttackerRef


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
    # Phase 4a: スポットグラフ世界用の拡張フィールド。2D 経路では使われず、
    # 既存テストやコンストラクタは defaults で構築されるので互換性を維持する。
    # `last_known_spot_id`: CHASE 中の追跡対象が最後に居た spot
    last_known_spot_id: Optional[SpotId] = None
    # `flee_until_tick`: FLEE 状態が自動解除される tick。state==FLEE のときの
    # み意味を持つ。`current_tick > flee_until_tick` で IDLE に戻す判断材料。
    flee_until_tick: Optional[WorldTick] = None
    # `chase_attacker_ref`: CHASE 中の追跡対象（player or monster）のスナップ
    # ショット。`state==CHASE` のときのみ意味を持ち、`last_attacker_ref` (集約
    # フィールド) と独立に保持される。CHASE 中に第三者から殴られても
    # `last_attacker_ref` だけが上書きされ、追跡対象はこちらの ref で維持される。
    chase_attacker_ref: Optional["AttackerRef"] = None

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

    def with_passive_state(self, state: BehaviorStateEnum) -> "MonsterBehaviorState":
        """target を持たない受動状態へ戻した新しい状態を返す。"""
        return MonsterBehaviorState(
            state=state,
            target_id=None,
            last_known_position=None,
            initial_position=self.initial_position,
            patrol_index=self.patrol_index,
            search_timer=0,
            failure_count=0,
        )

    def with_spot_flee(
        self, flee_until_tick: WorldTick
    ) -> "MonsterBehaviorState":
        """スポットグラフ世界用 FLEE 状態への遷移。

        `flee_until_tick` を指定して自動解除タイミングを設定する。
        `target_id` / `last_known_position` はクリア（逃走中はターゲットを
        持たない概念）。
        """
        return MonsterBehaviorState(
            state=BehaviorStateEnum.FLEE,
            target_id=None,
            last_known_position=None,
            initial_position=self.initial_position,
            patrol_index=self.patrol_index,
            search_timer=0,
            failure_count=0,
            last_known_spot_id=self.last_known_spot_id,
            flee_until_tick=flee_until_tick,
        )

    def with_spot_chase(
        self,
        attacker_ref: "AttackerRef",
        last_known_spot_id: SpotId,
    ) -> "MonsterBehaviorState":
        """スポットグラフ世界用 CHASE 状態への遷移。

        `attacker_ref` (追跡対象 player or monster の参照) と
        `last_known_spot_id` (最後に target を見た spot) をスナップショット
        として保持する。`last_attacker_ref` (集約フィールド) と独立に固定
        されるため、CHASE 中に第三者から殴られても追跡対象は変わらない。
        `flee_until_tick` はクリア。`target_id` フィールドは 2D 経路の
        互換性維持のため None。
        """
        return MonsterBehaviorState(
            state=BehaviorStateEnum.CHASE,
            target_id=None,
            last_known_position=None,
            initial_position=self.initial_position,
            patrol_index=self.patrol_index,
            search_timer=0,
            failure_count=0,
            last_known_spot_id=last_known_spot_id,
            flee_until_tick=None,
            chase_attacker_ref=attacker_ref,
        )

    def with_spot_idle(self) -> "MonsterBehaviorState":
        """IDLE への手動リセット（FLEE / CHASE が解除条件を満たした際）。

        `last_known_spot_id` / `flee_until_tick` / `chase_attacker_ref` を
        全てクリアする。
        """
        return MonsterBehaviorState(
            state=BehaviorStateEnum.IDLE,
            target_id=None,
            last_known_position=None,
            initial_position=self.initial_position,
            patrol_index=self.patrol_index,
            search_timer=0,
            failure_count=0,
            last_known_spot_id=None,
            flee_until_tick=None,
            chase_attacker_ref=None,
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
