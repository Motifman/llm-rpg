import math
from typing import Optional, List
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import BehaviorStateEnum, DirectionEnum, BehaviorActionType
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.hostility_service import HostilityService, ConfigurableHostilityService
from ai_rpg_world.domain.world.service.target_selection_policy import TargetSelectionPolicy, NearestTargetPolicy
from ai_rpg_world.domain.world.service.skill_selection_policy import SkillSelectionPolicy, FirstInRangeSkillPolicy
from ai_rpg_world.domain.world.service.behavior_strategy import BehaviorStrategy, DefaultBehaviorStrategy
from ai_rpg_world.domain.world.event.behavior_events import (
    ActorStateChangedEvent,
    TargetSpottedEvent,
    TargetLostEvent,
)


class BehaviorService:
    """アクターの自律的な行動を制御するドメインサービス。ターゲット収集・状態更新・イベント発行を行い、アクション決定は戦略に委譲する。"""

    def __init__(
        self,
        pathfinding_service: PathfindingService,
        hostility_service: Optional[HostilityService] = None,
        target_policy: Optional[TargetSelectionPolicy] = None,
        strategy: Optional[BehaviorStrategy] = None,
    ):
        self._pathfinding_service = pathfinding_service
        self._hostility_service = hostility_service or ConfigurableHostilityService()
        self._target_policy = target_policy or NearestTargetPolicy()
        self._strategy = strategy or DefaultBehaviorStrategy(
            pathfinding_service,
            FirstInRangeSkillPolicy(),
        )

    def plan_action(
        self,
        actor_id: WorldObjectId,
        map_aggregate: PhysicalMapAggregate
    ) -> BehaviorAction:
        """
        アクターの現在の状態に基づいて次のアクションを決定する。

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

        # 1. 視界内の敵対候補を収集し、ポリシーで1体選択
        visible_hostiles = self._collect_visible_hostiles(
            actor, map_aggregate, component
        )
        target = self._target_policy.select_target(actor, visible_hostiles) if visible_hostiles else None

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
        return self._strategy.decide_action(
            actor, map_aggregate, component, target
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
        """視界内にいる敵対的なオブジェクトのリストを返す（FOV を考慮）。"""
        nearby_objects = map_aggregate.get_objects_in_range(
            actor.coordinate, component.vision_range
        )
        visible_hostiles = []
        for obj in nearby_objects:
            if obj.object_id == actor.object_id:
                continue
            if not obj.is_actor:
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
