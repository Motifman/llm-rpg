from ai_rpg_world.domain.combat.service.hit_box_config_service import (
    DefaultHitBoxConfigService,
)


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
