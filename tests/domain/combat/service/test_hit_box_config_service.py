from ai_rpg_world.domain.combat.service.hit_box_config_service import (
    DefaultHitBoxConfigService,
)
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestDefaultHitBoxConfigService:
    def test_get_substeps_per_tick_default(self):
        config = DefaultHitBoxConfigService()
        assert config.get_substeps_per_tick() == 4

    def test_get_substeps_per_tick_custom(self):
        config = DefaultHitBoxConfigService(substeps_per_tick=8)
        assert config.get_substeps_per_tick() == 8

    def test_substeps_per_tick_is_clamped_to_one_when_zero_or_negative(self):
        zero_config = DefaultHitBoxConfigService(substeps_per_tick=0)
        negative_config = DefaultHitBoxConfigService(substeps_per_tick=-3)
        assert zero_config.get_substeps_per_tick() == 1
        assert negative_config.get_substeps_per_tick() == 1

    def test_get_substeps_for_hit_box_uses_velocity_bands(self):
        config = DefaultHitBoxConfigService(
            substeps_per_tick=4,
            low_speed_substeps=2,
            high_speed_substeps=8,
            low_speed_threshold=0.5,
            high_speed_threshold=1.5,
        )

        low = self._create_hit_box(HitBoxVelocity(0.25, 0.0, 0.0))
        mid = self._create_hit_box(HitBoxVelocity(1.0, 0.0, 0.0))
        high = self._create_hit_box(HitBoxVelocity(2.0, 0.0, 0.0))

        assert config.get_substeps_for_hit_box(low) == 2
        assert config.get_substeps_for_hit_box(mid) == 4
        assert config.get_substeps_for_hit_box(high) == 8

    def test_get_max_collision_checks_per_tick(self):
        config = DefaultHitBoxConfigService(max_collision_checks_per_tick=128)
        assert config.get_max_collision_checks_per_tick() == 128

    def _create_hit_box(self, velocity: HitBoxVelocity) -> HitBoxAggregate:
        return HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId.create(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(0),
            duration=10,
            velocity=velocity,
        )
