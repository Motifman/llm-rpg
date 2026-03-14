"""HarvestSessionPolicy の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest
from ai_rpg_world.domain.world.service.harvest_session_policy import HarvestSessionPolicy
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    HarvestableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    ActorBusyException,
    InteractionOutOfRangeException,
    NotFacingTargetException,
)
from ai_rpg_world.domain.world.exception.harvest_exception import NotHarvestableException
from ai_rpg_world.domain.common.value_object import WorldTick


@pytest.fixture
def current_tick():
    return WorldTick(10)


class TestValidateCanStartHarvest:
    """validate_can_start_harvest のテスト"""

    class TestSuccessCases:
        def test_adjacent_facing_target_succeeds(self, current_tick):
            # Given: actor at (0,0) facing EAST, harvestable at (1,0)
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.EAST),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(
                    loot_table_id=1,
                    max_quantity=1,
                    harvest_duration=10,
                ),
            )

            # When & Then: 例外なしで通過
            HarvestSessionPolicy.validate_can_start_harvest(
                actor, target, current_tick
            )

        def test_same_cell_succeeds(self, current_tick):
            # Given: actor and target 同一マス（向きチェックはスキップ）
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.NORTH),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(loot_table_id=1),
            )

            # When & Then
            HarvestSessionPolicy.validate_can_start_harvest(
                actor, target, current_tick
            )

        def test_diagonal_adjacent_succeeds(self, current_tick):
            # Given: 8方向隣接（chebyshev=1）、SE方向を向く
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTHEAST),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(loot_table_id=1),
            )

            # When & Then
            HarvestSessionPolicy.validate_can_start_harvest(
                actor, target, current_tick
            )

        def test_harvestable_with_all_params_succeeds(self, current_tick):
            # Given: パラメータを指定した HarvestableComponent
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(
                    loot_table_id=1,
                    max_quantity=5,
                    respawn_interval=100,
                    harvest_duration=15,
                    stamina_cost=20,
                ),
            )

            # When & Then
            HarvestSessionPolicy.validate_can_start_harvest(
                actor, target, current_tick
            )

    class TestActorBusy:
        def test_raises_when_actor_busy(self, current_tick):
            # Given: actor が busy_until=20
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.EAST),
                busy_until=WorldTick(20),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(loot_table_id=1),
            )

            # When & Then: current_tick=10 < 20 なので busy
            with pytest.raises(ActorBusyException) as exc_info:
                HarvestSessionPolicy.validate_can_start_harvest(
                    actor, target, current_tick
                )
            assert "busy" in str(exc_info.value).lower()

        def test_passes_when_busy_until_passed(self, current_tick):
            # Given: actor が busy_until=5、current_tick=10（すでに完了）
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.EAST),
                busy_until=WorldTick(5),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(loot_table_id=1),
            )

            # When & Then: 例外なし
            HarvestSessionPolicy.validate_can_start_harvest(
                actor, target, current_tick
            )

    class TestDistance:
        def test_raises_when_too_far(self, current_tick):
            # Given: 2マス以上離れている
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.EAST),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(2, 2, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(loot_table_id=1),
            )

            # When & Then
            with pytest.raises(InteractionOutOfRangeException) as exc_info:
                HarvestSessionPolicy.validate_can_start_harvest(
                    actor, target, current_tick
                )
            assert "far" in str(exc_info.value).lower() or "too" in str(
                exc_info.value
            ).lower()

        def test_raises_when_distance_exactly_2(self, current_tick):
            # Given: chebyshev distance = 2
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.EAST),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(2, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(loot_table_id=1),
            )

            # When & Then
            with pytest.raises(InteractionOutOfRangeException):
                HarvestSessionPolicy.validate_can_start_harvest(
                    actor, target, current_tick
                )

    class TestDirection:
        def test_raises_when_not_facing_adjacent_target(self, current_tick):
            # Given: actor at (0,0), target at (1,0) (East). Actor faces West.
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.WEST),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(loot_table_id=1),
            )

            # When & Then
            with pytest.raises(NotFacingTargetException) as exc_info:
                HarvestSessionPolicy.validate_can_start_harvest(
                    actor, target, current_tick
                )
            assert "facing" in str(exc_info.value).lower()

        def test_passes_when_facing_correct_direction(self, current_tick):
            # Given: actor faces EAST, target is East
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.EAST),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=HarvestableComponent(loot_table_id=1),
            )

            # When & Then
            HarvestSessionPolicy.validate_can_start_harvest(
                actor, target, current_tick
            )

    class TestHarvestable:
        def test_raises_when_target_not_harvestable(self, current_tick):
            # Given: target が HarvestableComponent でない（ActorComponent）
            from ai_rpg_world.domain.world.entity.world_object_component import (
                ActorComponent as OtherActor,
            )

            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.EAST),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=OtherActor(direction=DirectionEnum.WEST),
            )

            # When & Then
            with pytest.raises(NotHarvestableException) as exc_info:
                HarvestSessionPolicy.validate_can_start_harvest(
                    actor, target, current_tick
                )
            assert "harvestable" in str(exc_info.value).lower() or "not" in str(
                exc_info.value
            ).lower()

        def test_raises_when_component_none(self, current_tick):
            # Given: component が None
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.EAST),
            )
            target = WorldObject(
                WorldObjectId(200),
                Coordinate(1, 0, 0),
                ObjectTypeEnum.RESOURCE,
                component=None,
            )

            # When & Then
            with pytest.raises(NotHarvestableException) as exc_info:
                HarvestSessionPolicy.validate_can_start_harvest(
                    actor, target, current_tick
                )
            assert "harvestable" in str(exc_info.value).lower() or "not" in str(
                exc_info.value
            ).lower()
