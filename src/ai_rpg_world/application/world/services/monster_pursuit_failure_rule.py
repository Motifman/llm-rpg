from typing import Any, Optional

from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.enum.world_enum import BehaviorActionType
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class MonsterPursuitFailureRule:
    """monster pursuit の pre/post action failure を判定する rule。"""

    def evaluate_pre_action(
        self,
        monster: MonsterAggregate,
        physical_map: PhysicalMapAggregate,
        actor_coordinate: Coordinate,
        observation: Any,
    ) -> Optional[PursuitFailureReason]:
        if not monster.has_active_pursuit:
            return None
        if monster.behavior_state not in (
            BehaviorStateEnum.CHASE,
            BehaviorStateEnum.SEARCH,
        ):
            return None
        if observation.selected_target is not None:
            return None

        target_id = monster.behavior_target_id
        if target_id is None:
            return None

        try:
            physical_map.get_object(target_id)
        except ObjectNotFoundException:
            if monster.behavior_state == BehaviorStateEnum.SEARCH:
                last_known = monster.behavior_last_known_position
                if last_known is not None and actor_coordinate == last_known:
                    return PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
            return PursuitFailureReason.TARGET_MISSING
        return None

    def evaluate_post_action(
        self,
        monster: MonsterAggregate,
        actor_coordinate: Coordinate,
        observation: Any,
        action: Any,
    ) -> Optional[PursuitFailureReason]:
        if monster.behavior_state != BehaviorStateEnum.SEARCH:
            return None
        if not monster.has_active_pursuit:
            return None
        if observation.selected_target is not None:
            return None
        last_known = monster.behavior_last_known_position
        if last_known is None or actor_coordinate != last_known:
            return None
        if action.action_type == BehaviorActionType.MOVE:
            return None
        return PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
