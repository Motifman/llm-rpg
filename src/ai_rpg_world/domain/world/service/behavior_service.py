import math
from collections.abc import Callable

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.service.allegiance_service import AllegianceService
from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService, HostilityService
from ai_rpg_world.domain.world.service.target_selection_policy import (
    HighestThreatTargetPolicy,
    PackLeaderTargetPolicy,
    PreyPriorityTargetPolicy,
    TargetSelectionPolicy,
)
from ai_rpg_world.domain.world.value_object.behavior_context import (
    GrowthContext,
    SkillSelectionContext,
    TargetSelectionContext,
)
from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.facing import Facing
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _default_target_policy_factory(
    component: AutonomousBehaviorComponent,
    hostility_service: HostilityService,
) -> TargetSelectionPolicy:
    return PreyPriorityTargetPolicy(
        hostility_service,
        PackLeaderTargetPolicy(HighestThreatTargetPolicy()),
    )


class BehaviorService:
    """
    観測（視界内の脅威・敵対・選択ターゲット等）を組み立てるドメインサービス。
    モンスターの decide 用に build_observation を提供する。
    """

    def __init__(
        self,
        hostility_service: HostilityService | None = None,
        allegiance_service: AllegianceService | None = None,
        target_policy: TargetSelectionPolicy | None = None,
        target_policy_factory: Callable[[AutonomousBehaviorComponent], TargetSelectionPolicy] | None = None,
    ):
        self._hostility_service = hostility_service or ConfigurableHostilityService()
        self._allegiance_service = allegiance_service
        self._target_policy = target_policy
        self._target_policy_factory = target_policy_factory or (
            lambda c: _default_target_policy_factory(c, self._hostility_service)
        )

    def build_observation(
        self,
        actor_id: WorldObjectId,
        map_aggregate: PhysicalMapAggregate,
        target_context: TargetSelectionContext | None = None,
        skill_context: SkillSelectionContext | None = None,
        pack_rally_coordinate: Coordinate | None = None,
        growth_context: GrowthContext | None = None,
        current_tick: WorldTick | None = None,
        visible_feed: list[WorldObject] | None = None,
        selected_feed_target: WorldObject | None = None,
    ) -> BehaviorObservation:
        """
        アクターの観測（視界内脅威・敵対・選択ターゲット等）を組み立てて返す。
        モンスターの decide 用にアプリ層から呼ぶ。
        """
        actor = map_aggregate.get_object(actor_id)
        component = actor.component
        if not isinstance(component, AutonomousBehaviorComponent):
            return BehaviorObservation(
                visible_threats=[],
                visible_hostiles=[],
                selected_target=None,
                visible_feed=visible_feed or [],
                selected_feed_target=selected_feed_target,
                skill_context=skill_context,
                growth_context=growth_context,
                target_context=target_context,
                pack_rally_coordinate=pack_rally_coordinate,
                current_tick=current_tick,
            )
        target_policy = (
            self._target_policy
            if self._target_policy is not None
            else self._target_policy_factory(component)
        )
        visible_threats = self._collect_visible_threats(actor, map_aggregate, component)
        visible_hostiles = self._collect_visible_hostiles(actor, map_aggregate, component)
        selected_target = (
            target_policy.select_target(actor, visible_hostiles, target_context)
            if visible_hostiles
            else None
        )
        return BehaviorObservation(
            visible_threats=visible_threats,
            visible_hostiles=visible_hostiles,
            selected_target=selected_target,
            visible_feed=visible_feed or [],
            selected_feed_target=selected_feed_target,
            skill_context=skill_context,
            growth_context=growth_context,
            target_context=target_context,
            pack_rally_coordinate=pack_rally_coordinate,
            current_tick=current_tick,
        )

    def _collect_visible_threats(
        self,
        actor: WorldObject,
        map_aggregate: PhysicalMapAggregate,
        component: AutonomousBehaviorComponent,
    ) -> list[WorldObject]:
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
        actor: WorldObject,
        map_aggregate: PhysicalMapAggregate,
        component: AutonomousBehaviorComponent,
    ) -> list[WorldObject]:
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
        actor: WorldObject,
        target_coord: Coordinate,
        component: AutonomousBehaviorComponent,
    ) -> bool:
        if component.fov_angle >= 360.0:
            return True
        if actor.coordinate == target_coord:
            return True
        actor_dir = Facing.from_direction(component.direction).to_2d_vector()
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
