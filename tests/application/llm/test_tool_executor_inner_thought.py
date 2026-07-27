"""tool_executor_helpers（心の声・警告）のテスト。"""

from pathlib import Path

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    with_inner_thought_empty_warning,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_EXPLORE


def test_source_does_not_use_section_heading_style_for_inner_thought() -> None:
    """行動内の心の声は section 見出し風の「【心の声】」ではなく表示層の「心の声:」へ集約する。"""
    source_root = Path("src")
    offenders = [
        str(path)
        for path in source_root.rglob("*.py")
        if "【心の声】" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_inner_thought_warning_prepends_on_success_when_missing() -> None:
    base = LlmCommandResultDto(success=True, message="完了")
    out = with_inner_thought_empty_warning(TOOL_NAME_SPOT_GRAPH_EXPLORE, {}, base)
    assert out.success is True
    assert out.message.startswith("【警告】")
    assert "完了" in out.message


def test_inner_thought_warning_skips_when_present() -> None:
    base = LlmCommandResultDto(success=True, message="完了")
    out = with_inner_thought_empty_warning(
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        {"inner_thought": "足元を見る。"},
        base,
    )
    assert out.message == "完了"
