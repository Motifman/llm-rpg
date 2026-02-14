"""BehaviorStrategy および DefaultBehaviorStrategy のテスト"""

import pytest
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import (
    ObjectTypeEnum,
    BehaviorStateEnum,
    BehaviorActionType,
)
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
    MonsterSkillInfo,
)
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.skill_selection_policy import (
    FirstInRangeSkillPolicy,
    SkillSelectionPolicy,
)
from ai_rpg_world.domain.world.service.behavior_strategy import (
    BehaviorStrategy,
    DefaultBehaviorStrategy,
)
from ai_rpg_world.domain.world.event.behavior_events import BehaviorStuckEvent
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
    AStarPathfindingStrategy,
)


class TestDefaultBehaviorStrategy:
    """DefaultBehaviorStrategy の正常・境界・スタックイベントのテスト"""

    @pytest.fixture
    def pathfinding_service(self) -> PathfindingService:
        return PathfindingService(AStarPathfindingStrategy())

    @pytest.fixture
    def skill_policy(self) -> FirstInRangeSkillPolicy:
        return FirstInRangeSkillPolicy()

    @pytest.fixture
    def strategy(
        self, pathfinding_service: PathfindingService, skill_policy: SkillSelectionPolicy
    ) -> DefaultBehaviorStrategy:
        return DefaultBehaviorStrategy(pathfinding_service, skill_policy)

    @pytest.fixture
    def map_aggregate(self) -> PhysicalMapAggregate:
        tiles = [
            Tile(Coordinate(x, y), TerrainType.grass())
            for x in range(10)
            for y in range(10)
        ]
        return PhysicalMapAggregate.create(SpotId(1), tiles)

    @pytest.fixture
    def actor_chase_with_target(self, map_aggregate: PhysicalMapAggregate) -> WorldObject:
        skills = [MonsterSkillInfo(slot_index=0, range=2, mp_cost=10)]
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            vision_range=5,
            available_skills=skills,
        )
        comp.last_known_target_position = Coordinate(7, 5)
        comp.target_id = WorldObjectId(1)
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        return actor

    @pytest.fixture
    def target_in_range(self, map_aggregate: PhysicalMapAggregate) -> WorldObject:
        target = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(7, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        map_aggregate.add_object(target)
        return target

    def test_decide_action_chase_with_target_in_skill_range_returns_use_skill(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
        actor_chase_with_target: WorldObject,
        target_in_range: WorldObject,
    ):
        """CHASE 状態でターゲットが射程内のとき USE_SKILL を返すこと"""
        component = actor_chase_with_target.component
        assert isinstance(component, AutonomousBehaviorComponent)
        action = strategy.decide_action(
            actor_chase_with_target,
            map_aggregate,
            component,
            target_in_range,
        )
        assert action.action_type == BehaviorActionType.USE_SKILL
        assert action.skill_slot_index == 0

    def test_decide_action_chase_with_target_out_of_skill_range_returns_move(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """CHASE 状態でターゲットが射程外のとき MOVE を返すこと"""
        skills = [MonsterSkillInfo(slot_index=0, range=1, mp_cost=10)]
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            vision_range=5,
            available_skills=skills,
        )
        comp.last_known_target_position = Coordinate(8, 5)
        comp.target_id = WorldObjectId(1)
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        target = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(8, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        map_aggregate.add_object(target)
        action = strategy.decide_action(actor, map_aggregate, comp, target)
        assert action.action_type == BehaviorActionType.MOVE
        assert action.coordinate is not None

    def test_decide_action_chase_no_target_returns_move_toward_last_known(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """CHASE 状態でターゲットなし（見失い）のとき last_known へ移動すること"""
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            vision_range=5,
        )
        comp.last_known_target_position = Coordinate(7, 5)
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        action = strategy.decide_action(actor, map_aggregate, comp, None)
        assert action.action_type == BehaviorActionType.MOVE
        assert action.coordinate == Coordinate(6, 5)

    def test_decide_action_flee_returns_move_away(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """FLEE 状態のときターゲットから離れる方向へ MOVE を返すこと"""
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.FLEE,
            vision_range=5,
        )
        comp.target_id = WorldObjectId(1)
        comp.initial_position = Coordinate(2, 2)
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        target = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(6, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        map_aggregate.add_object(target)
        action = strategy.decide_action(actor, map_aggregate, comp, target)
        assert action.action_type == BehaviorActionType.MOVE
        assert action.coordinate is not None

    def test_decide_action_return_returns_move_toward_initial(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """RETURN 状態のとき初期位置へ MOVE を返すこと"""
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.RETURN,
            vision_range=5,
        )
        comp.initial_position = Coordinate(1, 1)
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        action = strategy.decide_action(actor, map_aggregate, comp, None)
        assert action.action_type == BehaviorActionType.MOVE
        assert action.coordinate is not None

    def test_decide_action_idle_returns_wait(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """IDLE 状態のとき WAIT を返すこと"""
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.IDLE,
            vision_range=5,
        )
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        action = strategy.decide_action(actor, map_aggregate, comp, None)
        assert action.action_type == BehaviorActionType.WAIT
        assert action.coordinate is None
        assert action.skill_slot_index is None

    def test_decide_action_patrol_returns_move(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """PATROL 状態で巡回ポイントがあるとき MOVE を返すこと"""
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.PATROL,
            vision_range=5,
            patrol_points=[Coordinate(2, 5), Coordinate(7, 5)],
        )
        comp.current_patrol_index = 0
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        action = strategy.decide_action(actor, map_aggregate, comp, None)
        assert action.action_type == BehaviorActionType.MOVE
        assert action.coordinate is not None

    def test_decide_action_chase_no_skills_returns_move(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
        target_in_range: WorldObject,
    ):
        """CHASE + ターゲットありだがスキルが空のとき MOVE を返すこと"""
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            vision_range=5,
            available_skills=[],
        )
        comp.target_id = target_in_range.object_id
        comp.last_known_target_position = target_in_range.coordinate
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        action = strategy.decide_action(actor, map_aggregate, comp, target_in_range)
        assert action.action_type == BehaviorActionType.MOVE

    def test_decide_action_stuck_emits_behavior_stuck_event(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """経路が取れず移動失敗が max_failures に達したとき BehaviorStuckEvent が発行されること"""
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            max_failures=2,
            vision_range=5,
        )
        comp.last_known_target_position = Coordinate(9, 9)
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                wall = WorldObject(
                    object_id=WorldObjectId(1000 + dx + dy * 10),
                    coordinate=Coordinate(5 + dx, 5 + dy),
                    object_type=ObjectTypeEnum.GATE,
                    is_blocking=True,
                )
                map_aggregate.add_object(wall)
        strategy.decide_action(actor, map_aggregate, comp, None)
        strategy.decide_action(actor, map_aggregate, comp, None)
        events = map_aggregate.get_events()
        assert any(isinstance(e, BehaviorStuckEvent) for e in events)
        assert comp.state == BehaviorStateEnum.RETURN
