"""TIME_OF_DAY_IS / WEATHER_IS condition の評価検証 (PR4 行動制限)。

「夜には釣りができない」「嵐の日は沖の釣り場へ行けない」のような
時間帯・天候による interaction 制限が _evaluate_condition で正しく
判定されることを確認する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioPredicateEvaluationException,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.predicate_result import PredicateResult
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    WeatherTypeIsPredicate,
)


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


class TestWeatherCommonPredicateAdapter:
    """天候interactionが共通核を使いつつ既存の否定・失敗契約を保つ。"""

    @pytest.mark.parametrize(
        ("condition_type", "common_satisfied", "expected"),
        [
            (InteractionConditionTypeEnum.WEATHER_IS, True, True),
            (InteractionConditionTypeEnum.WEATHER_IS, False, False),
            (InteractionConditionTypeEnum.WEATHER_IS_NOT, True, False),
            (InteractionConditionTypeEnum.WEATHER_IS_NOT, False, True),
        ],
    )
    def test_is_and_is_not_use_one_positive_common_evaluation(
        self,
        condition_type: InteractionConditionTypeEnum,
        common_satisfied: bool,
        expected: bool,
        obj: SpotObject,
    ) -> None:
        """正条件を一度評価し、IS_NOTだけ正常な真偽を反転する。"""
        common = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.satisfied()
            if common_satisfied
            else PredicateResult.not_satisfied(
                failed_predicate=WeatherTypeIsPredicate(WeatherTypeEnum.STORM),
                failed_path=(),
            )
        )
        service = SpotInteractionService(predicate_evaluator=common)
        condition = InteractionCondition(
            condition_type=condition_type,
            required_weather_type="STORM",
        )

        ok, _ = service._evaluate_condition(
            condition,
            obj,
            frozenset(),
            owned_item_spec_counts={},
            current_weather_type="STORM",
        )

        assert ok is expected
        common.evaluate.assert_called_once()
        predicate, context = common.evaluate.call_args.args
        assert predicate == WeatherTypeIsPredicate(WeatherTypeEnum.STORM)
        assert context.current_weather_type is WeatherTypeEnum.STORM

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    @pytest.mark.parametrize(
        "condition_type",
        [
            InteractionConditionTypeEnum.WEATHER_IS,
            InteractionConditionTypeEnum.WEATHER_IS_NOT,
        ],
    )
    def test_indeterminate_common_result_never_becomes_allowed(
        self,
        reason: str,
        condition_type: InteractionConditionTypeEnum,
        obj: SpotObject,
    ) -> None:
        """入力不足・未対応はIS_NOTでも成立へ反転せず即時停止する。"""
        common = MagicMock()
        failed = WeatherTypeIsPredicate(WeatherTypeEnum.STORM)
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"current_weather_type"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(
                failed_predicate=failed,
                failed_path=(),
            )
        )
        condition = InteractionCondition(
            condition_type=condition_type,
            required_weather_type="STORM",
        )

        with pytest.raises(ScenarioPredicateEvaluationException):
            SpotInteractionService(
                predicate_evaluator=common,
            )._evaluate_condition(
                condition,
                obj,
                frozenset(),
                owned_item_spec_counts={},
                current_weather_type="CLEAR",
            )

    @pytest.mark.parametrize(
        ("condition_type", "required", "current", "expected"),
        [
            (InteractionConditionTypeEnum.WEATHER_IS, "UNKNOWN", "UNKNOWN", True),
            (InteractionConditionTypeEnum.WEATHER_IS, "UNKNOWN", "CLEAR", False),
            (InteractionConditionTypeEnum.WEATHER_IS_NOT, "UNKNOWN", "CLEAR", True),
            (InteractionConditionTypeEnum.WEATHER_IS_NOT, "UNKNOWN", "UNKNOWN", False),
        ],
    )
    def test_invalid_direct_strings_keep_legacy_comparison(
        self,
        condition_type: InteractionConditionTypeEnum,
        required: str,
        current: str,
        expected: bool,
        obj: SpotObject,
    ) -> None:
        """loaderを迂回した未知文字列は従来の完全一致比較を維持する。"""
        condition = InteractionCondition(
            condition_type=condition_type,
            required_weather_type=required,
        )

        ok, _ = SpotInteractionService()._evaluate_condition(
            condition,
            obj,
            frozenset(),
            owned_item_spec_counts={},
            current_weather_type=current,
        )

        assert ok is expected

    def test_precondition_result_keeps_original_condition_path_and_message(
        self,
        obj: SpotObject,
    ) -> None:
        """天候不一致は元条件・配列位置・作者文面を失わず構造化結果へ戻す。"""
        condition = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.WEATHER_IS,
            required_weather_type="STORM",
            failure_message="嵐のときだけ操作できる",
        )
        interaction = InteractionDef(
            action_name="raise_sail",
            display_label="帆を上げる",
            preconditions=(
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.ALWAYS,
                ),
                condition,
            ),
            effects=(),
        )

        result = SpotInteractionService().evaluate_preconditions_result(
            interaction,
            obj,
            frozenset(),
            frozenset(),
            owned_item_spec_counts={},
            current_weather_type="CLEAR",
        )

        assert not result.is_satisfied
        assert result.failed_predicate is condition
        assert result.failed_path == (1,)
        assert result.failure_message == "嵐のときだけ操作できる"
