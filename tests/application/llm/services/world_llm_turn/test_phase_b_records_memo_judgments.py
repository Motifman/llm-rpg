"""memo 完了の判断が、採否に関わらず trace に残る。

採用した判断だけを残すと、hint が減った run を見て「意味判定が厳しすぎる」と
誤読する。実際には接続が落ちて重なり判定へ縮退していた、という可能性を切り
分けられない (design_decisions #5)。

そのため phase_b は、問うた memo ごとの判断と、縮退したことの両方を残す。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    SOURCE_JUDGMENT,
    MemoCompletionHint,
    MemoCompletionJudgment,
    MemoHintDetection,
    PendingTodo,
)
from ai_rpg_world.application.llm.services.world_llm_turn import phase_b
from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _RecordingTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(
        self,
        kind: str,
        *,
        tick: int | None = None,
        player_id: int | None = None,
        **payload: Any,
    ) -> Any:
        self.events.append({"kind": kind, "tick": tick, "player_id": player_id, **payload})
        return None

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event["kind"] == kind]


def _memo(memo_id: str, content: str) -> PendingTodo:
    return PendingTodo(id=memo_id, content=content, handle=f"m_{memo_id}")


def _run(detection: MemoHintDetection, monkeypatch: pytest.MonkeyPatch):
    trace = _RecordingTrace()
    monkeypatch.setattr(
        phase_b,
        "execute_tool",
        MagicMock(return_value=LlmCommandResultDto(success=True, message="押した")),
    )
    monkeypatch.setattr(
        phase_b, "maybe_interrupt_busy", MagicMock(return_value=(False, None))
    )
    monkeypatch.setattr(phase_b, "record_prompt_dataset_turn_result", MagicMock())

    wiring = MagicMock()
    wiring.runtime.trace_recorder = trace
    wiring.runtime.current_tick.return_value = 11
    wiring.tool_call_loop_guard.record_and_check.return_value = None
    wiring.memo_completion_hint_service.detect.return_value = detection
    phase_a = LlmPhaseAResult(
        player_id=PlayerId(4),
        prompt={"messages": [], "tool_runtime_context": None},
        tools_payload=[{"type": "function", "function": {"name": "interact"}}],
        tool_call={"name": "interact", "arguments": {}},
        exception=None,
    )

    phase_b.run_phase_b(wiring, phase_a)
    return trace


class TestEveryMemoJudgmentIsTraced:
    """問うた memo ごとの判断が、採否つきで残ることを保証する。"""

    def test_each_asked_memo_leaves_one_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """memo 2 件を問えば、判断も 2 件残る。"""
        detection = MemoHintDetection(
            hint=None,
            judgments=(
                MemoCompletionJudgment(
                    memo_id="m1",
                    memo_content="鎌を研ぐ",
                    probability=0.2,
                    min_probability=0.7,
                    accepted=False,
                    latency_ms=88.0,
                    source="jev",
                ),
                MemoCompletionJudgment(
                    memo_id="m2",
                    memo_content="小麦を集める",
                    probability=0.9,
                    min_probability=0.7,
                    accepted=True,
                    latency_ms=88.0,
                    source="jev",
                ),
            ),
        )

        trace = _run(detection, monkeypatch)

        events = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)
        assert [event["memo_id"] for event in events] == ["m1", "m2"]
        assert [event["accepted"] for event in events] == [False, True]
        assert all(event["question"] == "memo_completed" for event in events)
        assert all(event["player_id"] == 4 for event in events)

    def test_a_fallback_leaves_its_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """重なり判定へ縮退したときは、理由つきの 1 件が残る。"""
        detection = MemoHintDetection(
            hint=None, unavailable_reason="TYPED_JUDGMENT_RATE_LIMITED"
        )

        trace = _run(detection, monkeypatch)

        events = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)
        assert len(events) == 1
        assert events[0]["unavailable_reason"] == "TYPED_JUDGMENT_RATE_LIMITED"
        assert events[0]["accepted"] is False

    def test_a_hint_records_which_measure_fired_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """hint には、重なり由来か判断由来かが残る。

        混ぜて数えると、意味判定に替えた効果が見えない。
        """
        detection = MemoHintDetection(
            hint=MemoCompletionHint(
                memo=_memo("m2", "小麦を集める"),
                similarity=0.93,
                source=SOURCE_JUDGMENT,
            ),
            judgments=(),
        )

        trace = _run(detection, monkeypatch)

        hints = trace.of_kind(TraceEventKind.MEMO_HINT)
        assert len(hints) == 1
        assert hints[0]["hint_source"] == "judgment"
        assert hints[0]["memo_id"] == "m2"

    def test_nothing_is_traced_when_no_memo_was_asked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """問わなかった turn では判断が残らない (**正の対照**)。"""
        trace = _run(MemoHintDetection(hint=None), monkeypatch)

        assert trace.of_kind(TraceEventKind.TYPED_JUDGMENT) == []
