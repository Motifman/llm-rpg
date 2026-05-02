"""failure_feedback_for_prompt のテスト。"""

from datetime import datetime

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.failure_feedback_for_prompt import (
    build_pre_turn_failure_section,
)


def test_empty_returns_empty() -> None:
    assert build_pre_turn_failure_section([]) == ""


def test_success_latest_returns_empty() -> None:
    e = ActionResultEntry(
        occurred_at=datetime.now(),
        action_summary="a",
        result_summary="ok",
        success=True,
    )
    assert build_pre_turn_failure_section([e]) == ""


def test_failure_includes_code_and_reschedule_note() -> None:
    e = ActionResultEntry(
        occurred_at=datetime.now(),
        action_summary="x(1) を実行しました。",
        result_summary="失敗。理由 対処: 直せ",
        success=False,
        error_code="INVALID_FOO",
        tool_name="spot_graph_travel",
        argument_fingerprint='{"destination_label": "北"}',
        should_reschedule=True,
    )
    out = build_pre_turn_failure_section([e])
    assert "## 前ターンの行動は失敗" in out
    assert "INVALID_FOO" in out
    assert "spot_graph_travel" in out
    assert "再試行がスケジュール" in out
    assert "北" in out or "destination" in out


def test_consecutive_same_fingerprint_adds_warning() -> None:
    fp = '{"x": 1}'
    t = datetime(2025, 1, 1, 12, 0, 0)
    newer = ActionResultEntry(
        occurred_at=t,
        action_summary="a1",
        result_summary="失敗1",
        success=False,
        error_code="E1",
        tool_name="t1",
        argument_fingerprint=fp,
    )
    older = ActionResultEntry(
        occurred_at=t,
        action_summary="a0",
        result_summary="失敗0",
        success=False,
        error_code="E0",
        tool_name="t1",
        argument_fingerprint=fp,
    )
    out = build_pre_turn_failure_section([newer, older])
    assert "連続失敗" in out
    assert "別のラベル" in out or "別種" in out
