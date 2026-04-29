"""tool_executor_helpers（心の声・警告）のテスト。"""

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    append_inner_thought_to_message,
    with_inner_thought_empty_warning,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_EXPLORE


def test_append_inner_thought_appends_when_present() -> None:
    out = append_inner_thought_to_message("操作した。", {"inner_thought": " 胸騒ぎがした。  "})
    assert "操作した。" in out
    assert "【心の声】" in out
    assert "胸騒ぎがした。" in out


def test_append_inner_thought_unchanged_when_empty() -> None:
    assert append_inner_thought_to_message("同上", {}) == "同上"
    assert append_inner_thought_to_message("同上", {"inner_thought": "   "}) == "同上"


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
