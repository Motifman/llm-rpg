"""
モンスターの行動状態遷移ルールを一箇所にまとめる純粋なドメインサービス。
観測＋現在状態スナップショットを入力に「適用する遷移＋発行するイベント」を返す。
リポジトリ・Map 集約に依存しない。Phase 3 で Monster.decide からも同じサービスを呼ぶ。
"""

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import BehaviorStateEnum
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.world.event.behavior_events import (
    ActorStateChangedEvent,
    TargetSpottedEvent,
    TargetLostEvent,
)
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
    状態遷移の適用内容と発行するイベント。
    呼び出し元（Strategy または Monster.decide）が component / 自身に反映し、events を event_sink / add_event する。
    """
    apply_enrage: bool = False
    flee_from_threat_id: Optional[WorldObjectId] = None
    flee_from_threat_coordinate: Optional[Coordinate] = None
    spot_target_params: Optional[SpotTargetParams] = None
    do_lose_target: bool = False
    lost_target_id: Optional[WorldObjectId] = None
    last_known_coordinate: Optional[Coordinate] = None
    events: List[DomainEvent] = field(default_factory=list)


class BehaviorStateTransitionService:
    """
    観測と現在状態から「どの遷移を適用するか」と「発行するイベント」を返す純粋なドメインサービス。
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
        観測と現在状態に基づき、適用する遷移とイベントを返す。
        呼び出し元は返り値に従って component（または Monster）を更新し、events を event_sink に追加する。
        """
        result = StateTransitionResult()
        old_state = snapshot.state

        # 0. ボスフェーズ: HP が閾値以下なら ENRAGE へ遷移
        if snapshot.phase_thresholds and snapshot.hp_percentage <= snapshot.phase_thresholds[0]:
            if snapshot.state not in (BehaviorStateEnum.ENRAGE, BehaviorStateEnum.FLEE):
                result.apply_enrage = True
                result.events = list(result.events)
                result.events.append(
                    ActorStateChangedEvent.create(
                        aggregate_id=actor_id,
                        aggregate_type="Actor",
                        actor_id=actor_id,
                        old_state=old_state,
                        new_state=BehaviorStateEnum.ENRAGE,
                    )
                )
                old_state = BehaviorStateEnum.ENRAGE

        # 1a. 視界内に脅威(THREAT)がいれば FLEE に遷移
        if observation.visible_threats and snapshot.state != BehaviorStateEnum.FLEE:
            nearest = min(
                observation.visible_threats,
                key=lambda obj: actor_coordinate.euclidean_distance_to(obj.coordinate),
            )
            result.flee_from_threat_id = nearest.object_id
            result.flee_from_threat_coordinate = nearest.coordinate
            result.events = list(result.events)
            result.events.append(
                TargetSpottedEvent.create(
                    aggregate_id=actor_id,
                    aggregate_type="Actor",
                    actor_id=actor_id,
                    target_id=nearest.object_id,
                    coordinate=nearest.coordinate,
                )
            )
            if not result.apply_enrage:
                result.events.append(
                    ActorStateChangedEvent.create(
                        aggregate_id=actor_id,
                        aggregate_type="Actor",
                        actor_id=actor_id,
                        old_state=old_state,
                        new_state=BehaviorStateEnum.FLEE,
                    )
                )
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
            # 状態変化と TargetSpotted は呼び出し元が component.spot_target 後に old_state != new_state で出す。
            # ここでは spot_target の結果状態がわからないので、イベントは呼び出し元で出す方針にする。
            # ただし計画では「サービスがイベントを返す」なので、spot 時もイベントを返す。
            # spot_target は component 側で FLEE/CHASE 等を決めるため、サービスは「TargetSpotted は出す」とし、
            # ActorStateChanged は呼び出し元が component 更新後に出す（既存 Strategy と同じ）。
            result.events = list(result.events)
            result.events.append(
                TargetSpottedEvent.create(
                    aggregate_id=actor_id,
                    aggregate_type="Actor",
                    actor_id=actor_id,
                    target_id=observation.selected_target.object_id,
                    coordinate=observation.selected_target.coordinate,
                )
            )
            return result

        # 2. ターゲットなしで既にターゲットを持っていたら lose_target
        if not observation.visible_threats and not observation.selected_target and snapshot.target_id:
            result.do_lose_target = True
            result.lost_target_id = snapshot.target_id
            result.last_known_coordinate = snapshot.last_known_target_position
            result.events = list(result.events)
            if snapshot.last_known_target_position:
                result.events.append(
                    TargetLostEvent.create(
                        aggregate_id=actor_id,
                        aggregate_type="Actor",
                        actor_id=actor_id,
                        target_id=snapshot.target_id,
                        last_known_coordinate=snapshot.last_known_target_position,
                    )
                )
            # ActorStateChanged は lose_target による状態変化なので、呼び出し元が component 更新後に出す
            return result

        return result
