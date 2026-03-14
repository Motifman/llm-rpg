"""MapInteractionPolicy の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest
from ai_rpg_world.domain.world.service.map_interaction_policy import MapInteractionPolicy
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    InteractableComponent,
    ChestComponent,
    PlaceableComponent,
    StaticPlaceableInnerComponent,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    ActorBusyException,
    InteractionOutOfRangeException,
    NotFacingTargetException,
    NotInteractableException,
)
from ai_rpg_world.domain.common.value_object import WorldTick


@pytest.fixture
def current_tick():
    return WorldTick(10)


class TestValidateCanInteract:
    """validate_can_interact のテスト"""

    class TestSuccessCases:
        def test_adjacent_facing_target_succeeds(self, current_tick):
            # Given: actor at (0,0) facing SOUTH, target at (0,1)
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk", {"name": "Bob"}),
            )

            # When & Then: 例外なしで通過
            MapInteractionPolicy.validate_can_interact(actor, target, current_tick)

        def test_same_cell_succeeds(self, current_tick):
            # Given: actor and target 同一マス（向きチェックはスキップ）
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.NORTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then
            MapInteractionPolicy.validate_can_interact(actor, target, current_tick)

        def test_diagonal_adjacent_succeeds(self, current_tick):
            # Given: 8方向隣接（chebyshev=1）
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTHEAST),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then
            MapInteractionPolicy.validate_can_interact(actor, target, current_tick)

    class TestActorBusy:
        def test_raises_when_actor_busy(self, current_tick):
            # Given: actor が busy_until=20
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
                busy_until=WorldTick(20),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then: current_tick=10 < 20 なので busy
            with pytest.raises(ActorBusyException) as exc_info:
                MapInteractionPolicy.validate_can_interact(actor, target, current_tick)
            assert "busy" in str(exc_info.value).lower()

        def test_passes_when_busy_until_passed(self, current_tick):
            # Given: actor が busy_until=5、current_tick=10（すでに完了）
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
                busy_until=WorldTick(5),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then: 例外なし
            MapInteractionPolicy.validate_can_interact(actor, target, current_tick)

    class TestDistance:
        def test_raises_when_too_far(self, current_tick):
            # Given: 2マス以上離れている
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(2, 2, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then
            with pytest.raises(InteractionOutOfRangeException) as exc_info:
                MapInteractionPolicy.validate_can_interact(actor, target, current_tick)
            assert "far" in str(exc_info.value).lower() or "too" in str(exc_info.value).lower()

        def test_raises_when_distance_exactly_2(self, current_tick):
            # Given: chebyshev distance = 2
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(2, 0, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then
            with pytest.raises(InteractionOutOfRangeException):
                MapInteractionPolicy.validate_can_interact(actor, target, current_tick)

    class TestDirection:
        def test_raises_when_not_facing_adjacent_target(self, current_tick):
            # Given: actor at (0,0), target at (0,1) (South). Actor faces North.
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.NORTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then
            with pytest.raises(NotFacingTargetException) as exc_info:
                MapInteractionPolicy.validate_can_interact(actor, target, current_tick)
            assert "facing" in str(exc_info.value).lower()

        def test_passes_when_facing_correct_direction(self, current_tick):
            # Given: actor faces SOUTH, target is South
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )

            # When & Then
            MapInteractionPolicy.validate_can_interact(actor, target, current_tick)

    class TestInteractable:
        def test_raises_when_target_not_interactable(self, current_tick):
            # Given: target に component なし、または interaction_type が None
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.CHEST,
                component=None,
            )

            # When & Then
            with pytest.raises(NotInteractableException) as exc_info:
                MapInteractionPolicy.validate_can_interact(actor, target, current_tick)
            assert "interactable" in str(exc_info.value).lower() or "not" in str(exc_info.value).lower()

        def test_passes_when_target_has_interaction_type(self, current_tick):
            # Given: ChestComponent は interaction_type = OPEN_CHEST
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=False),
            )

            # When & Then
            MapInteractionPolicy.validate_can_interact(actor, target, current_tick)

        def test_raises_when_component_has_no_interaction_type(self, current_tick):
            # Given: コンポーネントはあるが interaction_type が None（PlaceableComponent + StaticPlaceableInnerComponent）
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                WorldObjectId(2),
                Coordinate(0, 1, 0),
                ObjectTypeEnum.SIGN,
                component=PlaceableComponent(
                    ItemSpecId(1),
                    StaticPlaceableInnerComponent(),
                ),
            )

            # When & Then: interaction_type が None のため NotInteractableException
            with pytest.raises(NotInteractableException) as exc_info:
                MapInteractionPolicy.validate_can_interact(actor, target, current_tick)
            assert "interactable" in str(exc_info.value).lower() or "not" in str(
                exc_info.value
            ).lower()
