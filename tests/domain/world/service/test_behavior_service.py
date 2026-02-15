import pytest
import math
from unittest.mock import MagicMock
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import (
    ObjectTypeEnum,
    BehaviorStateEnum,
    DirectionEnum,
    BehaviorActionType,
    Disposition,
)
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent, MonsterSkillInfo
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService
from ai_rpg_world.domain.world.service.allegiance_service import PackAllegianceService
from ai_rpg_world.domain.world.service.skill_selection_policy import SkillSelectionPolicy
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.service.behavior_strategy import DefaultBehaviorStrategy
from ai_rpg_world.domain.world.exception.behavior_exception import (
    VisionRangeValidationException,
    FOVAngleValidationException,
    SearchDurationValidationException,
    HPPercentageValidationException,
    FleeThresholdValidationException,
    MaxFailuresValidationException
)
from ai_rpg_world.domain.world.event.behavior_events import (
    ActorStateChangedEvent,
    TargetSpottedEvent,
    TargetLostEvent,
    BehaviorStuckEvent
)
from ai_rpg_world.domain.common.exception import ValidationException


class TestAutonomousBehaviorComponent:
    """AutonomousBehaviorComponentのバリデーションと状態遷移のテスト"""

    def test_validation_success(self):
        """正常なパラメータで生成できること"""
        comp = AutonomousBehaviorComponent(
            vision_range=5,
            search_duration=3,
            hp_percentage=0.5,
            flee_threshold=0.2,
            max_failures=5,
            random_move_chance=0.5
        )
        assert comp.vision_range == 5
        assert comp.hp_percentage == 0.5

    def test_validation_errors(self):
        """異常なパラメータで例外が発生すること"""
        with pytest.raises(VisionRangeValidationException):
            AutonomousBehaviorComponent(vision_range=-1)
        
        with pytest.raises(FOVAngleValidationException):
            AutonomousBehaviorComponent(fov_angle=361)
            
        with pytest.raises(SearchDurationValidationException):
            AutonomousBehaviorComponent(search_duration=-1)

        with pytest.raises(HPPercentageValidationException):
            AutonomousBehaviorComponent(hp_percentage=1.1)

        with pytest.raises(FleeThresholdValidationException):
            AutonomousBehaviorComponent(flee_threshold=-0.1)

        with pytest.raises(MaxFailuresValidationException):
            AutonomousBehaviorComponent(max_failures=0)

        with pytest.raises(ValidationException):
            AutonomousBehaviorComponent(random_move_chance=1.5)

    def test_state_transitions(self):
        """捕捉・見失いによる状態遷移が正しいこと"""
        comp = AutonomousBehaviorComponent(hp_percentage=1.0, flee_threshold=0.2)
        target_id = WorldObjectId(1)
        coord = Coordinate(1, 1)

        # 1. 捕捉 (通常時 -> CHASE)
        comp.spot_target(target_id, coord)
        assert comp.state == BehaviorStateEnum.CHASE
        assert comp.target_id == target_id

        # 2. 見失い (CHASE -> SEARCH)
        comp.lose_target()
        assert comp.state == BehaviorStateEnum.SEARCH

        # 3. 捕捉 (HP低時 -> FLEE)
        comp.update_hp(0.1)
        comp.spot_target(target_id, coord)
        assert comp.state == BehaviorStateEnum.FLEE

        # 4. 見失い (FLEE -> RETURN)
        comp.lose_target()
        assert comp.state == BehaviorStateEnum.RETURN


