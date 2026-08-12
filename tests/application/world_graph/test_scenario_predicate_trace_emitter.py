"""シナリオ述語traceが評価をやり直さず、最新の記録器へ診断値を渡す契約。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_graph.scenario_predicate_evaluation import (
    ProbabilityDecision,
    ScenarioPredicateEvaluation,
)
from ai_rpg_world.application.world_graph.scenario_predicate_trace_emitter import (
    ScenarioPredicateTraceEmitter,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.value_object.predicate_result import PredicateResult
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


def _evaluation() -> ScenarioPredicateEvaluation:
    condition = ScenarioEventCondition(
        condition_type="PROBABILITY",
        probability=0.5,
    )
    return ScenarioPredicateEvaluation(
        result=PredicateResult.not_satisfied(
            failed_predicate=condition,
            failed_path=(1,),
        ),
        probability_decisions=(
            ProbabilityDecision(
                path=(1,),
                probability=0.5,
                sampled_value=0.75,
                is_satisfied=False,
            ),
        ),
    )


class TestScenarioPredicateTraceEmitter:
    """評価済み結果の変換、後付け配線、記録障害の分離を保証する。"""

    def test_emits_json_compatible_result_and_probability_decision(self) -> None:
        """評価結果と実際の乱数値を、再評価せずJSON互換payloadへ変換する。"""
        recorder = MagicMock()
        emitter = ScenarioPredicateTraceEmitter(lambda: recorder)

        emitter.emit(
            evaluation=_evaluation(),
            root_condition_type="IMPLICIT_AND",
            current_tick=WorldTick(4),
            purpose="scenario_event_conditions",
            owner_id="arrival",
        )

        recorder.record.assert_called_once()
        args, kwargs = recorder.record.call_args
        assert args == (TraceEventKind.SCENARIO_PREDICATE_EVALUATED,)
        assert kwargs["tick"] == 4
        assert kwargs["failed_path"] == [1]
        assert kwargs["probability_decisions"] == [
            {
                "path": [1],
                "probability": 0.5,
                "sampled_value": 0.75,
                "is_satisfied": False,
            }
        ]
        json.dumps(kwargs)

    def test_provider_follows_late_injection_and_replacement(self) -> None:
        """記録器が未設定なら無動作で、後付けと差替え後は最新の実体へ記録する。"""
        holder: dict[str, object | None] = {"recorder": None}
        first = MagicMock()
        second = MagicMock()
        emitter = ScenarioPredicateTraceEmitter(lambda: holder["recorder"])
        arguments = {
            "evaluation": _evaluation(),
            "root_condition_type": "PROBABILITY",
            "current_tick": WorldTick(1),
            "purpose": "reactive_object_binding",
            "owner_id": 7,
        }

        emitter.emit(**arguments)
        holder["recorder"] = first
        emitter.emit(**arguments)
        holder["recorder"] = second
        emitter.emit(**arguments)

        first.record.assert_called_once()
        second.record.assert_called_once()

    def test_provider_or_recorder_failure_does_not_escape(self) -> None:
        """trace取得・記録の障害は世界処理を停止させない。"""
        def broken_provider() -> object:
            raise RuntimeError("provider failed")

        emitter = ScenarioPredicateTraceEmitter(broken_provider)
        emitter.emit(
            evaluation=_evaluation(),
            root_condition_type="PROBABILITY",
            current_tick=WorldTick(1),
            purpose="reactive_passage_binding",
            owner_id=10,
        )
        recorder = MagicMock()
        recorder.record.side_effect = RuntimeError("record failed")
        emitter = ScenarioPredicateTraceEmitter(lambda: recorder)
        emitter.emit(
            evaluation=_evaluation(),
            root_condition_type="PROBABILITY",
            current_tick=WorldTick(1),
            purpose="reactive_passage_binding",
            owner_id=10,
        )
