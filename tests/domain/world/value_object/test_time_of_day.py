"""TimeOfDay と時間帯純粋関数のテスト"""

import pytest
from ai_rpg_world.domain.world.value_object.time_of_day import (
    TimeOfDay,
    time_of_day_from_tick,
    is_active_at_time,
)
from ai_rpg_world.domain.world.enum.world_enum import ActiveTimeType


class TestTimeOfDay:
    """TimeOfDay 列挙のテスト"""

    def test_time_of_day_values(self):
        """MORNING, DAY, EVENING, NIGHT が定義されていること"""
        assert TimeOfDay.MORNING.value == "MORNING"
        assert TimeOfDay.DAY.value == "DAY"
        assert TimeOfDay.EVENING.value == "EVENING"
        assert TimeOfDay.NIGHT.value == "NIGHT"


class TestTimeOfDayFromTick:
    """time_of_day_from_tick 純粋関数のテスト"""

    def test_ticks_per_day_positive_required(self):
        """ticks_per_day が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="ticks_per_day must be positive"):
            time_of_day_from_tick(0, 0)
        with pytest.raises(ValueError, match="ticks_per_day must be positive"):
            time_of_day_from_tick(0, -1)

    def test_one_day_four_quarters(self):
        """1日を4等分して NIGHT, MORNING, DAY, EVENING が返ること"""
        ticks_per_day = 24
        quarter = 6
        # 0-5: NIGHT, 6-11: MORNING, 12-17: DAY, 18-23: EVENING
        assert time_of_day_from_tick(0, ticks_per_day) == TimeOfDay.NIGHT
        assert time_of_day_from_tick(5, ticks_per_day) == TimeOfDay.NIGHT
        assert time_of_day_from_tick(6, ticks_per_day) == TimeOfDay.MORNING
        assert time_of_day_from_tick(11, ticks_per_day) == TimeOfDay.MORNING
        assert time_of_day_from_tick(12, ticks_per_day) == TimeOfDay.DAY
        assert time_of_day_from_tick(17, ticks_per_day) == TimeOfDay.DAY
        assert time_of_day_from_tick(18, ticks_per_day) == TimeOfDay.EVENING
        assert time_of_day_from_tick(23, ticks_per_day) == TimeOfDay.EVENING

    def test_tick_wraps_modulo(self):
        """tick が 1 日を超えても剰余で正しい時間帯が返ること"""
        ticks_per_day = 24
        assert time_of_day_from_tick(24, ticks_per_day) == TimeOfDay.NIGHT
        assert time_of_day_from_tick(30, ticks_per_day) == TimeOfDay.MORNING
        # 100 % 24 = 4 → 0-5 の区間なので NIGHT
        assert time_of_day_from_tick(100, ticks_per_day) == TimeOfDay.NIGHT
        # 42 % 24 = 18 → 18-23 の区間なので EVENING
        assert time_of_day_from_tick(42, ticks_per_day) == TimeOfDay.EVENING


class TestIsActiveAtTime:
    """is_active_at_time 純粋関数のテスト"""

    def test_always_active_at_any_time(self):
        """ALWAYS は任意の時間帯で True"""
        for tod in TimeOfDay:
            assert is_active_at_time(ActiveTimeType.ALWAYS, tod) is True

    def test_diurnal_only_day(self):
        """DIURNAL は DAY のときのみ True"""
        assert is_active_at_time(ActiveTimeType.DIURNAL, TimeOfDay.DAY) is True
        assert is_active_at_time(ActiveTimeType.DIURNAL, TimeOfDay.MORNING) is False
        assert is_active_at_time(ActiveTimeType.DIURNAL, TimeOfDay.EVENING) is False
        assert is_active_at_time(ActiveTimeType.DIURNAL, TimeOfDay.NIGHT) is False

    def test_nocturnal_only_night(self):
        """NOCTURNAL は NIGHT のときのみ True"""
        assert is_active_at_time(ActiveTimeType.NOCTURNAL, TimeOfDay.NIGHT) is True
        assert is_active_at_time(ActiveTimeType.NOCTURNAL, TimeOfDay.MORNING) is False
        assert is_active_at_time(ActiveTimeType.NOCTURNAL, TimeOfDay.DAY) is False
        assert is_active_at_time(ActiveTimeType.NOCTURNAL, TimeOfDay.EVENING) is False

    def test_crepuscular_morning_and_evening(self):
        """CREPUSCULAR は MORNING と EVENING のとき True"""
        assert is_active_at_time(ActiveTimeType.CREPUSCULAR, TimeOfDay.MORNING) is True
        assert is_active_at_time(ActiveTimeType.CREPUSCULAR, TimeOfDay.EVENING) is True
        assert is_active_at_time(ActiveTimeType.CREPUSCULAR, TimeOfDay.DAY) is False
        assert is_active_at_time(ActiveTimeType.CREPUSCULAR, TimeOfDay.NIGHT) is False
