"""``DefaultPromptBuilder`` が prompt を組むたびに ``PROMPT_SECTION_BREAKDOWN`` を trace に残すことの検証。

- 各 section の文字数が独立に payload に乗る
- trace_recorder 未注入なら no-op
"""
from __future__ import annotations

from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
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

class TestPromptBuilderSectionBreakdownTraceEmission:
    """``_emit_prompt_section_breakdown_trace`` が section 別 char 数を払い出す
    (実験 #356 後続: prefix cache 分析用)。"""

    def test_section_different_char_event_included(self) -> None:
        """各 section のテキスト長が独立に payload に乗る。token ではなく char。"""
        from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = recorder
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda : 7
        tools = [{'type': 'function', 'function': {'name': 'wait', 'description': '待つ', 'parameters': {}}}, {'type': 'function', 'function': {'name': 'move', 'description': '移動する', 'parameters': {}}}]
        builder._emit_prompt_section_breakdown_trace(player_id=PlayerId(3), system_content='SYSTEM' * 10, objective_text='目的目的目的', current_state_text='現在地表示', active_memos_text='メモ', recent_events_text='出来事' * 20, inventory_text='持ち物', instruction='指示文', tools=tools, user_content='USER_BODY' * 5)
        events = [e for e in captured if e.kind == TraceEventKind.PROMPT_SECTION_BREAKDOWN]
        assert len(events) == 1
        p = events[0].payload
        assert events[0].tick == 7
        assert events[0].player_id == 3
        assert p['system_chars'] == 60
        assert p['objective_chars'] == 6
        assert p['current_state_chars'] == 5
        assert p['memos_chars'] == 2
        assert 'prediction_feedback_chars' not in p
        assert p['recent_events_chars'] == 60
        assert 'recall_chars' not in p
        assert p['inventory_chars'] == 3
        assert p['instruction_chars'] == 3
        assert p['user_content_chars'] == 45
        assert p['messages_total_chars'] == 60 + 45
        assert p['tools_count'] == 2
        assert p['tools_chars'] > 0

    def test_recorder_uninjected_section_breakdown_emit_op(self) -> None:
        """trace_recorder=None でも例外なく完走 (prompt 構築を止めない)。"""
        from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = None
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda : 0
        builder._emit_prompt_section_breakdown_trace(player_id=PlayerId(1), system_content='', objective_text='', current_state_text='', active_memos_text='', recent_events_text='', inventory_text='', instruction='', tools=[], user_content='')
