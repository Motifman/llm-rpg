import pytest
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum, MovementCapabilityEnum
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent


class TestActorComponent:
    def test_actor_creation(self):
        capability = MovementCapability.ghost()
        actor_comp = ActorComponent(
            direction=DirectionEnum.NORTH,
            capability=capability,
            owner_id="player_1",
            is_npc=False
        )
        
        obj = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0, 0),
            ObjectTypeEnum.PLAYER,
            is_blocking=True,
            component=actor_comp
        )
        
        assert obj.object_type == ObjectTypeEnum.PLAYER
        assert isinstance(obj.component, ActorComponent)
        assert obj.component.direction == DirectionEnum.NORTH
        assert obj.component.capability == capability
        assert obj.component.owner_id == "player_1"
        assert obj.component.is_npc is False

    def test_actor_turn(self):
        actor_comp = ActorComponent()
        assert actor_comp.direction == DirectionEnum.SOUTH
        
        actor_comp.turn(DirectionEnum.EAST)
        assert actor_comp.direction == DirectionEnum.EAST

    def test_actor_to_dict(self):
        actor_comp = ActorComponent(owner_id="p1")
        d = actor_comp.to_dict()
        
        assert d["direction"] == "SOUTH"
        assert d["owner_id"] == "p1"
        assert "WALK" in d["capabilities"]
