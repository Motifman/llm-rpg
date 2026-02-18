import math
from typing import Optional, List, Callable
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
from ai_rpg_world.domain.world.value_object.behavior_context import (
    PlanActionContext,
    TargetSelectionContext,
    SkillSelectionContext,
    GrowthContext,
)
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, BehaviorActionType
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.hostility_service import HostilityService, ConfigurableHostilityService
from ai_rpg_world.domain.world.service.allegiance_service import AllegianceService
from ai_rpg_world.domain.world.service.target_selection_policy import (
    TargetSelectionPolicy,
    PreyPriorityTargetPolicy,
    HighestThreatTargetPolicy,
)
from ai_rpg_world.domain.world.service.skill_selection_policy import SkillSelectionPolicy, FirstInRangeSkillPolicy
from ai_rpg_world.domain.world.service.behavior_strategy import (
    BehaviorStrategy,
    DefaultBehaviorStrategy,
    BossBehaviorStrategy,
)
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import BehaviorStateTransitionService


def _default_strategy_factory(component: AutonomousBehaviorComponent, pathfinding_service: PathfindingService) -> BehaviorStrategy:
    if component.behavior_strategy_type == "boss":
        return BossBehaviorStrategy(pathfinding_service)
    return DefaultBehaviorStrategy(
        pathfinding_service,
        FirstInRangeSkillPolicy(),
        state_transition_service=BehaviorStateTransitionService(),
    )


def _default_target_policy_factory(
    component: AutonomousBehaviorComponent,
    hostility_service: HostilityService,
) -> TargetSelectionPolicy:
    return PreyPriorityTargetPolicy(
        hostility_service,
        HighestThreatTargetPolicy(),
    )


class BehaviorService:
    """
    アクターの自律的な行動を制御するドメインサービス。
    コンテキスト（視界内の脅威・敵対・ターゲット等）を収集し、状態遷移とアクション決定は戦略に委譲する。
    """

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
        self._target_policy_factory = target_policy_factory or (
            lambda c: _default_target_policy_factory(c, self._hostility_service)
        )

    def plan_action(
        self,
        actor_id: WorldObjectId,
        map_aggregate: PhysicalMapAggregate,
        target_context: Optional[TargetSelectionContext] = None,
        skill_context: Optional[SkillSelectionContext] = None,
        pack_rally_coordinate: Optional[Coordinate] = None,
        growth_context: Optional[GrowthContext] = None,
        current_tick: Optional[WorldTick] = None,
        event_sink: Optional[List] = None,
    ) -> BehaviorAction:
        """
        アクターの現在の状態に基づいて次のアクションを決定する。
        観測（視界内脅威・敵対・選択ターゲット等）を組み立て、戦略の update_state / decide_action に委譲する。
        行動イベント（TargetSpotted, ActorStateChanged 等）は event_sink に追加される。
        呼び出し元でモンスター集約に add_event して save すると、commit 時に発行される。
        """
        actor = map_aggregate.get_object(actor_id)
        component = actor.component

        if not isinstance(component, AutonomousBehaviorComponent):
            return BehaviorAction.wait()

        if component.initial_position is None:
            component.initial_position = actor.coordinate

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

        visible_threats = self._collect_visible_threats(actor, map_aggregate, component)
        visible_hostiles = self._collect_visible_hostiles(actor, map_aggregate, component)
        selected_target = (
            target_policy.select_target(actor, visible_hostiles, target_context)
            if visible_hostiles
            else None
        )

        observation = BehaviorObservation(
            visible_threats=visible_threats,
            visible_hostiles=visible_hostiles,
            selected_target=selected_target,
            skill_context=skill_context,
            growth_context=growth_context,
            target_context=target_context,
            pack_rally_coordinate=pack_rally_coordinate,
            current_tick=current_tick,
        )

        sink = event_sink if event_sink is not None else []
        context = PlanActionContext(
            actor_id=actor_id,
            actor=actor,
            map_aggregate=map_aggregate,
            component=component,
            observation=observation,
            event_sink=sink,
        )

        strategy.update_state(context)
        return strategy.decide_action(context)

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

    def _collect_visible_threats(
        self,
        actor,
        map_aggregate: PhysicalMapAggregate,
        component: AutonomousBehaviorComponent,
    ) -> List:
        """視界内にいる脅威(THREAT)オブジェクトのリストを返す（FOV を考慮）。味方は除外する。"""
        nearby_objects = map_aggregate.get_objects_in_range(
            actor.coordinate, component.vision_range
        )
        visible_threats = []
        for obj in nearby_objects:
            if obj.object_id == actor.object_id:
                continue
            if not obj.is_actor:
                continue
            if self._allegiance_service and self._allegiance_service.is_ally(component, obj.component):
                continue
            if not self._hostility_service.is_threat(component, obj.component):
                continue
            if not map_aggregate.is_visible(actor.coordinate, obj.coordinate):
                continue
            if self._is_within_fov(actor, obj.coordinate, component):
                visible_threats.append(obj)
        return visible_threats

    def _collect_visible_hostiles(
        self,
        actor,
        map_aggregate: PhysicalMapAggregate,
        component: AutonomousBehaviorComponent,
    ) -> List:
        """視界内にいる敵対的なオブジェクトのリストを返す（FOV を考慮）。味方は除外する。THREAT は含めない（攻撃対象にしない）。"""
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
