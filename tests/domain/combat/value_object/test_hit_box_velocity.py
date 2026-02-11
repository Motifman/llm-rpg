from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class TestHitBoxVelocity:
    def test_zero_is_stationary(self):
        velocity = HitBoxVelocity.zero()
        assert velocity.is_stationary is True

    def test_non_zero_is_not_stationary(self):
        velocity = HitBoxVelocity(dx=1.0, dy=0.0, dz=0.0)
        assert velocity.is_stationary is False

    def test_small_value_is_stationary_with_epsilon(self):
        velocity = HitBoxVelocity(dx=1e-12, dy=0.0, dz=0.0)
        assert velocity.is_stationary is True

    def test_apply_to_coordinate_with_step_ratio(self):
        velocity = HitBoxVelocity(dx=2.0, dy=-1.0, dz=1.0)
        current = Coordinate(10, 10, 0)

        updated = velocity.apply_to(current, step_ratio=0.5)

        assert updated == Coordinate(11, 9, 0)

    def test_apply_to_precise_position(self):
        velocity = HitBoxVelocity(dx=0.25, dy=0.5, dz=0.0)
        updated = velocity.apply_to_precise(1.0, 1.0, 0.0, step_ratio=0.5)
        assert updated == (1.125, 1.25, 0.0)
