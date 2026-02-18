import pytest
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
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
        chest = ChestComponent(item_ids=[ItemInstanceId.create(101), ItemInstanceId.create(102)])
        
        # When
        obj = WorldObject(obj_id, coord, ObjectTypeEnum.CHEST, component=chest)
        
        # Then
        assert obj.object_id == obj_id
        assert obj.coordinate == coord
        assert isinstance(obj.component, ChestComponent)
        assert [e.value for e in obj.component.item_ids] == [101, 102]

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
        from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum

        data = {"key": "value"}
        interactable = InteractableComponent(interaction_type="examine", data=data)
        obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST, component=interactable)

        assert obj.is_actor is False
        assert obj.interaction_type == InteractionTypeEnum.EXAMINE
        assert obj.interaction_data == data

    def test_non_component_properties(self):
        """コンポーネントがない場合のプロパティがデフォルト値を返すこと"""
        obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST)
        
        assert obj.is_actor is False
        assert obj.capability is None
        assert obj.direction is None
        assert obj.interaction_type is None
        assert obj.interaction_data == {}

    def test_busy_state(self):
        """ビジー状態の管理が正しく動作すること"""
        from ai_rpg_world.domain.common.value_object import WorldTick
        
        obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.PLAYER)
        
        # 初期状態はビジーではない
        assert obj.busy_until is None
        assert obj.is_busy(WorldTick(10)) is False
        
        # ビジー状態を設定
        obj.set_busy(WorldTick(20))
        assert obj.busy_until == WorldTick(20)
        assert obj.is_busy(WorldTick(10)) is True
        assert obj.is_busy(WorldTick(19)) is True
        assert obj.is_busy(WorldTick(20)) is False # 20時点で完了
        
        # ビジー解除
        obj.clear_busy()
        assert obj.busy_until is None
        assert obj.is_busy(WorldTick(10)) is False
