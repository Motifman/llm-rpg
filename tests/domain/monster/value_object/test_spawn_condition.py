"""SpawnCondition 値オブジェクトのテスト"""

import pytest
from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


class TestSpawnCondition:
    """SpawnCondition のテスト"""

    def test_create_none_time_band(self):
        """time_band が None のとき任意の時間帯で満たす"""
        condition = SpawnCondition(time_band=None)
        for tod in TimeOfDay:
            assert condition.is_satisfied_at(tod) is True

    def test_create_with_time_band(self):
        """time_band を指定したときその時間帯のみ True"""
        condition = SpawnCondition(time_band=TimeOfDay.NIGHT)
        assert condition.is_satisfied_at(TimeOfDay.NIGHT) is True
        assert condition.is_satisfied_at(TimeOfDay.DAY) is False
        assert condition.is_satisfied_at(TimeOfDay.MORNING) is False
        assert condition.is_satisfied_at(TimeOfDay.EVENING) is False

    def test_frozen(self):
        """SpawnCondition は不変であること"""
        condition = SpawnCondition(time_band=TimeOfDay.DAY)
        with pytest.raises(AttributeError):
            condition.time_band = TimeOfDay.NIGHT
