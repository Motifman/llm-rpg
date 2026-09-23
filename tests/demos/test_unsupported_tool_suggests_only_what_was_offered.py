"""存在しない tool 名への失敗文は、そのターンに送った tool だけを勧める (#1413)。

## handler 表から作ると、出していない tool を勧める

失敗文の「現在使える tool」は ``_tool_handlers`` の全キーから作っていた。会議中に
送った tool は 7 個なのに、失敗文には ``interact`` や ``attack``、この世界で出して
いない ``memory_*`` まで 33 個が並んでいた。勧められた名前を次のターンに呼ぶと、
今度は「いまは選べない」で落ちる。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    offered_tools_from_payload,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_name_rescue import (
    NO_MATCH_OPTION,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _LlmPhaseAResult,
    _WorldLlmWiring,
)

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)


class _StubClient:
    """LLM は呼ばない。dispatch だけを見る。"""


def _wiring(runtime) -> _WorldLlmWiring:
    return _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=_StubClient(),
    )


def _listed_tools(message: str) -> set[str]:
    found = re.search(r"現在使える tool: \[(.*)\]", message)
    assert found is not None, message
    return {name.strip() for name in found.group(1).split(",") if name.strip()}


@pytest.fixture()
def in_a_meeting():
    runtime = create_world_runtime(_DRILL)
    runtime.call_emergency_meeting(_MORI)
    wiring = _wiring(runtime)
    offered = offered_tools_from_payload(wiring._build_tools_payload(_MORI))
    assert "interact" not in offered
    return wiring, offered


class TestTheFailureListsOnlyTheOfferedTools:
    """UNSUPPORTED_TOOL の失敗文が、そのターンに送った tool だけから作られることを保証する。"""

    def test_the_listed_tools_are_exactly_the_offered_ones_during_a_meeting(
        self, in_a_meeting
    ) -> None:
        """会議中に存在しない名前を呼ぶと、一覧は送った tool と一致し、interact は載らない。"""
        wiring, offered = in_a_meeting

        result = wiring._execute_tool(
            _MORI, "gather", {}, None, offered_tools_at_prompt=offered
        )

        assert result.error_code == "UNSUPPORTED_TOOL"
        assert _listed_tools(result.message) == set(offered)

    def test_a_name_close_to_a_hidden_tool_is_not_suggested(self, in_a_meeting) -> None:
        """会議中に interact の短縮形を呼んでも、送っていない interact を提案しない。

        **正の対照**: 会議の外では同じ名前に interact を提案する。
        """
        wiring, offered = in_a_meeting

        result = wiring._execute_tool(
            _MORI, "spot_graph_interact", {}, None, offered_tools_at_prompt=offered
        )

        assert "もしかして" not in result.message

    def test_outside_a_meeting_the_same_name_is_suggested(self) -> None:
        """会議の外では、送った一覧に interact があるので提案する (上の試験の対照)。"""
        runtime = create_world_runtime(_DRILL)
        wiring = _wiring(runtime)
        offered = offered_tools_from_payload(wiring._build_tools_payload(_MORI))

        result = wiring._execute_tool(
            _MORI, "spot_graph_interact", {}, None, offered_tools_at_prompt=offered
        )

        assert "もしかして 'interact' ですか?" in result.message


class _PicksSpeak(ITypedJudgmentPort):
    """選択肢に speak があれば確信をもって選ぶ。問われた内容を残す。"""

    def __init__(self) -> None:
        self.questions: list[ChoiceQuestion] = []

    def judge(self, state, questions):
        (name, question), = questions.items()
        assert isinstance(question, ChoiceQuestion)
        self.questions.append(question)
        return {
            name: JudgmentResult(
                value="speak",
                probabilities={"speak": 0.95},
                confidence=0.93,
                source=JudgmentSource.STUB,
                latency_ms=1.0,
            )
        }


class _RecordingTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):
        self.events.append({"kind": kind, "tick": tick, "player_id": player_id, **payload})

    def of_kind(self, kind) -> list[dict[str, Any]]:
        return [e for e in self.events if e["kind"] == kind]


def _phase_b_calling(name: str, *, port: ITypedJudgmentPort | None):
    """会議中に ``name`` を呼んだ 1 ターンを、実際に送った payload のまま Phase B に通す。"""
    runtime = create_world_runtime(_DRILL)
    runtime.call_emergency_meeting(_MORI)
    trace = _RecordingTrace()
    runtime.set_trace_recorder(trace)
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=_StubClient(),
        typed_judgment_port=port,
    )
    payload = wiring._build_tools_payload(_MORI)
    phase_a = _LlmPhaseAResult(
        player_id=_MORI,
        prompt={
            "messages": [],
            "tool_runtime_context": runtime.build_llm_context(_MORI).tool_runtime_context,
        },
        tools_payload=payload,
        tool_call={
            "name": name,
            "arguments": {"channel": "say", "content": "集まろう", "inner_thought": "皆に伝えたい"},
        },
        exception=None,
    )
    return wiring.run_phase_b(phase_a), trace, offered_tools_from_payload(payload)


class TestTheJudgmentSuggestsFromTheSentTools:
    """Phase B から、送った tool の説明が判断に届き、提案と trace に反映されることを保証する。"""

    def test_say_is_suggested_as_speak_and_the_failure_stays_a_failure(self) -> None:
        """say を呼ぶと、判断が speak を選び、失敗文の提案が speak になる。実行はしない。"""
        result, _, _ = _phase_b_calling("say", port=_PicksSpeak())

        assert result.success is False
        assert result.error_code == "UNSUPPORTED_TOOL"
        assert "もしかして 'speak' ですか?" in result.message

    def test_the_options_are_the_sent_tools_with_their_first_description_line(self) -> None:
        """選択肢は送った tool と該当なしだけで、意味は送った説明の 1 行目。"""
        port = _PicksSpeak()

        _, _, offered = _phase_b_calling("say", port=port)

        (question,) = port.questions
        assert set(question.options) == set(offered) | {NO_MATCH_OPTION}
        assert "interact" not in question.options
        assert question.options["speak"] == offered["speak"]
        assert offered["speak"]
        assert "\n" not in question.options["speak"]

    def test_one_typed_judgment_is_traced(self) -> None:
        """TYPED_JUDGMENT に question=tool_name_rescue が 1 件、提案と出所つきで残る。"""
        _, trace, _ = _phase_b_calling("say", port=_PicksSpeak())

        (event,) = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)
        assert event["question"] == "tool_name_rescue"
        assert event["player_id"] == int(_MORI.value)
        assert event["requested"] == "say"
        assert event["suggested"] == "speak"
        assert event["suggestion_source"] == "judgment"

    def test_without_a_port_nothing_is_asked_or_traced(self) -> None:
        """判断ポートが無い配線では判断を問わず、TYPED_JUDGMENT も残さない (**正の対照**)。"""
        result, trace, _ = _phase_b_calling("say", port=None)

        assert result.error_code == "UNSUPPORTED_TOOL"
        assert "もしかして" not in result.message
        assert trace.of_kind(TraceEventKind.TYPED_JUDGMENT) == []


class _Raises(ITypedJudgmentPort):
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def judge(self, state, questions):
        raise self.exc


class TestAJudgmentFailureKeepsTheUnsupportedToolFailure:
    """判断が得られなくても、失敗は UNSUPPORTED_TOOL のまま届き、判断不能が trace に残ることを保証する。"""

    @pytest.mark.parametrize(
        ("exc", "reason"),
        [
            (TypedJudgmentUnavailableException("down", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED"),
             "TYPED_JUDGMENT_TRANSPORT_FAILED"),
            (ValueError("probability is not a number"), "UNEXPECTED_ERROR"),
        ],
    )
    def test_the_failure_and_the_wake_up_survive_and_the_reason_is_traced(
        self, exc: Exception, reason: str
    ) -> None:
        """判断ポートがどんな例外を投げても、UNSUPPORTED_TOOL と次 tick の起床が保たれ、trace に理由が残る。"""
        result, trace, offered = _phase_b_calling("say", port=_Raises(exc))

        assert result.error_code == "UNSUPPORTED_TOOL"
        assert result.should_reschedule is True
        assert "現在使える tool" in result.message
        (event,) = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)
        assert event["fallback_reason"] == "unavailable"
        assert event["unavailable_reason"] == reason
