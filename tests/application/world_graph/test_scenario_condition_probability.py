"""PROBABILITY condition_type の評価検証 (Phase D-1)。

seed 注入で決定的になることと、確率範囲外を弾くこと、AND/OR/NOT ネスト下で
動作することを確認する。
"""

from __future__ import annotations

import random

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
    ScenarioEventConditionValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


@pytest.fixture
def evaluator_factory():
    """seed を指定して決定的な evaluator を作るファクトリ。"""
    def _make(seed: int) -> ScenarioConditionEvaluator:
        from unittest.mock import MagicMock
        return ScenarioConditionEvaluator(
            world_flag_state=MutableWorldFlagState(),
            spot_interior_repository=MagicMock(),
            player_status_repository=MagicMock(),
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
            random_source=random.Random(seed),
        )
    return _make


def _empty_graph() -> SpotGraphAggregate:
    return SpotGraphAggregate.empty(SpotGraphId.create(1))


class TestProbabilityValidation:
    """domain レベルのバリデーション (probability の不在 / 範囲外)。"""

    def test_probability_missing_probability(self) -> None:
        """probability 欠落で PROBABILITY は構築できない。"""
        with pytest.raises(ScenarioEventConditionValidationException):
            ScenarioEventCondition(condition_type="PROBABILITY")

    def test_rejects_probability(self) -> None:
        """probability が範囲外なら弾く。"""
        with pytest.raises(ScenarioEventConditionValidationException):
            ScenarioEventCondition(condition_type="PROBABILITY", probability=1.5)
        with pytest.raises(ScenarioEventConditionValidationException):
            ScenarioEventCondition(condition_type="PROBABILITY", probability=-0.1)

    def test_probability_2(self) -> None:
        """範囲内の probability は受理される。"""
        c0 = ScenarioEventCondition(condition_type="PROBABILITY", probability=0.0)
        c1 = ScenarioEventCondition(condition_type="PROBABILITY", probability=1.0)
        assert c0.probability == 0.0
        assert c1.probability == 1.0


class TestProbabilityEvaluation:
    """ScenarioConditionEvaluator の PROBABILITY 評価。"""

    def test_one_zero_true(self, evaluator_factory) -> None:
        """確率 1 0 は常に True。"""
        ev = evaluator_factory(seed=42)
        cond = ScenarioEventCondition(
            condition_type="PROBABILITY", probability=1.0,
        )
        for _ in range(20):
            assert ev.evaluate(cond, WorldTick(0), _empty_graph()) is True

    def test_zero_0_false(self, evaluator_factory) -> None:
        """確率 0 0 は常に False。"""
        ev = evaluator_factory(seed=42)
        cond = ScenarioEventCondition(
            condition_type="PROBABILITY", probability=0.0,
        )
        for _ in range(20):
            assert ev.evaluate(cond, WorldTick(0), _empty_graph()) is False

    def test_same_seed_same(self, evaluator_factory) -> None:
        """再現性のテスト: seed=123 で 2 つ作って同じ結果が出る。"""
        cond = ScenarioEventCondition(
            condition_type="PROBABILITY", probability=0.5,
        )
        ev1 = evaluator_factory(seed=123)
        ev2 = evaluator_factory(seed=123)
        seq1 = [ev1.evaluate(cond, WorldTick(0), _empty_graph()) for _ in range(50)]
        seq2 = [ev2.evaluate(cond, WorldTick(0), _empty_graph()) for _ in range(50)]
        assert seq1 == seq2

    def test_zero_five_true(self, evaluator_factory) -> None:
        """大数で 50% に近い (sanity check)。"""
        ev = evaluator_factory(seed=42)
        cond = ScenarioEventCondition(
            condition_type="PROBABILITY", probability=0.5,
        )
        outcomes = [
            ev.evaluate(cond, WorldTick(0), _empty_graph())
            for _ in range(1000)
        ]
        true_count = sum(outcomes)
        # 1000 回で 50% 期待 → 標準偏差 ~16、±5σ = 80。安全マージンで 400〜600
        assert 400 <= true_count <= 600

    def test_probability(self, evaluator_factory) -> None:
        """確率 1.0 と確率 1.0 の AND は True。確率 1.0 と 0.0 の AND は False。"""
        ev = evaluator_factory(seed=42)
        both_true = ScenarioEventCondition(
            condition_type="AND",
            children=(
                ScenarioEventCondition(condition_type="PROBABILITY", probability=1.0),
                ScenarioEventCondition(condition_type="PROBABILITY", probability=1.0),
            ),
        )
        one_false = ScenarioEventCondition(
            condition_type="AND",
            children=(
                ScenarioEventCondition(condition_type="PROBABILITY", probability=1.0),
                ScenarioEventCondition(condition_type="PROBABILITY", probability=0.0),
            ),
        )
        assert ev.evaluate(both_true, WorldTick(0), _empty_graph()) is True
        assert ev.evaluate(one_false, WorldTick(0), _empty_graph()) is False

    def test_not_probability(self, evaluator_factory) -> None:
        """NOT(PROBABILITY=1.0) は常に False。"""
        ev = evaluator_factory(seed=42)
        not_certain = ScenarioEventCondition(
            condition_type="NOT",
            children=(
                ScenarioEventCondition(condition_type="PROBABILITY", probability=1.0),
            ),
        )
        for _ in range(10):
            assert ev.evaluate(not_certain, WorldTick(0), _empty_graph()) is False
