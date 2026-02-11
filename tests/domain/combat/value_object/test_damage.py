import pytest
from ai_rpg_world.domain.combat.value_object.damage import Damage
from ai_rpg_world.domain.combat.exception.combat_exceptions import DamageValidationException

class TestDamage:
    def test_create_normal(self):
        dmg = Damage.normal(10)
        assert dmg.value == 10
        assert not dmg.is_critical
        assert not dmg.is_evaded

    def test_create_critical(self):
        dmg = Damage.normal(20, is_critical=True)
        assert dmg.value == 20
        assert dmg.is_critical
        assert not dmg.is_evaded

    def test_create_evaded(self):
        dmg = Damage.evaded()
        assert dmg.value == 0
        assert dmg.is_evaded

    def test_negative_value_fails(self):
        with pytest.raises(DamageValidationException):
            Damage(value=-1)