class TestBehaviorService:
    @pytest.fixture
    def pathfinding_service(self):
        strategy = AStarPathfindingStrategy()
        return PathfindingService(strategy)

    @pytest.fixture
    def hostility_service(self):
        from ai_rpg_world.domain.world.enum.world_enum import Disposition
        return ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}}
        )

    @pytest.fixture
    def behavior_service(self, pathfinding_service, hostility_service):
        return BehaviorService(pathfinding_service, hostility_service)

    @pytest.fixture
    def map_aggregate(self):
        tiles = []
        terrain = TerrainType.grass()
        for x in range(10):
            for y in range(10):
                tiles.append(Tile(Coordinate(x, y), terrain))
        return PhysicalMapAggregate.create(SpotId(1), tiles)

    class TestPlanning:
        """計画ロジックの総合テスト"""

        def test_chase_logic(self, behavior_service, map_aggregate):
            """敵を見つけたら追跡状態になり、移動先が返ること"""
            monster_id = WorldObjectId(100)
            comp = AutonomousBehaviorComponent(race="goblin", vision_range=5, fov_angle=360)
            monster = WorldObject(monster_id, Coordinate(0, 0), ObjectTypeEnum.NPC, is_blocking=False, component=comp)
            map_aggregate.add_object(monster)

            player_id = WorldObjectId(1)
            player = WorldObject(player_id, Coordinate(2, 0), ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human"))
            map_aggregate.add_object(player)

            # 実行
            next_move = behavior_service.plan_next_move(monster_id, map_aggregate)

            assert comp.state == BehaviorStateEnum.CHASE
            assert next_move == Coordinate(1, 0)
            
            # イベント確認
            events = map_aggregate.get_events()
            assert any(isinstance(e, TargetSpottedEvent) for e in events)
            assert any(isinstance(e, ActorStateChangedEvent) for e in events)

        def test_flee_logic_advanced(self, behavior_service, map_aggregate):
            """逃走時に適切な遠方地点への1歩を返すこと"""
            monster_id = WorldObjectId(100)
            comp = AutonomousBehaviorComponent(race="goblin", hp_percentage=0.1, flee_threshold=0.2, vision_range=5, fov_angle=360)
            monster = WorldObject(monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp)
            map_aggregate.add_object(monster)

            player_id = WorldObjectId(1)
            player_coord = Coordinate(6, 5)
            player = WorldObject(player_id, player_coord, ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human"))
            map_aggregate.add_object(player)

            # 実行
            initial_dist = monster.coordinate.euclidean_distance_to(player_coord)
            next_move = behavior_service.plan_next_move(monster_id, map_aggregate)

            assert comp.state == BehaviorStateEnum.FLEE
            assert next_move is not None
            
            new_dist = next_move.euclidean_distance_to(player_coord)
            assert new_dist > initial_dist

        def test_search_logic(self, behavior_service, map_aggregate):
            """見失った後、目的地へ向かい、到着後に探索（タイマー更新）すること"""
            monster_id = WorldObjectId(100)
            last_pos = Coordinate(2, 2)
            comp = AutonomousBehaviorComponent(
                state=BehaviorStateEnum.SEARCH,
                search_duration=2,
                random_move_chance=0.0 # 確率要素を排除
            )
            comp.update_last_known_position(last_pos)
            monster = WorldObject(monster_id, Coordinate(1, 2), ObjectTypeEnum.NPC, is_blocking=False, component=comp)
            map_aggregate.add_object(monster)

            # 1. 目的地(2,2)への移動
            next_move = behavior_service.plan_next_move(monster_id, map_aggregate)
            assert next_move == last_pos
            
            # 位置を更新して再度実行 (到着済み)
            map_aggregate.move_object(monster_id, last_pos, WorldTick(10))
            
            # 2. 探索1ターン目 (タイマー 0 -> 1)
            behavior_service.plan_next_move(monster_id, map_aggregate)
            assert comp.search_timer == 1
            assert comp.state == BehaviorStateEnum.SEARCH

            # 3. 探索2ターン目 (タイマー 1 -> 2 >= duration) -> RETURN
            behavior_service.plan_next_move(monster_id, map_aggregate)
            assert comp.state == BehaviorStateEnum.RETURN

        def test_stuck_logic(self, behavior_service, map_aggregate):
            """移動失敗が重なるとスタックイベントが発行され、RETURN状態になること"""
            monster_id = WorldObjectId(100)
            comp = AutonomousBehaviorComponent(state=BehaviorStateEnum.CHASE, max_failures=2)
            comp.update_last_known_position(Coordinate(9, 9))
            monster = WorldObject(monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp)
            map_aggregate.add_object(monster)

            # 周囲を壁で囲む (8方向)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    wall = WorldObject(WorldObjectId(1000+dx+dy*10), Coordinate(5+dx, 5+dy), ObjectTypeEnum.GATE, is_blocking=True)
                    map_aggregate.add_object(wall)

            # 1回目失敗
            behavior_service.plan_next_move(monster_id, map_aggregate)
            assert comp.failure_count == 1
            
            # 2回目失敗 -> STUCK & RETURN
            map_aggregate.clear_events()
            behavior_service.plan_next_move(monster_id, map_aggregate)
            
            assert comp.state == BehaviorStateEnum.RETURN
            assert any(isinstance(e, BehaviorStuckEvent) for e in map_aggregate.get_events())

        def test_skill_planning(self, behavior_service, map_aggregate):
            """ターゲットが射程内にいる場合、スキル使用アクションを返すこと"""
            monster_id = WorldObjectId(100)
            skills = [MonsterSkillInfo(slot_index=0, range=2, mp_cost=10)]
            comp = AutonomousBehaviorComponent(
                race="goblin", 
                vision_range=5, 
                fov_angle=360,
                available_skills=skills
            )
            monster = WorldObject(monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, component=comp)
            map_aggregate.add_object(monster)

            player_id = WorldObjectId(1)
            # 距離2の位置にプレイヤー
            player = WorldObject(player_id, Coordinate(7, 5), ObjectTypeEnum.PLAYER, component=ActorComponent(race="human"))
            map_aggregate.add_object(player)

            # 実行
            action = behavior_service.plan_action(monster_id, map_aggregate)

            assert action.action_type == BehaviorActionType.USE_SKILL
            assert action.skill_slot_index == 0

        def test_skill_planning_no_skills_returns_move(self, behavior_service, map_aggregate):
            """スキルがない場合は攻撃せず移動アクションを返すこと"""
            monster_id = WorldObjectId(100)
            comp = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=5,
                fov_angle=360,
                available_skills=[],
            )
            monster = WorldObject(monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, component=comp)
            map_aggregate.add_object(monster)
            player = WorldObject(WorldObjectId(1), Coordinate(7, 5), ObjectTypeEnum.PLAYER, component=ActorComponent(race="human"))
            map_aggregate.add_object(player)
            action = behavior_service.plan_action(monster_id, map_aggregate)
            assert action.action_type == BehaviorActionType.MOVE
            assert action.coordinate is not None

        def test_skill_planning_target_out_of_range_returns_move(self, behavior_service, map_aggregate):
            """ターゲットが射程外の場合は移動アクションを返すこと"""
            monster_id = WorldObjectId(100)
            skills = [MonsterSkillInfo(slot_index=0, range=1, mp_cost=10)]
            comp = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=10,
                fov_angle=360,
                available_skills=skills,
            )
            monster = WorldObject(monster_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=comp)
            map_aggregate.add_object(monster)
            player = WorldObject(WorldObjectId(1), Coordinate(5, 0), ObjectTypeEnum.PLAYER, component=ActorComponent(race="human"))
            map_aggregate.add_object(player)
            action = behavior_service.plan_action(monster_id, map_aggregate)
            assert action.action_type == BehaviorActionType.MOVE
            assert action.coordinate is not None

        def test_skill_planning_multiple_skills_in_range_returns_first(self, behavior_service, map_aggregate):
            """射程内に複数スキルがある場合は最初のスキルを選択すること"""
            monster_id = WorldObjectId(100)
            skills = [
                MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
                MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
            ]
            comp = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=5,
                fov_angle=360,
                available_skills=skills,
            )
            monster = WorldObject(monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, component=comp)
            map_aggregate.add_object(monster)
            player = WorldObject(WorldObjectId(1), Coordinate(6, 5), ObjectTypeEnum.PLAYER, component=ActorComponent(race="human"))
            map_aggregate.add_object(player)
            action = behavior_service.plan_action(monster_id, map_aggregate)
            assert action.action_type == BehaviorActionType.USE_SKILL
            assert action.skill_slot_index == 0

    class TestVisibility:
        """視認判定のテスト"""

        def test_fov_angle_limit(self, behavior_service, map_aggregate):
            """視野角の外にいる敵を無視すること"""
            monster_id = WorldObjectId(100)
            # 南向き、視野角90度
            comp = AutonomousBehaviorComponent(race="goblin", direction=DirectionEnum.SOUTH, fov_angle=90)
            monster = WorldObject(monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp)
            map_aggregate.add_object(monster)

            # 真後ろ（北）にプレイヤー
            player = WorldObject(WorldObjectId(1), Coordinate(5, 4), ObjectTypeEnum.PLAYER, component=ActorComponent(race="human"))
            map_aggregate.add_object(player)

            behavior_service.plan_next_move(monster_id, map_aggregate)
            assert comp.state == BehaviorStateEnum.IDLE # 気づかない

            # 前方（南）にプレイヤー
            player2 = WorldObject(WorldObjectId(2), Coordinate(5, 6), ObjectTypeEnum.PLAYER, component=ActorComponent(race="human"))
            map_aggregate.add_object(player2)

            behavior_service.plan_next_move(monster_id, map_aggregate)
            assert comp.state == BehaviorStateEnum.CHASE # 気づく

        def test_z_axis_distance(self, behavior_service, pathfinding_service):
            """Z軸を含む距離計算が正しいこと"""
            tiles = [Tile(Coordinate(0,0,0), TerrainType.grass()), Tile(Coordinate(0,0,1), TerrainType.grass())]
            map_agg = PhysicalMapAggregate.create(SpotId(2), tiles)
            
            comp = AutonomousBehaviorComponent(vision_range=1)
            monster = WorldObject(WorldObjectId(100), Coordinate(0,0,0), ObjectTypeEnum.NPC, is_blocking=False, component=comp)
            map_agg.add_object(monster)
            
            # 距離1の敵
            p1 = WorldObject(WorldObjectId(1), Coordinate(0,0,1), ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human"))
            map_agg.add_object(p1)
            
            # 敵対サービスが人間を敵視するように再設定
            from ai_rpg_world.domain.world.enum.world_enum import Disposition
            behavior_service._hostility_service = ConfigurableHostilityService(race_disposition_table={"monster": {"human": Disposition.HOSTILE}})
            
            behavior_service.plan_next_move(WorldObjectId(100), map_agg)
            assert comp.state == BehaviorStateEnum.CHASE

    class TestCustomPolicyAndStrategy:
        """カスタムポリシー・戦略を注入した BehaviorService の動作"""

        def test_behavior_service_uses_injected_skill_policy(self, pathfinding_service, map_aggregate):
            """注入したスキル選択ポリシーが使われること（2番目スキルを選ぶポリシー）"""
            class SecondInRangeSkillPolicy(SkillSelectionPolicy):
                def select_slot(self, actor, target, available_skills, context=None):
                    in_range = [
                        s for s in available_skills
                        if actor.coordinate.distance_to(target.coordinate) <= s.range
                    ]
                    return in_range[1].slot_index if len(in_range) > 1 else (in_range[0].slot_index if in_range else None)

            strategy = DefaultBehaviorStrategy(pathfinding_service, SecondInRangeSkillPolicy())
            from ai_rpg_world.domain.world.enum.world_enum import Disposition
            hostility = ConfigurableHostilityService(race_disposition_table={"goblin": {"human": Disposition.HOSTILE}})
            service = BehaviorService(pathfinding_service, hostility, strategy=strategy)

            monster_id = WorldObjectId(100)
            skills = [
                MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
                MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
            ]
            comp = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=5,
                fov_angle=360,
                available_skills=skills,
            )
            monster = WorldObject(monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, component=comp)
            map_aggregate.add_object(monster)
            player = WorldObject(
                WorldObjectId(1), Coordinate(6, 5), ObjectTypeEnum.PLAYER, component=ActorComponent(race="human")
            )
            map_aggregate.add_object(player)

            action = service.plan_action(monster_id, map_aggregate)
            assert action.action_type == BehaviorActionType.USE_SKILL
            assert action.skill_slot_index == 1

    class TestAllegianceExclusion:
        """味方をターゲットから除外するテスト"""

        def test_ally_excluded_from_targets(self, pathfinding_service, map_aggregate):
            """同一パックの味方は視界内にいてもターゲットに選ばれず、プレイヤーのみターゲットになる"""
            from ai_rpg_world.domain.world.enum.world_enum import Disposition
            hostility = ConfigurableHostilityService(race_disposition_table={"goblin": {"human": Disposition.HOSTILE}})
            allegiance = PackAllegianceService()
            service = BehaviorService(
                pathfinding_service, hostility, allegiance_service=allegiance
            )
            pack = PackId.create("wolf_pack")
            monster_a_id = WorldObjectId(100)
            comp_a = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=10,
                fov_angle=360,
                pack_id=pack,
            )
            monster_a = WorldObject(
                monster_a_id, Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp_a
            )
            map_aggregate.add_object(monster_a)

            monster_b_id = WorldObjectId(101)
            comp_b = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=10,
                fov_angle=360,
                pack_id=pack,
            )
            monster_b = WorldObject(
                monster_b_id, Coordinate(6, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp_b
            )
            map_aggregate.add_object(monster_b)

            player_id = WorldObjectId(1)
            player = WorldObject(
                player_id, Coordinate(7, 5), ObjectTypeEnum.PLAYER, is_blocking=False,
                component=ActorComponent(race="human"),
            )
            map_aggregate.add_object(player)

            action = service.plan_action(monster_a_id, map_aggregate)
            assert comp_a.target_id == player_id
            assert comp_a.target_id != monster_b_id

        def test_actor_not_in_map_raises_object_not_found(self, behavior_service, map_aggregate):
            """マップに存在しない actor_id で plan_action を呼ぶと ObjectNotFoundException"""
            missing_id = WorldObjectId(99999)
            with pytest.raises(ObjectNotFoundException) as exc_info:
                behavior_service.plan_action(missing_id, map_aggregate)
            assert str(missing_id) in str(exc_info.value) or "99999" in str(exc_info.value)
            assert "not found" in str(exc_info.value).lower()
            assert exc_info.value.error_code == "MAP.OBJECT_NOT_FOUND"

    class TestEnrageTransition:
        """phase_thresholds による ENRAGE 遷移のテスト"""

        def test_phase_threshold_triggers_enrage_state(self, pathfinding_service, hostility_service, map_aggregate):
            """HP% が phase_thresholds[0] 以下になると ENRAGE 状態に遷移しイベントが発行されること"""
            service = BehaviorService(pathfinding_service, hostility_service)
            comp = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=5,
                fov_angle=360,
                hp_percentage=0.3,
                flee_threshold=0.1,
                phase_thresholds=[0.5],
            )
            monster_id = WorldObjectId(100)
            monster = WorldObject(
                monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp
            )
            map_aggregate.add_object(monster)
            player = WorldObject(
                WorldObjectId(1), Coordinate(6, 5), ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human")
            )
            map_aggregate.add_object(player)
            service.plan_action(monster_id, map_aggregate)
            assert comp.state == BehaviorStateEnum.ENRAGE
            events = map_aggregate.get_events()
            assert any(
                isinstance(e, ActorStateChangedEvent) and e.new_state == BehaviorStateEnum.ENRAGE
                for e in events
            )

    class TestDispositionThreatFlee:
        """THREAT（脅威）視界内で FLEE に遷移するテスト"""

        def test_threat_in_sight_transitions_to_flee(self, pathfinding_service, map_aggregate):
            """視界内に THREAT がいる場合、攻撃せず FLEE に遷移すること"""
            hostility = ConfigurableHostilityService(
                race_disposition_table={
                    "goblin": {"dragon": Disposition.THREAT},
                }
            )
            service = BehaviorService(pathfinding_service, hostility)
            comp = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=3,
                fov_angle=360,
                hp_percentage=1.0,
            )
            monster_id = WorldObjectId(100)
            monster = WorldObject(
                monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp
            )
            map_aggregate.add_object(monster)
            dragon = WorldObject(
                WorldObjectId(200),
                Coordinate(6, 5),
                ObjectTypeEnum.NPC,
                is_blocking=False,
                component=AutonomousBehaviorComponent(race="dragon"),
            )
            map_aggregate.add_object(dragon)

            action = service.plan_action(monster_id, map_aggregate)

            assert comp.state == BehaviorStateEnum.FLEE
            assert comp.target_id == dragon.object_id
            assert action.action_type == BehaviorActionType.MOVE

        def test_hostile_and_threat_present_threat_triggers_flee(self, pathfinding_service, map_aggregate):
            """視界内に HOSTILE と THREAT がいる場合、THREAT で FLEE になること（THREAT 優先）"""
            hostility = ConfigurableHostilityService(
                race_disposition_table={
                    "goblin": {
                        "human": Disposition.HOSTILE,
                        "dragon": Disposition.THREAT,
                    },
                }
            )
            service = BehaviorService(pathfinding_service, hostility)
            comp = AutonomousBehaviorComponent(
                race="goblin",
                vision_range=3,
                fov_angle=360,
                hp_percentage=1.0,
            )
            monster_id = WorldObjectId(100)
            monster = WorldObject(
                monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp
            )
            map_aggregate.add_object(monster)
            human = WorldObject(
                WorldObjectId(1),
                Coordinate(5, 6),
                ObjectTypeEnum.PLAYER,
                is_blocking=False,
                component=ActorComponent(race="human"),
            )
            dragon = WorldObject(
                WorldObjectId(200),
                Coordinate(5, 4),
                ObjectTypeEnum.NPC,
                is_blocking=False,
                component=AutonomousBehaviorComponent(race="dragon"),
            )
            map_aggregate.add_object(human)
            map_aggregate.add_object(dragon)

            service.plan_action(monster_id, map_aggregate)

            assert comp.state == BehaviorStateEnum.FLEE
            assert comp.target_id == dragon.object_id

    class TestDispositionPreyPriority:
        """PREY（獲物）優先ターゲット選択のテスト"""

        def test_prey_selected_over_hostile(self, pathfinding_service, map_aggregate):
            """視界内に HOSTILE と PREY がいる場合、PREY がターゲットに選ばれること"""
            hostility = ConfigurableHostilityService(
                race_disposition_table={
                    "wolf": {
                        "human": Disposition.HOSTILE,
                        "rabbit": Disposition.PREY,
                    },
                }
            )
            service = BehaviorService(pathfinding_service, hostility)
            comp = AutonomousBehaviorComponent(
                race="wolf",
                vision_range=10,
                fov_angle=360,
                hp_percentage=1.0,
            )
            monster_id = WorldObjectId(100)
            monster = WorldObject(
                monster_id, Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp
            )
            map_aggregate.add_object(monster)
            human = WorldObject(
                WorldObjectId(1),
                Coordinate(5, 4),
                ObjectTypeEnum.PLAYER,
                is_blocking=False,
                component=ActorComponent(race="human"),
            )
            rabbit = WorldObject(
                WorldObjectId(201),
                Coordinate(5, 6),
                ObjectTypeEnum.NPC,
                is_blocking=False,
                component=AutonomousBehaviorComponent(race="rabbit"),
            )
            map_aggregate.add_object(human)
            map_aggregate.add_object(rabbit)

            service.plan_action(monster_id, map_aggregate)

            assert comp.state == BehaviorStateEnum.CHASE
            assert comp.target_id == rabbit.object_id
