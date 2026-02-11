from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class TestHitBoxVelocity:
    def test_zero_is_stationary(self):
        velocity = HitBoxVelocity.zero()
        assert velocity.is_stationary is True

    def test_non_zero_is_not_stationary(self):
        velocity = HitBoxVelocity(dx=1, dy=0, dz=0)
        assert velocity.is_stationary is False

    def test_apply_to_coordinate(self):
        velocity = HitBoxVelocity(dx=2, dy=-1, dz=1)
        current = Coordinate(10, 10, 0)

        updated = velocity.apply_to(current)

        assert updated == Coordinate(12, 9, 1)
