import pytest
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ChestComponent, DoorComponent
from ai_rpg_world.domain.world.exception.map_exception import LockedDoorException
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum


class TestWorldObject:
    def test_world_object_creation_with_chest(self):
        # Given
        obj_id = WorldObjectId(1)
        coord = Coordinate(1, 1)
        chest = ChestComponent(item_ids=[101, 102])
        
        # When
        obj = WorldObject(obj_id, coord, ObjectTypeEnum.CHEST, component=chest)
        
        # Then
        assert obj.object_id == obj_id
        assert obj.coordinate == coord
        assert isinstance(obj.component, ChestComponent)
        assert obj.component.item_ids == [101, 102]

    def test_world_object_creation_with_door(self):
        # Given
        obj_id = WorldObjectId(2)
        coord = Coordinate(2, 2)
        door = DoorComponent(is_locked=True)
        
        # When
        obj = WorldObject(obj_id, coord, ObjectTypeEnum.DOOR, component=door)
        
        # Then
        assert obj.object_id == obj_id
        assert isinstance(obj.component, DoorComponent)
        assert obj.component.is_locked is True
        assert obj.component.is_open is False

    def test_door_interaction(self):
        door = DoorComponent(is_locked=True)
        
        with pytest.raises(LockedDoorException):
            door.open()
            
        door.unlock()
        door.open()
        assert door.is_open is True

    def test_world_object_to_dict(self):
        obj = WorldObject(
            WorldObjectId(1), 
            Coordinate(1, 1), 
            ObjectTypeEnum.CHEST, 
            component=ChestComponent(is_open=True)
        )
        
        d = obj.to_dict()
        assert d["object_id"] == "1"
        assert d["component"]["is_open"] is True

    def test_actor_properties(self):
        """アクター関連のプロパティが正しく動作すること"""
        from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
        
        cap = MovementCapability.normal_walk()
        actor = ActorComponent(direction=DirectionEnum.NORTH, capability=cap)
        obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.PLAYER, component=actor)
        
        assert obj.is_actor is True
        assert obj.capability == cap
        assert obj.direction == DirectionEnum.NORTH
        
        obj.turn(DirectionEnum.SOUTH)
        assert obj.direction == DirectionEnum.SOUTH

    def test_interactable_properties(self):
        """インタラクション関連のプロパティが正しく動作すること"""
        from ai_rpg_world.domain.world.entity.world_object_component import InteractableComponent
        
        data = {"key": "value"}
        interactable = InteractableComponent(interaction_type="examine", data=data)
        obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST, component=interactable)
        
        assert obj.is_actor is False
        assert obj.interaction_type == "examine"
        assert obj.interaction_data == data

    def test_non_component_properties(self):
        """コンポーネントがない場合のプロパティがデフォルト値を返すこと"""
        obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST)
        
        assert obj.is_actor is False
        assert obj.capability is None
        assert obj.direction is None
        assert obj.interaction_type is None
        assert obj.interaction_data == {}
