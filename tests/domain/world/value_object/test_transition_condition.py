"""遷移条件値オブジェクトのテスト"""

import pytest
from ai_rpg_world.domain.world.value_object.transition_condition import (
    RequireRelation,
    RequireToll,
    BlockIfWeather,
    block_if_weather,
)
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


class TestRequireRelation:
    def test_creation(self):
        c = RequireRelation(relation_type="guild_member")
        assert c.relation_type == "guild_member"

    def test_immutable(self):
        c = RequireRelation(relation_type="quest")
        with pytest.raises(AttributeError):
            c.relation_type = "other"


class TestRequireToll:
    def test_creation_with_optional_defaults(self):
        c = RequireToll(amount_gold=10)
        assert c.amount_gold == 10
        assert c.recipient_type == "spot"
        assert c.recipient_id is None

    def test_creation_full(self):
        c = RequireToll(amount_gold=50, recipient_type="guild", recipient_id="g1")
        assert c.amount_gold == 50
        assert c.recipient_type == "guild"
        assert c.recipient_id == "g1"


class TestBlockIfWeather:
    def test_creation_via_helper(self):
        c = block_if_weather([WeatherTypeEnum.BLIZZARD, WeatherTypeEnum.STORM])
        assert WeatherTypeEnum.BLIZZARD in c.blocked_weather_types
        assert WeatherTypeEnum.STORM in c.blocked_weather_types
        assert len(c.blocked_weather_types) == 2

    def test_creation_direct_tuple(self):
        c = BlockIfWeather(blocked_weather_types=(WeatherTypeEnum.RAIN,))
        assert WeatherTypeEnum.RAIN in c.blocked_weather_types
