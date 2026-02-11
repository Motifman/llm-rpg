import pytest

from ai_rpg_world.domain.combat.exception.combat_exceptions import HitEffectValidationException
from ai_rpg_world.domain.combat.value_object.hit_effect import HitEffect, HitEffectType


class TestHitEffect:
    def test_knockback_factory(self):
        effect = HitEffect.knockback(cells=2, chance=0.5)
        assert effect.effect_type == HitEffectType.KNOCKBACK
        assert effect.duration_ticks == 0
        assert effect.intensity == 2.0
        assert effect.chance == 0.5

    def test_slow_factory(self):
        effect = HitEffect.slow(rate=0.25, duration_ticks=4)
        assert effect.effect_type == HitEffectType.SLOW
        assert effect.duration_ticks == 4
        assert effect.intensity == 0.25
        assert effect.chance == 1.0

    def test_poison_factory(self):
        effect = HitEffect.poison(damage_per_tick=3.0, duration_ticks=5)
        assert effect.effect_type == HitEffectType.POISON
        assert effect.duration_ticks == 5
        assert effect.intensity == 3.0

    def test_paralysis_factory(self):
        effect = HitEffect.paralysis(duration_ticks=3)
        assert effect.effect_type == HitEffectType.PARALYSIS
        assert effect.duration_ticks == 3
        assert effect.intensity == 1.0

    def test_silence_factory(self):
        effect = HitEffect.silence(duration_ticks=2)
        assert effect.effect_type == HitEffectType.SILENCE
        assert effect.duration_ticks == 2
        assert effect.intensity == 1.0

    def test_negative_duration_raises(self):
        with pytest.raises(HitEffectValidationException, match="duration_ticks cannot be negative"):
            HitEffect(HitEffectType.POISON, duration_ticks=-1, intensity=1.0)

    def test_negative_intensity_raises(self):
        with pytest.raises(HitEffectValidationException, match="intensity cannot be negative"):
            HitEffect(HitEffectType.SLOW, duration_ticks=3, intensity=-0.1)

    def test_invalid_chance_raises(self):
        with pytest.raises(HitEffectValidationException, match="chance must be between 0 and 1"):
            HitEffect(HitEffectType.POISON, duration_ticks=3, intensity=1.0, chance=1.2)

    @pytest.mark.parametrize("effect_type", [HitEffectType.SLOW, HitEffectType.POISON, HitEffectType.PARALYSIS, HitEffectType.SILENCE])
    def test_continuous_effect_requires_positive_duration(self, effect_type: HitEffectType):
        with pytest.raises(HitEffectValidationException, match="requires duration_ticks >= 1"):
            HitEffect(effect_type=effect_type, duration_ticks=0, intensity=1.0)
