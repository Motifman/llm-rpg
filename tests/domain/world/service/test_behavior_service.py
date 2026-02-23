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
from ai_rpg_world.domain.world.value_object.behavior_context import GrowthContext
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
        comp.hp_percentage = 0.1
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

    class TestBuildObservationAndErrors:
        """build_observation とエラー系のテスト（plan_action 削除に伴い観測・例外のみ残す）"""

        def test_actor_not_in_map_raises_object_not_found(self, behavior_service, map_aggregate):
            """マップに存在しない actor_id で build_observation を呼ぶと ObjectNotFoundException"""
            missing_id = WorldObjectId(99999)
            with pytest.raises(ObjectNotFoundException) as exc_info:
                behavior_service.build_observation(missing_id, map_aggregate)
            assert str(missing_id) in str(exc_info.value) or "99999" in str(exc_info.value)
            assert "not found" in str(exc_info.value).lower()
            assert exc_info.value.error_code == "MAP.OBJECT_NOT_FOUND"

        def test_build_observation_returns_observation_with_visible_hostiles(self, behavior_service, map_aggregate):
            """build_observation が視界内の敵対・選択ターゲットを含む観測を返すこと"""
            monster_id = WorldObjectId(100)
            comp = AutonomousBehaviorComponent(race="goblin", vision_range=5, fov_angle=360)
            monster = WorldObject(monster_id, Coordinate(0, 0), ObjectTypeEnum.NPC, is_blocking=False, component=comp)
            map_aggregate.add_object(monster)
            player_id = WorldObjectId(1)
            player = WorldObject(player_id, Coordinate(2, 0), ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human"))
            map_aggregate.add_object(player)
            growth = GrowthContext(effective_flee_threshold=0.2, allow_chase=True)
            obs = behavior_service.build_observation(
                monster_id,
                map_aggregate,
                growth_context=growth,
                current_tick=WorldTick(0),
            )
            assert obs.visible_hostiles or obs.visible_threats or obs.selected_target is not None
            assert obs.growth_context is growth
            assert obs.current_tick is not None

        def test_build_observation_non_autonomous_returns_empty_like_observation(self, behavior_service, map_aggregate):
            """自律でないアクターでは build_observation が空の観測を返すこと"""
            actor_id = WorldObjectId(50)
            actor = WorldObject(actor_id, Coordinate(1, 1), ObjectTypeEnum.NPC, is_blocking=False, component=ActorComponent(race="human"))
            map_aggregate.add_object(actor)
            obs = behavior_service.build_observation(actor_id, map_aggregate)
            assert obs.visible_threats == []
            assert obs.visible_hostiles == []
            assert obs.selected_target is None

