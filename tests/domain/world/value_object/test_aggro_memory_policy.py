"""AggroMemoryPolicy のテスト（正常・境界・例外）"""

import pytest
from ai_rpg_world.domain.world.value_object.aggro_memory_policy import AggroMemoryPolicy


class TestAggroMemoryPolicy:
    """正常ケース"""

    def test_none_never_forgets(self):
        policy = AggroMemoryPolicy(forget_after_ticks=None)
        assert policy.is_forgotten(1000, 0) is False
        assert policy.is_forgotten(1000, 999) is False

    def test_forget_after_ticks_zero_elapsed_not_forgotten(self):
        policy = AggroMemoryPolicy(forget_after_ticks=10)
        assert policy.is_forgotten(10, 10) is False
        assert policy.is_forgotten(19, 10) is False

    def test_forget_after_ticks_elapsed_forgotten(self):
        policy = AggroMemoryPolicy(forget_after_ticks=10)
        assert policy.is_forgotten(21, 10) is True
        assert policy.is_forgotten(100, 0) is True

    def test_revenge_never_forget_default_false(self):
        policy = AggroMemoryPolicy(forget_after_ticks=10, revenge_never_forget=False)
        assert policy.is_forgotten(21, 10) is True

    def test_revenge_never_forget_true_does_not_affect_is_forgotten(self):
        """revenge_never_forget は is_forgotten の戻り値は変えず、将来の拡張用"""
        policy = AggroMemoryPolicy(forget_after_ticks=10, revenge_never_forget=True)
        assert policy.is_forgotten(21, 10) is True

    def test_immutability(self):
        policy = AggroMemoryPolicy(forget_after_ticks=5)
        with pytest.raises(AttributeError):
            policy.forget_after_ticks = 10


class TestAggroMemoryPolicyValidation:
    """例外・境界"""

    def test_negative_forget_after_ticks_raises(self):
        with pytest.raises(ValueError, match="forget_after_ticks must be non-negative"):
            AggroMemoryPolicy(forget_after_ticks=-1)

    def test_forget_after_ticks_zero_allowed(self):
        policy = AggroMemoryPolicy(forget_after_ticks=0)
        assert policy.is_forgotten(1, 0) is True
        assert policy.is_forgotten(0, 0) is False
