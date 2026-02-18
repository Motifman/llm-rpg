"""SpawnCondition 値オブジェクトのテスト"""

import pytest
from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


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

    class TestIsSatisfied:
        """is_satisfied（時間帯・天候・エリア）のテスト"""

        def test_time_band_only_none_satisfies_all(self):
            """time_band のみ None のときは常に True"""
            condition = SpawnCondition(time_band=None)
            assert condition.is_satisfied(TimeOfDay.DAY) is True
            assert condition.is_satisfied(TimeOfDay.NIGHT, weather_type=WeatherTypeEnum.RAIN) is True

        def test_time_band_only_mismatch_returns_false(self):
            """time_band のみ指定で時間帯が一致しないと False"""
            condition = SpawnCondition(time_band=TimeOfDay.NIGHT)
            assert condition.is_satisfied(TimeOfDay.DAY) is False
            assert condition.is_satisfied(TimeOfDay.NIGHT) is True

        def test_preferred_weather_none_ignored(self):
            """preferred_weather が None のときは天候を無視"""
            condition = SpawnCondition(time_band=None, preferred_weather=None)
            assert condition.is_satisfied(TimeOfDay.DAY, weather_type=WeatherTypeEnum.RAIN) is True

        def test_preferred_weather_match_returns_true(self):
            """preferred_weather に現在天候が含まれると True"""
            condition = SpawnCondition(
                time_band=None,
                preferred_weather=frozenset({WeatherTypeEnum.RAIN, WeatherTypeEnum.HEAVY_RAIN}),
            )
            assert condition.is_satisfied(TimeOfDay.DAY, weather_type=WeatherTypeEnum.RAIN) is True
            assert condition.is_satisfied(TimeOfDay.DAY, weather_type=WeatherTypeEnum.HEAVY_RAIN) is True

        def test_preferred_weather_mismatch_returns_false(self):
            """preferred_weather に現在天候が含まれないと False"""
            condition = SpawnCondition(
                time_band=None,
                preferred_weather=frozenset({WeatherTypeEnum.RAIN}),
            )
            assert condition.is_satisfied(TimeOfDay.DAY, weather_type=WeatherTypeEnum.CLEAR) is False
            assert condition.is_satisfied(TimeOfDay.DAY, weather_type=None) is False

        def test_required_area_traits_none_ignored(self):
            """required_area_traits が None のときはエリアを無視"""
            condition = SpawnCondition(time_band=None, required_area_traits=None)
            assert condition.is_satisfied(TimeOfDay.DAY, area_traits=set()) is True

        def test_required_area_traits_subset_returns_true(self):
            """area_traits が required_area_traits を包含すると True"""
            condition = SpawnCondition(
                time_band=None,
                required_area_traits=frozenset({"lava", "nest_exit"}),
            )
            assert condition.is_satisfied(
                TimeOfDay.DAY, area_traits={"lava", "nest_exit", "other"}
            ) is True

        def test_required_area_traits_missing_returns_false(self):
            """area_traits に required が欠けていると False"""
            condition = SpawnCondition(
                time_band=None,
                required_area_traits=frozenset({"lava", "nest_exit"}),
            )
            assert condition.is_satisfied(
                TimeOfDay.DAY, area_traits={"lava"}
            ) is False
            assert condition.is_satisfied(TimeOfDay.DAY, area_traits=None) is False

        def test_all_conditions_and(self):
            """時間帯・天候・エリアは AND で評価される"""
            condition = SpawnCondition(
                time_band=TimeOfDay.NIGHT,
                preferred_weather=frozenset({WeatherTypeEnum.RAIN}),
                required_area_traits=frozenset({"lava"}),
            )
            assert condition.is_satisfied(
                TimeOfDay.NIGHT,
                weather_type=WeatherTypeEnum.RAIN,
                area_traits={"lava"},
            ) is True
            assert condition.is_satisfied(
                TimeOfDay.DAY,
                weather_type=WeatherTypeEnum.RAIN,
                area_traits={"lava"},
            ) is False
            assert condition.is_satisfied(
                TimeOfDay.NIGHT,
                weather_type=WeatherTypeEnum.CLEAR,
                area_traits={"lava"},
            ) is False
            assert condition.is_satisfied(
                TimeOfDay.NIGHT,
                weather_type=WeatherTypeEnum.RAIN,
                area_traits=set(),
            ) is False
