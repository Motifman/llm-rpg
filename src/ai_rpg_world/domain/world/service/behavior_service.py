import math
from typing import Optional, List, Callable
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.behavior_context import (
    TargetSelectionContext,
    SkillSelectionContext,
)
from ai_rpg_world.domain.world.enum.world_enum import BehaviorStateEnum, DirectionEnum, BehaviorActionType
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.hostility_service import HostilityService, ConfigurableHostilityService
from ai_rpg_world.domain.world.service.allegiance_service import AllegianceService
from ai_rpg_world.domain.world.service.target_selection_policy import (
    TargetSelectionPolicy,
    NearestTargetPolicy,
    HighestThreatTargetPolicy,
)
from ai_rpg_world.domain.world.service.skill_selection_policy import SkillSelectionPolicy, FirstInRangeSkillPolicy
from ai_rpg_world.domain.world.service.behavior_strategy import (
    BehaviorStrategy,
    DefaultBehaviorStrategy,
    BossBehaviorStrategy,
)
from ai_rpg_world.domain.world.event.behavior_events import (
    ActorStateChangedEvent,
    TargetSpottedEvent,
    TargetLostEvent,
)


def _default_strategy_factory(component: AutonomousBehaviorComponent, pathfinding_service: PathfindingService) -> BehaviorStrategy:
    if component.behavior_strategy_type == "boss":
        return BossBehaviorStrategy(pathfinding_service)
    return DefaultBehaviorStrategy(pathfinding_service, FirstInRangeSkillPolicy())


def _default_target_policy_factory(component: AutonomousBehaviorComponent) -> TargetSelectionPolicy:
    return HighestThreatTargetPolicy()


