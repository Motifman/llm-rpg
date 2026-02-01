import pytest
from ai_rpg_world.domain.world.enum.world_enum import MovementCapabilityEnum
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability


class TestMovementCapability:
    def test_normal_walk(self):
        cap = MovementCapability.normal_walk()
        assert cap.has_capability(MovementCapabilityEnum.WALK)
        assert not cap.has_capability(MovementCapabilityEnum.SWIM)
        assert cap.speed_modifier == 1.0

    def test_ghost(self):
        cap = MovementCapability.ghost()
        assert cap.has_capability(MovementCapabilityEnum.WALK)
        assert cap.has_capability(MovementCapabilityEnum.GHOST_WALK)

    def test_with_capability(self):
        cap = MovementCapability.normal_walk().with_capability(MovementCapabilityEnum.FLY)
        assert cap.has_capability(MovementCapabilityEnum.FLY)
        assert cap.has_capability(MovementCapabilityEnum.WALK)

    def test_without_capability(self):
        cap = MovementCapability.ghost().without_capability(MovementCapabilityEnum.GHOST_WALK)
        assert not cap.has_capability(MovementCapabilityEnum.GHOST_WALK)
        assert cap.has_capability(MovementCapabilityEnum.WALK)

    def test_speed_modifier(self):
        cap = MovementCapability.normal_walk().with_speed_modifier(0.5)
        assert cap.speed_modifier == 0.5

    def test_negative_speed_modifier_becomes_zero(self):
        cap = MovementCapability.normal_walk().with_speed_modifier(-1.0)
        assert cap.speed_modifier == 0.0
