"""
行動戦略。
アクターの状態遷移と「次のアクション」決定のロジックを戦略に集約する。
"""

import math
import random
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.domain.world.value_object.behavior_context import (
    PlanActionContext,
    SkillSelectionContext,
    TargetSelectionContext,
)
from ai_rpg_world.domain.world.enum.world_enum import BehaviorStateEnum, DirectionEnum
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.skill_selection_policy import (
    SkillSelectionPolicy,
    BossSkillPolicy,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    ObjectNotFoundException,
    PathNotFoundException,
    InvalidPathRequestException,
)
from ai_rpg_world.domain.world.event.behavior_events import (
    ActorStateChangedEvent,
    BehaviorStuckEvent,
    TargetLostEvent,
    TargetSpottedEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.entity.world_object import WorldObject
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate


class BehaviorStrategy(ABC):
    """
    アクターの状態遷移と次のアクション決定を担当する戦略のインターフェース。
    状態更新・イベント発行・アクション決定を一箇所にカプセル化する。
    """

    @abstractmethod
    def update_state(self, context: PlanActionContext) -> None:
        """
        コンテキストに基づきコンポーネントの状態を更新し、必要に応じてイベントを発行する。
        （フェーズ→ENRAGE、脅威→FLEE、ターゲット捕捉→CHASE/FLEE、見失い→SEARCH/RETURN 等）
        """
        pass

    @abstractmethod
    def decide_action(self, context: PlanActionContext) -> BehaviorAction:
        """
        現在の状態とコンテキストに基づき、実行すべきアクションを決定する。
        """
        pass


class DefaultBehaviorStrategy(BehaviorStrategy):
    """
    デフォルトの行動戦略。
    状態遷移（update_state）と行動決定（decide_action）を一箇所に集約する。
    追跡・逃走・巡回・帰還・探索などの移動と、射程内でのスキル使用をスキル選択ポリシーに委譲する。
    """

    def __init__(
        self,
        pathfinding_service: PathfindingService,
        skill_policy: SkillSelectionPolicy,
    ):
        self._pathfinding_service = pathfinding_service
        self._skill_policy = skill_policy

    def update_state(self, context: PlanActionContext) -> None:
        """フェーズ・脅威・ターゲット・見失いに応じた状態遷移とイベント発行を行う。"""
        component = context.component
        old_state = component.state

        # 0. ボスフェーズ: HPが閾値以下なら ENRAGE へ遷移
        if component.phase_thresholds:
            if component.hp_percentage <= component.phase_thresholds[0]:
                if component.state not in (BehaviorStateEnum.ENRAGE, BehaviorStateEnum.FLEE):
                    self._publish_state_changed(context, old_state, BehaviorStateEnum.ENRAGE)
                    component.set_state(BehaviorStateEnum.ENRAGE)
                    old_state = BehaviorStateEnum.ENRAGE

        # 1a. 視界内に脅威(THREAT)がいれば FLEE に遷移
        target = None
        if context.visible_threats and component.state != BehaviorStateEnum.FLEE:
            self._publish_state_changed(context, old_state, BehaviorStateEnum.FLEE)
            component.set_state(BehaviorStateEnum.FLEE)
            old_state = BehaviorStateEnum.FLEE
            nearest = min(
                context.visible_threats,
                key=lambda obj: context.actor.coordinate.euclidean_distance_to(obj.coordinate),
            )
            target = nearest
            component.target_id = target.object_id
            component.last_known_target_position = target.coordinate
            context.map_aggregate.add_event(
                TargetSpottedEvent.create(
                    aggregate_id=context.actor_id,
                    aggregate_type="Actor",
                    actor_id=context.actor_id,
                    target_id=target.object_id,
                    coordinate=target.coordinate,
                )
            )

        # 1b. 脅威でない場合は渡されたターゲットで spot_target
        if target is None and context.target and component.state != BehaviorStateEnum.FLEE:
            effective_flee = context.growth_context.effective_flee_threshold if context.growth_context else None
            allow_chase = context.growth_context.allow_chase if context.growth_context else None
            component.spot_target(
                context.target.object_id,
                context.target.coordinate,
                effective_flee_threshold=effective_flee,
                allow_chase=allow_chase,
            )
            if old_state != component.state:
                self._publish_state_changed(context, old_state, component.state)
                context.map_aggregate.add_event(
                    TargetSpottedEvent.create(
                        aggregate_id=context.actor_id,
                        aggregate_type="Actor",
                        actor_id=context.actor_id,
                        target_id=context.target.object_id,
                        coordinate=context.target.coordinate,
                    )
                )

        # 2. ターゲットなしで既にターゲットを持っていたら lose_target（脅威でターゲットを設定した直後は除く）
        if not context.visible_threats and not context.target and component.target_id:
            lost_target_id = component.target_id
            last_coord = component.last_known_target_position
            component.lose_target()
            if old_state != component.state:
                self._publish_state_changed(context, old_state, component.state)
                if last_coord:
                    context.map_aggregate.add_event(
                        TargetLostEvent.create(
                            aggregate_id=context.actor_id,
                            aggregate_type="Actor",
                            actor_id=context.actor_id,
                            target_id=lost_target_id,
                            last_known_coordinate=last_coord,
                        )
                    )

    def decide_action(self, context: PlanActionContext) -> BehaviorAction:
        actor = context.actor
        map_aggregate = context.map_aggregate
        component = context.component
        target = context.target

        # 攻撃可能かチェック (CHASE または ENRAGE かつターゲットが視界内)
        attack_states = (BehaviorStateEnum.CHASE, BehaviorStateEnum.ENRAGE)
        if component.state in attack_states and target:
            slot = self._skill_policy.select_slot(
                actor, target, component.available_skills, context.skill_context
            )
            if slot is not None:
                return BehaviorAction.use_skill(slot)

        # 状態に応じた移動先計算
        next_coord = None
        if (
            component.territory_radius is not None
            and component.initial_position is not None
            and component.state in (BehaviorStateEnum.CHASE, BehaviorStateEnum.ENRAGE)
        ):
            if actor.coordinate.distance_to(component.initial_position) > component.territory_radius:
                component.set_state(BehaviorStateEnum.RETURN)
                next_coord = self._calculate_return_move(actor, component, map_aggregate)
        if next_coord is not None:
            return BehaviorAction.move(next_coord)

        if component.state == BehaviorStateEnum.FLEE:
            next_coord = self._calculate_flee_move(actor, component, map_aggregate)
        elif component.state in (BehaviorStateEnum.CHASE, BehaviorStateEnum.ENRAGE):
            next_coord = self._calculate_chase_move(actor, component, map_aggregate)
        elif component.state == BehaviorStateEnum.SEARCH:
            next_coord = self._calculate_search_move(actor, component, map_aggregate)
        elif component.state == BehaviorStateEnum.PATROL:
            next_coord = self._calculate_patrol_move(actor, component, map_aggregate)
        elif component.state == BehaviorStateEnum.RETURN:
            next_coord = self._calculate_return_move(actor, component, map_aggregate)

        if next_coord is None and context.pack_rally_coordinate:
            is_follower = component.pack_id is not None and not component.is_pack_leader
            if is_follower and component.state in (BehaviorStateEnum.IDLE, BehaviorStateEnum.PATROL):
                if actor.coordinate != context.pack_rally_coordinate:
                    next_coord = self._get_next_step_to(
                        actor, context.pack_rally_coordinate, map_aggregate, component
                    )

        if next_coord is not None:
            return BehaviorAction.move(next_coord)
        return BehaviorAction.wait()

    def _publish_state_changed(
        self,
        context: PlanActionContext,
        old_state: BehaviorStateEnum,
        new_state: BehaviorStateEnum,
    ) -> None:
        context.map_aggregate.add_event(
            ActorStateChangedEvent.create(
                aggregate_id=context.actor_id,
                aggregate_type="Actor",
                actor_id=context.actor_id,
                old_state=old_state,
                new_state=new_state,
            )
        )

    def _calculate_chase_move(
        self,
        actor: "WorldObject",
        component: AutonomousBehaviorComponent,
        map_aggregate: "PhysicalMapAggregate",
    ) -> Optional[Coordinate]:
        if not component.last_known_target_position:
            return None
        return self._get_next_step_to(
            actor, component.last_known_target_position, map_aggregate, component
        )

    def _calculate_flee_move(
        self,
        actor: "WorldObject",
        component: AutonomousBehaviorComponent,
        map_aggregate: "PhysicalMapAggregate",
    ) -> Optional[Coordinate]:
        target_id = component.target_id
        if not target_id:
            return self._calculate_return_move(actor, component, map_aggregate)
        try:
            target = map_aggregate.get_object(target_id)
        except ObjectNotFoundException:
            component.lose_target()
            return self._calculate_return_move(actor, component, map_aggregate)
        flee_goal = self._find_flee_goal(
            actor, target.coordinate, component, map_aggregate
        )
        if not flee_goal:
            return None
        return self._get_next_step_to(actor, flee_goal, map_aggregate, component)

    def _find_flee_goal(
        self,
        actor: "WorldObject",
        enemy_coord: Coordinate,
        component: AutonomousBehaviorComponent,
        map_aggregate: "PhysicalMapAggregate",
    ) -> Optional[Coordinate]:
        best_coord = None
        max_dist = actor.coordinate.euclidean_distance_to(enemy_coord)
        r = component.vision_range
        curr = actor.coordinate
        samples = []
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            tx = int(curr.x + r * math.cos(rad))
            ty = int(curr.y + r * math.sin(rad))
            samples.append(Coordinate(tx, ty, curr.z))
        for sample in samples:
            if not map_aggregate.is_passable(sample, component.capability):
                continue
            dist = sample.euclidean_distance_to(enemy_coord)
            if dist > max_dist:
                max_dist = dist
                best_coord = sample
        return best_coord

    def _calculate_return_move(
        self,
        actor: "WorldObject",
        component: AutonomousBehaviorComponent,
        map_aggregate: "PhysicalMapAggregate",
    ) -> Optional[Coordinate]:
        if not component.initial_position:
            component.set_state(BehaviorStateEnum.IDLE)
            return None
        if actor.coordinate == component.initial_position:
            component.set_state(BehaviorStateEnum.IDLE)
            return None
        return self._get_next_step_to(
            actor, component.initial_position, map_aggregate, component
        )

    def _calculate_search_move(
        self,
        actor: "WorldObject",
        component: AutonomousBehaviorComponent,
        map_aggregate: "PhysicalMapAggregate",
    ) -> Optional[Coordinate]:
        if not component.last_known_target_position:
            component.set_state(BehaviorStateEnum.RETURN)
            return self._calculate_return_move(actor, component, map_aggregate)
        if actor.coordinate != component.last_known_target_position:
            return self._get_next_step_to(
                actor,
                component.last_known_target_position,
                map_aggregate,
                component,
            )
        if component.tick_search():
            if component.state == BehaviorStateEnum.PATROL:
                return self._calculate_patrol_move(actor, component, map_aggregate)
            return self._calculate_return_move(actor, component, map_aggregate)
        new_dir = random.choice([
            DirectionEnum.NORTH,
            DirectionEnum.SOUTH,
            DirectionEnum.EAST,
            DirectionEnum.WEST,
        ])
        component.turn(new_dir)
        if random.random() < component.random_move_chance:
            neighbors = []
            curr = actor.coordinate
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                neighbor = Coordinate(curr.x + dx, curr.y + dy, curr.z)
                if map_aggregate.is_passable(neighbor, component.capability):
                    neighbors.append(neighbor)
            if neighbors:
                return random.choice(neighbors)
        return None

    def _calculate_patrol_move(
        self,
        actor: "WorldObject",
        component: AutonomousBehaviorComponent,
        map_aggregate: "PhysicalMapAggregate",
    ) -> Optional[Coordinate]:
        if not component.patrol_points:
            return None
        target_point = component.patrol_points[component.current_patrol_index]
        if actor.coordinate == target_point:
            component.current_patrol_index = (
                component.current_patrol_index + 1
            ) % len(component.patrol_points)
            target_point = component.patrol_points[component.current_patrol_index]
        return self._get_next_step_to(
            actor, target_point, map_aggregate, component
        )

    def _get_next_step_to(
        self,
        actor: "WorldObject",
        goal: Coordinate,
        map_aggregate: "PhysicalMapAggregate",
        component: AutonomousBehaviorComponent,
    ) -> Optional[Coordinate]:
        try:
            path = self._pathfinding_service.calculate_path(
                start=actor.coordinate,
                goal=goal,
                map_data=map_aggregate,
                capability=component.capability,
                allow_partial_path=True,
                smooth_path=False,
                exclude_object_id=actor.object_id,
            )
            if len(path) > 1:
                component.on_move_success()
                return path[1]
            if actor.coordinate != goal:
                if component.on_move_failed():
                    map_aggregate.add_event(
                        BehaviorStuckEvent.create(
                            aggregate_id=actor.object_id,
                            aggregate_type="Actor",
                            actor_id=actor.object_id,
                            state=component.state,
                            coordinate=actor.coordinate,
                        )
                    )
        except (PathNotFoundException, InvalidPathRequestException):
            if component.on_move_failed():
                map_aggregate.add_event(
                    BehaviorStuckEvent.create(
                        aggregate_id=actor.object_id,
                        aggregate_type="Actor",
                        actor_id=actor.object_id,
                        state=component.state,
                        coordinate=actor.coordinate,
                    )
                )
            return None
        return None


class BossBehaviorStrategy(DefaultBehaviorStrategy):
    """
    ボス用行動戦略。DefaultBehaviorStrategy と同一の移動ロジックだが、
    BossSkillPolicy により複数体射程内でAOE優先・使用可能スロットのみ選択する。
    """
    def __init__(self, pathfinding_service: PathfindingService):
        super().__init__(pathfinding_service, BossSkillPolicy())
