import pytest
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.skill.enum.skill_enum import SkillHitPatternType
from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillSpecValidationException
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.player.enum.player_enum import Element


class TestSkillSpec:
    @staticmethod
    def _sample_spec(**overrides) -> SkillSpec:
        base = {
            "skill_id": SkillId(1),
            "name": "Slash",
            "element": Element.NEUTRAL,
            "deck_cost": 2,
            "cast_lock_ticks": 1,
            "cooldown_ticks": 6,
            "power_multiplier": 1.5,
            "hit_pattern": SkillHitPattern.single_pulse(
                pattern_type=SkillHitPatternType.MELEE,
                shape=HitBoxShape.single_cell(),
            ),
        }
        base.update(overrides)
        return SkillSpec(**base)

    class TestValidation:
        def test_skill_spec_accepts_optional_cost_none(self):
            spec = TestSkillSpec._sample_spec(mp_cost=None, stamina_cost=None, hp_cost=None)
            assert spec.has_resource_cost is False

        def test_skill_spec_has_resource_cost_when_any_positive(self):
            spec = TestSkillSpec._sample_spec(mp_cost=3)
            assert spec.has_resource_cost is True

        @pytest.mark.parametrize("field,value", [("deck_cost", -1), ("cast_lock_ticks", -1), ("cooldown_ticks", -1)])
        def test_skill_spec_rejects_negative_fields(self, field, value):
            kwargs = {field: value}
            with pytest.raises(SkillSpecValidationException):
                TestSkillSpec._sample_spec(**kwargs)

        def test_skill_spec_rejects_non_positive_power_multiplier(self):
            with pytest.raises(SkillSpecValidationException):
                TestSkillSpec._sample_spec(power_multiplier=0)

        @pytest.mark.parametrize("field,value", [("mp_cost", -1), ("stamina_cost", -1), ("hp_cost", -1)])
        def test_skill_spec_rejects_negative_optional_costs(self, field, value):
            kwargs = {field: value}
            with pytest.raises(SkillSpecValidationException):
                TestSkillSpec._sample_spec(**kwargs)

        def test_skill_spec_rejects_negative_targeting_range(self):
            with pytest.raises(SkillSpecValidationException, match="targeting_range cannot be negative"):
                TestSkillSpec._sample_spec(targeting_range=-1)

        def test_skill_spec_accepts_zero_targeting_range(self):
            spec = TestSkillSpec._sample_spec(targeting_range=0)
            assert spec.targeting_range == 0

        def test_skill_spec_accepts_positive_targeting_range(self):
            spec = TestSkillSpec._sample_spec(targeting_range=5)
            assert spec.targeting_range == 5

        def test_skill_spec_default_targeting_range_is_one(self):
            spec = TestSkillSpec._sample_spec()
            assert spec.targeting_range == 1
