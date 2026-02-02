import pytest
import math
from unittest.mock import MagicMock
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, BehaviorStateEnum, DirectionEnum
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService
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
        return ConfigurableHostilityService(
            race_hostility_table={"goblin": {"human"}}
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
            map_aggregate.move_object(monster_id, last_pos)
            
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
            behavior_service._hostility_service = ConfigurableHostilityService(race_hostility_table={"monster": {"human"}})
            
            behavior_service.plan_next_move(WorldObjectId(100), map_agg)
            assert comp.state == BehaviorStateEnum.CHASE
