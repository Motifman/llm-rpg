"""置き換えた行動名を、当人に見せて trace に残す。

## 黙って置き換えない

``gather`` を ``reap_wheat`` として実行したなら、そう解釈したことを結果文で
当人に見せる。黙って通すと ``gather`` が通る名前だと学び、同じ名前を書き
続ける。救済が「名前を覚えなくてよい」状態を作ってしまう。

## 問わなかったことと、問って採らなかったことを分ける

trace に残すのは採用した判断だけではない。採らなかった判断と、判断を得られ
なかった場合も残す。残さないと、OFF の run と全件 fallback の run が同じに
見え、閾値を動かす判断ができない (design_decisions #5)。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Union

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services._argument_resolvers.action_name_rescue import (
    NO_MATCH_OPTION,
    ActionNameRescue,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    ACTION_HISTORY_PROJECTION_KEY,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    adapt_executor_handler_with_resolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_INTERACT,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _FixedPort(ITypedJudgmentPort):
    def __init__(
        self,
        *,
        chosen: str = "reap_wheat",
        probability: float = 0.97,
        raises: bool = False,
    ) -> None:
        self._chosen = chosen
        self._probability = probability
        self._raises = raises

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        if self._raises:
            raise TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED")
        name = next(iter(questions))
        return {
            name: JudgmentResult(
                value=self._chosen,
                probabilities={self._chosen: self._probability},
                confidence=0.96,
                source=JudgmentSource.JEV,
                latency_ms=131.0,
            )
        }


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


def _context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "OBJ1": ToolRuntimeTargetDto(
                label="OBJ1",
                kind="spot_graph_object",
                display_name="麦畑",
                world_object_id=10,
                available_interactions=("reap_wheat", "water_field"),
                interaction_labels=(
                    ("reap_wheat", "麦を刈り取る"),
                    ("water_field", "水をやる"),
                ),
            )
        }
    )


def _call(
    written: str,
    *,
    port: ITypedJudgmentPort | None,
    trace: _RecordingTrace | None = None,
    success_message: str = "麦を 3 束刈り取った",
) -> tuple[LlmCommandResultDto, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def raw_handler(_player_id: int, resolved: dict[str, Any], _context: Any) -> LlmCommandResultDto:
        seen.append(resolved)
        return LlmCommandResultDto(success=True, message=success_message)

    rescue = ActionNameRescue(port=port, min_confidence=0.7) if port is not None else None
    handler = adapt_executor_handler_with_resolver(
        raw_handler,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        SpotGraphArgumentResolver(action_name_rescue=rescue),
        trace_recorder_provider=(lambda: trace) if trace is not None else None,
        current_tick_provider=(lambda: 7) if trace is not None else None,
    )
    result = handler(
        PlayerId(3),
        {
            "target_label": "麦畑",
            "action_name": written,
            "inner_thought": "小麦を集めたい",
        },
        _context(),
    )
    return result, seen


class TestTheAgentIsToldHowItsNameWasRead:
    """置き換えたことが結果文で当人に届くことを保証する。"""

    def test_a_replaced_name_is_explained_in_the_result(self) -> None:
        """救済したときは、書いた名前とどう解釈したかが結果文に出る。"""
        result, _ = _call("gather", port=_FixedPort())

        assert "gather" in result.message
        assert "reap_wheat" in result.message

    def test_the_original_result_message_is_kept(self) -> None:
        """executor が返した文面は消さずに残す。"""
        result, _ = _call("gather", port=_FixedPort())

        assert "麦を 3 束刈り取った" in result.message

    def test_a_name_that_needed_no_rescue_gets_no_note(self) -> None:
        """一覧にある名前を書いたときは、余分な説明を足さない (**正の対照**)。"""
        result, _ = _call("reap_wheat", port=_FixedPort())

        assert result.message == "麦を 3 束刈り取った"

    def test_the_executor_receives_the_offered_name(self) -> None:
        """executor には一覧の名前が渡る。"""
        _, seen = _call("gather", port=_FixedPort())

        assert seen[0]["action_name"] == "reap_wheat"

    def test_the_history_keeps_the_offered_name(self) -> None:
        """履歴に残る識別引数は、生値ではなく一覧の名前になる。

        生値を残すと「``gather`` で通った」と読めて、崩れが定着する。
        """
        _, seen = _call("gather", port=_FixedPort())

        identifiers, _free_text = seen[0][ACTION_HISTORY_PROJECTION_KEY]
        assert identifiers["action_name"] == "reap_wheat"


class TestEveryJudgmentLeavesATrace:
    """発火・確率・閾値・採否・出所が trace に残ることを保証する。"""

    def test_an_accepted_judgment_is_traced(self) -> None:
        """採用した判断は、元の値と選択と確率と閾値と採否つきで残る。"""
        trace = _RecordingTrace()
        _call("gather", port=_FixedPort(), trace=trace)

        events = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)
        assert len(events) == 1
        event = events[0]
        assert event["question"] == "action_name_rescue"
        assert event["original"] == "gather"
        assert event["chosen"] == "reap_wheat"
        assert event["probability"] == 0.97
        assert event["min_confidence"] == 0.7
        assert event["accepted"] is True
        assert event["source"] == "jev"
        assert event["player_id"] == 3
        assert event["tick"] == 7

    def test_a_rejected_judgment_is_traced_too(self) -> None:
        """確信が足りず採らなかった判断も残る。閾値を動かす判断に要る。"""
        trace = _RecordingTrace()
        _call("gather", port=_FixedPort(probability=0.3), trace=trace)

        event = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)[0]
        assert event["accepted"] is False
        assert event["probability"] == 0.3

    def test_a_no_match_answer_is_traced_without_a_choice(self) -> None:
        """「該当なし」のときは選択を残さない。世界に無い操作名を残さない。"""
        trace = _RecordingTrace()
        _call("gather", port=_FixedPort(chosen=NO_MATCH_OPTION), trace=trace)

        event = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)[0]
        assert event["chosen"] is None
        assert event["accepted"] is False

    def test_an_unavailable_judgment_is_traced_with_its_reason(self) -> None:
        """判断を得られなかったことは、理由つきで残る。

        「確信が足りなかった」と同じ形にすると、OFF の run と全件 fallback の
        run が trace で見分けられない。
        """
        trace = _RecordingTrace()
        _call("gather", port=_FixedPort(raises=True), trace=trace)

        event = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)[0]
        assert event["unavailable_reason"] == "TYPED_JUDGMENT_TRANSPORT_FAILED"
        assert event["accepted"] is False

    def test_nothing_is_traced_when_no_judgment_was_asked(self) -> None:
        """一覧にある名前なら、判断を問わないので trace にも出ない。"""
        trace = _RecordingTrace()
        _call("reap_wheat", port=_FixedPort(), trace=trace)

        assert trace.of_kind(TraceEventKind.TYPED_JUDGMENT) == []


class TestWithoutAPortNothingChanges:
    """判断を持たない run が、現行と同じ振る舞いになることを保証する。"""

    def test_an_invented_name_is_passed_through_unchanged(self) -> None:
        """ポートが無ければ、発明された名前はそのまま executor へ渡る。"""
        _, seen = _call("gather", port=None)

        assert seen[0]["action_name"] == "gather"

    def test_no_note_and_no_trace_without_a_port(self) -> None:
        """ポートが無ければ、結果文も trace も現行のままになる。"""
        trace = _RecordingTrace()
        result, _ = _call("gather", port=None, trace=trace)

        assert result.message == "麦を 3 束刈り取った"
        assert trace.of_kind(TraceEventKind.TYPED_JUDGMENT) == []
