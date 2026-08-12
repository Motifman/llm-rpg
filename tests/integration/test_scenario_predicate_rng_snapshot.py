"""シナリオ条件用乱数列が world snapshot 再開後も連続することを
保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    ScenarioPredicateRngSubsystemCodec,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


_SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "scenarios"
    / "darkened_station.json"
)
_CONDITION = ScenarioEventCondition(
    condition_type="PROBABILITY",
    probability=0.5,
)


def _runtime():
    return create_world_runtime(
        _SCENARIO,
        config=ResolvedLlmRuntimeConfig.for_tests(scenario_random_seed=1046),
    )


def _evaluate_probability(runtime, count: int) -> list[bool]:
    evaluator = runtime._scenario_event_stage._condition_evaluator
    graph = runtime._spot_graph_repo.find_graph()
    return [
        evaluator.evaluate(_CONDITION, WorldTick(runtime.current_tick()), graph)
        for _ in range(count)
    ]


class TestScenarioPredicateRngSnapshotContinuity:
    """確率条件の乱数位置を保存し、再開前後で同じ判定列を得られる。
    """

    def test_resume_continues_from_next_probability_draw(self) -> None:
        """7回評価後に保存・再開しても、続く12回は連続実行と一致する。
        """
        continuous = _runtime()
        _evaluate_probability(continuous, 7)
        captured = ScenarioPredicateRngSubsystemCodec().capture(continuous)
        expected_tail = _evaluate_probability(continuous, 12)

        resumed = _runtime()
        payload_after_json_round_trip = json.loads(json.dumps(captured))
        ScenarioPredicateRngSubsystemCodec().restore(
            resumed,
            payload_after_json_round_trip,
        )
        actual_tail = _evaluate_probability(resumed, 12)

        assert actual_tail == expected_tail

    def test_runtime_and_evaluator_share_the_snapshotted_random_source(self) -> None:
        """runtime が保存する乱数源は、条件評価器が消費する同一実体である。
        """
        runtime = _runtime()

        assert (
            runtime._scenario_predicate_random
            is runtime._scenario_event_stage._condition_evaluator._random
        )


class TestScenarioPredicateRngSnapshotValidation:
    """壊れた乱数状態を、稼働中の乱数位置を変えずに拒否する。"""

    def test_invalid_internal_state_does_not_mutate_runtime(self) -> None:
        """不正な内部列は ValueError となり、復元先の次の値を変えない。
        """
        runtime = _runtime()
        before = runtime._scenario_predicate_random.getstate()
        payload = {
            "schema_version": 1,
            "state_version": 3,
            "internal_state": [1],
            "gaussian_cache": None,
        }

        with pytest.raises(ValueError, match="scenario_predicate_rng state is invalid"):
            ScenarioPredicateRngSubsystemCodec().restore(runtime, payload)

        assert runtime._scenario_predicate_random.getstate() == before

    def test_overflowing_internal_value_is_wrapped_without_mutation(self) -> None:
        """巨大な内部整数も ValueError となり、復元先の乱数位置を変えない。
        """
        runtime = _runtime()
        before = runtime._scenario_predicate_random.getstate()
        payload = ScenarioPredicateRngSubsystemCodec().capture(runtime)
        payload["internal_state"][0] = 1 << 100

        with pytest.raises(ValueError, match="scenario_predicate_rng state is invalid"):
            ScenarioPredicateRngSubsystemCodec().restore(runtime, payload)

        assert runtime._scenario_predicate_random.getstate() == before
