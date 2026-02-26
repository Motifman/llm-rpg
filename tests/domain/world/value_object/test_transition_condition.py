"""遷移条件値オブジェクトのテスト（正常・境界・不変性）"""

import pytest
from ai_rpg_world.domain.world.value_object.transition_condition import (
    TransitionCondition,
    RequireRelation,
    RequireToll,
    BlockIfWeather,
    block_if_weather,
)
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


class TestTransitionConditionBase:
    """基底マーカー TransitionCondition のテスト"""

    def test_base_class_is_instantiable(self):
        """マーカーとして無引数でインスタンス化できること"""
        c = TransitionCondition()
        assert isinstance(c, TransitionCondition)

    def test_subclass_is_instance_of_base(self):
        """RequireRelation 等が TransitionCondition のサブタイプであること"""
        assert isinstance(RequireRelation(relation_type="x"), TransitionCondition)
        assert isinstance(RequireToll(amount_gold=0), TransitionCondition)
        assert isinstance(BlockIfWeather(blocked_weather_types=()), TransitionCondition)


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

    def test_creation_zero_gold(self):
        """amount_gold=0 で生成できること（評価側で常に許可される）"""
        c = RequireToll(amount_gold=0)
        assert c.amount_gold == 0

    def test_creation_negative_gold_allowed(self):
        """amount_gold に負数も設定可能であること（値オブジェクトは検証しない）"""
        c = RequireToll(amount_gold=-1)
        assert c.amount_gold == -1

    def test_immutable(self):
        """RequireToll は不変であること"""
        c = RequireToll(amount_gold=10)
        with pytest.raises(AttributeError):
            c.amount_gold = 20


class TestBlockIfWeather:
    def test_creation_via_helper(self):
        c = block_if_weather([WeatherTypeEnum.BLIZZARD, WeatherTypeEnum.STORM])
        assert WeatherTypeEnum.BLIZZARD in c.blocked_weather_types
        assert WeatherTypeEnum.STORM in c.blocked_weather_types
        assert len(c.blocked_weather_types) == 2

    def test_creation_direct_tuple(self):
        c = BlockIfWeather(blocked_weather_types=(WeatherTypeEnum.RAIN,))
        assert WeatherTypeEnum.RAIN in c.blocked_weather_types

    def test_creation_empty_blocked_weather_types(self):
        """blocked_weather_types が空タプルでも生成できること（該当天候なし＝常に通行可に近い）"""
        c = BlockIfWeather(blocked_weather_types=())
        assert len(c.blocked_weather_types) == 0

    def test_immutable(self):
        """BlockIfWeather は不変であること"""
        c = block_if_weather([WeatherTypeEnum.RAIN])
        with pytest.raises(AttributeError):
            c.blocked_weather_types = (WeatherTypeEnum.STORM,)
