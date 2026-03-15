"""
モンスターの行動状態遷移規則を集約する純粋なドメインサービス。
record_attacked_by、apply_behavior_transition、apply_territory_return_if_needed の
状態変更ルールを一箇所に集約する。

イベントは集約内で生成する（DDD）ため、本サービスは「適用すべき遷移」のみを返す。
リポジトリに依存しない。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Literal

from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum, EcologyTypeEnum
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    StateTransitionResult,
    SpotTargetParams,
)


@dataclass(frozen=True)
class AttackedTransitionResult:
    """被弾時（record_attacked_by）の遷移結果。"""

    no_transition: bool = False
    """True の場合、呼び出し元は何も変更しない（PATROL_ONLY または AMBUSH 範囲外）。"""

    new_state: Optional[BehaviorStateEnum] = None
    new_target_id: Optional[WorldObjectId] = None
    new_last_known_position: Optional[Coordinate] = None
    clear_pursuit: bool = False
    sync_pursuit: bool = False


@dataclass
class EventSpec:
    """発行すべきイベントの仕様。集約が実際のイベントを生成する。"""

    kind: Literal["target_spotted", "target_lost", "actor_state_changed"]
    target_id: Optional[WorldObjectId] = None
    coordinate: Optional[Coordinate] = None
    last_known_coordinate: Optional[Coordinate] = None
    old_state: Optional[BehaviorStateEnum] = None
    new_state: Optional[BehaviorStateEnum] = None


@dataclass
class TransitionApplicationOutput:
    """apply_behavior_transition の適用結果。"""

    final_state: BehaviorStateEnum
    final_target_id: Optional[WorldObjectId] = None
    final_last_known_position: Optional[Coordinate] = None
    clear_pursuit: bool = False
    sync_pursuit: Optional[tuple[WorldObjectId, Coordinate]] = None
    preserve_pursuit_last_known: Optional[tuple[WorldObjectId, Coordinate]] = None
    events: List[EventSpec] = field(default_factory=list)


class MonsterBehaviorStateMachine:
    """
    モンスターの行動状態遷移規則を集約する純粋なドメインサービス。
    record_attacked_by と apply_behavior_transition のルールを一元化する。
    """

    def compute_attacked_transition(
        self,
        attacker_id: WorldObjectId,
        attacker_coordinate: Coordinate,
        ecology_type: EcologyTypeEnum,
        hp_percentage: float,
        effective_flee_threshold: float,
        allow_chase: bool,
        current_behavior_state: BehaviorStateEnum,
        behavior_initial_position: Optional[Coordinate],
        ambush_chase_range: Optional[int],
    ) -> AttackedTransitionResult:
        """
        被弾時の遷移を計算する。
        生態タイプ・成長段階に応じて CHASE / FLEE 等を返す。
        """
        if ecology_type == EcologyTypeEnum.PATROL_ONLY:
            return AttackedTransitionResult(no_transition=True)

        if ecology_type == EcologyTypeEnum.FLEE_ONLY:
            return AttackedTransitionResult(
                new_state=BehaviorStateEnum.FLEE,
                new_target_id=attacker_id,
                new_last_known_position=attacker_coordinate,
                clear_pursuit=True,
                sync_pursuit=False,
            )

        if (
            ecology_type == EcologyTypeEnum.AMBUSH
            and behavior_initial_position is not None
            and ambush_chase_range is not None
        ):
            if (
                behavior_initial_position.distance_to(attacker_coordinate)
                > ambush_chase_range
            ):
                return AttackedTransitionResult(no_transition=True)

        if hp_percentage <= effective_flee_threshold:
            return AttackedTransitionResult(
                new_state=BehaviorStateEnum.FLEE,
                new_target_id=attacker_id,
                new_last_known_position=attacker_coordinate,
                clear_pursuit=True,
                sync_pursuit=False,
            )

        if allow_chase and current_behavior_state != BehaviorStateEnum.ENRAGE:
            return AttackedTransitionResult(
                new_state=BehaviorStateEnum.CHASE,
                new_target_id=attacker_id,
                new_last_known_position=attacker_coordinate,
                clear_pursuit=False,
                sync_pursuit=True,
            )

        return AttackedTransitionResult(
            new_state=current_behavior_state,
            new_target_id=attacker_id,
            new_last_known_position=attacker_coordinate,
            clear_pursuit=False,
            sync_pursuit=True,
        )

    def apply_transition(
        self,
        result: StateTransitionResult,
        current_state: BehaviorStateEnum,
        current_target_id: Optional[WorldObjectId],
        current_last_known_position: Optional[Coordinate],
        hp_percentage: float,
        effective_flee_threshold: float,
        allow_chase: bool,
    ) -> TransitionApplicationOutput:
        """
        StateTransitionResult を適用した結果を返す。
        集約はこの出力に従って状態を更新し、イベントを発行する。
        """
        old_state = current_state

        if result.apply_enrage:
            old_state = current_state
            current_state = BehaviorStateEnum.ENRAGE
            events: List[EventSpec] = [
                EventSpec(
                    kind="actor_state_changed",
                    old_state=old_state,
                    new_state=BehaviorStateEnum.ENRAGE,
                )
            ]
        else:
            events = []

        if (
            result.flee_from_threat_id is not None
            and result.flee_from_threat_coordinate is not None
        ):
            current_state = BehaviorStateEnum.FLEE
            current_target_id = result.flee_from_threat_id
            current_last_known_position = result.flee_from_threat_coordinate
            events.append(
                EventSpec(
                    kind="target_spotted",
                    target_id=result.flee_from_threat_id,
                    coordinate=result.flee_from_threat_coordinate,
                )
            )
            if not result.apply_enrage:
                events.append(
                    EventSpec(
                        kind="actor_state_changed",
                        old_state=old_state,
                        new_state=BehaviorStateEnum.FLEE,
                    )
                )
            old_state = BehaviorStateEnum.FLEE

        if result.spot_target_params is not None:
            params = result.spot_target_params
            current_target_id = params.target_id
            current_last_known_position = params.coordinate
            effective_flee = (
                params.effective_flee_threshold
                if params.effective_flee_threshold is not None
                else effective_flee_threshold
            )
            allow = (
                params.allow_chase if params.allow_chase is not None else allow_chase
            )
            if hp_percentage <= effective_flee:
                current_state = BehaviorStateEnum.FLEE
                clear_pursuit = True
                sync_pursuit = None
                preserve_pursuit_last_known = None
            elif allow and current_state != BehaviorStateEnum.ENRAGE:
                current_state = BehaviorStateEnum.CHASE
                clear_pursuit = False
                sync_pursuit = (params.target_id, params.coordinate)
                preserve_pursuit_last_known = None
            else:
                clear_pursuit = False
                sync_pursuit = None
                preserve_pursuit_last_known = None

            events.append(
                EventSpec(
                    kind="target_spotted",
                    target_id=params.target_id,
                    coordinate=params.coordinate,
                )
            )
            if old_state != current_state:
                events.append(
                    EventSpec(
                        kind="actor_state_changed",
                        old_state=old_state,
                        new_state=current_state,
                    )
                )
            old_state = current_state

            return TransitionApplicationOutput(
                final_state=current_state,
                final_target_id=current_target_id,
                final_last_known_position=current_last_known_position,
                clear_pursuit=clear_pursuit,
                sync_pursuit=sync_pursuit,
                preserve_pursuit_last_known=preserve_pursuit_last_known,
                events=events,
            )

        if result.do_lose_target:
            retained_target_id = result.lost_target_id or current_target_id
            retained_last_known = (
                result.last_known_coordinate or current_last_known_position
            )
            if current_state in (
                BehaviorStateEnum.CHASE,
                BehaviorStateEnum.ENRAGE,
            ):
                current_state = BehaviorStateEnum.SEARCH
                if (
                    retained_target_id is not None
                    and retained_last_known is not None
                ):
                    preserve_pursuit_last_known = (
                        retained_target_id,
                        retained_last_known,
                    )
                else:
                    preserve_pursuit_last_known = None
                sync_pursuit = None
                current_target_id = retained_target_id
                current_last_known_position = retained_last_known
            elif current_state == BehaviorStateEnum.FLEE:
                current_state = BehaviorStateEnum.RETURN
                preserve_pursuit_last_known = None
                sync_pursuit = None
                current_target_id = None
                current_last_known_position = None
            else:
                preserve_pursuit_last_known = None
                sync_pursuit = None
                current_target_id = retained_target_id
                current_last_known_position = retained_last_known

            if retained_target_id is not None and retained_last_known is not None:
                events.append(
                    EventSpec(
                        kind="target_lost",
                        target_id=retained_target_id,
                        last_known_coordinate=retained_last_known,
                    )
                )
            if old_state != current_state:
                events.append(
                    EventSpec(
                        kind="actor_state_changed",
                        old_state=old_state,
                        new_state=current_state,
                    )
                )

            return TransitionApplicationOutput(
                final_state=current_state,
                final_target_id=current_target_id,
                final_last_known_position=current_last_known_position,
                clear_pursuit=(current_state == BehaviorStateEnum.RETURN),
                sync_pursuit=sync_pursuit,
                preserve_pursuit_last_known=preserve_pursuit_last_known,
                events=events,
            )

        if result.apply_enrage or (
            result.flee_from_threat_id is not None
            and result.flee_from_threat_coordinate is not None
        ):
            return TransitionApplicationOutput(
                final_state=current_state,
                final_target_id=current_target_id,
                final_last_known_position=current_last_known_position,
                clear_pursuit=(
                    result.flee_from_threat_id is not None
                    and result.flee_from_threat_coordinate is not None
                ),
                sync_pursuit=None,
                preserve_pursuit_last_known=None,
                events=events,
            )

        return TransitionApplicationOutput(
            final_state=current_state,
            final_target_id=current_target_id,
            final_last_known_position=current_last_known_position,
            clear_pursuit=False,
            sync_pursuit=None,
            preserve_pursuit_last_known=None,
            events=events,
        )

    def should_return_to_territory(
        self,
        actor_coordinate: Coordinate,
        behavior_initial_position: Optional[Coordinate],
        territory_radius: Optional[int],
        current_state: BehaviorStateEnum,
    ) -> bool:
        """
        テリトリを超えていたら True を返す。
        CHASE / ENRAGE のときのみ判定する。
        """
        if territory_radius is None or territory_radius <= 0:
            return False
        if behavior_initial_position is None:
            return False
        if current_state not in (
            BehaviorStateEnum.CHASE,
            BehaviorStateEnum.ENRAGE,
        ):
            return False
        return (
            actor_coordinate.euclidean_distance_to(behavior_initial_position)
            > float(territory_radius)
        )
