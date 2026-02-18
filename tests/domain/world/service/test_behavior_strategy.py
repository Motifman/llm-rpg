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
from ai_rpg_world.domain.world.value_object.behavior_context import PlanActionContext
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.value_object.behavior_context import SkillSelectionContext
from ai_rpg_world.domain.world.service.skill_selection_policy import (
    FirstInRangeSkillPolicy,
    SkillSelectionPolicy,
    BossSkillPolicy,
)
from ai_rpg_world.domain.world.service.behavior_strategy import (
    BehaviorStrategy,
    DefaultBehaviorStrategy,
    BossBehaviorStrategy,
)
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.event.behavior_events import (
    ActorStateChangedEvent,
    BehaviorStuckEvent,
    TargetLostEvent,
    TargetSpottedEvent,
)
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
    AStarPathfindingStrategy,
)


def _make_context(actor_id, actor, map_aggregate, component, target=None, **kwargs):
    """decide_action テスト用の PlanActionContext を組み立てる。"""
    return PlanActionContext(
        actor_id=actor_id,
        actor=actor,
        map_aggregate=map_aggregate,
        component=component,
        visible_threats=kwargs.get("visible_threats", []),
        visible_hostiles=kwargs.get("visible_hostiles", []),
        target=target,
        target_context=kwargs.get("target_context"),
        skill_context=kwargs.get("skill_context"),
        pack_rally_coordinate=kwargs.get("pack_rally_coordinate"),
        growth_context=kwargs.get("growth_context"),
        event_sink=kwargs.get("event_sink", []),
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
        ctx = _make_context(
            actor_chase_with_target.object_id,
            actor_chase_with_target,
            map_aggregate,
            component,
            target_in_range,
        )
        action = strategy.decide_action(ctx)
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
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, target)
        action = strategy.decide_action(ctx)
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
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, None)
        action = strategy.decide_action(ctx)
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
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, target)
        action = strategy.decide_action(ctx)
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
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, None)
        action = strategy.decide_action(ctx)
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
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, None)
        action = strategy.decide_action(ctx)
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
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, None)
        action = strategy.decide_action(ctx)
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
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, target_in_range)
        action = strategy.decide_action(ctx)
        assert action.action_type == BehaviorActionType.MOVE

    def test_decide_action_stuck_emits_behavior_stuck_event_to_event_sink(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """経路が取れず移動失敗が max_failures に達したとき BehaviorStuckEvent が event_sink に追加されること"""
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
        event_sink = []
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, None, event_sink=event_sink)
        strategy.decide_action(ctx)
        strategy.decide_action(ctx)
        assert any(isinstance(e, BehaviorStuckEvent) for e in event_sink)
        assert comp.state == BehaviorStateEnum.RETURN

    def test_decide_action_enrage_with_target_in_skill_range_returns_use_skill(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """ENRAGE 状態でターゲットが射程内のとき USE_SKILL を返すこと（CHASE と同様）"""
        skills = [MonsterSkillInfo(slot_index=0, range=5, mp_cost=10)]
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.ENRAGE,
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
        target = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(7, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        map_aggregate.add_object(target)
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, target)
        action = strategy.decide_action(ctx)
        assert action.action_type == BehaviorActionType.USE_SKILL
        assert action.skill_slot_index == 0

    def test_update_state_with_visible_threats_transitions_to_flee(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """visible_threats が渡されたとき FLEE に遷移し、最も近い脅威をターゲットにすること"""
        comp = AutonomousBehaviorComponent(
            race="goblin",
            vision_range=5,
            fov_angle=360,
            hp_percentage=1.0,
            state=BehaviorStateEnum.IDLE,
        )
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        threat = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(6, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=AutonomousBehaviorComponent(race="dragon"),
        )
        map_aggregate.add_object(threat)
        event_sink = []
        ctx = PlanActionContext(
            actor_id=actor.object_id,
            actor=actor,
            map_aggregate=map_aggregate,
            component=comp,
            visible_threats=[threat],
            visible_hostiles=[],
            target=None,
            event_sink=event_sink,
        )
        strategy.update_state(ctx)
        assert comp.state == BehaviorStateEnum.FLEE
        assert comp.target_id == threat.object_id
        assert comp.last_known_target_position == threat.coordinate
        # 行動イベントは event_sink に追加され、Map には積まれない（Map には create/add のみ）
        assert any(isinstance(e, TargetSpottedEvent) for e in event_sink)
        assert any(isinstance(e, ActorStateChangedEvent) for e in event_sink)
        behavior_event_types = (TargetSpottedEvent, TargetLostEvent, ActorStateChangedEvent, BehaviorStuckEvent)
        assert not any(isinstance(e, behavior_event_types) for e in map_aggregate.get_events())

    def test_decide_action_territory_radius_exceeded_returns_toward_initial(
        self,
        strategy: DefaultBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """CHASE/ENRAGE 中に初期位置から territory_radius を超えたら RETURN に遷移し初期位置へ MOVE を返すこと"""
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            vision_range=10,
            territory_radius=3,
            initial_position=Coordinate(1, 1),
        )
        comp.last_known_target_position = Coordinate(8, 8)
        comp.target_id = WorldObjectId(1)
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, None)
        action = strategy.decide_action(ctx)
        assert comp.state == BehaviorStateEnum.RETURN
        assert action.action_type == BehaviorActionType.MOVE
        assert action.coordinate is not None

    def test_decide_action_pack_rally_coordinate_follower_moves_toward_rally(
        self,
        pathfinding_service: PathfindingService,
        map_aggregate: PhysicalMapAggregate,
    ):
        """フォロワー（pack_id あり・is_pack_leader=False）が IDLE のとき pack_rally_coordinate へ MOVE を返すこと"""
        skill_policy = FirstInRangeSkillPolicy()
        strategy = DefaultBehaviorStrategy(pathfinding_service, skill_policy)
        pack_id = PackId.create("pack1")
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.IDLE,
            vision_range=5,
            pack_id=pack_id,
            is_pack_leader=False,
        )
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        map_aggregate.add_object(actor)
        rally = Coordinate(8, 5)
        ctx = _make_context(
            actor.object_id, actor, map_aggregate, comp, None,
            pack_rally_coordinate=rally,
        )
        action = strategy.decide_action(ctx)
        assert action.action_type == BehaviorActionType.MOVE
        assert action.coordinate is not None
        assert action.coordinate != actor.coordinate


