"""
モンスターの「次の一手」を解決する IMonsterActionResolver のアプリケーション層実装。
PhysicalMapAggregate と PathfindingService, SkillSelectionPolicy を使って
移動先座標またはスキルスロットを決定する。
"""

import math
import random
from typing import Optional, Callable

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.skill_selection_policy import SkillSelectionPolicy
from ai_rpg_world.domain.world.exception.map_exception import (
    ObjectNotFoundException,
    PathNotFoundException,
    InvalidPathRequestException,
)
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.action_resolver import IMonsterActionResolver


def create_monster_action_resolver_factory(
    pathfinding_service: PathfindingService,
    skill_policy: SkillSelectionPolicy,
) -> Callable[..., IMonsterActionResolver]:
    """アプリ層でリゾルバを生成するためのファクトリを返す。"""
    def factory(
        map_aggregate: PhysicalMapAggregate,
        actor: WorldObject,
    ) -> MonsterActionResolverImpl:
        return MonsterActionResolverImpl(
            map_aggregate,
            pathfinding_service,
            skill_policy,
            actor,
        )
    return factory


class MonsterActionResolverImpl:
    """
    IMonsterActionResolver の実装。
    マップ・パス探索・スキル選択を使って、モンスターの状態と観測から BehaviorAction を返す。
    """

    def __init__(
        self,
        map_aggregate: PhysicalMapAggregate,
        pathfinding_service: PathfindingService,
        skill_policy: SkillSelectionPolicy,
        actor: WorldObject,
    ):
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            raise TypeError(
                "MonsterActionResolverImpl requires actor with AutonomousBehaviorComponent"
            )
        self._map_aggregate = map_aggregate
        self._pathfinding_service = pathfinding_service
        self._skill_policy = skill_policy
        self._actor = actor
        self._component = actor.component

    def resolve_action(
        self,
        monster: MonsterAggregate,
        observation: BehaviorObservation,
        actor_coordinate: Coordinate,
    ) -> BehaviorAction:
        """モンスターの状態と観測から次の一手を返す。"""
        target = observation.selected_target
        attack_states = (BehaviorStateEnum.CHASE, BehaviorStateEnum.ENRAGE)
        if monster.behavior_state in attack_states and target is not None:
            slot = self._skill_policy.select_slot(
                self._actor,
                target,
                self._component.available_skills,
                observation.skill_context,
            )
            if slot is not None:
                return BehaviorAction.use_skill(slot)

        # テリトリ超過で RETURN にした直後は initial_position へ移動
        if (
            monster.behavior_initial_position is not None
            and monster.behavior_state == BehaviorStateEnum.RETURN
        ):
            next_coord = self._get_next_step_to(
                actor_coordinate,
                monster.behavior_initial_position,
            )
            if next_coord is not None:
                return BehaviorAction.move(next_coord)
            if actor_coordinate == monster.behavior_initial_position:
                return BehaviorAction.wait()

        if monster.behavior_state == BehaviorStateEnum.FLEE:
            next_coord = self._calculate_flee_move(monster, actor_coordinate)
        elif monster.behavior_state in (
            BehaviorStateEnum.CHASE,
            BehaviorStateEnum.ENRAGE,
        ):
            next_coord = self._calculate_chase_move(monster, actor_coordinate)
        elif monster.behavior_state == BehaviorStateEnum.SEARCH:
            next_coord = self._calculate_search_move(monster, actor_coordinate)
        elif monster.behavior_state == BehaviorStateEnum.PATROL:
            next_coord = self._calculate_patrol_move(monster, actor_coordinate)
        elif monster.behavior_state == BehaviorStateEnum.RETURN:
            next_coord = self._calculate_return_move(monster, actor_coordinate)
        else:
            next_coord = None

        if next_coord is not None:
            return BehaviorAction.move(next_coord)

        # パック集結
        if observation.pack_rally_coordinate is not None:
            is_follower = (
                self._component.pack_id is not None
                and not self._component.is_pack_leader
            )
            if (
                is_follower
                and monster.behavior_state
                in (BehaviorStateEnum.IDLE, BehaviorStateEnum.PATROL)
            ):
                if actor_coordinate != observation.pack_rally_coordinate:
                    next_coord = self._get_next_step_to(
                        actor_coordinate,
                        observation.pack_rally_coordinate,
                    )
                    if next_coord is not None:
                        return BehaviorAction.move(next_coord)

        return BehaviorAction.wait()

    def _get_next_step_to(
        self,
        start: Coordinate,
        goal: Coordinate,
    ) -> Optional[Coordinate]:
        """start から goal への次の一歩を返す。"""
        try:
            path = self._pathfinding_service.calculate_path(
                start=start,
                goal=goal,
                map_data=self._map_aggregate,
                capability=self._component.capability,
                allow_partial_path=True,
                smooth_path=False,
                exclude_object_id=self._actor.object_id,
            )
            if len(path) > 1:
                return path[1]
        except (PathNotFoundException, InvalidPathRequestException):
            pass
        return None

    def _calculate_chase_move(
        self, monster: MonsterAggregate, actor_coordinate: Coordinate
    ) -> Optional[Coordinate]:
        if monster.behavior_last_known_position is None:
            return None
        return self._get_next_step_to(
            actor_coordinate,
            monster.behavior_last_known_position,
        )

    def _calculate_flee_move(
        self, monster: MonsterAggregate, actor_coordinate: Coordinate
    ) -> Optional[Coordinate]:
        target_id = monster.behavior_target_id
        if target_id is None:
            return self._calculate_return_move(monster, actor_coordinate)
        try:
            target = self._map_aggregate.get_object(target_id)
        except ObjectNotFoundException:
            return self._calculate_return_move(monster, actor_coordinate)
        flee_goal = self._find_flee_goal(
            actor_coordinate, target.coordinate
        )
        if flee_goal is None:
            return None
        return self._get_next_step_to(actor_coordinate, flee_goal)

    def _find_flee_goal(
        self, actor_coordinate: Coordinate, enemy_coord: Coordinate
    ) -> Optional[Coordinate]:
        best_coord = None
        max_dist = actor_coordinate.euclidean_distance_to(enemy_coord)
        r = self._component.vision_range
        curr = actor_coordinate
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            tx = int(curr.x + r * math.cos(rad))
            ty = int(curr.y + r * math.sin(rad))
            sample = Coordinate(tx, ty, curr.z)
            if not self._map_aggregate.is_passable(
                sample, self._component.capability
            ):
                continue
            dist = sample.euclidean_distance_to(enemy_coord)
            if dist > max_dist:
                max_dist = dist
                best_coord = sample
        return best_coord

    def _calculate_return_move(
        self, monster: MonsterAggregate, actor_coordinate: Coordinate
    ) -> Optional[Coordinate]:
        if monster.behavior_initial_position is None:
            return None
        if actor_coordinate == monster.behavior_initial_position:
            return None
        return self._get_next_step_to(
            actor_coordinate,
            monster.behavior_initial_position,
        )

    def _calculate_search_move(
        self, monster: MonsterAggregate, actor_coordinate: Coordinate
    ) -> Optional[Coordinate]:
        if monster.behavior_last_known_position is None:
            return self._calculate_return_move(monster, actor_coordinate)
        if actor_coordinate != monster.behavior_last_known_position:
            return self._get_next_step_to(
                actor_coordinate,
                monster.behavior_last_known_position,
            )
        # 到達済み: ランダムに方向転換 or ランダム移動（状態更新は別途）
        if random.random() < self._component.random_move_chance:
            neighbors = []
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                neighbor = Coordinate(
                    actor_coordinate.x + dx,
                    actor_coordinate.y + dy,
                    actor_coordinate.z,
                )
                if self._map_aggregate.is_passable(
                    neighbor, self._component.capability
                ):
                    neighbors.append(neighbor)
            if neighbors:
                return random.choice(neighbors)
        return None

    def _calculate_patrol_move(
        self, monster: MonsterAggregate, actor_coordinate: Coordinate
    ) -> Optional[Coordinate]:
        if not self._component.patrol_points:
            return None
        idx = monster.behavior_patrol_index
        target_point = self._component.patrol_points[idx]
        if actor_coordinate == target_point:
            next_idx = (idx + 1) % len(self._component.patrol_points)
            target_point = self._component.patrol_points[next_idx]
        return self._get_next_step_to(actor_coordinate, target_point)
