import pytest
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum, MovementCapabilityEnum
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent


class TestActorComponent:
    def test_actor_creation(self):
        capability = MovementCapability.ghost()
        player_id = PlayerId(100)
        actor_comp = ActorComponent(
            direction=DirectionEnum.NORTH,
            capability=capability,
            player_id=player_id,
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
        assert obj.component.player_id == player_id
        assert obj.component.is_npc is False

    def test_actor_turn(self):
        actor_comp = ActorComponent()
        assert actor_comp.direction == DirectionEnum.SOUTH
        
        actor_comp.turn(DirectionEnum.EAST)
        assert actor_comp.direction == DirectionEnum.EAST

    def test_actor_to_dict(self):
        player_id = PlayerId(100)
        actor_comp = ActorComponent(player_id=player_id)
        d = actor_comp.to_dict()
        
        assert d["direction"] == "SOUTH"
        assert d["player_id"] == "100"
        assert "WALK" in d["capabilities"]
