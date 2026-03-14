"""ChestInteractionPolicy の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest
from ai_rpg_world.domain.world.service.chest_interaction_policy import ChestInteractionPolicy
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    ChestComponent,
    InteractableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    ActorBusyException,
    ChestClosedException,
    InteractionOutOfRangeException,
    NotAChestException,
)
from ai_rpg_world.domain.common.value_object import WorldTick


@pytest.fixture
def current_tick():
    return WorldTick(10)


class TestValidateCanAccessChest:
    """validate_can_access_chest のテスト"""

    class TestSuccessCases:
        def test_open_chest_adjacent_succeeds(self, current_tick):
            # Given: 開いたチェストに隣接
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            chest = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )

            # When & Then
            ChestInteractionPolicy.validate_can_access_chest(actor, chest, current_tick)

        def test_same_cell_succeeds(self, current_tick):
            # Given: actor と chest が同一マス
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
            )
            chest = WorldObject(
                WorldObjectId(2),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )

            # When & Then
            ChestInteractionPolicy.validate_can_access_chest(actor, chest, current_tick)

    class TestActorBusy:
        def test_raises_when_actor_busy(self, current_tick):
            # Given: actor が busy
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
                busy_until=WorldTick(20),
            )
            chest = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )

            # When & Then
            with pytest.raises(ActorBusyException) as exc_info:
                ChestInteractionPolicy.validate_can_access_chest(actor, chest, current_tick)
            assert "busy" in str(exc_info.value).lower()

        def test_passes_when_busy_expired(self, current_tick):
            # Given: busy_until が過去
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
                busy_until=WorldTick(5),
            )
            chest = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )

            # When & Then
            ChestInteractionPolicy.validate_can_access_chest(actor, chest, current_tick)

    class TestChestComponent:
        def test_raises_when_not_chest(self, current_tick):
            # Given: component が ChestComponent でない
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then
            with pytest.raises(NotAChestException) as exc_info:
                ChestInteractionPolicy.validate_can_access_chest(actor, target, current_tick)
            assert "chest" in str(exc_info.value).lower()

        def test_raises_when_component_none(self, current_tick):
            # Given: component が None
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
            )
            obj = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.CHEST,
                component=None,
            )

            # When & Then
            with pytest.raises(NotAChestException):
                ChestInteractionPolicy.validate_can_access_chest(actor, obj, current_tick)

    class TestChestOpen:
        def test_raises_when_chest_closed(self, current_tick):
            # Given: 閉じたチェスト
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
            )
            chest = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=False),
            )

            # When & Then
            with pytest.raises(ChestClosedException) as exc_info:
                ChestInteractionPolicy.validate_can_access_chest(actor, chest, current_tick)
            assert "closed" in str(exc_info.value).lower()

    class TestDistance:
        def test_raises_when_too_far(self, current_tick):
            # Given: 2マス以上離れている
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
            )
            chest = WorldObject(
                WorldObjectId(2),
                Coordinate(2, 0, 0),
                ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )

            # When & Then
            with pytest.raises(InteractionOutOfRangeException) as exc_info:
                ChestInteractionPolicy.validate_can_access_chest(actor, chest, current_tick)
            assert "far" in str(exc_info.value).lower() or "too" in str(exc_info.value).lower()

        def test_raises_when_diagonal_2_away(self, current_tick):
            # Given: chebyshev distance = 2（斜め2マス）
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(),
            )
            chest = WorldObject(
                WorldObjectId(2),
                Coordinate(2, 2, 0),
                ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )

            # When & Then
            with pytest.raises(InteractionOutOfRangeException):
                ChestInteractionPolicy.validate_can_access_chest(actor, chest, current_tick)
