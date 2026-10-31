"""``DefaultPromptBuilder`` が prompt を組むたびに ``PROMPT_SECTION_BREAKDOWN`` を trace に残すことの検証。

- 区画ごとの文字数は、作業記憶の区画の本文 (見出しの行を除く) から数え、独立に payload に乗る (design_decisions D1630-3)
- trace_recorder 未注入なら no-op
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.being.contract import Description, Orientation, Scene
from ai_rpg_world.being.domain.working_memory import (
    RECENT_EVENTS_PREAMBLE,
    Closing,
    MemoryTexts,
    WorkingMemory,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _capture_trace(recorder: NullTraceRecorder) -> list:
    """NullTraceRecorder の record を wrap して capture list を返す。"""
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper
    return captured


def _builder(recorder: NullTraceRecorder | None) -> DefaultPromptBuilder:
    builder = object.__new__(DefaultPromptBuilder)
    builder._trace_recorder = recorder
    builder._trace_recorder_provider = None
    builder._current_tick_provider = lambda: 7
    return builder


def _memory(memory: MemoryTexts, *, goal: str | None = "目的目的目的") -> WorkingMemory:
    return WorkingMemory.compose(
        orientation=Orientation([Description(heading="ペルソナ", text="ハル")]),
        conduct="作法",
        imposed_goal=goal,
        memory=memory,
        scene=Scene([Description(heading="現在地と周囲", text="現在地表示")]),
        closing=Closing(instruction="指示文"),
    )


class TestPromptBuilderSectionBreakdownTraceEmission:
    """``_emit_prompt_section_breakdown_trace`` が区画ごとの文字数を払い出す (実験 #356 後続: prefix cache 分析用)。"""

    def test_each_section_body_is_counted_separately(self) -> None:
        """各区画の本文の長さが独立に payload に乗る。直近の出来事は前置きの一文を含めて数える。token ではなく char。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        tools = [
            {"type": "function", "function": {"name": "wait", "description": "待つ", "parameters": {}}},
            {"type": "function", "function": {"name": "move", "description": "移動する", "parameters": {}}},
        ]
        memory = _memory(
            MemoryTexts(
                known_people="- ミオ",
                backstory="いきさつ",
                recent_events="出来事" * 20,
                episode_index="(まだ無い)",
                memo="メモ",
            )
        )

        _builder(recorder)._emit_prompt_section_breakdown_trace(
            player_id=PlayerId(3),
            memory=memory,
            system_content="SYSTEM" * 10,
            user_content="USER_BODY" * 5,
            tools=tools,
        )

        events = [e for e in captured if e.kind == TraceEventKind.PROMPT_SECTION_BREAKDOWN]
        assert len(events) == 1
        p = events[0].payload
        assert (events[0].tick, events[0].player_id) == (7, 3)
        assert p["system_chars"] == 60
        assert p["objective_chars"] == 6
        assert p["known_people_chars"] == 4
        assert p["backstory_chars"] == 4
        assert p["recent_events_chars"] == len(RECENT_EVENTS_PREAMBLE) + 1 + 60
        assert p["episode_index_chars"] == 6
        assert p["memos_chars"] == 2
        assert p["current_state_chars"] == 5
        assert p["instruction_chars"] == 3
        assert "inventory_chars" not in p
        assert "recall_chars" not in p
        assert p["user_content_chars"] == 45
        assert p["messages_total_chars"] == 60 + 45
        assert p["tools_count"] == 2
        assert p["tools_chars"] > 0

    def test_missing_sections_count_as_zero(self) -> None:
        """出ていない区画 (目的、知っている人、いきさつ) は 0 と数える。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        _builder(recorder)._emit_prompt_section_breakdown_trace(
            player_id=PlayerId(3),
            memory=_memory(MemoryTexts(), goal=None),
            system_content="",
            user_content="",
            tools=[],
        )

        p = next(e for e in captured if e.kind == TraceEventKind.PROMPT_SECTION_BREAKDOWN).payload
        assert (p["objective_chars"], p["known_people_chars"], p["backstory_chars"]) == (0, 0, 0)

    def test_recorder_uninjected_section_breakdown_emit_op(self) -> None:
        """trace_recorder=None でも例外なく完走 (prompt 構築を止めない)。"""
        _builder(None)._emit_prompt_section_breakdown_trace(
            player_id=PlayerId(1), memory=_memory(MemoryTexts()), system_content="", user_content="", tools=[]
        )
