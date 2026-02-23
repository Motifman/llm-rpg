"""
モンスターの行動状態遷移ルールを一箇所にまとめる純粋なドメインサービス。
観測＋現在状態スナップショットを入力に「適用する遷移」のみを返す。
イベントは集約内で生成する（DDD）ため、本サービスはイベントを返さない。
リポジトリ・Map 集約に依存しない。Monster.decide および Strategy（非モンスター用）から呼ぶ。
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.monster.value_object.behavior_state_snapshot import BehaviorStateSnapshot

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
    from ai_rpg_world.domain.world.entity.world_object import WorldObject


@dataclass(frozen=True)
class SpotTargetParams:
    """spot_target を適用する際のパラメータ。"""
    target_id: WorldObjectId
    coordinate: Coordinate
    effective_flee_threshold: Optional[float] = None
    allow_chase: Optional[bool] = None


@dataclass
class StateTransitionResult:
    """
    状態遷移の適用内容のみ。イベントは呼び出し元（Strategy または Monster.decide）が
    適用結果に応じて集約内で生成・add_event する。
    """
    apply_enrage: bool = False
    flee_from_threat_id: Optional[WorldObjectId] = None
    flee_from_threat_coordinate: Optional[Coordinate] = None
    spot_target_params: Optional[SpotTargetParams] = None
    do_lose_target: bool = False
    lost_target_id: Optional[WorldObjectId] = None
    last_known_coordinate: Optional[Coordinate] = None


class BehaviorStateTransitionService:
    """
    観測と現在状態から「どの遷移を適用するか」のみを返す純粋なドメインサービス。
    イベントは呼び出し元（Monster 集約内または Strategy 適用後）で生成する。
    モンスターの振る舞いの責務のため Monster ドメインに配置する。
    """

    def compute_transition(
        self,
        observation: "BehaviorObservation",
        snapshot: BehaviorStateSnapshot,
        actor_id: WorldObjectId,
        actor_coordinate: Coordinate,
    ) -> StateTransitionResult:
        """
        観測と現在状態に基づき、適用する遷移のみを返す。
        呼び出し元は返り値に従って component（または Monster）を更新し、
        適用した内容に応じてイベントを集約内で生成・add_event する。
        """
        result = StateTransitionResult()
        old_state = snapshot.state

        # 0. ボスフェーズ: HP が閾値以下なら ENRAGE へ遷移
        if snapshot.phase_thresholds and snapshot.hp_percentage <= snapshot.phase_thresholds[0]:
            if snapshot.state not in (BehaviorStateEnum.ENRAGE, BehaviorStateEnum.FLEE):
                result.apply_enrage = True
                old_state = BehaviorStateEnum.ENRAGE

        # 1a. 視界内に脅威(THREAT)がいれば FLEE に遷移
        if observation.visible_threats and snapshot.state != BehaviorStateEnum.FLEE:
            nearest = min(
                observation.visible_threats,
                key=lambda obj: actor_coordinate.euclidean_distance_to(obj.coordinate),
            )
            result.flee_from_threat_id = nearest.object_id
            result.flee_from_threat_coordinate = nearest.coordinate
            return result

        # 1b. 脅威でない場合は渡されたターゲットで spot_target
        if observation.selected_target and snapshot.state != BehaviorStateEnum.FLEE:
            effective_flee = (
                observation.growth_context.effective_flee_threshold
                if observation.growth_context else None
            )
            allow_chase = (
                observation.growth_context.allow_chase
                if observation.growth_context else None
            )
            result.spot_target_params = SpotTargetParams(
                target_id=observation.selected_target.object_id,
                coordinate=observation.selected_target.coordinate,
                effective_flee_threshold=effective_flee,
                allow_chase=allow_chase,
            )
            return result

        # 2. ターゲットなしで既にターゲットを持っていたら lose_target
        if not observation.visible_threats and not observation.selected_target and snapshot.target_id:
            result.do_lose_target = True
            result.lost_target_id = snapshot.target_id
            result.last_known_coordinate = snapshot.last_known_target_position
            return result

        return result
