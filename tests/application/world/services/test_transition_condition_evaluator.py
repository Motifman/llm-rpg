"""TransitionConditionEvaluator のテスト（正常・境界・例外）"""

import pytest
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.transition_condition import (
    TransitionCondition,
    RequireRelation,
    RequireToll,
    block_if_weather,
)
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
    TransitionContext,
    ITransitionRelationChecker,
)


def _minimal_player_status(player_id: int, gold_value: int = 100) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold.create(gold_value),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
    )


@pytest.fixture
def context():
    status = _minimal_player_status(1, gold_value=500)
    return TransitionContext(
        player_id=1,
        player_status=status,
        from_spot_id=SpotId(1),
        to_spot_id=SpotId(2),
        current_weather=WeatherState.clear(),
    )


@pytest.fixture
def context_blizzard():
    status = _minimal_player_status(1, gold_value=500)
    return TransitionContext(
        player_id=1,
        player_status=status,
        from_spot_id=SpotId(1),
        to_spot_id=SpotId(2),
        current_weather=WeatherState(WeatherTypeEnum.BLIZZARD, 1.0),
    )


class TestTransitionConditionEvaluatorEmptyConditions:
    def test_empty_conditions_allowed(self, context):
        evaluator = TransitionConditionEvaluator()
        allowed, msg = evaluator.evaluate([], context)
        assert allowed is True
        assert msg is None


class TestTransitionConditionEvaluatorRequireToll:
    def test_require_toll_sufficient_gold_allowed(self, context):
        evaluator = TransitionConditionEvaluator()
        allowed, msg = evaluator.evaluate([RequireToll(amount_gold=100)], context)
        assert allowed is True
        assert msg is None

    def test_require_toll_insufficient_gold_blocked(self, context):
        evaluator = TransitionConditionEvaluator()
        allowed, msg = evaluator.evaluate([RequireToll(amount_gold=1000)], context)
        assert allowed is False
        assert "通行料が不足" in msg
        assert "1000" in msg and "500" in msg

    def test_require_toll_zero_always_allowed(self, context):
        evaluator = TransitionConditionEvaluator()
        allowed, msg = evaluator.evaluate([RequireToll(amount_gold=0)], context)
        assert allowed is True


class TestTransitionConditionEvaluatorBlockIfWeather:
    def test_block_if_weather_clear_allowed(self, context):
        evaluator = TransitionConditionEvaluator()
        allowed, msg = evaluator.evaluate([
            block_if_weather([WeatherTypeEnum.BLIZZARD, WeatherTypeEnum.STORM])
        ], context)
        assert allowed is True
        assert msg is None

    def test_block_if_weather_blizzard_blocked(self, context_blizzard):
        evaluator = TransitionConditionEvaluator()
        allowed, msg = evaluator.evaluate([
            block_if_weather([WeatherTypeEnum.BLIZZARD, WeatherTypeEnum.STORM])
        ], context_blizzard)
        assert allowed is False
        assert "悪天候" in msg or "通行止め" in msg


class TestTransitionConditionEvaluatorRequireRelation:
    def test_require_relation_no_checker_blocked(self, context):
        evaluator = TransitionConditionEvaluator(relation_checker=None)
        allowed, msg = evaluator.evaluate([RequireRelation(relation_type="guild")], context)
        assert allowed is False
        assert "関係" in msg

    def test_require_relation_checker_returns_true_allowed(self, context):
        class AlwaysTrueChecker(ITransitionRelationChecker):
            def has_relation(self, player_id, relation_type, from_spot_id, to_spot_id):
                return True
        evaluator = TransitionConditionEvaluator(relation_checker=AlwaysTrueChecker())
        allowed, msg = evaluator.evaluate([RequireRelation(relation_type="guild")], context)
        assert allowed is True
        assert msg is None

    def test_require_relation_checker_returns_false_blocked(self, context):
        class AlwaysFalseChecker(ITransitionRelationChecker):
            def has_relation(self, player_id, relation_type, from_spot_id, to_spot_id):
                return False
        evaluator = TransitionConditionEvaluator(relation_checker=AlwaysFalseChecker())
        allowed, msg = evaluator.evaluate([RequireRelation(relation_type="guild")], context)
        assert allowed is False
        assert "関係者" in msg or "関係" in msg


class TestTransitionConditionEvaluatorMultipleConditions:
    def test_all_must_pass(self, context):
        evaluator = TransitionConditionEvaluator()
        # 通行料OK + 天候OK
        allowed, _ = evaluator.evaluate([
            RequireToll(amount_gold=10),
            block_if_weather([WeatherTypeEnum.BLIZZARD]),
        ], context)
        assert allowed is True

    def test_first_fail_short_circuits(self, context_blizzard):
        evaluator = TransitionConditionEvaluator()
        conditions = [
            RequireToll(amount_gold=10),
            block_if_weather([WeatherTypeEnum.BLIZZARD]),
        ]
        allowed, msg = evaluator.evaluate(conditions, context_blizzard)
        assert allowed is False
        assert "悪天候" in msg or "通行止め" in msg


class TestTransitionConditionEvaluatorUnknownConditionType:
    """未知の遷移条件タイプを渡した場合の挙動"""

    @pytest.fixture
    def context(self):
        status = _minimal_player_status(1, gold_value=500)
        return TransitionContext(
            player_id=1,
            player_status=status,
            from_spot_id=SpotId(1),
            to_spot_id=SpotId(2),
            current_weather=WeatherState.clear(),
        )

    def test_unknown_condition_type_returns_false_with_message(self, context):
        """未対応の遷移条件サブクラスを渡すと (False, '不明な遷移条件です') が返ること"""
        class UnknownCondition(TransitionCondition):
            """評価器が扱わない条件タイプ（将来の拡張用など）"""
            pass

        evaluator = TransitionConditionEvaluator()
        allowed, msg = evaluator.evaluate([UnknownCondition()], context)
        assert allowed is False
        assert msg == "不明な遷移条件です"

    def test_unknown_condition_fails_before_known_conditions_evaluated(self, context):
        """未知条件が先頭にある場合、その時点で不許可となりメッセージが返ること"""
        class UnknownCondition(TransitionCondition):
            pass

        evaluator = TransitionConditionEvaluator()
        conditions = [
            UnknownCondition(),
            RequireToll(amount_gold=0),  # こちらは満たすが評価されない
        ]
        allowed, msg = evaluator.evaluate(conditions, context)
        assert allowed is False
        assert "不明な遷移条件" in msg
