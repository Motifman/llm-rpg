import pytest
from ai_rpg_world.domain.skill.exception.skill_exceptions import (
    SkillDeckProgressIdValidationException,
    SkillLoadoutIdValidationException,
)
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId


class TestSkillIds:
    class TestSkillLoadoutId:
        def test_create_from_int_and_str(self):
            assert SkillLoadoutId.create(1) == SkillLoadoutId(1)
            assert SkillLoadoutId.create("2") == SkillLoadoutId(2)

        def test_invalid_values_raise(self):
            with pytest.raises(SkillLoadoutIdValidationException):
                SkillLoadoutId.create(0)
            with pytest.raises(SkillLoadoutIdValidationException):
                SkillLoadoutId.create("abc")

        def test_int_and_str_conversion(self):
            value = SkillLoadoutId(10)
            assert int(value) == 10
            assert str(value) == "10"

    class TestSkillDeckProgressId:
        def test_create_from_int_and_str(self):
            assert SkillDeckProgressId.create(1) == SkillDeckProgressId(1)
            assert SkillDeckProgressId.create("2") == SkillDeckProgressId(2)

        def test_invalid_values_raise(self):
            with pytest.raises(SkillDeckProgressIdValidationException):
                SkillDeckProgressId.create(-1)
            with pytest.raises(SkillDeckProgressIdValidationException):
                SkillDeckProgressId.create("x")

        def test_int_and_str_conversion(self):
            value = SkillDeckProgressId(15)
            assert int(value) == 15
            assert str(value) == "15"