class BehaviorService:
    """アクターの自律的な行動を制御するドメインサービス。ターゲット収集・状態更新・イベント発行を行い、アクション決定は戦略に委譲する。"""

    def __init__(
        self,
        pathfinding_service: PathfindingService,
        hostility_service: Optional[HostilityService] = None,
        allegiance_service: Optional[AllegianceService] = None,
        target_policy: Optional[TargetSelectionPolicy] = None,
        strategy: Optional[BehaviorStrategy] = None,
        strategy_factory: Optional[Callable[[AutonomousBehaviorComponent], BehaviorStrategy]] = None,
        target_policy_factory: Optional[Callable[[AutonomousBehaviorComponent], TargetSelectionPolicy]] = None,
    ):
        self._pathfinding_service = pathfinding_service
        self._hostility_service = hostility_service or ConfigurableHostilityService()
        self._allegiance_service = allegiance_service
        self._target_policy = target_policy
        self._strategy = strategy
        self._strategy_factory = strategy_factory or (
            lambda c: _default_strategy_factory(c, pathfinding_service)
        )
        self._target_policy_factory = target_policy_factory or _default_target_policy_factory

    def plan_action(
        self,
        actor_id: WorldObjectId,
        map_aggregate: PhysicalMapAggregate,
        target_context: Optional[TargetSelectionContext] = None,
        skill_context: Optional[SkillSelectionContext] = None,
        pack_rally_coordinate: Optional[Coordinate] = None,
    ) -> BehaviorAction:
        """
        アクターの現在の状態に基づいて次のアクションを決定する。

        Args:
            target_context: ターゲット選択の補助情報（HP%・脅威値等）。省略可
            skill_context: スキル選択の補助情報（使用可能スロット・射程内数等）。省略可
            pack_rally_coordinate: 群れの集結座標（味方が戦闘に入った座標）。省略可

        Returns:
            実行すべきアクション。
        """
        actor = map_aggregate.get_object(actor_id)
        component = actor.component

        if not isinstance(component, AutonomousBehaviorComponent):
            return BehaviorAction.wait()

        if component.initial_position is None:
            component.initial_position = actor.coordinate

        old_state = component.state
        target_policy = (
            self._target_policy
            if self._target_policy is not None
            else self._target_policy_factory(component)
        )
        strategy = (
            self._strategy
            if self._strategy is not None
            else self._strategy_factory(component)
        )

        # 0. ボスフェーズ: HPが閾値以下なら ENRAGE へ遷移
        if component.phase_thresholds:
            if component.hp_percentage <= component.phase_thresholds[0]:
                if component.state not in (BehaviorStateEnum.ENRAGE, BehaviorStateEnum.FLEE):
                    if old_state != BehaviorStateEnum.ENRAGE:
                        self._publish_state_changed(
                            map_aggregate, actor_id, old_state, BehaviorStateEnum.ENRAGE
                        )
                    component.set_state(BehaviorStateEnum.ENRAGE)
                    old_state = BehaviorStateEnum.ENRAGE

        # 1. 視界内の敵対候補を収集し、ポリシーで1体選択
        visible_hostiles = self._collect_visible_hostiles(
            actor, map_aggregate, component
        )
        target = (
            target_policy.select_target(actor, visible_hostiles, target_context)
            if visible_hostiles
            else None
        )

        # 2. ターゲットの有無に応じて状態更新とイベント発行
        if target:
            component.spot_target(target.object_id, target.coordinate)
            if old_state != component.state:
                self._publish_state_changed(
                    map_aggregate, actor_id, old_state, component.state
                )
                map_aggregate.add_event(
                    TargetSpottedEvent.create(
                        aggregate_id=actor_id,
                        aggregate_type="Actor",
                        actor_id=actor_id,
                        target_id=target.object_id,
                        coordinate=target.coordinate,
                    )
                )
        else:
            if component.target_id:
                lost_target_id = component.target_id
                last_coord = component.last_known_target_position
                component.lose_target()
                if old_state != component.state:
                    self._publish_state_changed(
                        map_aggregate, actor_id, old_state, component.state
                    )
                    if last_coord:
                        map_aggregate.add_event(
                            TargetLostEvent.create(
                                aggregate_id=actor_id,
                                aggregate_type="Actor",
                                actor_id=actor_id,
                                target_id=lost_target_id,
                                last_known_coordinate=last_coord,
                            )
                        )

        # 3. 戦略にアクション決定を委譲
        return strategy.decide_action(
            actor,
            map_aggregate,
            component,
            target,
            target_context=target_context,
            skill_context=skill_context,
            pack_rally_coordinate=pack_rally_coordinate,
        )

    def plan_next_move(
        self,
        actor_id: WorldObjectId,
        map_aggregate: PhysicalMapAggregate
    ) -> Optional[Coordinate]:
        """互換性のために残す。内部で plan_action を呼び出す。"""
        action = self.plan_action(actor_id, map_aggregate)
        if action.action_type == BehaviorActionType.MOVE:
            return action.coordinate
        return None

    def _publish_state_changed(
        self,
        map_aggregate: PhysicalMapAggregate,
        actor_id: WorldObjectId,
        old_state: BehaviorStateEnum,
        new_state: BehaviorStateEnum,
    ) -> None:
        map_aggregate.add_event(
            ActorStateChangedEvent.create(
                aggregate_id=actor_id,
                aggregate_type="Actor",
                actor_id=actor_id,
                old_state=old_state,
                new_state=new_state,
            )
        )

    def _collect_visible_hostiles(
        self,
        actor,
        map_aggregate: PhysicalMapAggregate,
        component: AutonomousBehaviorComponent,
    ) -> List:
        """視界内にいる敵対的なオブジェクトのリストを返す（FOV を考慮）。味方は除外する。"""
        nearby_objects = map_aggregate.get_objects_in_range(
            actor.coordinate, component.vision_range
        )
        visible_hostiles = []
        for obj in nearby_objects:
            if obj.object_id == actor.object_id:
                continue
            if not obj.is_actor:
                continue
            if self._allegiance_service and self._allegiance_service.is_ally(component, obj.component):
                continue
            if not self._hostility_service.is_hostile(component, obj.component):
                continue
            if not map_aggregate.is_visible(actor.coordinate, obj.coordinate):
                continue
            if self._is_within_fov(actor, obj.coordinate, component):
                visible_hostiles.append(obj)
        return visible_hostiles

    def _is_within_fov(
        self,
        actor,
        target_coord: Coordinate,
        component: AutonomousBehaviorComponent,
    ) -> bool:
        if component.fov_angle >= 360.0:
            return True
        if actor.coordinate == target_coord:
            return True
        dir_vectors = {
            DirectionEnum.NORTH: (0, -1),
            DirectionEnum.SOUTH: (0, 1),
            DirectionEnum.EAST: (1, 0),
            DirectionEnum.WEST: (-1, 0),
        }
        actor_dir = dir_vectors.get(component.direction)
        if actor_dir is None:
            return True
        target_vec = (
            target_coord.x - actor.coordinate.x,
            target_coord.y - actor.coordinate.y,
        )
        if target_vec == (0, 0):
            return True
        angle_to_target = math.degrees(
            math.atan2(target_vec[1], target_vec[0])
        )
        angle_actor = math.degrees(
            math.atan2(actor_dir[1], actor_dir[0])
        )
        diff = (angle_to_target - angle_actor + 180) % 360 - 180
        return abs(diff) <= (component.fov_angle / 2.0)
