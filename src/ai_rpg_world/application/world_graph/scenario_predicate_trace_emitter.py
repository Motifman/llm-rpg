"""シナリオ述語の評価結果を再評価せずtraceへ記録する。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Optional

from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.application.world_graph.scenario_predicate_evaluation import (
    ScenarioPredicateEvaluation,
)
from ai_rpg_world.domain.common.value_object import WorldTick


_logger = logging.getLogger(__name__)


class ScenarioPredicateTraceEmitter:
    """最新recorderを実行時に解決し、評価済み結果をJSON互換payloadへ変換する。"""

    def __init__(
        self,
        trace_recorder_provider: Callable[[], Optional[ITraceRecorder]],
    ) -> None:
        if not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable")
        self._trace_recorder_provider = trace_recorder_provider

    def emit(
        self,
        *,
        evaluation: ScenarioPredicateEvaluation,
        root_condition_type: str,
        current_tick: WorldTick,
        purpose: str,
        owner_id: str | int,
        owner_index: Optional[int] = None,
        player_id: Optional[int] = None,
    ) -> None:
        """一度だけ得た評価結果を記録し、trace障害は世界進行へ波及させない。"""
        try:
            recorder = self._trace_recorder_provider()
            if recorder is None:
                return
            result = evaluation.result
            recorder.record(
                TraceEventKind.SCENARIO_PREDICATE_EVALUATED,
                tick=current_tick.value,
                player_id=player_id,
                purpose=purpose,
                owner_id=owner_id,
                owner_index=owner_index,
                is_satisfied=result.is_satisfied,
                reason_code=(
                    result.reason_code.value
                    if result.reason_code is not None
                    else None
                ),
                root_condition_type=root_condition_type,
                failed_condition_type=(
                    result.failed_predicate.condition_type
                    if result.failed_predicate is not None
                    else None
                ),
                failed_path=(
                    list(result.failed_path)
                    if result.failed_path is not None
                    else None
                ),
                missing_context=sorted(result.missing_context),
                probability_decisions=[
                    {
                        "path": list(decision.path),
                        "probability": decision.probability,
                        "sampled_value": decision.sampled_value,
                        "is_satisfied": decision.is_satisfied,
                    }
                    for decision in evaluation.probability_decisions
                ],
            )
        except Exception:
            _logger.warning(
                "scenario predicate trace emission failed; world processing continues",
                exc_info=True,
            )


__all__ = ["ScenarioPredicateTraceEmitter"]
