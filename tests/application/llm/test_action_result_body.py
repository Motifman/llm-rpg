from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    format_action_result_body,
    format_action_result_line_for_recent_events,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH

_AT = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _entry(**overrides: object) -> ActionResultEntry:
    fields: dict[str, object] = {
        "occurred_at": _AT,
        "action_summary": "扉を調べた",
        "result_summary": "鍵がかかっていた",
        "success": True,
        "tool_name": "interact",
        "game_time_label": "1日目 朝",
        "inner_thought": "鍵を探そう",
        "identifier_arguments": {"target": "扉"},
    }
    return ActionResultEntry(**{**fields, **overrides})  # type: ignore[arg-type]


class TestFormatActionResultBody:
    """format_action_result_body が、直近の出来事の行から時刻の前置きと心の声だけを除いた文を返すことを保証する (design_decisions D1824-7)。"""

    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            {"omit_result_in_prompt": True},
            {"tool_name": TOOL_NAME_SPEECH, "action_summary": "「おはよう」と言った", "result_summary": "ミオが振り向いた"},
            {"success": False, "error_code": "LOCKED", "should_reschedule": True},
            {"success": False, "error_code": None},
            {"game_time_label": None},
            {"inner_thought": None},
        ],
        ids=["succeeded", "result-omitted", "speech", "failed-with-code", "failed-outside-world", "no-time-label", "no-inner-thought"],
    )
    def test_line_is_time_prefix_plus_body_plus_inner_thought(self, overrides: dict[str, object]) -> None:
        """行は「[時刻] 」+ 本文 + 「心の声:」の続き行でできていて、本文はその間のすべてになる。"""
        entry = _entry(**overrides)
        prefix = f"[{entry.game_time_label}] " if entry.game_time_label else ""
        inner = f"\n  心の声: {entry.inner_thought}" if entry.inner_thought else ""

        assert format_action_result_line_for_recent_events(entry) == prefix + format_action_result_body(entry) + inner

    def test_body_of_a_succeeded_move_keeps_action_result_and_call(self) -> None:
        """成功した行動の本文は、行動、結果、「呼び出し:」の行を持ち、時刻も心の声も持たない。"""
        body = format_action_result_body(_entry())

        assert body.startswith("[行動] 扉を調べた → [結果] 鍵がかかっていた\n  呼び出し: interact(")
        assert "1日目 朝" not in body
        assert "心の声" not in body

    def test_body_of_a_failed_move_keeps_the_error_code(self) -> None:
        """失敗した行動の本文は、error_code と道具の名前を持つ。"""
        body = format_action_result_body(_entry(success=False, error_code="LOCKED"))

        assert body == "[行動] 扉を調べた → [失敗] | error_code=LOCKED | tool=interact | 鍵がかかっていた"