class TestBossBehaviorStrategy:
    """BossBehaviorStrategy のテスト（BossSkillPolicy 使用・AOE優先の確認）"""

    @pytest.fixture
    def pathfinding_service(self) -> PathfindingService:
        return PathfindingService(AStarPathfindingStrategy())

    @pytest.fixture
    def strategy(self, pathfinding_service: PathfindingService) -> BossBehaviorStrategy:
        return BossBehaviorStrategy(pathfinding_service)

    @pytest.fixture
    def map_aggregate(self) -> PhysicalMapAggregate:
        tiles = [
            Tile(Coordinate(x, y), TerrainType.grass())
            for x in range(10)
            for y in range(10)
        ]
        return PhysicalMapAggregate.create(SpotId(1), tiles)

    def test_decide_action_uses_boss_skill_policy_aoe_priority(
        self,
        strategy: BossBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """BossSkillPolicy により targets_in_range_by_slot で AOE 優先のスロットを返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            vision_range=5,
            available_skills=skills,
        )
        comp.target_id = WorldObjectId(1)
        comp.last_known_target_position = Coordinate(6, 5)
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
        skill_context = SkillSelectionContext(
            usable_slot_indices={0, 1},
            targets_in_range_by_slot={0: 1, 1: 3},
        )
        ctx = _make_context(
            actor.object_id, actor, map_aggregate, comp, target,
            skill_context=skill_context,
        )
        action = strategy.decide_action(ctx)
        assert action.action_type == BehaviorActionType.USE_SKILL
        assert action.skill_slot_index == 1

    def test_decide_action_boss_without_context_returns_first_in_range(
        self,
        strategy: BossBehaviorStrategy,
        map_aggregate: PhysicalMapAggregate,
    ):
        """context なしのときは射程内の最初のスキルを返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            vision_range=5,
            available_skills=skills,
        )
        comp.target_id = WorldObjectId(1)
        comp.last_known_target_position = Coordinate(6, 5)
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
        ctx = _make_context(actor.object_id, actor, map_aggregate, comp, target)
        action = strategy.decide_action(ctx)
        assert action.action_type == BehaviorActionType.USE_SKILL
        assert action.skill_slot_index == 0
