"""TIME_OF_DAY_IS / WEATHER_IS condition の評価検証 (PR4 行動制限)。

「夜には釣りができない」「嵐の日は沖の釣り場へ行けない」のような
時間帯・天候による interaction 制限が _evaluate_condition で正しく
判定されることを確認する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _make_spot_object() -> SpotObject:
    """テスト用の最小 SpotObject を作る。"""
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="test_obj",
        description="test",
        object_type=ObjectTypeEnum.RESOURCE,
        state={},
        interactions=(),
    )


@pytest.fixture
def svc() -> SpotInteractionService:
    return SpotInteractionService()


@pytest.fixture
def obj() -> SpotObject:
    return _make_spot_object()


class TestTimeOfDayIsNot:
    """TIME_OF_DAY_IS_NOT: 「夜以外なら成立」の検証。"""

    def test_morning(self, svc, obj) -> None:
        """夜以外なら 成立 morning。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
            required_time_of_day_phase="night",
            failure_message="夜は釣りできない",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_time_of_day_phase="morning",
        )
        assert ok is True
        assert msg is None

    def test_documented_behavior_2(self, svc, obj) -> None:
        """夜なら 拒否。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
            required_time_of_day_phase="night",
            failure_message="夜は釣りできない",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_time_of_day_phase="night",
        )
        assert ok is False
        assert msg == "夜は釣りできない"

    def test_provider_2(self, svc, obj) -> None:
        """day_night 宣言が無いシナリオでこの condition を使うと fail する
        (silent skip を避けるための boundary フェイル)。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
            required_time_of_day_phase="night",
            failure_message="",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_time_of_day_phase=None,  # provider 不在
        )
        assert ok is False
        assert "day_night provider" in (msg or "")

    def test_required_phase_missing(self, svc, obj) -> None:
        """required phase 欠落で 拒否。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
            required_time_of_day_phase=None,
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_time_of_day_phase="morning",
        )
        assert ok is False


class TestTimeOfDayIs:
    """TIME_OF_DAY_IS: 「指定 phase のときだけ成立」の検証。"""

    def test_matches_4(self, svc, obj) -> None:
        """一致なら 成立。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS,
            required_time_of_day_phase="noon",
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_time_of_day_phase="noon",
        )
        assert ok is True

    def test_matches_3(self, svc, obj) -> None:
        """不一致なら 拒否。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS,
            required_time_of_day_phase="noon",
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_time_of_day_phase="evening",
        )
        assert ok is False


class TestWeatherIsNot:
    """WEATHER_IS_NOT: 「嵐以外なら成立」の検証。"""

    def test_clear(self, svc, obj) -> None:
        """嵐以外なら 成立 CLEAR。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.WEATHER_IS_NOT,
            required_weather_type="STORM",
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_weather_type="CLEAR",
        )
        assert ok is True

    def test_documented_behavior(self, svc, obj) -> None:
        """嵐なら 拒否。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.WEATHER_IS_NOT,
            required_weather_type="STORM",
            failure_message="嵐で危険",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_weather_type="STORM",
        )
        assert ok is False
        assert msg == "嵐で危険"

    def test_provider(self, svc, obj) -> None:
        """provider 不在で 拒否。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.WEATHER_IS_NOT,
            required_weather_type="STORM",
        )
        ok, msg = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_weather_type=None,
        )
        assert ok is False
        assert "weather provider" in (msg or "")


class TestWeatherIs:
    """WEATHER_IS: 「指定 weather のときだけ成立」の検証。"""

    def test_matches_2(self, svc, obj) -> None:
        """一致なら 成立。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.WEATHER_IS,
            required_weather_type="RAIN",
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_weather_type="RAIN",
        )
        assert ok is True

    def test_matches(self, svc, obj) -> None:
        """不一致なら 拒否。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.WEATHER_IS,
            required_weather_type="RAIN",
        )
        ok, _ = svc._evaluate_condition(
            cond, obj, frozenset(),
            owned_item_spec_counts={},
            current_weather_type="CLEAR",
        )
        assert ok is False
